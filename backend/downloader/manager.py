"""Download manager — queue + progress (Hakuneko DownloadManager patterns)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx
from sqlalchemy import select

from backend.database.session import SessionLocal
from backend.models import DownloadJob, DownloadStatus, LibraryEpisode
from backend.providers import get_registry
from backend.services import ffmpeg_tools, library
from backend.services.settings import get_app_settings

logger = logging.getLogger("animebox.downloader")


class DownloadManager:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self._cancel_flags: set[int] = set()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run(), name="download-worker")
            await self._requeue_pending()

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            finally:
                self._worker = None

    async def _requeue_pending(self) -> None:
        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    select(DownloadJob).where(
                        DownloadJob.status.in_([DownloadStatus.queued.value, DownloadStatus.downloading.value])
                    )
                )
            ).scalars().all()
            for job in rows:
                job.status = DownloadStatus.queued.value
                job.progress = 0
                await self._queue.put(job.id)
            await db.commit()

    async def enqueue(
        self,
        *,
        anime_id: str,
        anime_title: str,
        source: str,
        season: int,
        episode: int,
        episode_title: str | None,
        voiceover: str | None,
        steam_deck: bool,
    ) -> DownloadJob:
        async with SessionLocal() as db:
            job = DownloadJob(
                anime_external_id=anime_id,
                anime_title=anime_title,
                source=source,
                season=season,
                episode=episode,
                episode_title=episode_title,
                voiceover=voiceover,
                status=DownloadStatus.queued.value,
                progress=0,
                steam_deck=steam_deck,
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
            job_id = job.id
        await self._queue.put(job_id)
        return job

    async def cancel(self, job_id: int) -> bool:
        self._cancel_flags.add(job_id)
        async with SessionLocal() as db:
            job = await db.get(DownloadJob, job_id)
            if not job:
                return False
            if job.status in (DownloadStatus.queued.value, DownloadStatus.downloading.value, DownloadStatus.failed.value):
                job.status = DownloadStatus.cancelled.value
                await db.commit()
                return True
        return False

    async def retry(self, job_id: int) -> bool:
        async with SessionLocal() as db:
            job = await db.get(DownloadJob, job_id)
            if not job:
                return False
            job.status = DownloadStatus.queued.value
            job.progress = 0
            job.error = None
            await db.commit()
        self._cancel_flags.discard(job_id)
        await self._queue.put(job_id)
        return True

    async def _run(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                async with self._lock:
                    await self._process(job_id)
            except Exception as exc:
                logger.exception("Download job %s crashed: %s", job_id, exc)
            finally:
                self._queue.task_done()

    async def _update(self, job_id: int, **fields) -> None:
        async with SessionLocal() as db:
            job = await db.get(DownloadJob, job_id)
            if not job:
                return
            for k, v in fields.items():
                setattr(job, k, v)
            await db.commit()

    async def _process(self, job_id: int) -> None:
        if job_id in self._cancel_flags:
            self._cancel_flags.discard(job_id)
            await self._update(job_id, status=DownloadStatus.cancelled.value)
            return

        async with SessionLocal() as db:
            job = await db.get(DownloadJob, job_id)
            if not job or job.status == DownloadStatus.cancelled.value:
                return
            anime_id = job.anime_external_id
            anime_title = job.anime_title
            season = job.season
            episode = job.episode
            voiceover = job.voiceover
            steam_deck = job.steam_deck
            source = job.source
            episode_title = job.episode_title
            settings = await get_app_settings(db)
            if settings.steam_deck_optimize:
                steam_deck = True

        await self._update(job_id, status=DownloadStatus.downloading.value, progress=1, error=None)

        try:
            registry = get_registry()
            stream = await registry.resolve_stream(anime_id, episode, voiceover=voiceover)
            await self._update(job_id, voiceover=stream.voiceover, source_url=stream.video.url, progress=5)

            if job_id in self._cancel_flags:
                self._cancel_flags.discard(job_id)
                await self._update(job_id, status=DownloadStatus.cancelled.value)
                return

            # Browser-safe containers make downloaded episodes playable without transcoding.
            ext = "webm" if stream.video.type == "webm" else "mp4"
            dest = library.episode_path(anime_title, season, episode, ext=ext)

            if stream.video.type in ("m3u8", "mpd"):
                tmp = await self._download_hls(
                    job_id,
                    stream.video.url,
                    dest,
                    stream.video.headers,
                )
            else:
                tmp = dest.with_name(f"{dest.stem}.part{dest.suffix}")
                await self._download_progressive(job_id, stream.video.url, tmp, stream.video.headers)

            if job_id in self._cancel_flags:
                self._cancel_flags.discard(job_id)
                tmp.unlink(missing_ok=True)
                await self._update(job_id, status=DownloadStatus.cancelled.value)
                return

            final_path = dest
            if steam_deck and ffmpeg_tools.ffmpeg_available():
                await self._update(job_id, progress=90)
                optimized = dest.with_name(dest.stem + ".steamdeck.mkv")
                await ffmpeg_tools.optimize_for_steam_deck(tmp, optimized)
                tmp.unlink(missing_ok=True)
                if dest.exists() and dest != optimized:
                    dest.unlink(missing_ok=True)
                final_path = optimized
            else:
                tmp.replace(dest)

            library.append_episode_metadata(
                anime_title,
                season=season,
                episode=episode,
                voiceover=stream.voiceover,
                file_name=final_path.name,
                source=source,
            )
            detail = await registry.get_anime(anime_id)
            await library.save_poster(anime_title, detail.poster)

            size = final_path.stat().st_size if final_path.exists() else None
            async with SessionLocal() as db:
                existing = (
                    await db.execute(
                        select(LibraryEpisode).where(
                            LibraryEpisode.anime_external_id == anime_id,
                            LibraryEpisode.season == season,
                            LibraryEpisode.episode == episode,
                        )
                    )
                ).scalar_one_or_none()
                if existing:
                    existing.file_path = str(final_path)
                    existing.file_size = size
                    existing.voiceover = stream.voiceover
                    if episode_title:
                        existing.title = episode_title
                else:
                    db.add(
                        LibraryEpisode(
                            anime_external_id=anime_id,
                            season=season,
                            episode=episode,
                            title=episode_title or f"Episode {episode}",
                            voiceover=stream.voiceover,
                            file_path=str(final_path),
                            file_size=size,
                        )
                    )
                job_row = await db.get(DownloadJob, job_id)
                if job_row:
                    job_row.status = DownloadStatus.completed.value
                    job_row.progress = 100
                    job_row.file_path = str(final_path)
                    job_row.voiceover = stream.voiceover
                await db.commit()
            logger.info("Downloaded %s S%sE%s -> %s", anime_title, season, episode, final_path)
        except Exception as exc:
            logger.exception("Download failed job=%s: %s", job_id, exc)
            await self._update(
                job_id,
                status=DownloadStatus.failed.value,
                error=str(exc)[:2000],
            )

    async def _download_hls(
        self,
        job_id: int,
        url: str,
        dest: Path,
        headers: dict[str, str],
    ) -> Path:
        # Keep media suffix last so ffmpeg can select the output muxer.
        temporary = dest.with_name(f"{dest.stem}.part{dest.suffix}")
        temporary.unlink(missing_ok=True)
        await self._update(job_id, progress=10)
        await ffmpeg_tools.download_hls_with_ffmpeg(url, temporary, headers)
        await self._update(job_id, progress=85)
        return temporary

    async def _download_progressive(
        self,
        job_id: int,
        url: str,
        dest: Path,
        headers: dict[str, str],
    ) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(follow_redirects=True, timeout=None) as client:
            async with client.stream("GET", url, headers=headers) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length") or 0)
                done = 0
                with dest.open("wb") as f:
                    async for chunk in resp.aiter_bytes(1024 * 256):
                        if job_id in self._cancel_flags:
                            raise asyncio.CancelledError("cancelled")
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            pct = 5 + (done / total) * 80
                            await self._update(job_id, progress=round(pct, 1))


download_manager = DownloadManager()
