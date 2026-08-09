#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
FAILED=0
ok(){ echo "[OK]   $1${2:+: $2}"; }
fail(){ echo "[FAIL] $1 — $2" >&2; FAILED=1; }
echo "AnimeBox diagnostics"
if command -v python3 >/dev/null && python3 -c 'import sys; assert sys.version_info >= (3,12)' 2>/dev/null; then ok "Python 3.12+" "$(python3 --version)"; else fail "Python 3.12+" "Install Python 3.12+."; fi
if command -v npm >/dev/null; then ok "Node/npm" "$(node --version) / npm $(npm --version)"; else fail "Node/npm" "Install Node.js 20+."; fi
command -v git >/dev/null && ok "Git" "$(git --version)" || fail "Git" "Install Git."
[[ -f .references/anicli-api/pyproject.toml ]] && ok "anicli-api" "present" || fail "anicli-api" "Run ./scripts/install.sh with internet."
[[ -x .venv/bin/python ]] && .venv/bin/python -c 'import backend.main' >/dev/null 2>&1 && ok "Python environment" "imports OK" || fail "Python environment" "Run ./scripts/install.sh."
[[ -d frontend/node_modules ]] && ok "Frontend dependencies" "present" || fail "Frontend dependencies" "Run ./scripts/install.sh."
[[ -f frontend/dist/index.html ]] && ok "Frontend build" "present" || fail "Frontend build" "Run ./scripts/run.sh without --skip-build."
[[ -f .env ]] && ok "Default environment" "present" || fail "Default environment" "Run ./scripts/run.sh; it creates .env automatically."
mkdir -p data library
if printf ok > data/.write-test 2>/dev/null; then rm -f data/.write-test; ok "data/library" "writable"; else fail "data/library" "Grant write access to project directory."; fi
command -v ffmpeg >/dev/null && ok "ffmpeg" "$(ffmpeg -version 2>/dev/null | head -n1)" || echo "[WARN] ffmpeg missing — offline playback works; new HLS downloads do not."
[[ "$FAILED" -eq 0 ]] || exit 1
echo "AnimeBox is ready."
