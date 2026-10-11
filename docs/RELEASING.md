# Releasing AnimeBox

Releases are built and published by `.github/workflows/release.yml`.

## Version

The version lives in two places that CI checks are equal:

- `backend/__init__.py` → `__version__ = "2.0.0"`
- `frontend/package.json` → `"version": "2.0.0"`

Prereleases use a semver suffix in **both** places and in the tag, e.g. `2.0.1-beta.1` / `v2.0.1-beta.1`.

## Steps

1. Update the version in both files.
2. Add a `## [X.Y.Z] — YYYY-MM-DD` section to `CHANGELOG.md` (the workflow refuses to publish without it).
3. Run the checks locally and the manual tests in [TESTING.md](TESTING.md).
4. Commit, then tag and push:

   ```bash
   git tag v2.0.0
   git push origin main v2.0.0
   ```

## What the workflow does

1. **checks** (`ci.yml`): backend tests, frontend type-check/lint/tests/build, version consistency, no agent files tracked.
2. **meta**: verifies the tag equals the code version; tags with `-` become prereleases.
3. **build** (Windows x64, Linux x64 on Ubuntu 22.04 for SteamOS compatibility, macOS x64, macOS arm64):
   PyInstaller one-folder build with the compiled UI, bundled FFmpeg (+ license notice), archive
   `AnimeBox-<version>-<platform>.zip|tar.gz` with a `.sha256`, content verification (`release/verify_archive.py`),
   packaged-app smoke test, and an informational live AnimeGO check (does not block the release — sites can be down).
4. **publish** (tags only): refuses to publish unless all four archives exist and their checksums verify, writes
   `SHA256SUMS.txt`, and creates the GitHub Release with notes from `CHANGELOG.md` plus generated notes.

`workflow_dispatch` runs everything except publishing; the archives are available as workflow artifacts.

## Building locally

```bash
python -m pip install -r backend/requirements.txt -r release/requirements-build.txt
python release/build_portable.py --ffmpeg /path/to/ffmpeg
python release/verify_archive.py release/artifacts/AnimeBox-*.zip   # or .tar.gz on Linux
```

Builds are native: build each platform on that platform.

## Signing

Artifacts are unsigned unless signing is configured. macOS users may need Control-click → Open; Windows SmartScreen may
warn on first launch. To sign, add certificates as repository secrets and a signing step before archiving; never put
secrets in the workflow file.

## Requirements and permissions

- The repository's Actions must be allowed to create releases (`contents: write` is requested only by the publish job).
- No extra secrets are required: the default `GITHUB_TOKEN` is used.
