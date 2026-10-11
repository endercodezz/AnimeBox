"""Provider health derived from real operations and explicit diagnostics.

A provider is reported ``ok`` only when every pipeline stage (search, details,
episodes, voiceovers, stream) has most recently succeeded. Importability alone
proves nothing.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from backend.providers.errors import STAGES

logger = logging.getLogger("animebox.health")


@dataclass
class StageResult:
    ok: bool
    at: float
    latency_ms: int | None = None
    error: str | None = None


@dataclass
class SourceHealth:
    stages: dict[str, StageResult] = field(default_factory=dict)
    last_check_at: float | None = None

    @property
    def status(self) -> str:
        results = [self.stages.get(stage) for stage in STAGES]
        search = self.stages.get("search")
        if any(r is not None and not r.ok for r in results):
            return "down" if search is not None and not search.ok else "degraded"
        if all(r is not None and r.ok for r in results):
            return "ok"
        if any(r is not None for r in results):
            return "partial"
        return "unknown"


class HealthTracker:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._sources: dict[str, SourceHealth] = {}
        self._dirty_since: float | None = None
        self._load()

    def _load(self) -> None:
        if not self._path or not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            for source, data in raw.items():
                stages = {name: StageResult(**value) for name, value in data.get("stages", {}).items() if name in STAGES}
                self._sources[source] = SourceHealth(stages=stages, last_check_at=data.get("last_check_at"))
        except (OSError, ValueError, TypeError) as exc:
            logger.debug("Ignoring unreadable provider health file: %s", exc)

    def _save(self) -> None:
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                source: {
                    "stages": {name: asdict(result) for name, result in health.stages.items()},
                    "last_check_at": health.last_check_at,
                }
                for source, health in self._sources.items()
            }
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._path)
        except OSError as exc:
            logger.debug("Could not persist provider health: %s", exc)

    def record(self, source: str, stage: str, ok: bool, latency_ms: int | None = None, error: str | None = None) -> None:
        if stage not in STAGES:
            return
        with self._lock:
            health = self._sources.setdefault(source, SourceHealth())
            health.stages[stage] = StageResult(ok=ok, at=time.time(), latency_ms=latency_ms, error=(error or None) and error[:300])
            self._save()

    def mark_checked(self, source: str) -> None:
        with self._lock:
            self._sources.setdefault(source, SourceHealth()).last_check_at = time.time()
            self._save()

    def get(self, source: str) -> SourceHealth:
        with self._lock:
            return self._sources.get(source) or SourceHealth()
