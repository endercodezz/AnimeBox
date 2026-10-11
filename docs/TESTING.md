# Testing AnimeBox

## Automated tests (CI)

CI never talks to real anime sites: provider, stream and media-proxy tests use deterministic fakes and in-memory HTTP
transports, so a site being down cannot break the build.

```bash
python -m pytest -q          # backend: library integrity, migrations, media proxy security, provider engine,
                             # download queue, playback progress, API errors, ffmpeg handling, portable launcher
cd frontend
npm run check                # tsc + oxlint + vitest
npm run build
```

| Area | Tests |
|---|---|
| Empty-library regression, file detection, missing/partial files, delete, rescan | `tests/test_library.py` |
| 1.x database upgrade, backups, rollback, repeatability, constraints | `tests/test_migrations.py` |
| SSRF protection, session scoping, header isolation, redirects, playlist rewriting | `tests/test_media_proxy.py` |
| Provider timeouts/failures, player fallback, exact cache recovery, health status | `tests/test_provider_registry.py` |
| Queue rules, validation, atomic finalisation, retries, recovery, concurrency, Range resume | `tests/test_downloads.py` |
| Progress persistence/restoration, error mapping, settings validation, Host protection | `tests/test_api.py` |
| ffmpeg discovery, progress parsing, process cleanup | `tests/test_ffmpeg.py` |
| UI utilities, episode grid accessibility, API client errors | `frontend/src/**/*.test.ts(x)` |

The release workflow additionally smoke-tests every packaged build (startup, bundled UI, providers, empty library on a
fresh install, ffmpeg detection, Host protection, clean shutdown with the WAL checkpointed).

## Manual integration tests with real sources

Run these before tagging a release and after bumping `patches/anicli-api.ref`. Use a throwaway data folder so your
own library is not touched:

```bash
# from the repository root
export DATA_PATH=./.tmp/manual/data LIBRARY_PATH=./.tmp/manual/library \
       DATABASE_URL=sqlite+aiosqlite:///./.tmp/manual/data/animebox.db PORT=8799
python -m backend.main
```

(PowerShell: `$env:DATA_PATH='./.tmp/manual/data'` etc.) Then open `http://127.0.0.1:8799`.

### 1. Provider diagnostics

**Settings → Sources → Check** for AnimeGO. Expected: all five stages (Search, Title, Episodes, Voiceovers, Stream)
green, status "Работает". Repeat for each enabled experimental source and note failures in the release notes.

Command-line equivalent:

```bash
python -c "import asyncio; from backend.providers.registry import ProviderRegistry as R; r=R(); asyncio.run(r.check('animego')); print({k: (v.ok, v.error) for k, v in r.health.get('animego').stages.items()})"
```

### 2. AnimeGO end to end

1. Search «Врата Штейна». Expected: results from AnimeGO plus a status chip per source.
2. Open the title. Expected: description, episode grid; **no new folder appears in `library/`** and the Library page
   stays empty.
3. Pick episode 1 and a voiceover with several players (e.g. AniLibria). Click **Смотреть онлайн**. Expected: playback
   starts; the subtitle line shows the voiceover and the player that worked.
4. Seek to ~5:00, go back to the title page, open the episode again. Expected: playback resumes near 5:00.
5. In the player, switch voiceover and quality. Expected: playback continues near the same position.
6. Press `Shift+N` on the last episode. Expected: nothing happens (no next episode).

### 3. Downloads

1. Download one episode. Expected: progress rises with real speed and size; status «Готово»; the title appears in the
   Library with one episode; `library/<Title>/Season 1/Episode 01.mp4`, `poster.*` and `metadata.json` exist; no
   `*.part.*` remains.
2. Play it from the Library with the network disconnected. Expected: plays, progress is restored.
3. Queue a whole season, stop AnimeBox mid-download, start it again. Expected: interrupted jobs are back in the queue
   and continue; no orphaned partial files.
4. Cancel a running download. Expected: ffmpeg exits, partial file removed, no empty title folder.
5. AnimeVost (direct MP4): pause and resume a download. Expected: resumes from the same byte offset.
6. Delete the downloaded file manually, open the Library. Expected: the episode is hidden; **Rescan** removes the stale
   record.

### 4. Upgrade from 1.x

Copy a 1.x `data/` folder (and `library/`) into the test folders and start 2.0. Expected: `data/backups/` contains a
copy; the Library lists only titles with existing files; history and progress are kept; titles that were only
browsed in 1.x are gone from the Library but still searchable.

### 5. Network

Configure a proxy in **Settings → Network**, repeat steps 2.3 and 3.1. Expected: playback and downloads work through
the proxy (signed CVH/OKCDN links require the same IP for resolution and fetching).
