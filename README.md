# AnimeBox

**English** | [Русский](README.ru.md)

A local anime library for searching, watching, and traveling without internet access. AnimeBox runs on your computer, stores episodes as regular files, and requires no account or cloud service.

> **Status:** early MVP. Many bugs remain, and active development is ongoing. Source websites can change without notice, so individual providers may temporarily stop working.

## Features

| Feature | Status |
|---|---|
| Search across multiple sources | ✅ |
| Title details, episodes, and voiceovers | ✅ |
| Online HLS playback through a local proxy | ✅ |
| Episode or season downloads | 🟨 |
| Download queue, progress, cancellation, and retry | ✅ |
| Local library and offline player | ✅ |
| Saved watch progress | ✅ |
| Steam Deck optimization | ✅ |

## Interface

AnimeBox uses a dark cinematic interface with a violet accent. After launch, open `http://127.0.0.1:8787`. On a title page, choose a **Season voiceover**; it applies to playback and downloads for every episode. You can still open a specific episode's voiceover list and set an override for that episode. **Auto-select** follows the voiceover priority from Settings and uses the first available option when no preferred voiceover is present.

> **Download recommendation:** the author recommends choosing **AnimeGO** whenever it is available because it currently works best and provides the most stable downloads.

The **Shut down** button in the header stops the local server cleanly and releases port `8787`. Closing the browser tab alone does not stop the server, protecting active downloads from accidental interruption.

## How the portable build works

The archive does not contain two separate applications. `AnimeBox.exe`/`AnimeBox` is one Python launcher with a FastAPI backend and embedded static files from the prebuilt React/TypeScript frontend. Node.js is not included in the archive and does not run on the user's device; the browser receives regular HTML/CSS/JavaScript files from the local backend.

The `.references/` directory contains local checkouts of upstream open-source projects and is not committed to Git. Installation scripts and CI clone `anicli-api`, then apply the tracked compatibility patch from `patches/`. Required compatibility changes therefore do not remain hidden inside a fully ignored checkout.

## Portable releases

For most users, the recommended option is to download the archive for their platform from GitHub Releases. Python, Node.js, Git, and a system FFmpeg installation are not required: the Python runtime, backend, compiled frontend, `anicli-api`, and FFmpeg are included.

AnimeBox remains a web application: the launcher starts a private server at `http://127.0.0.1:8787` and opens the system browser. No separate desktop interface is installed.

| Archive | How to run |
|---|---|
| `AnimeBox-Windows-x64.zip` | extract the archive and open `AnimeBox.exe` |
| `AnimeBox-Linux-x64.tar.gz` | Linux x86_64, including Steam Deck/SteamOS; extract, then run `chmod +x AnimeBox && ./AnimeBox` |
| `AnimeBox-macOS-x64.zip` | Intel Mac; extract and open the launcher |
| `AnimeBox-macOS-arm64.zip` | Apple Silicon; extract and open the launcher |

The portable folder already contains a base `.env`, `data/`, `library/`, bundled FFmpeg, and all runtime dependencies. Windows and Linux/Steam Deck archives use GPL FFmpeg builds from BtbN; macOS archives use Homebrew builds. Internet access is required only for search, fetching new streams, and downloads. The downloaded library, local posters, MP4 files, and watch progress work offline; no external web fonts are used.

When updating, preserve and move these items into the new portable folder:

- `.env` — settings;
- `data/` — database, history, and progress;
- `library/` — downloaded episodes and posters.

An unsigned macOS build may require **Control-click → Open** on first launch. Fully extract the portable archive before running AnimeBox.

## Quick start from source

Running from source requires Python 3.12+, Node.js 20+ with npm, Git, and FFmpeg in `PATH`. Docker is not required. The installation script downloads the official `anicli-api` repository (MIT) into `.references/anicli-api`; the other reference projects are needed only for development.

### Windows 11

```powershell
git clone https://github.com/endercodezz/AnimeBox.git
cd AnimeBox
.\scripts\install.ps1
.\scripts\run.ps1
```

Double-click launch is also available: run `scripts\install.cmd`, then `scripts\run.cmd`. For diagnostics, use `scripts\check.cmd`.

The first `install` or `run` creates a base `.env` from `.env.example`. An existing `.env` is never overwritten.

### macOS / Linux / Steam Deck

```bash
git clone https://github.com/endercodezz/AnimeBox.git
cd AnimeBox
chmod +x scripts/*.sh
./scripts/install.sh
./scripts/run.sh
```

### Development mode

```powershell
# Windows
.\scripts\run.ps1 -Dev
```

```bash
# macOS / Linux
./scripts/run.sh --dev
```

