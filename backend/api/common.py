from __future__ import annotations

import logging
from typing import NoReturn

from fastapi import HTTPException

from backend.providers.errors import ProviderError
from backend.providers.ids import canonical_id, safe_canonical_id

logger = logging.getLogger("animebox.api")


def anime_id_param(value: str) -> str:
    """Canonical provider id or HTTP 400."""
    try:
        return canonical_id(value)
    except ValueError as exc:
        raise HTTPException(400, {"code": "invalid_id", "message": str(exc)}) from exc


def library_id_param(value: str) -> str:
    return safe_canonical_id(value)


def provider_failure(exc: Exception, action: str) -> NoReturn:
    if isinstance(exc, ProviderError):
        raise HTTPException(exc.http_status, exc.to_detail()) from exc
    logger.exception("%s failed", action)
    raise HTTPException(502, {"code": "internal_error", "message": f"{action} failed: {type(exc).__name__}"}) from exc
