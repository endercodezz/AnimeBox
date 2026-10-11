"""App settings persisted in SQLite (HakuNeko-style key/value settings).

``.env`` provides defaults; values saved from the UI override them and are
applied to the running process immediately.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models import AppSetting
from backend.providers.catalog import DEFAULT_SOURCE, SOURCE_BY_ID, default_enabled_sources
from backend.schemas import QUALITIES, AppSettingsOut, AppSettingsUpdate, dedupe_casefold

logger = logging.getLogger("animebox.settings")


async def _get_raw(db: AsyncSession) -> dict:
    raw: dict = {}
    for row in (await db.execute(select(AppSetting))).scalars().all():
        try:
            raw[row.key] = json.loads(row.value)
        except ValueError:
            raw[row.key] = row.value
    return raw


def _int(value, fallback: int, lo: int, hi: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return number if lo <= number <= hi else fallback


async def get_app_settings(db: AsyncSession) -> AppSettingsOut:
    cfg = get_settings()
    raw = await _get_raw(db)
    voiceovers = raw.get("preferred_voiceovers")
    if not isinstance(voiceovers, list):
        voiceovers = cfg.preferred_voiceover_list
    enabled = raw.get("enabled_sources")
    if not isinstance(enabled, list):
        enabled = default_enabled_sources()
    enabled = [s for s in enabled if s in SOURCE_BY_ID] or [DEFAULT_SOURCE]
    default_source = raw.get("default_source")
    if default_source not in SOURCE_BY_ID:
        default_source = DEFAULT_SOURCE
    quality = _int(raw.get("default_quality"), cfg.default_quality, 144, 4320)
    proxy = raw.get("http_proxy") if "http_proxy" in raw else cfg.http_proxy
    return AppSettingsOut(
        preferred_voiceovers=dedupe_casefold([str(v).strip() for v in voiceovers if str(v).strip()]),
        default_quality=quality if quality in QUALITIES else 1080,
        steam_deck_optimize=bool(raw.get("steam_deck_optimize", False)),
        steam_deck_crf=_int(raw.get("steam_deck_crf"), cfg.steam_deck_crf, 0, 51),
        steam_deck_height=_int(raw.get("steam_deck_height"), cfg.steam_deck_height, 240, 2160),
        default_source=default_source,
        enabled_sources=enabled,
        http_proxy=proxy or None,
        max_concurrent_downloads=_int(raw.get("max_concurrent_downloads"), cfg.max_concurrent_downloads, 1, 6),
        autoplay_next=bool(raw.get("autoplay_next", True)),
        remember_volume=bool(raw.get("remember_volume", True)),
    )


async def apply_runtime(settings: AppSettingsOut, *, network_changed: bool = False) -> None:
    """Push effective settings into the running process."""
    from backend.downloader.manager import download_manager
    from backend.providers import get_registry

    cfg = get_settings()
    cfg.preferred_voiceovers = ",".join(settings.preferred_voiceovers)
    cfg.default_quality = settings.default_quality
    cfg.http_proxy = settings.http_proxy or None
    cfg.steam_deck_crf = settings.steam_deck_crf
    cfg.steam_deck_height = settings.steam_deck_height
    cfg.max_concurrent_downloads = settings.max_concurrent_downloads
    registry = get_registry()
    registry.configure(enabled_sources=settings.enabled_sources, default_source=settings.default_source)
    if network_changed:
        await registry.apply_network_settings()
    download_manager.set_concurrency(settings.max_concurrent_downloads)


async def update_app_settings(db: AsyncSession, patch: AppSettingsUpdate) -> AppSettingsOut:
    before = await get_app_settings(db)
    changes = patch.model_dump(exclude_unset=True)
    if "enabled_sources" in changes and changes["enabled_sources"] is not None:
        unknown = [s for s in changes["enabled_sources"] if s not in SOURCE_BY_ID]
        if unknown:
            raise ValueError(f"Unknown sources: {', '.join(unknown)}")
        if not changes["enabled_sources"]:
            raise ValueError("Enable at least one source")
    if changes.get("default_source") is not None and changes["default_source"] not in SOURCE_BY_ID:
        raise ValueError(f"Unknown source: {changes['default_source']}")
    for key, value in changes.items():
        if value is None and key != "http_proxy":
            continue
        if key == "http_proxy":
            value = value or None
        row = await db.get(AppSetting, key)
        encoded = json.dumps(value)
        if row is None:
            db.add(AppSetting(key=key, value=encoded))
        else:
            row.value = encoded
    await db.commit()
    after = await get_app_settings(db)
    await apply_runtime(after, network_changed=(before.http_proxy or None) != (after.http_proxy or None))
    return after
