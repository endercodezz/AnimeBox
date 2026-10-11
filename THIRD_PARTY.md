# Third-party software

AnimeBox uses and is inspired by the following open-source projects. Attribution notices are preserved in source
comments where code is adapted. Reference repositories live in local `.references/` checkouts, are not committed, and
are not included in release archives (except the installed `anicli-api` package itself).

## anicli-api

- **Repository:** https://github.com/vypivshiy/anicli-api
- **Author:** vypivshiy
- **License:** MIT
- **Used for:** search, title metadata, episodes, voiceovers/sources and stream extraction (AnimeGO, AniLiberty,
  AnimeVost, Yummy Anime, and other extractors). Installed from a pinned commit (`patches/anicli-api.ref`) with a small
  tracked compatibility patch (`patches/`), and wrapped by `backend/providers/`.
- **Adapted code:** `backend/providers/players.py` contains an adapter derived from anicli-api's `CdnVideoHub`
  decoder (for AnimeGO's current CVH iframe URLs) and an awaited variant of the Yummy Anime CVH flow. Both are marked
  with attribution comments. The anicli-api package is bundled into portable builds under its MIT license.

## ani-cli-ru

- **Repository:** https://github.com/vypivshiy/ani-cli-ru
- **Author:** vypivshiy
- **License:** GPL-3.0
- **Used for:** interaction-flow ideas (search → episode → voiceover → play), voiceover preference ordering, and the
  approach of routing HLS playlist entries through a local reverse proxy. AnimeBox 1.x adapted ani-cli-ru's HLS
  rewriting code; AnimeBox 2.0 replaced it with its own implementation (`backend/player/proxy.py`,
  `backend/player/sessions.py`) based on server-issued session tokens. No ani-cli-ru source code is included in 2.0.

## HakuNeko

- **Repository:** https://github.com/manga-download/hakuneko
- **Organization:** manga-download / HakuNeko
- **License:** Unlicense (public domain dedication)
- **Used for:** architecture ideas — connector registry, download job queue, settings persistence and library folder
  layout. Inspiration only; no JavaScript connectors were ported.

## Sonarr

- **Repository:** https://github.com/Sonarr/Sonarr
- **Organization:** Sonarr / Servarr contributors
- **License:** GPL-3.0
- **Used for:** architecture ideas for durable download queues, failed-download handling, validation before import,
  naming and library lifecycle. Inspiration only; no C# source files were copied.

## FFmpeg

- **Website:** https://ffmpeg.org/
- **Project:** FFmpeg contributors
- **License:** LGPL-2.1-or-later or GPL-2.0-or-later depending on build configuration (bundled builds are GPL)
- **Used for:** HLS/DASH downloading, remuxing, validation and optional Steam Deck transcoding. Windows and
  Linux/Steam Deck archives bundle unmodified GPL builds from [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds)
  (which publishes sources and build scripts); macOS archives bundle Homebrew FFmpeg with its relocated dynamic
  libraries. Each archive contains `tools/FFMPEG-NOTICE.txt` and, where the upstream package provides it, the FFmpeg
  license file. FFmpeg runs as a separate program; AnimeBox does not link against it.

## PyInstaller

- **Repository:** https://github.com/pyinstaller/pyinstaller
- **License:** GPL-2.0-or-later with a bootloader exception permitting distribution of bundled applications
- **Used for:** packaging the Python runtime and backend into portable launchers.

## Frontend libraries (bundled into the web UI)

| Project | License | Used for |
|---|---|---|
| [React](https://github.com/facebook/react), [React Router](https://github.com/remix-run/react-router) | MIT | UI framework and routing |
| [hls.js](https://github.com/video-dev/hls.js) | Apache-2.0 | HLS playback in the browser |
| [Tailwind CSS](https://github.com/tailwindlabs/tailwindcss) | MIT | Styling (build-time) |
| [Unbounded](https://github.com/googlefonts/unbounded) via [Fontsource](https://fontsource.org/) | SIL Open Font License 1.1 | Display typeface |
| [Manrope](https://github.com/sharanda/manrope) via [Fontsource](https://fontsource.org/) | SIL Open Font License 1.1 | Body typeface |

## Python libraries (bundled into portable builds)

FastAPI, Pydantic, SQLAlchemy, aiosqlite, h2, attrs (MIT); Starlette, Uvicorn, httpx, httpcore (BSD-3-Clause). Their license files ship inside the bundled package metadata.

---

When modifying vendor references under `.references/`, keep their original LICENSE files intact and put AnimeBox
changes in tracked patches under `patches/`.
