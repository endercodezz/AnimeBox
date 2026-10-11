# AnimeBox portable builds

Builds are native per operating system. On Windows, Linux or macOS with Python 3.12 and Node 24+:

```bash
python scripts/patch_anicli.py --checkout
python -m pip install -r backend/requirements.txt -r release/requirements-build.txt
python release/build_portable.py --ffmpeg /path/to/native/ffmpeg
python release/verify_archive.py release/artifacts/AnimeBox-<version>-<platform>.zip
```

The archive name is `AnimeBox-<version>-<Platform>-<arch>` (version from `backend/__init__.py`).
`AnimeBox-<version>-Linux-x64` also targets Steam Deck/SteamOS.

Generated files (all ignored by Git):

- `release/work/` — PyInstaller cache;
- `release/dist/` — raw one-folder application;
- `release/artifacts/` — ready folder, archive and `.sha256`.

The archive contains the Python runtime, backend dependencies, the compiled frontend, anicli-api, FFmpeg with
`tools/FFMPEG-NOTICE.txt`, a default `.env`, empty `data/` and `library/`, `LICENSE.txt`, `THIRD_PARTY.md` and
`CHANGELOG.md`. Python, Node and Git are not needed to run it. On macOS the builder bundles FFmpeg's non-system dylibs
under `tools/lib/`, rewrites load paths, ad-hoc signs them and includes `scripts/grant-macos-permissions.sh`.

`verify_archive.py` fails the build if required files are missing, if developer/agent state (`.tmp`, `.claude`,
`.references`, …) or user data (databases, logs, partial downloads, library media) is inside, or if the checksum does
not match.

See [docs/RELEASING.md](../docs/RELEASING.md) for the CI release process.
