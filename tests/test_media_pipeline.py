from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from backend.downloader.manager import DownloadManager
from backend.player.proxy import _rewrite_m3u8
from backend.providers.registry import _pick_video


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
