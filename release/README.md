# AnimeBox portable builds

Builds are native per operating system. Run this on Windows, Linux, or macOS using Python 3.12 and Node 20+:

```bash
python -m pip install -r backend/requirements.txt -r release/requirements-build.txt
python release/build_portable.py --ffmpeg /path/to/native/ffmpeg
```

`AnimeBox-Linux-x64` also targets Steam Deck/SteamOS. CI produces one tested Linux x86_64 archive instead of duplicating identical application binaries under separate names.

Generated files:

- `release/work/` — PyInstaller cache;
- `release/dist/` — raw one-folder application;
- `release/artifacts/` — ready folder, archive and SHA-256.

End-user archive contains Python runtime, backend dependencies, prebuilt frontend, anicli-api, ffmpeg, ready `.env`, `data/` and `library/`. Python/Node/Git are not required to run it.

macOS artifacts are unsigned unless signing/notarization secrets are configured in CI. Windows artifacts are unsigned unless a signing certificate is configured.
