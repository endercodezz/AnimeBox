# AnimeBox

**English** | [Русский](README.ru.md)

A local anime library for Russian-language anime sites. Search, pick a voiceover, watch in the browser, or download
episodes and watch them later without internet. AnimeBox runs on your computer, stores episodes as regular files, and
needs no account or cloud service.

> Source websites change without notice. AnimeGO is the recommended and best-tested source; others are marked
> experimental. AnimeBox shows each source's real status in **Settings → Sources**.

## Features

| | |
|---|---|
| Search | Several sources in parallel; a slow or broken source never blocks the others, and each source's result is shown |
| Title page | Description, episodes, voiceovers with their players, progress and offline status per episode |
| Watching | Built-in player with progress saving/restore, keyboard shortcuts, quality, speed, voiceover switching, audio tracks and subtitles when the stream provides them, automatic next episode |
| Reliability | If one player of a voiceover fails (e.g. CVH), the next one is tried (Kodik, Aniboom, …); expired streams are re-resolved without losing your position |
| Downloads | Episode or whole season, parallel queue, real progress and speed, retries, cancel; pause/resume for direct MP4 files |
| Library | Only episodes that really exist on disk; storage usage, sorting, filtering, deletion, rescan |
| Offline | Downloaded episodes, posters and progress work without internet, even when the source is down |
| Steam Deck | Linux build runs on SteamOS; optional H.265 transcoding to save space |

### Sources

| Source | Status | Notes |
|---|---|---|
| AnimeGO | **Stable**, default | Many voiceovers; several players per voiceover with automatic fallback |
| AniLiberty (AniLibria) | Experimental | Own voiceover only |
| AnimeVost | Experimental | Own voiceover only; direct MP4 (downloads can be paused) |
| Yummy Anime | Experimental | Some players are DASH-only: downloadable, not playable in the browser |
| AniLib, DreamCast, SameBand | Experimental, off by default | Small or region-dependent catalogs |

HDRezka is not offered: its extractor relies on working around an anti-bot check. AnimeBox does not bypass CAPTCHAs
or other access restrictions.

## Install (portable, recommended)

