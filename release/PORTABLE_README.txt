AnimeBox Portable
=================

Windows:            double-click AnimeBox.exe
Linux / Steam Deck: run ./AnimeBox from this folder
macOS:              fully extract the archive, then open AnimeBox
                    (first launch may require Control-click > Open)

AnimeBox starts a private server on http://127.0.0.1:8787 and opens your browser.
Closing the browser tab does not stop it: use "Stop" in the sidebar.

Keep these when updating or moving AnimeBox (copy them into the new folder):
  .env       settings
  data/      database: history, progress, download queue, settings
  library/   downloaded anime
AnimeBox 2.0 upgrades a 1.x database automatically and keeps a copy in data/backups/.

Internet is needed for search, online playback and new downloads.
Downloaded episodes play offline.

Logs: data/animebox.log (proxy passwords are not written to the log).

If a macOS download reports "ffmpeg failed", open Terminal in this folder and run:
  bash scripts/grant-macos-permissions.sh
If macOS still blocks files from an archive you trust:
  bash scripts/grant-macos-permissions.sh --clear-quarantine

Do not expose the AnimeBox port to public networks.
Licenses: LICENSE.txt, THIRD_PARTY.md, tools/FFMPEG-NOTICE.txt
