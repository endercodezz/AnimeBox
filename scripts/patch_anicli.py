from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKOUT = ROOT / ".references" / "anicli-api"
PATCH = ROOT / "patches" / "anicli-api-remove-dead-sovetromantica.patch"


def git_apply(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(CHECKOUT), "apply", *args, str(PATCH)],
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> int:
    if not (CHECKOUT / "pyproject.toml").is_file():
        raise SystemExit(f"anicli-api checkout not found: {CHECKOUT}")
    if git_apply("--check").returncode == 0:
        result = git_apply()
        if result.returncode != 0:
            raise SystemExit(result.stderr.strip() or "failed to patch anicli-api")
        print("Applied AnimeBox compatibility patch to anicli-api")
        return 0
    if git_apply("--reverse", "--check").returncode == 0:
        print("AnimeBox compatibility patch already applied")
        return 0
    raise SystemExit("anicli-api checkout is incompatible with AnimeBox patch; update patches/anicli-api-remove-dead-sovetromantica.patch")


if __name__ == "__main__":
    sys.exit(main())
