"""ffmpeg helpers — remux / Steam Deck optimize (Hakuneko mux inspiration)."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path

from backend.config import ROOT_DIR, get_settings

logger = logging.getLogger("animebox.ffmpeg")


def ffmpeg_path() -> str | None:
    executable = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    bundled = ROOT_DIR / "tools" / executable
    if bundled.is_file():
        return str(bundled)
    return shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    return ffmpeg_path() is not None


async def run_ffmpeg(args: list[str]) -> None:
    executable = ffmpeg_path()
    if not executable:
        raise RuntimeError("ffmpeg not found")
    proc = await asyncio.create_subprocess_exec(
        executable,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
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
        raise RuntimeError(err.decode("utf-8", errors="ignore")[-2000:] or "ffmpeg failed")


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
