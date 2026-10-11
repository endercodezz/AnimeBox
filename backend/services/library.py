"""Library filesystem helpers (Hakuneko-inspired path layout).

Layout::

    library/<Anime Title>/Season <N>/Episode <NN>.<ext>
    library/<Anime Title>/poster.jpg
    library/<Anime Title>/metadata.json

Path helpers in this module are *pure*: computing where an episode would live
never touches the disk. Directories are created only by :func:`ensure_dir`,
which the download manager calls right before writing a file. (In 1.x merely
opening an anime page created its folder, which made browsed titles show up in
the offline library.)
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from backend.config import ROOT_DIR, get_settings

logger = logging.getLogger("animebox.library")

MEDIA_EXTENSIONS = frozenset({".mp4", ".mkv", ".webm", ".m4v", ".mov", ".ts"})
# Anything smaller cannot be a playable episode (truncated / error page saved to disk).
MIN_MEDIA_BYTES = 1024
PART_MARKER = ".part"
_EPISODE_FILE_RE = re.compile(r"^Episode (\d{1,4})(?:\.steamdeck)?\.(\w+)$", re.IGNORECASE)
_SEASON_DIR_RE = re.compile(r"^Season (\d{1,3})$", re.IGNORECASE)


def library_root() -> Path:
    return get_settings().library_path


def sanitize_name(name: str) -> str:
    name = (name or "").strip() or "Unknown"
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:120] or "Unknown"


def anime_dir_path(title: str, root: Path | None = None) -> Path:
    return (root or library_root()) / sanitize_name(title)


def season_dir_path(title: str, season: int, root: Path | None = None) -> Path:
    return anime_dir_path(title, root) / f"Season {int(season)}"


def episode_file_path(title: str, season: int, episode: int, ext: str = "mp4", root: Path | None = None) -> Path:
    return season_dir_path(title, season, root) / f"Episode {int(episode):02d}.{ext.lstrip('.')}"


def partial_path(final: Path) -> Path:
    """Temporary sibling of ``final``; keeps the media suffix last so ffmpeg picks the muxer."""
    return final.with_name(f"{final.stem}{PART_MARKER}{final.suffix}")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def to_stored_path(path: Path, root: Path | None = None) -> str:
    """Store library files relative to the library root so moving a portable folder keeps working."""
    root = (root or library_root()).resolve()
    resolved = path.resolve()
    if _is_relative_to(resolved, root):
        return resolved.relative_to(root).as_posix()
    return str(resolved)


def resolve_stored_path(stored: str, root: Path | None = None) -> Path:
    """Resolve a stored path, including 1.x values relative to the process working directory."""
    root = root or library_root()
    normalized = (stored or "").replace("\\", "/")
    candidate = Path(normalized)
    if candidate.is_absolute() or re.match(r"^[A-Za-z]:/", normalized):
        return Path(stored)
    in_library = root / candidate
    if in_library.exists():
        return in_library
    legacy = ROOT_DIR / candidate  # 1.x stored "library/<title>/..." relative to the app folder
    if legacy.exists():
        return legacy
    return in_library


def is_partial_file(path: Path) -> bool:
    return PART_MARKER in path.name.lower()


def is_valid_media_file(path: Path) -> bool:
    """Cheap validity check used by every library read (existence, type, size)."""
    if path.suffix.lower() not in MEDIA_EXTENSIONS or is_partial_file(path):
        return False
    try:
        stat = path.stat()
    except OSError:
        return False
    return path.is_file() and stat.st_size >= MIN_MEDIA_BYTES


def file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def parse_episode_file(path: Path) -> tuple[int, int] | None:
    """Return ``(season, episode)`` for files that follow the library layout."""
    match = _EPISODE_FILE_RE.match(path.name)
    season_match = _SEASON_DIR_RE.match(path.parent.name)
    if not match or not season_match:
        return None
    return int(season_match.group(1)), int(match.group(1))


def _atomic_write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_metadata(anime_dir: Path) -> dict:
    path = anime_dir / "metadata.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_metadata(anime_dir: Path, meta: dict) -> Path:
    path = anime_dir / "metadata.json"
    data = read_metadata(anime_dir)
    data.update(meta)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
    return path


def record_episode_metadata(
    anime_dir: Path,
    *,
    anime_id: str,
    title: str,
    season: int,
    episode: int,
    voiceover: str | None,
    file_name: str,
    source: str,
    quality: int | None = None,
) -> None:
    data = read_metadata(anime_dir)
    episodes = [
        item
        for item in data.get("episodes", [])
        if isinstance(item, dict) and not (item.get("season") == season and item.get("episode") == episode)
    ]
    episodes.append(
        {
            "season": season,
            "episode": episode,
            "voiceover": voiceover,
            "file": file_name,
            "source": source,
            "quality": quality,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    write_metadata(
        anime_dir,
        {
            "id": anime_id,
            "title": title,
            "episodes": sorted(episodes, key=lambda item: (item.get("season", 1), item.get("episode", 0))),
        },
    )


def remove_episode_metadata(anime_dir: Path, season: int, episode: int) -> None:
    data = read_metadata(anime_dir)
    if not data:
        return
    data["episodes"] = [
        item
        for item in data.get("episodes", [])
        if isinstance(item, dict) and not (item.get("season") == season and item.get("episode") == episode)
    ]
    write_metadata(anime_dir, data)


_IMAGE_SIGNATURES = (
    (bytes.fromhex("ffd8ff"), "image/jpeg", "jpg"),
    (bytes.fromhex("89504e47"), "image/png", "png"),
    (b"GIF8", "image/gif", "gif"),
)


def image_type(data: bytes) -> tuple[str, str] | None:
    """(mime, extension) from magic bytes; 1.x saved WebP posters under a .jpg name."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    for signature, mime, ext in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return mime, ext
    return None


