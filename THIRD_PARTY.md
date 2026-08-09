# Third-party software

AnimeBox uses and is inspired by the following open-source projects.
Attribution notices are preserved where code patterns or libraries are reused.
Reference repositories live in local `.references/` checkouts and are excluded from AnimeBox release archives.

## anicli-api

- **Repository:** https://github.com/vypivshiy/anicli-api
- **Author:** vypivshiy
- **License:** MIT
- **Used for:** Search, title metadata, episodes, voiceovers/sources, and stream URL extraction (AnimeGo, AniLiberty, AnimeVost, Yummy Anime, and other extractors). Installed as an editable dependency from `.references/anicli-api` and wrapped by `backend/providers/`.

## ani-cli-ru

- **Repository:** https://github.com/vypivshiy/ani-cli-ru
- **Author:** vypivshiy
- **License:** GPL-3.0
- **Used for:** Interaction flow ideas (search → episode → voiceover → play), voiceover preference ordering, and reverse-proxy implementation for browser playback (`backend/player/proxy.py`). HLS URL-rewriting logic is adapted under GPL-3.0 with attribution comments in source.

## Hakuneko

- **Repository:** https://github.com/manga-download/hakuneko
- **Organization:** manga-download / HakuNeko
- **License:** Unlicense (public domain dedication)
- **Used for:** Architecture ideas — connector registry, download job queue, settings persistence, and library folder layout. Inspiration only; no JavaScript connectors were ported.

## Sonarr

- **Repository:** https://github.com/Sonarr/Sonarr
- **Organization:** Sonarr / Servarr contributors
- **License:** GPL-3.0
- **Used for:** Architecture ideas for durable download queues, failed-download handling, media imports, naming, and library lifecycle. Inspiration only; no C# source files were copied.

## FFmpeg

- **Website:** https://ffmpeg.org/
- **Project:** FFmpeg contributors
- **License:** LGPL-2.1-or-later or GPL-2.0-or-later depending on build configuration
- **Used for:** HLS/DASH downloading, remuxing, and optional Steam Deck transcoding. Windows archives bundle builds from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/), Linux and Steam Deck archives bundle GPL builds from [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds), and macOS archives bundle Homebrew builds.

## PyInstaller

- **Repository:** https://github.com/pyinstaller/pyinstaller
- **Organization:** PyInstaller Development Team
- **License:** GPL-2.0-or-later with a special exception permitting distribution of bundled applications
- **Used for:** Packaging Python runtime and AnimeBox backend into native portable launchers.

---

When modifying vendor references under `.references/`, keep their original LICENSE files intact.
