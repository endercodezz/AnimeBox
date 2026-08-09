"""App settings persisted in SQLite (Hakuneko-style descriptor values)."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models import AppSetting
from backend.schemas import AppSettingsOut, AppSettingsUpdate

DEFAULTS = {
    "preferred_voiceovers": None,  # filled from env
    "default_quality": None,
    "steam_deck_optimize": False,
    "steam_deck_crf": None,
    "steam_deck_height": None,
    "default_source": "animego",
    "http_proxy": None,
}


async def _get_raw(db: AsyncSession) -> dict:
    rows = (await db.execute(select(AppSetting))).scalars().all()
    raw: dict = {}
    for row in rows:
        try:
            raw[row.key] = json.loads(row.value)
        except Exception:
            raw[row.key] = row.value
    return raw


async def get_app_settings(db: AsyncSession) -> AppSettingsOut:
    cfg = get_settings()
    raw = await _get_raw(db)
    return AppSettingsOut(
        preferred_voiceovers=raw.get("preferred_voiceovers") or cfg.preferred_voiceover_list,
        default_quality=int(raw.get("default_quality") or cfg.default_quality),
        steam_deck_optimize=bool(raw.get("steam_deck_optimize", False)),
        steam_deck_crf=int(raw.get("steam_deck_crf") or cfg.steam_deck_crf),
        steam_deck_height=int(raw.get("steam_deck_height") or cfg.steam_deck_height),
        default_source=str(raw.get("default_source") or "animego"),
        http_proxy=raw.get("http_proxy") if raw.get("http_proxy") is not None else cfg.http_proxy,
    )


async def update_app_settings(db: AsyncSession, patch: AppSettingsUpdate) -> AppSettingsOut:
    current = await get_app_settings(db)
    data = current.model_dump()
    for key, value in patch.model_dump(exclude_unset=True).items():
        data[key] = value
        row = await db.get(AppSetting, key)
        encoded = json.dumps(value)
        if row is None:
            db.add(AppSetting(key=key, value=encoded))
        else:
            row.value = encoded
    await db.commit()

    # Hot-apply proxy / preferences into runtime settings object
    cfg = get_settings()
    if patch.preferred_voiceovers is not None:
        cfg.preferred_voiceovers = ",".join(patch.preferred_voiceovers)
    if patch.default_quality is not None:
        cfg.default_quality = patch.default_quality
    if patch.http_proxy is not None:
        cfg.http_proxy = patch.http_proxy or None
    if patch.steam_deck_crf is not None:
        cfg.steam_deck_crf = patch.steam_deck_crf
    if patch.steam_deck_height is not None:
        cfg.steam_deck_height = patch.steam_deck_height

    return await get_app_settings(db)
