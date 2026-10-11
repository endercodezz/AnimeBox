# Changelog

All notable changes to AnimeBox are documented here. Versions follow [Semantic Versioning](https://semver.org/).

## [2.0.0] — 2026-10-11

AnimeBox 2.0 is a reliability release with a completely redesigned interface. Existing libraries, history,
progress and settings are migrated automatically (a backup of the database is made first).

### Fixed

- **Browsing no longer adds anime to the offline library.** Opening a title page created its folder and the
  library listed every browsed title, even with zero downloaded episodes. The library is now derived only from
  downloaded files that exist and pass validation; missing, deleted and partial files are excluded.
- The same anime could be stored under two ids (`animego:%2Fanime%2F…` and `animego:/anime/…`) because route
  parameters were decoded twice. Ids are canonicalised everywhere and existing duplicates are merged.
- AnimeGO playback failed for many voiceovers: AnimeBox always picked the first player for a voiceover, and AnimeGO's
  CVH player URLs changed so the upstream extractor returned nothing. AnimeBox now falls back across all players of a
  voiceover (Kodik, Aniboom, CVH, …) and includes an adapter for the current CVH URL format.
- Recovering expired search data could silently open a *different* title with a similar name. Recovery now accepts
  only an exact provider match.
- With `HTTP_PROXY` set, OKCDN/CVH streams resolved through the proxy but were fetched directly, so the IP-bound links
  returned 403. Resolution, playback and downloads now share one network path.
- Online playback progress was saved but never restored.
- "Next episode" no longer navigates to episodes that do not exist.
- A valid download was marked failed when the poster or metadata could not be saved.
- Download progress was largely fake (fixed 1/5/10/85/90 % steps); cancelling did not stop a running ffmpeg process.
- Database file paths were stored relative to the process working directory; they are now relative to the library.
- The portable launcher never wrote `data/animebox.log`.
- Shutting down left the SQLite WAL un-checkpointed, so copying only `animebox.db` could lose recent changes.
- The anicli-api compatibility patch failed to apply on fresh Windows installs because of CRLF line endings.

### Security

- The media proxy no longer fetches arbitrary URLs. Playback uses short-lived media sessions; clients can request only
  URLs the server itself issued, every hop (including redirects) is checked against loopback/private/link-local
  networks, and provider headers stay scoped to their session.
- Requests whose `Host` header is not this machine are rejected (protection against DNS rebinding).
- Proxy credentials and signed URL parameters are redacted from logs.
- Settings and API input are validated.

### Providers

- New provider engine with per-stage timeouts (search, details, episodes, voiceovers, stream) and typed errors.
- Provider health is based on real operations and on an explicit end-to-end check; a provider is shown as working
  only when every stage most recently succeeded.
- One isolated HTTP session per source; connection errors are retried once, HTTP 403/429 and anti-bot pages are not.
- AnimeGO is the default and the only provider marked stable; AniLiberty, AnimeVost and Yummy Anime are experimental;
  AniLib, DreamCast and SameBand are opt-in. HDRezka is no longer offered because its extractor depends on an
  anti-bot workaround.
- anicli-api is pinned to a tested commit (`patches/anicli-api.ref`).

### Player

- Custom controls: keyboard shortcuts, volume, speed, quality (HLS levels or per-quality streams), voiceover switching
  without losing the position, audio tracks and subtitles when the stream provides them, fullscreen, episode list.
- Progress is saved periodically, on pause/seek, when the tab is hidden and when leaving the page, and restored on open.
- Network errors are retried; expired links are re-resolved automatically and playback resumes at the same position.
- Clear error messages with actions (retry, other voiceover, play the downloaded copy).
- Next-episode countdown only when the next episode exists (can be disabled in Settings).

### Downloads

- Configurable parallel downloads (1–6), real progress from ffmpeg's position/duration, transfer speed and size.
- Pause/resume for direct MP4/WebM downloads (HTTP Range); HLS downloads restart and say so.
- Automatic retries with a fresh stream resolution; cancellation stops ffmpeg; duplicate requests are skipped.
- Files are written to `*.part.*`, validated (size, readable container, duration ≥ 95 % of the source), then moved into
  place atomically. Interrupted jobs return to the queue after a restart; orphaned partial files are cleaned up.
- Steam Deck transcoding keeps the original file if transcoding fails.

### Interface

- New "Neon Cinema" design: bundled Unbounded and Manrope fonts (Latin + Cyrillic, works offline), redesigned Home,
  Search, Title, Player, Library, Downloads and Settings pages, responsive layouts for desktop, Steam Deck and phones.
- Home: continue watching, recently watched, recently downloaded, quick search.
- Title page: episode grid showing watch progress, offline availability and queued downloads; works from the local
  library when the source is offline.
- Library: storage usage, sorting, filtering, rescanning, deletion with confirmation.
- Settings: playback, downloads, providers (status per stage, manual check), network, storage, interface, diagnostics.

### Under the hood

- Versioned SQLite migrations with automatic backups in `data/backups/`, unique constraints and indexes.
- Backend split into focused API modules; backend (pytest) and frontend (Vitest) test suites run in CI on every push.
- Release workflow builds Windows x64, Linux x64 (Steam Deck), macOS x64 and macOS arm64 archives named
  `AnimeBox-<version>-<platform>`, verifies their contents, smoke-tests the packaged app, and publishes checksums.

## [1.1.3] and earlier

Early MVP releases: multi-source search via anicli-api, online HLS playback through a local proxy, downloads,
local library, Steam Deck optimisation and portable builds. See the Git history for details.
