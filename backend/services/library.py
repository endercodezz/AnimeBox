"""Local library filesystem helpers (Hakuneko-inspired path layout)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from backend.config import get_settings

logger = logging.getLogger("animebox.library")


def sanitize_name(name: str) -> str:
    name = name.strip() or "Unknown"
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:120] or "Unknown"


def anime_dir(title: str) -> Path:
    root = get_settings().library_path
    path = root / sanitize_name(title)
    path.mkdir(parents=True, exist_ok=True)
    return path


def season_dir(title: str, season: int) -> Path:
    path = anime_dir(title) / f"Season {season}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def episode_path(title: str, season: int, episode: int, ext: str = "mkv") -> Path:
    return season_dir(title, season) / f"Episode {episode:02d}.{ext.lstrip('.')}"


def write_metadata(title: str, meta: dict) -> Path:
    path = anime_dir(title) / "metadata.json"
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing.update(meta)
    existing["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def append_episode_metadata(
    title: str,
    *,
    season: int,
    episode: int,
    voiceover: str | None,
    file_name: str,
    source: str,
) -> None:
    path = anime_dir(title) / "metadata.json"
    data: dict = {"title": title, "episodes": []}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    episodes = [e for e in data.get("episodes", []) if not (e.get("season") == season and e.get("episode") == episode)]
    episodes.append(
        {
            "season": season,
            "episode": episode,
            "voiceover": voiceover,
            "file": file_name,
            "source": source,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "progress": 0,
        }
    )
    data["title"] = title
    data["episodes"] = sorted(episodes, key=lambda e: (e.get("season", 1), e.get("episode", 0)))
    write_metadata(title, data)


async def save_poster(title: str, poster_url: str | None, headers: dict | None = None) -> Path | None:
    if not poster_url:
        return None
    dest = anime_dir(title) / "poster.jpg"
    if dest.exists():
        return dest
    try:
        import httpx

        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            resp = await client.get(poster_url, headers=headers or {})
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return dest
    except Exception as exc:
        logger.warning("Poster download failed: %s", exc)
        return None
