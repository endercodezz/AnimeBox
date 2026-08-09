#!/usr/bin/env bash
# Install AnimeBox dependencies and build browser UI. Safe to run repeatedly.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SKIP_BUILD=0
[[ "${1:-}" == "--skip-build" ]] && SKIP_BUILD=1

need() { command -v "$1" >/dev/null 2>&1 || { echo "$1 not found. $2" >&2; exit 1; }; }
need python3 "Install Python 3.12+."
need npm "Install Node.js 20+ and npm."
need git "Install Git."
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)' || { echo "Python 3.12+ required: $(python3 --version)" >&2; exit 1; }

echo "==> AnimeBox setup"
echo "Root: $ROOT"
echo "Python: $(python3 --version)"
echo "Node:   $(node --version)"

ANICLI="$ROOT/.references/anicli-api"
if [[ ! -f "$ANICLI/pyproject.toml" ]]; then
  echo "==> Cloning anicli-api (MIT)"
  mkdir -p "$ROOT/.references"
  git clone --depth 1 https://github.com/vypivshiy/anicli-api "$ANICLI" || { echo "Failed to clone anicli-api. Check internet and retry." >&2; exit 1; }
else
  echo "==> anicli-api checkout: OK"
fi
python3 "$ROOT/scripts/patch_anicli.py"

PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]] || ! "$PYTHON" -c 'import sys' >/dev/null 2>&1; then
  if [[ -d "$ROOT/.venv" ]]; then
    echo "==> Existing .venv is broken or was moved; recreating"
    rm -rf "$ROOT/.venv"
  fi
  echo "==> Creating Python environment"
  python3 -m venv "$ROOT/.venv"
fi

echo "==> Installing backend"
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -r "$ROOT/backend/requirements.txt"

if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "==> Created default .env"
else
  echo "==> Keeping existing .env"
fi
mkdir -p "$ROOT/data" "$ROOT/library"

echo "==> Installing frontend"
if [[ -f "$ROOT/frontend/package-lock.json" ]]; then
  (cd "$ROOT/frontend" && npm ci)
else
  (cd "$ROOT/frontend" && npm install)
fi
if [[ "$SKIP_BUILD" -eq 0 ]]; then
  echo "==> Building frontend"
  (cd "$ROOT/frontend" && npm run build)
fi

if command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg: OK"
else
  echo "Warning: ffmpeg not found. New HLS downloads need it; downloaded library files still play." >&2
fi

echo
echo "AnimeBox is ready."
echo "Start: ./scripts/run.sh"
echo "Check: ./scripts/check.sh"
