"""Download manager 2.0 — durable queue with real progress.

Ideas from HakuNeko's DownloadManager and Sonarr's queue/import lifecycle:

- the queue lives in SQLite; jobs survive restarts and resume as ``queued``;
- up to ``max_concurrent_downloads`` jobs run at once;
- HLS goes through ffmpeg via the local media proxy (same network identity as
  playback); progress comes from ffmpeg's reported position/duration;
- progressive MP4/WebM is fetched directly with HTTP Range support, which is
  the only case where pause/resume is offered;
- files are written to ``*.part.*`` and moved into place atomically after
  validation; the library row is written only after the file is final;
- poster/metadata are best effort and never fail a valid download.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from backend.config import get_settings
from backend.database.session import SessionLocal
from backend.models import ACTIVE_DOWNLOAD_STATUSES, OPEN_DOWNLOAD_STATUSES, DownloadJob, DownloadStatus
from backend.player.sessions import UnsafeUpstream, media_sessions
from backend.providers.errors import NotFound, ProviderError
from backend.providers.http import DEFAULT_USER_AGENT, media_clients
from backend.services import ffmpeg_tools, library, library_index

logger = logging.getLogger("animebox.downloader")

MAX_ATTEMPTS = 3
RETRY_DELAYS = (3.0, 10.0)
PROGRESS_WRITE_INTERVAL = 1.0


class _Stop(Exception):
    """Raised inside a job when it must stop (pause/cancel/shutdown)."""


class DownloadValidationError(RuntimeError):
    pass


class _Progress:
    """Throttled progress reporting with an exponentially smoothed speed."""

    def __init__(self, manager: "DownloadManager", job_id: int, start: float, span: float) -> None:
        self.manager = manager
        self.job_id = job_id
        self.start = start
        self.span = span
        self._last_write = 0.0
        self._last_bytes = 0
        self._last_time = time.monotonic()
        self.speed: float | None = None

    def update(self, fraction: float | None, bytes_done: int, bytes_total: int | None = None) -> None:
        now = time.monotonic()
        elapsed = now - self._last_time
        if elapsed >= 0.5 and bytes_done >= self._last_bytes:
            instant = (bytes_done - self._last_bytes) / elapsed
            self.speed = instant if self.speed is None else 0.7 * self.speed + 0.3 * instant
            self._last_bytes, self._last_time = bytes_done, now
        if now - self._last_write < PROGRESS_WRITE_INTERVAL:
            return
        self._last_write = now
        fields: dict = {"bytes_done": bytes_done, "speed_bps": self.speed}
        if bytes_total:
            fields["bytes_total"] = bytes_total
        if fraction is not None:
            fields["progress"] = round(self.start + self.span * max(0.0, min(1.0, fraction)), 1)
        self.manager._schedule_update(self.job_id, fields)


class DownloadManager:
    def __init__(self) -> None:
        self._concurrency = get_settings().max_concurrent_downloads
        self._running: dict[int, asyncio.Task] = {}
        self._stop_reason: dict[int, str] = {}
        self._wakeup = asyncio.Event()
        self._scheduler: asyncio.Task | None = None
        self._pending_writes: set[asyncio.Task] = set()
        self.local_base_url = f"http://127.0.0.1:{get_settings().port}"

    # ------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        if self._scheduler is not None and not self._scheduler.done():
            return
        await self._recover()
        self._wakeup.set()  # start queued work immediately
        self._scheduler = asyncio.create_task(self._schedule_loop(), name="download-scheduler")

    async def stop(self) -> None:
        if self._scheduler is not None:
            self._scheduler.cancel()
            try:
                await self._scheduler
            except asyncio.CancelledError:
                pass
            self._scheduler = None
        running = list(self._running.items())
        for job_id, task in running:
            self._stop_reason[job_id] = "shutdown"
            task.cancel()
        for _job_id, task in running:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if self._pending_writes:
            await asyncio.gather(*self._pending_writes, return_exceptions=True)

    def set_concurrency(self, value: int) -> None:
        self._concurrency = max(1, min(6, int(value)))
        self._wakeup.set()

    async def _recover(self) -> None:
        """Interrupted jobs go back to the queue; orphaned partial files are removed."""
        keep_parts: set[Path] = set()
        async with SessionLocal() as db:
            rows = (await db.execute(select(DownloadJob).where(DownloadJob.status.in_(OPEN_DOWNLOAD_STATUSES)))).scalars().all()
            for job in rows:
                if job.status in ACTIVE_DOWNLOAD_STATUSES:
                    job.status = DownloadStatus.queued.value
                    job.speed_bps = None
                if job.resumable and job.file_path:
                    keep_parts.add(library.partial_path(library.resolve_stored_path(job.file_path)).resolve())
                else:
                    job.progress = 0
                    job.bytes_done = 0
            await db.commit()
        root = library.library_root()
        if root.is_dir():
            for part in root.rglob(f"*{library.PART_MARKER}.*"):
                if part.is_file() and part.resolve() not in keep_parts:
                    logger.info("Removing incomplete temporary file %s", part.name)
                    part.unlink(missing_ok=True)
            library.remove_empty_dirs(root)

    # -------------------------------------------------------------- commands
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
        quality: int | None = None,
        replace: bool = False,
    ) -> tuple[DownloadJob | None, str | None]:
        """Queue one episode. Returns ``(job, None)`` or ``(None, skip_reason)``."""
        async with SessionLocal() as db:
            open_job = (
                await db.execute(
                    select(DownloadJob.id).where(
                        DownloadJob.anime_external_id == anime_id,
                        DownloadJob.season == season,
                        DownloadJob.episode == episode,
                        DownloadJob.status.in_(OPEN_DOWNLOAD_STATUSES),
                    )
                )
            ).first()
            if open_job:
                return None, "already_queued"
            if not replace and (season, episode) in await library_index.downloaded_keys(db, anime_id):
                return None, "already_downloaded"
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
                quality=quality,
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
        self._wakeup.set()
        return job, None

    async def cancel(self, job_id: int) -> bool:
        async with SessionLocal() as db:
            job = await db.get(DownloadJob, job_id)
            if job is None or job.status not in (*OPEN_DOWNLOAD_STATUSES, DownloadStatus.failed.value):
                return False
            if job_id not in self._running:
                job.status = DownloadStatus.cancelled.value
                job.speed_bps = None
                job.finished_at = datetime.now(timezone.utc)
                self._remove_part(job.file_path)
                await db.commit()
                return True
        self._stop_reason[job_id] = "cancel"
        self._running[job_id].cancel()
        return True

    async def pause(self, job_id: int) -> bool:
        async with SessionLocal() as db:
            job = await db.get(DownloadJob, job_id)
            if job is None or not job.resumable or job.status not in ACTIVE_DOWNLOAD_STATUSES:
                return False
            if job_id not in self._running:
                job.status = DownloadStatus.paused.value
                await db.commit()
                return True
        self._stop_reason[job_id] = "pause"
        self._running[job_id].cancel()
        return True

    async def resume(self, job_id: int) -> bool:
        async with SessionLocal() as db:
            job = await db.get(DownloadJob, job_id)
            if job is None or job.status != DownloadStatus.paused.value:
                return False
            job.status = DownloadStatus.queued.value
            await db.commit()
        self._wakeup.set()
        return True

    async def retry(self, job_id: int) -> bool:
        async with SessionLocal() as db:
            job = await db.get(DownloadJob, job_id)
            if job is None or job.status not in (DownloadStatus.failed.value, DownloadStatus.cancelled.value):
                return False
            busy = (
                await db.execute(
                    select(DownloadJob.id).where(
                        DownloadJob.id != job_id,
                        DownloadJob.anime_external_id == job.anime_external_id,
                        DownloadJob.season == job.season,
                        DownloadJob.episode == job.episode,
                        DownloadJob.status.in_(OPEN_DOWNLOAD_STATUSES),
                    )
                )
            ).first()
            if busy:
                return False
            job.status = DownloadStatus.queued.value
            job.progress = 0
            job.bytes_done = 0
            job.bytes_total = None
            job.speed_bps = None
            job.error = None
            job.warning = None
            job.attempts = 0
            job.resumable = False
            job.finished_at = None
            await db.commit()
        self._wakeup.set()
        return True

    async def remove(self, job_id: int) -> bool:
        async with SessionLocal() as db:
            job = await db.get(DownloadJob, job_id)
            if job is None or job.status in OPEN_DOWNLOAD_STATUSES:
                return False
            await db.delete(job)
            await db.commit()
        return True

    async def clear_finished(self) -> int:
        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    select(DownloadJob).where(
                        DownloadJob.status.in_(
                            [DownloadStatus.completed.value, DownloadStatus.cancelled.value, DownloadStatus.failed.value]
                        )
                    )
                )
            ).scalars().all()
            for row in rows:
                await db.delete(row)
            await db.commit()
        return len(rows)

    # ------------------------------------------------------------- scheduler
    async def _schedule_loop(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._wakeup.wait(), timeout=5)
            except TimeoutError:
                pass
            self._wakeup.clear()
            try:
                await self._fill_slots()
            except Exception:  # noqa: BLE001 - scheduler must survive DB hiccups
                logger.exception("Download scheduler error")

    async def _fill_slots(self) -> None:
        free = self._concurrency - len(self._running)
        if free <= 0:
            return
        async with SessionLocal() as db:
            ids = (
                await db.execute(
                    select(DownloadJob.id)
                    .where(DownloadJob.status == DownloadStatus.queued.value)
                    .order_by(DownloadJob.id)
                    .limit(free + len(self._running))
                )
            ).scalars().all()
        for job_id in ids:
            if len(self._running) >= self._concurrency:
                break
            if job_id in self._running:
                continue
            self._running[job_id] = asyncio.create_task(self._run_job(job_id), name=f"download-{job_id}")

    async def _run_job(self, job_id: int) -> None:
        try:
            await self._process(job_id)
        except asyncio.CancelledError:
            reason = self._stop_reason.get(job_id, "shutdown")
            await self._on_stopped(job_id, reason)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Download job %s crashed", job_id)
            await self._update(job_id, status=DownloadStatus.failed.value, error=str(exc)[:2000], speed_bps=None)
        finally:
            self._running.pop(job_id, None)
            self._stop_reason.pop(job_id, None)
            self._wakeup.set()

    async def _on_stopped(self, job_id: int, reason: str) -> None:
        await self._flush_progress()
        async with SessionLocal() as db:
            job = await db.get(DownloadJob, job_id)
            if job is None:
                return
            job.speed_bps = None
            if reason == "pause" and job.resumable:
                job.status = DownloadStatus.paused.value
            elif reason == "shutdown":
                job.status = DownloadStatus.queued.value  # resumes on next start
                if not job.resumable:
                    self._remove_part(job.file_path)
                    job.progress = 0
                    job.bytes_done = 0
            else:
                job.status = DownloadStatus.cancelled.value
                job.finished_at = datetime.now(timezone.utc)
                self._remove_part(job.file_path)
            await db.commit()

    @staticmethod
    def _remove_part(stored_final: str | None) -> None:
        if not stored_final:
            return
        final = library.resolve_stored_path(stored_final)
        for candidate in (library.partial_path(final), library.partial_path(final.with_suffix(".mkv"))):
            candidate.unlink(missing_ok=True)
        # Do not leave an empty title folder behind for a download that never completed.
        anime_dir = final.parent.parent
        if anime_dir.is_dir() and anime_dir.resolve() != library.library_root().resolve():
            library.remove_empty_dirs(anime_dir, keep_root=False)

    # ------------------------------------------------------------ DB helpers
    async def _update(self, job_id: int, **fields) -> None:
        async with SessionLocal() as db:
            job = await db.get(DownloadJob, job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)
            await db.commit()

    async def _update_progress(self, job_id: int, fields: dict) -> None:
        async with SessionLocal() as db:
            job = await db.get(DownloadJob, job_id)
            # A late progress write must never touch a finished/stopped job.
            if job is None or job.status not in (DownloadStatus.downloading.value, DownloadStatus.processing.value):
                return
            for key, value in fields.items():
                setattr(job, key, value)
            await db.commit()

    def _schedule_update(self, job_id: int, fields: dict) -> None:
        task = asyncio.create_task(self._update_progress(job_id, fields))
        self._pending_writes.add(task)
        task.add_done_callback(self._pending_writes.discard)

    async def _flush_progress(self) -> None:
        if self._pending_writes:
            await asyncio.gather(*list(self._pending_writes), return_exceptions=True)

    # ---------------------------------------------------------------- worker
    async def _process(self, job_id: int) -> None:
        from backend.providers import get_registry
        from backend.services.settings import get_app_settings

        async with SessionLocal() as db:
            job = await db.get(DownloadJob, job_id)
            if job is None or job.status != DownloadStatus.queued.value:
                return
            settings = await get_app_settings(db)
            snapshot = {
                "anime_id": job.anime_external_id,
                "title": job.anime_title,
                "source": job.source,
                "season": job.season,
                "episode": job.episode,
                "episode_title": job.episode_title,
                "voiceover": job.voiceover,
                "quality": job.quality or settings.default_quality,
                "steam_deck": job.steam_deck or settings.steam_deck_optimize,
                "resume_from": job.file_path if job.resumable else None,
                "resume_url": job.source_url if job.resumable else None,
                "bytes_total": job.bytes_total,
            }

        registry = get_registry()
        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            await self._update(
                job_id, status=DownloadStatus.resolving.value, attempts=attempt, error=None, speed_bps=None
            )
            try:
                final = await self._attempt(job_id, registry, snapshot, refresh=attempt > 1)
            except (NotFound, DownloadValidationError) as exc:
                last_error = exc
                if isinstance(exc, NotFound):
                    break  # the episode/voiceover is gone; retrying will not help
            except (ProviderError, RuntimeError, OSError, UnsafeUpstream, LookupError) as exc:
                last_error = exc
            except Exception as exc:  # noqa: BLE001 - httpx and extractor errors
                last_error = exc
            else:
                logger.info("Downloaded %s S%sE%s -> %s", snapshot["title"], snapshot["season"], snapshot["episode"], final)
                return
            snapshot["resume_from"] = snapshot["resume_url"] = None
            logger.warning("Download job %s attempt %s failed: %s", job_id, attempt, last_error)
            if attempt < MAX_ATTEMPTS:
                await self._update(job_id, warning=f"Attempt {attempt} failed: {str(last_error)[:300]}; retrying")
                await asyncio.sleep(RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)])
        message = getattr(last_error, "message", None) or str(last_error) or type(last_error).__name__
        await self._flush_progress()
        async with SessionLocal() as db:
            job = await db.get(DownloadJob, job_id)
            if job is not None:
                self._remove_part(job.file_path)
                job.resumable = False
                await db.commit()
        await self._update(
            job_id,
            status=DownloadStatus.failed.value,
            error=message[:2000],
            speed_bps=None,
            finished_at=datetime.now(timezone.utc),
        )

    async def _attempt(self, job_id: int, registry, snap: dict, *, refresh: bool) -> Path:
        stream = await registry.resolve_stream(
            snap["anime_id"], snap["episode"], snap["voiceover"], snap["quality"], purpose="download", refresh=refresh
        )
        ext = "webm" if stream.video.type == "webm" else "mp4"
        final = library.episode_file_path(snap["title"], snap["season"], snap["episode"], ext)
        part = library.partial_path(final)
        resumable = stream.video.type in ("mp4", "webm")
        await self._update(
            job_id,
            status=DownloadStatus.downloading.value,
            voiceover=stream.voiceover,
            player_host=stream.player,
            quality=stream.video.quality,
            source_url=stream.video.url if resumable else None,
            file_path=library.to_stored_path(final),
            resumable=resumable,
            warning=None,
        )
        library.ensure_dir(final.parent)
        steam_deck = bool(snap["steam_deck"]) and ffmpeg_tools.ffmpeg_available()
        span = 80.0 if steam_deck else 100.0
        progress = _Progress(self, job_id, 0.0, span)

        expected_duration: list[float | None] = [None]
        if stream.video.type == "m3u8":
            session = media_sessions.create(stream.video.headers, registry.proxy, ttl=24 * 3600)
            try:
                url = self.local_base_url + session.url_for(stream.video.url)

                def on_progress(p: ffmpeg_tools.FfmpegProgress) -> None:
                    expected_duration[0] = p.duration or expected_duration[0]
                    progress.update(p.fraction, p.total_size)

                part.unlink(missing_ok=True)
                await ffmpeg_tools.download_stream_with_ffmpeg(url, part, on_progress=on_progress, hls=True)
            finally:
                media_sessions.drop(session.id)
        elif stream.video.type == "mpd":
            def on_progress_mpd(p: ffmpeg_tools.FfmpegProgress) -> None:
                expected_duration[0] = p.duration or expected_duration[0]
                progress.update(p.fraction, p.total_size)

            part.unlink(missing_ok=True)
            await ffmpeg_tools.download_stream_with_ffmpeg(
                stream.video.url, part, stream.video.headers, on_progress=on_progress_mpd
            )
        else:
            resume_url = snap.get("resume_url")
            if not resume_url:
                part.unlink(missing_ok=True)
            await self._download_progressive(job_id, resume_url or stream.video.url, stream.video.headers, part, progress)

        await self._validate(part, expected_duration[0], snap.get("bytes_total") if resumable else None)

        warning: str | None = None
        produced = part
        if steam_deck:
            await self._update(job_id, status=DownloadStatus.processing.value, progress=80.0, speed_bps=None)
            optimized_final = final.with_suffix(".mkv")
            optimized_part = library.partial_path(optimized_final)
            try:
                optimize_progress = _Progress(self, job_id, 80.0, 20.0)
                await ffmpeg_tools.optimize_for_steam_deck(
                    part, optimized_part, on_progress=lambda p: optimize_progress.update(p.fraction, p.total_size)
                )
                await self._validate(optimized_part, expected_duration[0], None)
            except asyncio.CancelledError:
                optimized_part.unlink(missing_ok=True)
                raise
            except Exception as exc:  # noqa: BLE001 - keep the valid original
                optimized_part.unlink(missing_ok=True)
                warning = f"Steam Deck optimization failed, original kept: {str(exc)[:300]}"
                logger.warning("Job %s: %s", job_id, warning)
            else:
                part.unlink(missing_ok=True)
                produced, final = optimized_part, optimized_final

        os.replace(produced, final)  # atomic within the season directory
        await self._finalize(job_id, snap, stream, final, warning)
        return final

    async def _download_progressive(self, job_id: int, url: str, headers: dict[str, str], part: Path, progress: _Progress) -> None:
        from backend.player.proxy import _open_upstream
        from backend.providers import get_registry

        offset = part.stat().st_size if part.exists() else 0
        session = media_sessions.create(headers or {"User-Agent": DEFAULT_USER_AGENT}, get_registry().proxy, ttl=3600)
        try:
            response, _final_url = await _open_upstream(session, url, f"bytes={offset}-" if offset else None)
        finally:
            media_sessions.drop(session.id)
        try:
            if response.status_code >= 400:
                raise RuntimeError(f"Media host answered HTTP {response.status_code}")
            total: int | None = None
            if offset and response.status_code == 206:
                content_range = response.headers.get("content-range", "")
                total = int(content_range.rsplit("/", 1)[-1]) if content_range.rsplit("/", 1)[-1].isdigit() else None
                mode = "ab"
            else:
                offset = 0
                mode = "wb"
                length = response.headers.get("content-length")
                total = int(length) if length and length.isdigit() else None
            if total:
                await self._update(job_id, bytes_total=total)
            done = offset
            with part.open(mode) as handle:
                async for chunk in response.aiter_bytes(512 * 1024):
                    handle.write(chunk)
                    done += len(chunk)
                    progress.update(done / total if total else None, done, total)
            if total and done != total:
                raise DownloadValidationError(f"Incomplete download: {done} of {total} bytes")
        finally:
            await response.aclose()

    async def _validate(self, path: Path, expected_duration: float | None, expected_size: int | None) -> None:
        size = library.file_size(path) or 0
        if size < library.MIN_MEDIA_BYTES:
            path.unlink(missing_ok=True)
            raise DownloadValidationError("Downloaded file is empty or truncated")
        if expected_size and size != expected_size:
            raise DownloadValidationError(f"Downloaded file size mismatch: {size} of {expected_size} bytes")
        if not ffmpeg_tools.ffmpeg_available():
            return
        duration = await ffmpeg_tools.probe_duration(path)
        if duration is None or duration <= 0:
            path.unlink(missing_ok=True)
            raise DownloadValidationError("Downloaded file is not a readable video")
        if expected_duration and duration < expected_duration * 0.95:
            path.unlink(missing_ok=True)
            raise DownloadValidationError(
                f"Download incomplete: {duration:.0f}s of {expected_duration:.0f}s"
            )

    async def _finalize(self, job_id: int, snap: dict, stream, final: Path, warning: str | None) -> None:
        await self._flush_progress()
        anime_dir = final.parent.parent
        async with SessionLocal() as db:
            row, previous = await library_index.record_episode(
                db,
                anime_id=snap["anime_id"],
                season=snap["season"],
                episode=snap["episode"],
                episode_title=snap["episode_title"],
                voiceover=stream.voiceover,
                path=final,
                quality=stream.video.quality,
            )
            await library_index.upsert_title(
                db, anime_id=snap["anime_id"], source=snap["source"], title=snap["title"], folder=anime_dir
            )
            job = await db.get(DownloadJob, job_id)
            if job is not None:
                job.status = DownloadStatus.completed.value
                job.progress = 100.0
                job.file_path = library.to_stored_path(final)
                job.bytes_done = library.file_size(final) or job.bytes_done
                job.speed_bps = None
                job.warning = warning
                job.error = None
                job.finished_at = datetime.now(timezone.utc)
            await db.commit()
        if previous is not None and previous.exists() and previous.resolve() != final.resolve():
            previous.unlink(missing_ok=True)

        # Optional extras — failures only produce a warning.
        extra_warnings: list[str] = []
        try:
            library.record_episode_metadata(
                anime_dir,
                anime_id=snap["anime_id"],
                title=snap["title"],
                season=snap["season"],
                episode=snap["episode"],
                voiceover=stream.voiceover,
                file_name=final.name,
                source=snap["source"],
                quality=stream.video.quality,
            )
        except OSError as exc:
            extra_warnings.append(f"metadata.json not written: {exc}")
        try:
            async with SessionLocal() as db:
                from backend.models import AnimeTitle

                title = (
                    await db.execute(select(AnimeTitle).where(AnimeTitle.external_id == snap["anime_id"]))
                ).scalar_one_or_none()
                poster_url = title.poster if title else None
            if poster_url:
                from backend.player.sessions import validate_upstream
                from backend.providers import get_registry

                await validate_upstream(poster_url, proxy=get_registry().proxy)
                await library.save_poster(anime_dir, poster_url, media_clients.get(get_registry().proxy))
        except Exception as exc:  # noqa: BLE001
            extra_warnings.append(f"poster not saved: {exc}")
        if extra_warnings:
            await self._update(job_id, warning="; ".join(filter(None, [warning, *extra_warnings]))[:2000])

    # ----------------------------------------------------------------- info
    def running_ids(self) -> list[int]:
        return list(self._running)


download_manager = DownloadManager()

