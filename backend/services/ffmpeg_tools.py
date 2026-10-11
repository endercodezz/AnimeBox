"""ffmpeg helpers — stream download, validation, Steam Deck transcode (HakuNeko mux inspiration).

Progress comes from ffmpeg's machine-readable ``-progress pipe:1`` output and the
input duration it reports; nothing is estimated.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import stat
import sys
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.config import ROOT_DIR, get_settings

logger = logging.getLogger("animebox.ffmpeg")
MACOS_PERMISSION_HINT = " Run 'bash scripts/grant-macos-permissions.sh' from the extracted AnimeBox folder."
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")


@dataclass
class FfmpegProgress:
    out_seconds: float
    total_size: int
    duration: float | None

    @property
    def fraction(self) -> float | None:
        if not self.duration or self.duration <= 0:
            return None
        return max(0.0, min(1.0, self.out_seconds / self.duration))


ProgressCallback = Callable[[FfmpegProgress], None]


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


def parse_duration(text: str) -> float | None:
    match = _DURATION_RE.search(text)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


async def _terminate(proc) -> None:
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except TimeoutError:
        proc.kill()
        await proc.wait()


async def run_ffmpeg(args: list[str], on_progress: ProgressCallback | None = None) -> str:
    """Run ffmpeg; returns the stderr tail. The process is always reaped, also on cancellation."""
    executable = ffmpeg_path()
    if not executable:
        raise RuntimeError(f"ffmpeg not found or not executable.{_macos_permission_hint()}")
    try:
        proc = await asyncio.create_subprocess_exec(
            executable,
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        detail = exc.strerror or str(exc)
        raise RuntimeError(
            f"Could not start ffmpeg at {executable}: {detail}.{_macos_permission_hint(executable)}"
        ) from exc

    tail: deque[str] = deque(maxlen=60)
    duration: list[float | None] = [None]

    async def read_stderr() -> None:
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            text = line.decode("utf-8", errors="ignore").rstrip()
            tail.append(text)
            if duration[0] is None:
                duration[0] = parse_duration(text)

    async def read_stdout() -> None:
        values: dict[str, str] = {}
        while True:
            line = await proc.stdout.readline()
            if not line:
                return
            key, _, value = line.decode("utf-8", errors="ignore").strip().partition("=")
            values[key] = value
            if key == "progress" and on_progress is not None:
                try:
                    out_us = int(values.get("out_time_us") or values.get("out_time_ms") or 0)
                except ValueError:
                    out_us = 0
                try:
                    size = int(values.get("total_size") or 0)
                except ValueError:
                    size = 0
                on_progress(FfmpegProgress(out_seconds=max(out_us, 0) / 1_000_000, total_size=size, duration=duration[0]))

    try:
        await asyncio.gather(read_stderr(), read_stdout())
        await proc.wait()
    except asyncio.CancelledError:
        await _terminate(proc)
        raise
    except BaseException:
        await _terminate(proc)
        raise
    if proc.returncode != 0:
        detail = "\n".join(tail)[-1600:].strip() or "no error output"
        raise RuntimeError(
            f"ffmpeg failed with exit code {proc.returncode} ({executable}): {detail}.{_macos_permission_hint(executable)}"
        )
    return "\n".join(tail)


@lru_cache(maxsize=1)
def _hls_demuxer_options() -> str:
    executable = ffmpeg_path()
    if not executable:
        return ""
    import subprocess

    try:
        return subprocess.run(
            [executable, "-hide_banner", "-h", "demuxer=hls"], capture_output=True, text=True, timeout=15
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def hls_input_options() -> list[str]:
    """Allow extension-less segment names (common on CDNs and behind the local media proxy)."""
    help_text = _hls_demuxer_options()
    options: list[str] = []
    if "allowed_extensions" in help_text:
        options += ["-allowed_extensions", "ALL"]
    if "extension_picky" in help_text:
        options += ["-extension_picky", "0"]
    return options


def header_args(headers: dict[str, str] | None) -> list[str]:
    if not headers:
        return []
    args: list[str] = []
    rest = {k: v for k, v in headers.items() if k.lower() != "user-agent"}
    user_agent = next((v for k, v in headers.items() if k.lower() == "user-agent"), None)
    if user_agent:
        args += ["-user_agent", user_agent]
    if rest:
        args += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in rest.items())]
    return args


async def download_stream_with_ffmpeg(
    url: str,
    dest: Path,
    headers: dict[str, str] | None = None,
    *,
    on_progress: ProgressCallback | None = None,
    hls: bool = False,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "info",
        "-progress",
        "pipe:1",
        *header_args(headers),
        *(hls_input_options() if hls else []),
        "-y",
        "-i",
        url,
        # ffmpeg picks the highest-resolution variant of a master playlist by default.
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    await run_ffmpeg(args, on_progress=on_progress)
    return dest


async def probe_duration(path: Path) -> float | None:
    """Container duration as reported by ffmpeg, or ``None`` if unreadable."""
    executable = ffmpeg_path()
    if not executable:
        return None
    proc = await asyncio.create_subprocess_exec(
        executable,
        "-hide_banner",
        "-i",
        str(path),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _out, err = await asyncio.wait_for(proc.communicate(), timeout=60)
    except (TimeoutError, asyncio.CancelledError):
        await _terminate(proc)
        raise
    return parse_duration(err.decode("utf-8", errors="ignore"))


async def optimize_for_steam_deck(src: Path, dest: Path, on_progress: ProgressCallback | None = None) -> Path:
    """H.265 / reduced resolution for a compact Steam Deck travel library."""
    settings = get_settings()
    await run_ffmpeg(
        [
            "-hide_banner",
            "-nostats",
            "-progress",
            "pipe:1",
            "-y",
            "-i",
            str(src),
            "-vf",
            f"scale=-2:'min({int(settings.steam_deck_height)},ih)'",
            "-c:v",
            "libx265",
            "-crf",
            str(int(settings.steam_deck_crf)),
            "-preset",
            "medium",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(dest),
        ],
        on_progress=on_progress,
    )
    return dest
