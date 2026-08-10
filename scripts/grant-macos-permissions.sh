#!/usr/bin/env bash
# Repair executable permissions for an extracted AnimeBox macOS portable build.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_SET=0
CLEAR_QUARANTINE=0

usage() {
  echo "Usage: bash scripts/grant-macos-permissions.sh [--clear-quarantine] [PORTABLE_FOLDER]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --clear-quarantine)
      CLEAR_QUARANTINE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -* )
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ "$ROOT_SET" -eq 1 ]]; then
        echo "Only one portable folder may be provided." >&2
        exit 2
      fi
      ROOT="$(cd "$1" && pwd)"
      ROOT_SET=1
      shift
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This helper supports macOS only." >&2
  exit 1
fi

LAUNCHER="$ROOT/AnimeBox"
FFMPEG="$ROOT/tools/ffmpeg"
for target in "$LAUNCHER" "$FFMPEG"; do
  if [[ ! -f "$target" ]]; then
    echo "Required portable file not found: $target" >&2
    echo "Fully extract AnimeBox-macOS-*.zip, then run this helper from that folder." >&2
    exit 1
  fi
done

chmod u+x "$LAUNCHER" "$FFMPEG"
echo "Executable permissions granted:"
echo "  $LAUNCHER"
echo "  $FFMPEG"

if [[ "$CLEAR_QUARANTINE" -eq 1 ]]; then
  if ! command -v xattr >/dev/null 2>&1; then
    echo "xattr not found; quarantine was not changed." >&2
    exit 1
  fi
  echo "Removing com.apple.quarantine from AnimeBox executables and bundled FFmpeg libraries."
  echo "Only use this option for an archive downloaded from a source you trust."
  xattr -d com.apple.quarantine "$LAUNCHER" "$FFMPEG" 2>/dev/null || true
  if [[ -d "$ROOT/tools/lib" ]]; then
    find "$ROOT/tools/lib" -maxdepth 1 -type f -name '*.dylib' \
      -exec xattr -d com.apple.quarantine {} + 2>/dev/null || true
  fi
fi

if "$FFMPEG" -version >/dev/null 2>&1; then
  echo "ffmpeg: OK"
  exit 0
fi

echo "ffmpeg still cannot start. Diagnostics:" >&2
echo "  Mac architecture: $(uname -m)" >&2
file "$FFMPEG" >&2 || true
otool -L "$FFMPEG" >&2 || true
echo "Try again with --clear-quarantine only if this archive came from a trusted source." >&2
exit 1