def poster_file(anime_dir: Path) -> Path | None:
    for name in ("poster.jpg", "poster.png", "poster.webp"):
        candidate = anime_dir / name
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


async def save_poster(anime_dir: Path, poster_url: str | None, client) -> Path | None:
    """Best-effort poster download. Failures never affect the downloaded episode."""
    if not poster_url or not poster_url.startswith(("http://", "https://")):
        return None
    existing = poster_file(anime_dir)
    if existing:
        return existing
    try:
        response = await client.get(poster_url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        detected = image_type(response.content[:16])
        if detected is None:
            raise ValueError(f"not an image (content-type {response.headers.get('content-type', '')!r})")
        dest = anime_dir / f"poster.{'jpg' if detected[1] == 'jpg' else detected[1]}"
        ensure_dir(anime_dir)
        tmp = dest.with_name(".poster.tmp")
        tmp.write_bytes(response.content)
        os.replace(tmp, dest)
        return dest
    except Exception as exc:  # noqa: BLE001 - poster is optional
        logger.warning("Poster download failed for %s: %s", anime_dir.name, exc)
        return None


def remove_empty_dirs(root: Path, *, keep_root: bool = True) -> int:
    """Remove directories that contain no files at all. Never deletes files."""
    removed = 0
    if not root.is_dir():
        return 0
    for current, dirs, files in os.walk(root, topdown=False):
        path = Path(current)
        if keep_root and path == root:
            continue
        if not files and not any((path / d).exists() for d in dirs):
            try:
                path.rmdir()
                removed += 1
            except OSError:
                pass
    return removed


def delete_files(paths: list[Path], anime_dir: Path | None = None) -> int:
    deleted = 0
    for path in paths:
        try:
            path.unlink()
            deleted += 1
        except FileNotFoundError:
            continue
        except OSError as exc:
            logger.warning("Could not delete %s: %s", path, exc)
    if anime_dir is not None and anime_dir.is_dir():
        # The title folder may now hold only artwork/metadata.
        remaining_media = [p for p in anime_dir.rglob("*") if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS]
        if not remaining_media:
            for leftover in ("poster.jpg", "poster.png", "poster.webp", "metadata.json"):
                (anime_dir / leftover).unlink(missing_ok=True)
        remove_empty_dirs(anime_dir, keep_root=False)
    return deleted


def disk_usage(path: Path) -> dict[str, int]:
    try:
        usage = shutil.disk_usage(path)
        return {"total": usage.total, "used": usage.used, "free": usage.free}
    except OSError:
        return {"total": 0, "used": 0, "free": 0}
