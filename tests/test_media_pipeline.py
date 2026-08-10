from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat

import pytest

from backend.downloader.manager import DownloadManager
from backend.player.proxy import _rewrite_m3u8
from backend.services import ffmpeg_tools
from backend.config import Settings
from backend.providers.registry import DEFAULT_SOURCES, _pick_video, load_extractor


def test_all_default_search_sources_import() -> None:
    settings = Settings(_env_file=None)

    for source in DEFAULT_SOURCES:
        extractor, module = load_extractor(source, settings)
        assert extractor is not None
        assert module.__name__ == f"anicli_api.source.{source}"


@dataclass
class FakeVideo:
    type: str
    quality: int
    url: str


def test_pick_video_prefers_hls_when_quality_matches() -> None:
    videos = [
        FakeVideo("mpd", 1080, "https://cdn.example/video.mpd"),
        FakeVideo("m3u8", 1080, "https://cdn.example/video.m3u8"),
    ]

    picked = _pick_video(videos, 1080)

    assert picked.type == "m3u8"


@pytest.mark.asyncio
async def test_stream_download_lets_ffmpeg_pick_highest_quality(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: list[str] = []

    async def fake_run_ffmpeg(args: list[str]) -> None:
        captured.extend(args)

    monkeypatch.setattr(ffmpeg_tools, "run_ffmpeg", fake_run_ffmpeg)

    await ffmpeg_tools.download_stream_with_ffmpeg(
        "https://cdn.example/master.m3u8",
        tmp_path / "episode.mp4",
    )

    assert "-map" not in captured
    assert captured[captured.index("-i") + 1] == "https://cdn.example/master.m3u8"
    assert captured[captured.index("-c") + 1] == "copy"


@pytest.mark.skipif(os.name == "nt", reason="Windows does not use POSIX execute bits")
def test_bundled_ffmpeg_repairs_only_user_execute_bit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = tmp_path / "tools" / "ffmpeg"
    executable.parent.mkdir()
    executable.write_bytes(b"ffmpeg")
    executable.chmod(0o640)
    monkeypatch.setattr(ffmpeg_tools, "ROOT_DIR", tmp_path)

    assert ffmpeg_tools.ffmpeg_path() == str(executable)
    assert executable.stat().st_mode & stat.S_IXUSR
    assert stat.S_IMODE(executable.stat().st_mode) == 0o740


def test_ffmpeg_from_path_is_not_modified(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executable = tmp_path / "system-ffmpeg"
    executable.write_bytes(b"ffmpeg")
    executable.chmod(0o755)
    monkeypatch.setattr(ffmpeg_tools, "ROOT_DIR", tmp_path / "portable")
    monkeypatch.setattr(ffmpeg_tools.shutil, "which", lambda _name: str(executable))

    assert ffmpeg_tools.ffmpeg_path() == str(executable)
    assert stat.S_IMODE(executable.stat().st_mode) == 0o755


@pytest.mark.asyncio
async def test_ffmpeg_launch_error_includes_path_and_macos_helper(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = tmp_path / "tools" / "ffmpeg"
    executable.parent.mkdir()
    executable.write_bytes(b"ffmpeg")
    executable.chmod(0o755)
    monkeypatch.setattr(ffmpeg_tools, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(ffmpeg_tools.sys, "platform", "darwin")

    async def fail_to_start(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(ffmpeg_tools.asyncio, "create_subprocess_exec", fail_to_start)

    with pytest.raises(RuntimeError) as exc_info:
        await ffmpeg_tools.run_ffmpeg(["-version"])

    message = str(exc_info.value)
    assert str(executable) in message
    assert "Permission denied" in message
    assert "grant-macos-permissions.sh" in message


@pytest.mark.asyncio
async def test_ffmpeg_exit_error_includes_code_and_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProcess:
        returncode = 7

        async def communicate(self):
            return b"", b"broken dylib"

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return FakeProcess()

    monkeypatch.setattr(ffmpeg_tools, "ffmpeg_path", lambda: "/usr/local/bin/ffmpeg")
    monkeypatch.setattr(ffmpeg_tools.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(RuntimeError, match="exit code 7.*broken dylib"):
        await ffmpeg_tools.run_ffmpeg(["-version"])


@pytest.mark.asyncio
async def test_ffmpeg_process_is_terminated_when_download_is_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProcess:
        returncode: int | None = None
        terminated = False

        async def communicate(self):
            raise __import__("asyncio").CancelledError

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = -15

        async def wait(self) -> int:
            return self.returncode or 0

        def kill(self) -> None:
            self.returncode = -9

    process = FakeProcess()

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return process

    monkeypatch.setattr(ffmpeg_tools, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(ffmpeg_tools.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(__import__("asyncio").CancelledError):
        await ffmpeg_tools.run_ffmpeg(["-version"])

    assert process.terminated is True


def test_rewrite_m3u8_rewrites_segments_and_uri_attributes() -> None:
    playlist = """#EXTM3U
#EXT-X-KEY:METHOD=AES-128,URI="keys/key.bin"
#EXT-X-MAP:URI="init.mp4"
#EXTINF:5,
segment-1.ts
"""

    rewritten = _rewrite_m3u8(playlist, "https://cdn.example/show/master.m3u8", "headers-id")

    assert "URI=\"/api/proxy/stream?url=https%3A%2F%2Fcdn.example%2Fshow%2Fkeys%2Fkey.bin&hid=headers-id\"" in rewritten
    assert "URI=\"/api/proxy/stream?url=https%3A%2F%2Fcdn.example%2Fshow%2Finit.mp4&hid=headers-id\"" in rewritten
    assert "/api/proxy/stream?url=https%3A%2F%2Fcdn.example%2Fshow%2Fsegment-1.ts&hid=headers-id" in rewritten


@pytest.mark.asyncio
async def test_hls_download_uses_container_extension_for_ffmpeg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manager = DownloadManager()
    captured: dict[str, Path] = {}

    async def fake_download(url: str, dest: Path, headers: dict[str, str]) -> Path:
        captured["dest"] = dest
        dest.write_bytes(b"media")
        return dest

    async def fake_update(_job_id: int, **_fields) -> None:
        return None

    monkeypatch.setattr("backend.downloader.manager.ffmpeg_tools.download_hls_with_ffmpeg", fake_download)
    monkeypatch.setattr(manager, "_update", fake_update)

    final = tmp_path / "Episode 01.mp4"
    temporary = await manager._download_hls(1, "https://cdn.example/video.m3u8", final, {})

    assert temporary == final.with_name("Episode 01.part.mp4")
    assert captured["dest"].suffix == ".mp4"
