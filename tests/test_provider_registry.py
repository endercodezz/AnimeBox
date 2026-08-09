from __future__ import annotations

import asyncio

import pytest

from backend.config import Settings
from backend.providers.registry import ProviderRegistry
from backend.schemas import SearchResult


@pytest.mark.asyncio
async def test_search_returns_fast_results_and_cancels_timed_out_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    settings = Settings(
        _env_file=None,
        library_path=tmp_path / "library",
        database_url="sqlite+aiosqlite:///:memory:",
        provider_search_timeout=0.02,
    )
    registry = ProviderRegistry(settings)
    cancelled = asyncio.Event()

    async def fake_search_one(source: str, _query: str) -> list[SearchResult]:
        if source == "blocked":
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
        return [
            SearchResult(
                id=f"{source}:result",
                title="K-On!",
                source=source,
            )
        ]

    monkeypatch.setattr(registry, "_search_one", fake_search_one)

    results = await asyncio.wait_for(
        registry.search("k-on", sources=["fast", "blocked"]),
        timeout=0.2,
    )

    assert [(item.source, item.title) for item in results] == [("fast", "K-On!")]
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_search_keeps_results_when_another_provider_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    settings = Settings(
        _env_file=None,
        library_path=tmp_path / "library",
        database_url="sqlite+aiosqlite:///:memory:",
    )
    registry = ProviderRegistry(settings)

    async def fake_search_one(source: str, _query: str) -> list[SearchResult]:
        if source == "broken":
            raise RuntimeError("provider unavailable")
        return [SearchResult(id=f"{source}:result", title="K-On!", source=source)]

    monkeypatch.setattr(registry, "_search_one", fake_search_one)

    results = await registry.search("k-on", sources=["fast", "broken"])

    assert [(item.source, item.title) for item in results] == [("fast", "K-On!")]
