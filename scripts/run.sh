#!/usr/bin/env bash
# Start AnimeBox in browser. Creates default .env on first run.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
DEV=0; SKIP_BUILD=0; NO_BROWSER=0
for arg in "$@"; do
  case "$arg" in
    --dev|-d) DEV=1 ;;
    --skip-build) SKIP_BUILD=1 ;;
    --no-browser) NO_BROWSER=1 ;;
    -h|--help) echo "Usage: ./scripts/run.sh [--dev] [--skip-build] [--no-browser]"; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

PYTHON="$ROOT/.venv/bin/python"
[[ -x "$PYTHON" ]] || { echo "AnimeBox is not installed. Run ./scripts/install.sh first." >&2; exit 1; }
"$PYTHON" -c 'import backend.main' >/dev/null 2>&1 || { echo "Backend environment is broken. Run ./scripts/install.sh again." >&2; exit 1; }

if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "==> Created default .env"
fi
mkdir -p "$ROOT/data" "$ROOT/library"
PORT="$("$PYTHON" - <<'PY'
from pathlib import Path
port=8787
for line in Path('.env').read_text(encoding='utf-8').splitlines():
    if line.strip().startswith('PORT='):
        try: port=int(line.split('=',1)[1].strip())
        except ValueError: pass
print(port)
PY
)"
URL="http://127.0.0.1:$PORT"

open_browser() {
  [[ "$NO_BROWSER" -eq 1 ]] && return
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$1" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then open "$1" >/dev/null 2>&1 & fi
}
cleanup() { [[ -n "${API_PID:-}" ]] && kill "$API_PID" >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM

if [[ "$DEV" -eq 0 ]]; then
  if [[ "$SKIP_BUILD" -eq 0 ]]; then
    [[ -d "$ROOT/frontend/node_modules" ]] || { echo "Frontend dependencies missing. Run ./scripts/install.sh first." >&2; exit 1; }
    echo "==> Building frontend"
    (cd "$ROOT/frontend" && npm run build)
  elif [[ ! -f "$ROOT/frontend/dist/index.html" ]]; then
    echo "frontend/dist missing. Run without --skip-build." >&2; exit 1
  fi
fi

if command -v lsof >/dev/null 2>&1; then
  OLD_PID="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  [[ -z "$OLD_PID" ]] || kill "$OLD_PID" >/dev/null 2>&1 || true
fi

echo "==> Starting AnimeBox"
echo "UI:   $URL"
echo "Docs: $URL/docs"
command -v ffmpeg >/dev/null 2>&1 || echo "Warning: ffmpeg unavailable; offline playback works, new HLS downloads do not." >&2
"$PYTHON" -m backend.main & API_PID=$!

READY=0
for _ in $(seq 1 60); do
  kill -0 "$API_PID" 2>/dev/null || { echo "AnimeBox stopped during startup." >&2; exit 1; }
  if command -v curl >/dev/null 2>&1 && curl -fsS "$URL/api/health" >/dev/null 2>&1; then READY=1; break; fi
  sleep .25
done
[[ "$READY" -eq 1 ]] || { echo "AnimeBox did not become ready at $URL." >&2; exit 1; }
echo "==> AnimeBox ready"

if [[ "$DEV" -eq 1 ]]; then
  [[ -d "$ROOT/frontend/node_modules" ]] || { echo "Frontend dependencies missing. Run ./scripts/install.sh first." >&2; exit 1; }
  open_browser "http://127.0.0.1:5173"
  (cd "$ROOT/frontend" && npm run dev)
else
  open_browser "$URL"
  echo "Press Ctrl+C to stop."
  wait "$API_PID"
fi
