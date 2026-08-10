AnimeBox Portable
=================

Windows:   double-click AnimeBox.exe
Linux / Steam Deck: run ./AnimeBox from extracted AnimeBox-Linux-x64 folder
macOS:     fully extract the archive, then run AnimeBox
           (first launch may require Control-click > Open)

If a macOS download reports "ffmpeg failed", open Terminal in this folder and run:
  bash scripts/grant-macos-permissions.sh
If macOS still blocks trusted downloaded files, run:
  bash scripts/grant-macos-permissions.sh --clear-quarantine
The second command removes Gatekeeper quarantine only from AnimeBox/FFmpeg files.
Use it only when the archive came from a source you trust.

AnimeBox starts a private localhost server and opens your system browser.
Keep these folders when updating or moving AnimeBox:
  .env       settings
  data/      database, history and cache
  library/   downloaded anime

Internet is needed for search and new downloads. Existing library playback works offline.
Do not expose AnimeBox port to public networks unless you understand the security implications.
