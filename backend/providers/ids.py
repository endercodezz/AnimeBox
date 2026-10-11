"""Stable external identifiers: ``<source>:<url-quoted provider key>``.

1.x clients sometimes sent the same title as ``animego:%2Fanime%2Fx`` and
``animego:/anime/x`` (route params were decoded twice). Every id entering the
backend is passed through :func:`canonical_id` so both spellings map to one
record.
"""

from __future__ import annotations

import re
from urllib.parse import quote, unquote

_SOURCE_RE = re.compile(r"^[a-z0-9_\-]{1,64}$")


def encode_external_id(source: str, key: str) -> str:
    return f"{source}:{quote(key, safe='')}"


def decode_external_id(external_id: str) -> tuple[str, str]:
    source, _, rest = (external_id or "").partition(":")
    if not source or not rest or not _SOURCE_RE.match(source):
        raise ValueError(f"Invalid anime id: {external_id!r}")
    return source, unquote(rest)


def canonical_id(external_id: str) -> str:
    source, key = decode_external_id(external_id)
    return encode_external_id(source, key)


def safe_canonical_id(external_id: str) -> str:
    """Canonical form, or the input unchanged when it is not a provider id (e.g. ``local:...``)."""
    try:
        return canonical_id(external_id)
    except ValueError:
        return external_id
