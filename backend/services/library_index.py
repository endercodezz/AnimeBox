"""Offline library queries.

The library is derived from ``library_episodes`` rows whose files actually exist
and pass :func:`backend.services.library.is_valid_media_file`. Catalog metadata
(``anime_titles``) only decorates those entries; browsing a title never adds it.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AnimeTitle, LibraryEpisode, WatchHistory
from backend.providers.ids import decode_external_id, safe_canonical_id
from backend.schemas import LibraryAnimeOut, LibraryEpisodeOut, LibraryStats, RescanResult
from backend.services import library

logger = logging.getLogger("animebox.library")


def poster_endpoint(anime_id: str) -> str:
    return f"/api/library/poster?id={quote(anime_id, safe='')}"


def episode_stream_url(episode_id: int) -> str:
    return f"/api/library/file/{episode_id}"


def anime_dir_for(title: AnimeTitle | None, episodes: list[LibraryEpisode]) -> Path | None:
    if title is not None and title.folder_path:
        return library.resolve_stored_path(title.folder_path)
    for ep in episodes:
        path = library.resolve_stored_path(ep.file_path)
        if library.parse_episode_file(path):
            return path.parent.parent
    return None


async def _titles(db: AsyncSession, ids: list[str]) -> dict[str, AnimeTitle]:
    if not ids:
        return {}
    rows = (await db.execute(select(AnimeTitle).where(AnimeTitle.external_id.in_(ids)))).scalars().all()
    return {row.external_id: row for row in rows}


async def list_library(db: AsyncSession) -> list[LibraryAnimeOut]:
    rows = (
        await db.execute(select(LibraryEpisode).order_by(LibraryEpisode.season, LibraryEpisode.episode))
    ).scalars().all()
    groups: dict[str, list[LibraryEpisode]] = defaultdict(list)
    for row in rows:
        groups[row.anime_external_id].append(row)
    titles = await _titles(db, list(groups))
    out: list[LibraryAnimeOut] = []
    for anime_id, episodes in groups.items():
        valid: list[tuple[LibraryEpisode, int]] = []
        for ep in episodes:
            path = library.resolve_stored_path(ep.file_path)
            if library.is_valid_media_file(path):
                valid.append((ep, library.file_size(path) or 0))
        if not valid:
            continue  # nothing playable offline -> not part of the library
        title = titles.get(anime_id)
        anime_dir = anime_dir_for(title, [ep for ep, _ in valid])
        local_poster = library.poster_file(anime_dir) if anime_dir else None
        try:
            source = decode_external_id(anime_id)[0]
        except ValueError:
            source = "local"
        last = max((ep.downloaded_at for ep, _ in valid if ep.downloaded_at), default=None)
        out.append(
            LibraryAnimeOut(
                id=anime_id,
                title=title.title if title else (anime_dir.name if anime_dir else anime_id),
                poster=poster_endpoint(anime_id) if local_poster else (title.poster if title else None),
                description=title.description if title else None,
                year=title.year if title else None,
                source=source,
                episode_count=len(valid),
                missing_count=len(episodes) - len(valid),
                watched_count=sum(1 for ep, _ in valid if ep.completed),
                size_bytes=sum(size for _, size in valid),
                last_downloaded_at=last,
                folder_path=str(anime_dir) if anime_dir else None,
            )
        )
    out.sort(key=lambda item: item.last_downloaded_at or datetime.min, reverse=True)
    return out


async def library_episodes(db: AsyncSession, anime_id: str) -> list[LibraryEpisodeOut]:
    rows = (
        await db.execute(
            select(LibraryEpisode)
            .where(LibraryEpisode.anime_external_id == anime_id)
            .order_by(LibraryEpisode.season, LibraryEpisode.episode)
        )
    ).scalars().all()
    out: list[LibraryEpisodeOut] = []
    for row in rows:
        path = library.resolve_stored_path(row.file_path)
        available = library.is_valid_media_file(path)
        item = LibraryEpisodeOut.model_validate(row, from_attributes=True)
        item.available = available
        item.file_size = library.file_size(path) if available else row.file_size
        item.stream_url = episode_stream_url(row.id) if available else None
        out.append(item)
    return out


async def downloaded_keys(db: AsyncSession, anime_id: str) -> set[tuple[int, int]]:
    return {(ep.season, ep.episode) for ep in await library_episodes(db, anime_id) if ep.available}


async def upsert_title(
    db: AsyncSession,
    *,
    anime_id: str,
    source: str,
    title: str,
    poster: str | None = None,
    description: str | None = None,
    year: int | None = None,
    folder: Path | None = None,
) -> AnimeTitle:
    row = (await db.execute(select(AnimeTitle).where(AnimeTitle.external_id == anime_id))).scalar_one_or_none()
    if row is None:
        row = AnimeTitle(external_id=anime_id, source=source, title=title)
        db.add(row)
    row.title = title or row.title
    row.poster = poster or row.poster
    row.description = description or row.description
    row.year = year or row.year
    if folder is not None:
        row.folder_path = library.to_stored_path(folder)
    return row


async def record_episode(
    db: AsyncSession,
    *,
    anime_id: str,
    season: int,
    episode: int,
    episode_title: str | None,
    voiceover: str | None,
    path: Path,
    quality: int | None,
) -> tuple[LibraryEpisode, Path | None]:
    """Upsert the library row. Returns the row and the previous file if it was replaced."""
    row = (
        await db.execute(
            select(LibraryEpisode).where(
                LibraryEpisode.anime_external_id == anime_id,
                LibraryEpisode.season == season,
                LibraryEpisode.episode == episode,
            )
        )
    ).scalar_one_or_none()
    stored = library.to_stored_path(path)
    previous: Path | None = None
    if row is None:
        row = LibraryEpisode(anime_external_id=anime_id, season=season, episode=episode, file_path=stored)
        db.add(row)
    else:
        old = library.resolve_stored_path(row.file_path)
        if old.resolve() != path.resolve():
            previous = old
        row.file_path = stored
        row.downloaded_at = datetime.now().astimezone()
        row.completed = False
        row.progress_seconds = 0.0
    row.title = episode_title or row.title or f"Episode {episode}"
    row.voiceover = voiceover
    row.file_size = library.file_size(path)
    row.quality = quality
    await db.flush()
    return row, previous


async def delete_episode(db: AsyncSession, episode_id: int) -> bool:
    row = await db.get(LibraryEpisode, episode_id)
    if row is None:
        return False
    path = library.resolve_stored_path(row.file_path)
    anime_dir = path.parent.parent if library.parse_episode_file(path) else None
    library.delete_files([path], anime_dir=None)
    if anime_dir is not None:
        library.remove_episode_metadata(anime_dir, row.season, row.episode)
        library.remove_empty_dirs(anime_dir)
    await db.execute(
        WatchHistory.__table__.update().where(WatchHistory.local_episode_id == row.id).values(local_episode_id=None)
    )
    await db.delete(row)
    await _detach_empty_title(db, row.anime_external_id, anime_dir)
    await db.commit()
    return True


async def _detach_empty_title(db: AsyncSession, anime_id: str, anime_dir: Path | None) -> None:
    await db.flush()
    remaining = (
        await db.execute(select(LibraryEpisode.id).where(LibraryEpisode.anime_external_id == anime_id).limit(1))
    ).first()
    if remaining is None:
        if anime_dir is not None:
            library.delete_files([], anime_dir=anime_dir)
        title = (await db.execute(select(AnimeTitle).where(AnimeTitle.external_id == anime_id))).scalar_one_or_none()
        if title is not None:
            title.folder_path = None


async def delete_anime(db: AsyncSession, anime_id: str) -> int:
    rows = (await db.execute(select(LibraryEpisode).where(LibraryEpisode.anime_external_id == anime_id))).scalars().all()
    if not rows:
        return 0
    title = (await db.execute(select(AnimeTitle).where(AnimeTitle.external_id == anime_id))).scalar_one_or_none()
    anime_dir = anime_dir_for(title, list(rows))
    paths = [library.resolve_stored_path(r.file_path) for r in rows]
    deleted = library.delete_files(paths, anime_dir=anime_dir)
    ids = [r.id for r in rows]
    await db.execute(
        WatchHistory.__table__.update().where(WatchHistory.local_episode_id.in_(ids)).values(local_episode_id=None)
    )
    await db.execute(delete(LibraryEpisode).where(LibraryEpisode.id.in_(ids)))
    if title is not None:
        title.folder_path = None
    await db.commit()
    return deleted


async def rescan(db: AsyncSession) -> RescanResult:
    """Drop rows whose files vanished and import untracked episodes that carry an AnimeBox id."""
    rows = (await db.execute(select(LibraryEpisode))).scalars().all()
    removed = 0
    tracked: set[Path] = set()
    for row in rows:
        path = library.resolve_stored_path(row.file_path)
        if library.is_valid_media_file(path):
            tracked.add(path.resolve())
            continue
        await db.delete(row)
        removed += 1
    await db.flush()

    imported = 0
    root = library.library_root()
    if root.is_dir():
        for anime_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            meta = library.read_metadata(anime_dir)
            raw_id = meta.get("id")
            if not isinstance(raw_id, str):
                continue
            anime_id = safe_canonical_id(raw_id)
            for media in sorted(anime_dir.rglob("*")):
                if media.resolve() in tracked or not library.is_valid_media_file(media):
                    continue
                key = library.parse_episode_file(media)
                if key is None:
                    continue
                exists = (
                    await db.execute(
                        select(LibraryEpisode.id).where(
                            LibraryEpisode.anime_external_id == anime_id,
                            LibraryEpisode.season == key[0],
                            LibraryEpisode.episode == key[1],
                        )
                    )
                ).first()
                if exists:
                    continue
                voice = next(
                    (
                        e.get("voiceover")
                        for e in meta.get("episodes", [])
                        if isinstance(e, dict) and e.get("season") == key[0] and e.get("episode") == key[1]
                    ),
                    None,
                )
                db.add(
                    LibraryEpisode(
                        anime_external_id=anime_id,
                        season=key[0],
                        episode=key[1],
                        title=f"Episode {key[1]}",
                        voiceover=voice,
                        file_path=library.to_stored_path(media),
                        file_size=library.file_size(media),
                    )
                )
                tracked.add(media.resolve())
                imported += 1
            if imported:
                try:
                    source = decode_external_id(anime_id)[0]
                except ValueError:
                    source = "local"
                await upsert_title(
                    db, anime_id=anime_id, source=source, title=str(meta.get("title") or anime_dir.name), folder=anime_dir
                )
    await db.commit()
    removed_dirs = library.remove_empty_dirs(root)
    return RescanResult(removed_missing=removed, imported=imported, removed_empty_dirs=removed_dirs)


async def stats(db: AsyncSession) -> LibraryStats:
    items = await list_library(db)
    root = library.library_root()
    usage = library.disk_usage(root)
    return LibraryStats(
        titles=len(items),
        episodes=sum(i.episode_count for i in items),
        size_bytes=sum(i.size_bytes for i in items),
        library_path=str(root),
        disk_total=usage["total"],
        disk_free=usage["free"],
    )