- Production UI + API: `http://127.0.0.1:8787`
- Vite UI in development mode: `http://127.0.0.1:5173`
- OpenAPI: `http://127.0.0.1:8787/docs`

`run` builds the frontend, starts the API, waits for a successful health check, and only then opens the browser. Use `--skip-build` / `-SkipBuild` to keep the existing frontend build and `--no-browser` / `-NoBrowser` to avoid opening the browser.

Check the installation without starting a download:

```powershell
.\scripts\check.ps1
```

```bash
./scripts/check.sh
```

## Configuration

On first launch, `.env.example` is copied to `.env`. Main options:

- `LIBRARY_PATH` — downloaded episode directory;
- `DATABASE_URL` — SQLite URL;
- `HTTP_PROXY` — optional HTTP/SOCKS proxy for restricted sources;
- `PROVIDER_SEARCH_TIMEOUT` — maximum wait for each search provider, `10` seconds by default; slow or blocked providers are skipped while results from available providers are returned;
- `PREFERRED_VOICEOVERS` — comma-separated voiceover priority for automatic selection;
- `DEFAULT_QUALITY` — preferred quality;
- `STEAM_DECK_CRF`, `STEAM_DECK_HEIGHT` — transcoding settings.

Most user-facing options are also available on the **Settings** page.

## Data storage

```text
library/
└── Anime Name/
    ├── poster.jpg
    ├── metadata.json
    └── Season 1/
        ├── Episode 01.mp4
        └── Episode 02.mp4

data/
├── animebox.db
└── search_cache/
```

`library/`, the database, cache, and `.env` are excluded from Git.

## Architecture

```text
backend/
├── api/          # FastAPI endpoints
├── providers/    # adapters over anicli-api
├── downloader/   # durable SQLite queue and ffmpeg downloads
├── player/       # HLS/media reverse proxy
├── services/     # library, settings, ffmpeg helpers
├── database/     # async SQLAlchemy + SQLite
├── models/       # persistence models
└── schemas/      # Pydantic API contracts

frontend/src/
├── api/          # typed API client
├── components/   # shared UI
└── pages/        # search, library, anime, player, downloads, settings
```

Backend: Python, FastAPI, async SQLAlchemy, SQLite, Pydantic, and httpx. Frontend: React, TypeScript, Tailwind CSS, Vite, and hls.js.

## Verification

```bash
# Backend
.venv/Scripts/python.exe -m pytest -q          # Windows
.venv/bin/python -m pytest -q                  # macOS/Linux

# Frontend
cd frontend
npm run lint
npm run build
```

For a runtime check, start AnimeBox, search for a title, choose a season voiceover, open an episode, download it, and then play it from **Library**.

## Troubleshooting

### `venv not found`

Run `scripts/install.ps1` or `scripts/install.sh`. If the environment was moved between directories or computers, delete `.venv` and install again.

### Search works, but the stream does not open

- try another voiceover or source;
- check whether the source website is available in your region;
- configure `HTTP_PROXY` in `.env` or the interface;
- inspect backend messages in the terminal.

### `Search cache expired`

Search for the title again and open it from the new results. AnimeBox does not permanently store links to source pages.

### Downloads require FFmpeg

When running from source, install FFmpeg and confirm that `ffmpeg -version` works in a new terminal. HLS/DASH downloads and Steam Deck optimization are unavailable without FFmpeg. Portable archives already include FFmpeg.

### A source suddenly stopped working

The provider may have changed its HTML/API or may be unavailable through your internet provider. AnimeBox waits no longer than `PROVIDER_SEARCH_TIMEOUT` for each source and returns results from available providers. If only one domain fails, the portable build is not necessarily broken—it may be a routing issue or source-specific block. Configure an HTTP/SOCKS proxy in Settings when needed. Do not edit `.references/anicli-api` manually: recreate the checkout with the installation script and keep compatibility changes in `patches/`.

## Legal notice

AnimeBox is a local client and does not host media content. Use it only with content and sources permitted by applicable law and service terms. The user is responsible for choosing sources and saving files.

## Credits

AnimeBox uses or studies work from:

- [anicli-api](https://github.com/vypivshiy/anicli-api) — catalog, episode, voiceover, and stream extraction;
- [ani-cli-ru](https://github.com/vypivshiy/ani-cli-ru) — UX and reverse-proxy approach;
- [HakuNeko](https://github.com/manga-download/hakuneko) — connector and downloader architecture;
- [Sonarr](https://github.com/Sonarr/Sonarr) — ideas for durable queues, imports, and media libraries.

Detailed licenses and reuse boundaries: [THIRD_PARTY.md](THIRD_PARTY.md).