Download the archive for your system from [GitHub Releases](https://github.com/endercodezz/AnimeBox/releases).
Python, Node.js and FFmpeg are bundled — nothing else to install.

| Archive | Run |
|---|---|
| `AnimeBox-<version>-Windows-x64.zip` | Extract, open `AnimeBox.exe` |
| `AnimeBox-<version>-Linux-x64.tar.gz` | Linux x86_64 and Steam Deck: extract, then `./AnimeBox` |
| `AnimeBox-<version>-macOS-x64.zip` | Intel Mac: extract, open `AnimeBox` |
| `AnimeBox-<version>-macOS-arm64.zip` | Apple Silicon: extract, open `AnimeBox` |

AnimeBox starts a private server on `http://127.0.0.1:8787` and opens your browser. Closing the tab does not stop it —
use **Stop** in the sidebar so active downloads are not interrupted by accident.

Verify a download with the published checksums: `sha256sum -c SHA256SUMS.txt --ignore-missing`.

**macOS:** unsigned builds may need **Control-click → Open** on first launch. If downloads report `ffmpeg failed`, run
`bash scripts/grant-macos-permissions.sh` in the AnimeBox folder (add `--clear-quarantine` only for archives from a
source you trust).

## Upgrading from 1.x

Your data lives in three places; nothing else needs to be kept:

- `.env` — settings (1.x files work unchanged),
- `data/` — database (history, progress, download history, settings),
- `library/` — downloaded episodes and posters.

**Portable:** extract the new version, then copy those three items from the old folder into the new one (replace the
empty ones). **From source:** `git pull`, then run the install script again.

On the first start AnimeBox 2.0:

1. copies the database to `data/backups/animebox-v0-<date>.db`;
2. merges duplicate entries created by the 1.x id bug, keeping the best progress;
3. converts stored paths to library-relative ones;
4. stops counting merely-browsed titles as library content (no files are deleted);
5. removes empty folders and abandoned `*.part.*` files left in `library/` by 1.x.

If anything goes wrong, the migration is rolled back and the backup stays in `data/backups/`. Files referenced by the
database but missing on disk are hidden from the library; **Library → Rescan** removes those records and picks up
episodes that AnimeBox downloaded earlier but no longer tracks.

## Run from source

Requires Python 3.12+, Node.js 20+, Git, and FFmpeg in `PATH`. Docker is not used. The install script fetches a pinned,
tested commit of [anicli-api](https://github.com/vypivshiy/anicli-api) into `.references/anicli-api` and applies the
compatibility patch from `patches/`.

```powershell
# Windows
git clone https://github.com/endercodezz/AnimeBox.git
cd AnimeBox
.\scripts\install.ps1
.\scripts\run.ps1
```

```bash
# macOS / Linux / Steam Deck
git clone https://github.com/endercodezz/AnimeBox.git
cd AnimeBox
./scripts/install.sh
./scripts/run.sh
```

`scripts\install.cmd`, `scripts\run.cmd` and `scripts\check.cmd` allow double-click launch on Windows.
Development mode with hot reload: `run.ps1 -Dev` / `run.sh --dev` (UI on `http://127.0.0.1:5173`, API docs on
`http://127.0.0.1:8787/docs`).

## Configuration

`.env` is created from `.env.example` on first run and never overwritten. Most options are also in **Settings**
(UI values take precedence). Notable options:

| Option | Meaning |
|---|---|
| `LIBRARY_PATH`, `DATA_PATH` | Where episodes and the database live (relative to the AnimeBox folder) |
| `HTTP_PROXY` | HTTP or SOCKS proxy used for search, playback **and** downloads |
| `PROVIDER_SEARCH_TIMEOUT`, `PROVIDER_DETAIL_TIMEOUT`, `PROVIDER_STREAM_TIMEOUT` | Per-stage time limits per source |
| `PREFERRED_VOICEOVERS` | Voiceover priority for automatic selection |
| `DEFAULT_QUALITY` | 360, 480, 720 or 1080 — closest available quality not above it |
| `MAX_CONCURRENT_DOWNLOADS` | Parallel downloads (1–6) |
| `ALLOWED_HOSTS` | Extra host names accepted besides `127.0.0.1`/`localhost` |

## Keyboard shortcuts (player)

| Key | Action |
|---|---|
| Space / K | Play / pause |
| ← / → | −5 s / +5 s |
| J / L | −10 s / +10 s |
| ↑ / ↓ | Volume |
| M | Mute |
| F | Fullscreen |
| Shift+N / Shift+P | Next / previous episode |
| < / > | Slower / faster |
| 0–9 | Jump to 0–90 % |
| / or Ctrl+K | Focus search (outside the player) |

## Data layout

```text
library/
└── Anime Name/
    ├── poster.jpg
    ├── metadata.json          # includes the AnimeBox id, used by Rescan
    └── Season 1/
        ├── Episode 01.mp4
        └── Episode 02.mp4
data/
├── animebox.db                # SQLite (history, progress, queue, settings)
├── backups/                   # automatic backups before schema upgrades
├── provider_health.json
└── search_cache/
```

## Architecture

```text
backend/
├── api/          # FastAPI routers: catalog, downloads, library, history, system
├── providers/    # provider engine over anicli-api: registry, players, health, cache, HTTP sessions
├── player/       # media sessions + HLS-rewriting media proxy
├── downloader/   # durable queue, concurrency, validation, atomic finalisation
├── services/     # library files/index, settings, ffmpeg
├── database/     # async SQLAlchemy + versioned migrations
├── models/  schemas/
frontend/src/
├── api/  lib/  components/  pages/  pages/player/
```

Backend: Python, FastAPI, async SQLAlchemy, SQLite, Pydantic, httpx. Frontend: React, TypeScript, Tailwind CSS, Vite,
hls.js.

## Development checks

```bash
python -m pytest -q             # backend (use the .venv interpreter)
cd frontend && npm run check    # type-check, lint, unit tests
npm run build
```

Manual tests against real sources: [docs/TESTING.md](docs/TESTING.md). Releases: [docs/RELEASING.md](docs/RELEASING.md).

## Troubleshooting

**A stream does not open.** The player tries every player of the chosen voiceover and shows which ones failed. Pick
another voiceover, or check **Settings → Sources → Check** to see which stage fails (search, title, episodes,
voiceovers, stream).

**A source shows "not responding".** The site may be unreachable from your network or may have changed. Results from
other sources are still shown. If a source works only through a proxy, set it in **Settings → Network** — it is then
used for search, playback and downloads alike (some video hosts tie links to your IP address).

**"Title data is outdated".** The source no longer recognises the stored link; search for the title again.

**Downloads fail with an ffmpeg error.** From source: install FFmpeg and check `ffmpeg -version`. Portable builds
include FFmpeg; **Settings → Diagnostics** shows which binary is used.

**The library shows fewer episodes than before.** Episodes whose files were deleted or moved are hidden. Use
**Library → Rescan**.

**Logs.** Portable builds write `data/animebox.log`; from source, logs go to the terminal. Proxy passwords and signed
link tokens are redacted.

## Legal notice

AnimeBox is a local client and does not host any media. Use it only with sources and content permitted by applicable
law and the sources' terms. You are responsible for the sources you choose and the files you save.

## Credits

AnimeBox uses and is inspired by:

- [anicli-api](https://github.com/vypivshiy/anicli-api) — search, titles, episodes, voiceovers and stream extraction;
- [ani-cli-ru](https://github.com/vypivshiy/ani-cli-ru) — interaction flow and the HLS reverse-proxy approach;
- [HakuNeko](https://github.com/manga-download/hakuneko) — connector registry and download manager architecture;
- [Sonarr](https://github.com/Sonarr/Sonarr) — durable queues, failed-download handling and library lifecycle ideas.

With gratitude to the authors of the original projects. Licenses and reuse details: [THIRD_PARTY.md](THIRD_PARTY.md).
