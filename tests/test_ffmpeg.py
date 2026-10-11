"""ffmpeg integration: binary discovery, error reporting, progress parsing, process cleanup."""

from __future__ import annotations

import asyncio
import importlib
import os
import stat
from pathlib import Path

import pytest

from backend.providers.catalog import SOURCES
from backend.services import ffmpeg_tools


def test_all_catalog_sources_import() -> None:
    for spec in SOURCES:
        module = importlib.import_module(f"anicli_api.source.{spec.module}")
        assert hasattr(module, "Extractor") and hasattr(module, "Search")


class FakeStream:
    def __init__(self, lines: list[bytes], block: bool = False) -> None:
        self._lines = list(lines)
        self._block = block

    async def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        if self._block:
            await asyncio.Event().wait()
        return b""


class FakeProcess:
    def __init__(self, returncode: int = 0, stdout: list[bytes] | None = None, stderr: list[bytes] | None = None, block=False):
        self._final = returncode
        self.returncode: int | None = None
        self.stdout = FakeStream(stdout or [], block)
        self.stderr = FakeStream(stderr or [], block)
        self.terminated = False

    async def wait(self) -> int:
        self.returncode = self._final if self.returncode is None else self.returncode
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9


async def test_stream_download_copies_and_lets_ffmpeg_pick_best_variant(monkeypatch, tmp_path: Path) -> None:
    captured: list[str] = []

    async def fake_run(args, on_progress=None):
        captured.extend(args)
        return ""

    monkeypatch.setattr(ffmpeg_tools, "run_ffmpeg", fake_run)
    monkeypatch.setattr(ffmpeg_tools, "hls_input_options", lambda: ["-allowed_extensions", "ALL"])
    await ffmpeg_tools.download_stream_with_ffmpeg(
        "https://cdn.example/master.m3u8",
        tmp_path / "episode.part.mp4",
        {"User-Agent": "Provider-UA", "Referer": "https://player.example/"},
        hls=True,
    )
    assert "-map" not in captured
    assert captured[captured.index("-i") + 1] == "https://cdn.example/master.m3u8"
    assert captured[captured.index("-c") + 1] == "copy"
    assert captured[captured.index("-user_agent") + 1] == "Provider-UA"
    assert captured[captured.index("-headers") + 1] == "Referer: https://player.example/\r\n"
    assert captured.index("-allowed_extensions") < captured.index("-i")
    assert captured[captured.index("-progress") + 1] == "pipe:1"


async def test_progress_is_parsed_from_machine_output(monkeypatch) -> None:
    proc = FakeProcess(
        stdout=[b"out_time_us=600000000\n", b"total_size=1048576\n", b"progress=continue\n", b"progress=end\n"],
        stderr=[b"  Duration: 00:20:00.00, start: 0.0, bitrate: 1 kb/s\n"],
    )

    async def spawn(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(ffmpeg_tools, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(ffmpeg_tools.asyncio, "create_subprocess_exec", spawn)
    seen: list[ffmpeg_tools.FfmpegProgress] = []
    # stderr is read concurrently; duration may arrive before or after the first progress block.
    await ffmpeg_tools.run_ffmpeg(["-i", "x"], on_progress=seen.append)
    assert seen and seen[0].out_seconds == 600 and seen[0].total_size == 1048576
    assert any(p.fraction == pytest.approx(0.5) for p in seen if p.duration)


def test_parse_duration() -> None:
    assert ffmpeg_tools.parse_duration("Duration: 01:02:03.50, start") == pytest.approx(3723.5)
    assert ffmpeg_tools.parse_duration("Duration: N/A") is None


@pytest.mark.skipif(os.name == "nt", reason="Windows does not use POSIX execute bits")
def test_bundled_ffmpeg_repairs_only_user_execute_bit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executable = tmp_path / "tools" / "ffmpeg"
    executable.parent.mkdir()
    executable.write_bytes(b"ffmpeg")
    executable.chmod(0o640)
    monkeypatch.setattr(ffmpeg_tools, "ROOT_DIR", tmp_path)

    assert ffmpeg_tools.ffmpeg_path() == str(executable)
    assert stat.S_IMODE(executable.stat().st_mode) == 0o740


def test_ffmpeg_from_path_is_not_modified(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executable = tmp_path / "system-ffmpeg"
    executable.write_bytes(b"ffmpeg")
    executable.chmod(0o755)
    initial_mode = stat.S_IMODE(executable.stat().st_mode)
    monkeypatch.setattr(ffmpeg_tools, "ROOT_DIR", tmp_path / "portable")
    monkeypatch.setattr(ffmpeg_tools.shutil, "which", lambda _name: str(executable))

    assert ffmpeg_tools.ffmpeg_path() == str(executable)
    assert stat.S_IMODE(executable.stat().st_mode) == initial_mode


async def test_ffmpeg_launch_error_includes_path_and_macos_helper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executable = tmp_path / "tools" / "ffmpeg"
    monkeypatch.setattr(ffmpeg_tools, "ffmpeg_path", lambda: str(executable))
    monkeypatch.setattr(ffmpeg_tools, "bundled_ffmpeg_path", lambda: executable)
    monkeypatch.setattr(ffmpeg_tools.sys, "platform", "darwin")

    async def fail_to_start(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(ffmpeg_tools.asyncio, "create_subprocess_exec", fail_to_start)
    with pytest.raises(RuntimeError) as exc_info:
        await ffmpeg_tools.run_ffmpeg(["-version"])
    message = str(exc_info.value)
    assert str(executable) in message and "Permission denied" in message and "grant-macos-permissions.sh" in message


async def test_ffmpeg_exit_error_includes_code_and_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    async def spawn(*_args, **_kwargs):
        return FakeProcess(returncode=7, stderr=[b"broken dylib\n"])

    monkeypatch.setattr(ffmpeg_tools, "ffmpeg_path", lambda: "/usr/local/bin/ffmpeg")
    monkeypatch.setattr(ffmpeg_tools.asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(RuntimeError, match="exit code 7.*broken dylib"):
        await ffmpeg_tools.run_ffmpeg(["-version"])


async def test_ffmpeg_process_is_terminated_when_download_is_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    process = FakeProcess(block=True)

    async def spawn(*_args, **_kwargs):
        return process

    monkeypatch.setattr(ffmpeg_tools, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(ffmpeg_tools.asyncio, "create_subprocess_exec", spawn)
    task = asyncio.create_task(ffmpeg_tools.run_ffmpeg(["-i", "x"]))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.terminated is True
