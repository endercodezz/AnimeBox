"""ffmpeg helpers — remux / Steam Deck optimize (Hakuneko mux inspiration)."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import stat
import sys
from pathlib import Path

from backend.config import ROOT_DIR, get_settings

logger = logging.getLogger("animebox.ffmpeg")
MACOS_PERMISSION_HINT = (
    " Run 'bash scripts/grant-macos-permissions.sh' from the extracted AnimeBox folder."
)


def bundled_ffmpeg_path() -> Path:
    executable = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    return ROOT_DIR / "tools" / executable


def _prepare_bundled_ffmpeg(path: Path) -> bool:
    if not path.is_file():
        return False
    if os.name == "nt" or os.access(path, os.X_OK):
        return True
    try:
        path.chmod(stat.S_IMODE(path.stat().st_mode) | stat.S_IXUSR)
    except OSError as exc:
        logger.warning("Could not make bundled ffmpeg executable at %s: %s", path, exc)
    return os.access(path, os.X_OK)


def ffmpeg_path() -> str | None:
    bundled = bundled_ffmpeg_path()
    if _prepare_bundled_ffmpeg(bundled):
        return str(bundled)
    return shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    executable = ffmpeg_path()
    return executable is not None and (os.name == "nt" or os.access(executable, os.X_OK))


def _macos_permission_hint(executable: str | None = None) -> str:
    if sys.platform != "darwin":
        return ""
    if executable is not None and Path(executable) != bundled_ffmpeg_path():
        return ""
    return MACOS_PERMISSION_HINT


async def run_ffmpeg(args: list[str]) -> None:
    executable = ffmpeg_path()
    if not executable:
        raise RuntimeError(f"ffmpeg not found or not executable.{_macos_permission_hint()}")
    try:
        proc = await asyncio.create_subprocess_exec(
            executable,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        detail = exc.strerror or str(exc)
        raise RuntimeError(
            f"Could not start ffmpeg at {executable}: {detail}.{_macos_permission_hint(executable)}"
        ) from exc
    try:
        _out, err = await proc.communicate()
    except asyncio.CancelledError:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except TimeoutError:
                proc.kill()
                await proc.wait()
        raise
    if proc.returncode != 0:
        detail = err.decode("utf-8", errors="ignore")[-1600:].strip() or "no error output"
        raise RuntimeError(
            f"ffmpeg failed with exit code {proc.returncode} ({executable}): {detail}."
            f"{_macos_permission_hint(executable)}"
        )


async def remux_to_mkv(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    await run_ffmpeg(["-y", "-i", str(src), "-c", "copy", "-movflags", "+faststart", str(dest)])
    return dest


async def download_stream_with_ffmpeg(url: str, dest: Path, headers: dict[str, str] | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    header_args: list[str] = []
    if headers:
        header_blob = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        header_args = ["-headers", header_blob]
    await run_ffmpeg(
        [
            *header_args,
            "-y",
            "-i",
            url,
            # Let ffmpeg choose the highest-resolution video stream from master
            # playlists instead of forcing the first (usually lowest) variant.
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )
    return dest


async def download_hls_with_ffmpeg(url: str, dest: Path, headers: dict[str, str] | None = None) -> Path:
    """Backward-compatible alias for stream downloads."""
    return await download_stream_with_ffmpeg(url, dest, headers)


async def optimize_for_steam_deck(src: Path, dest: Path | None = None) -> Path:
    """H.265 / smaller size / suitable resolution for Steam Deck travel library."""
    settings = get_settings()
    dest = dest or src.with_name(src.stem + ".steamdeck.mkv")
    height = settings.steam_deck_height
    crf = settings.steam_deck_crf
    await run_ffmpeg(
        [
            "-y",
            "-i",
            str(src),
            "-vf",
            f"scale=-2:{height}",
            "-c:v",
            "libx265",
            "-crf",
            str(crf),
            "-preset",
            "medium",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )
    return dest
