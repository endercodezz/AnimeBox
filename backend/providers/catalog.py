"""Supported sources and their maturity.

Only sources listed here are exposed. A new anicli-api module is not shown to
users until it is added and verified, so an upstream update cannot silently add
a broken provider to the UI.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpec:
    id: str
    label: str
    module: str
    stable: bool
    enabled_by_default: bool
    check_query: str
    note: str = ""


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        id="animego",
        label="AnimeGO",
        module="animego",
        stable=True,
        enabled_by_default=True,
        check_query="Врата Штейна",
        note="Рекомендуется. У каждой озвучки несколько плееров (Kodik, Aniboom, CVH) — при сбое AnimeBox переключается на следующий.",
    ),
    SourceSpec(
        id="anilibria",
        label="AniLiberty",
        module="anilibria",
        stable=False,
        enabled_by_default=True,
        check_query="Steins",
        note="API AniLibria/AniLiberty. Только собственная озвучка.",
    ),
    SourceSpec(
        id="animevost",
        label="AnimeVost",
        module="animevost",
        stable=False,
        enabled_by_default=True,
        check_query="Врата Штейна",
        note="API AnimeVost. Только собственная озвучка, прямые MP4-файлы (поддерживают паузу загрузки).",
    ),
    SourceSpec(
        id="yummy_anime",
        label="Yummy Anime",
        module="yummy_anime",
        stable=False,
        enabled_by_default=True,
        check_query="Врата Штейна",
        note="Часть плееров отдаёт только DASH: такие серии можно скачать, но не смотреть в браузере.",
    ),
    SourceSpec(
        id="anilibme",
        label="AniLib",
        module="anilibme",
        stable=False,
        enabled_by_default=False,
        check_query="Steins",
        note="Часто медленный или пустой вне своего региона.",
    ),
    SourceSpec(
        id="dreamcast",
        label="DreamCast",
        module="dreamcast",
        stable=False,
        enabled_by_default=False,
        check_query="Врата Штейна",
        note="Небольшой каталог.",
    ),
    SourceSpec(
        id="sameband",
        label="SameBand",
        module="sameband",
        stable=False,
        enabled_by_default=False,
        check_query="Врата Штейна",
        note="Небольшой каталог.",
    ),
)

# Not exposed: hdrezka (relies on an anti-bot User-Agent workaround; not anime-focused).
EXCLUDED_MODULES = frozenset({"hdrezka"})

SOURCE_BY_ID: dict[str, SourceSpec] = {spec.id: spec for spec in SOURCES}
DEFAULT_SOURCE = "animego"


def default_enabled_sources() -> list[str]:
    return [spec.id for spec in SOURCES if spec.enabled_by_default]
