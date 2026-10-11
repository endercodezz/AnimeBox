"""Caches.

``SearchCache`` persists the minimal data needed to rebuild an anicli-api
``Search`` object for an id (URL + provider payload). ``TTLCache`` keeps
short-lived details, episode lists and player lists in memory so opening a
title, picking a voiceover and starting playback do not refetch the same pages.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar

logger = logging.getLogger("animebox.cache")

SEARCH_TTL = 30 * 24 * 3600
T = TypeVar("T")


@dataclass
class CachedSearch:
    source: str
    url: str
    title: str
    thumbnail: str
    payload: dict[str, Any]
    saved_at: float


class SearchCache:
    def __init__(self, directory: Path, ttl: float = SEARCH_TTL, max_memory: int = 2000) -> None:
        self.directory = directory
        self.ttl = ttl
        self._mem: OrderedDict[str, CachedSearch] = OrderedDict()
        self._max_memory = max_memory

    def _path(self, external_id: str) -> Path:
        safe = re.sub(r"[^\w.-]+", "_", external_id)[:120]
        digest = hashlib.sha1(external_id.encode("utf-8")).hexdigest()[:10]
        return self.directory / f"{safe}-{digest}.json"

    def _legacy_path(self, external_id: str) -> Path:
        return self.directory / f"{re.sub(r'[^\w.-]+', '_', external_id)[:180]}.json"

    def put(self, external_id: str, entry: CachedSearch) -> None:
        self._mem[external_id] = entry
        self._mem.move_to_end(external_id)
        while len(self._mem) > self._max_memory:
            self._mem.popitem(last=False)
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self._path(external_id).write_text(json.dumps(asdict(entry), ensure_ascii=False), encoding="utf-8")
        except (OSError, TypeError, ValueError) as exc:
            logger.debug("Failed to persist search cache: %s", exc)

    def get(self, external_id: str) -> CachedSearch | None:
        now = time.time()
        entry = self._mem.get(external_id)
        if entry and now - entry.saved_at <= self.ttl:
            return entry
        for path in (self._path(external_id), self._legacy_path(external_id)):
            if not path.is_file():
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                entry = CachedSearch(
                    source=raw["source"],
                    url=raw["url"],
                    title=raw["title"],
                    thumbnail=raw.get("thumbnail") or "",
                    payload=raw.get("payload") or {},
                    saved_at=float(raw.get("saved_at") or 0),
                )
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if now - entry.saved_at > self.ttl:
                return None
            self._mem[external_id] = entry
            return entry
        return None

    def invalidate(self, external_id: str) -> None:
        self._mem.pop(external_id, None)
        for path in (self._path(external_id), self._legacy_path(external_id)):
            path.unlink(missing_ok=True)


class TTLCache(Generic[T]):
    def __init__(self, ttl: float, max_items: int = 256) -> None:
        self.ttl = ttl
        self.max_items = max_items
        self._items: OrderedDict[Any, tuple[float, T]] = OrderedDict()

    def get(self, key: Any) -> T | None:
        item = self._items.get(key)
        if item is None:
            return None
        saved_at, value = item
        if time.monotonic() - saved_at > self.ttl:
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return value

    def set(self, key: Any, value: T) -> None:
        self._items[key] = (time.monotonic(), value)
        self._items.move_to_end(key)
        while len(self._items) > self.max_items:
            self._items.popitem(last=False)

    def pop(self, key: Any) -> None:
        self._items.pop(key, None)

    def clear(self) -> None:
        self._items.clear()
