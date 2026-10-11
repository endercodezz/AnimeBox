"""Fetch the pinned anicli-api checkout and apply AnimeBox's compatibility patch.

Usage:
  python scripts/patch_anicli.py            # patch an existing checkout
  python scripts/patch_anicli.py --checkout # clone the pinned commit first if missing

The pinned commit lives in patches/anicli-api.ref. Bump it only after the
provider tests and a manual AnimeGO check (see docs/TESTING.md) pass.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKOUT = ROOT / ".references" / "anicli-api"
PATCH = ROOT / "patches" / "anicli-api-remove-dead-sovetromantica.patch"
REF_FILE = ROOT / "patches" / "anicli-api.ref"
REPOSITORY = "https://github.com/vypivshiy/anicli-api"


def git(*args: str, cwd: Path = CHECKOUT, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(cwd), *args], check=check, capture_output=True, text=True)


def pinned_ref() -> str:
    return REF_FILE.read_text(encoding="utf-8").strip()


def checkout() -> None:
    ref = pinned_ref()
    if (CHECKOUT / "pyproject.toml").is_file():
        current = git("rev-parse", "HEAD", check=False).stdout.strip()
        if current and current != ref:
            print(f"Note: .references/anicli-api is at {current[:10]}, AnimeBox is tested with {ref[:10]}")
        return
    print(f"Fetching anicli-api {ref[:10]} (MIT)")
    CHECKOUT.mkdir(parents=True, exist_ok=True)
    git("init", "-q")
    git("remote", "add", "origin", REPOSITORY, check=False)
    fetched = git("fetch", "--depth", "1", "origin", ref, check=False)
    if fetched.returncode != 0:
        raise SystemExit(f"Failed to fetch anicli-api {ref}: {fetched.stderr.strip()}")
    git("checkout", "-q", "FETCH_HEAD")


def git_apply(*args: str) -> subprocess.CompletedProcess[str]:
    return git("apply", *args, str(PATCH), check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--checkout", action="store_true", help="clone the pinned commit when the checkout is missing")
    args = parser.parse_args()
    if args.checkout:
        checkout()
    if not (CHECKOUT / "pyproject.toml").is_file():
        raise SystemExit(f"anicli-api checkout not found: {CHECKOUT}. Run: python scripts/patch_anicli.py --checkout")
    if git_apply("--check").returncode == 0:
        result = git_apply()
        if result.returncode != 0:
            raise SystemExit(result.stderr.strip() or "failed to patch anicli-api")
        print("Applied AnimeBox compatibility patch to anicli-api")
        return 0
    if git_apply("--reverse", "--check").returncode == 0:
        print("AnimeBox compatibility patch already applied")
        return 0
    raise SystemExit("anicli-api checkout is incompatible with the AnimeBox patch; update patches/ for this commit")


if __name__ == "__main__":
    sys.exit(main())
