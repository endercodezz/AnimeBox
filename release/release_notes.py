"""Print release notes for a version from CHANGELOG.md (plus download/checksum hints).

Usage: python release/release_notes.py 2.0.0 > notes.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def changelog_section(version: str, text: str) -> str | None:
    pattern = re.compile(rf"^## \[?{re.escape(version)}\]?.*?$(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def notes(version: str) -> str:
    changelog = ROOT / "CHANGELOG.md"
    section = changelog_section(version, changelog.read_text(encoding="utf-8")) if changelog.is_file() else None
    if not section:
        raise SystemExit(f"CHANGELOG.md has no section for {version}; add one before tagging")
    downloads = "\n".join(
        [
            "## Downloads",
            "",
            "| Platform | Archive |",
            "|---|---|",
            f"| Windows 10/11 x64 | `AnimeBox-{version}-Windows-x64.zip` |",
            f"| Linux x64 / Steam Deck | `AnimeBox-{version}-Linux-x64.tar.gz` |",
            f"| macOS Intel | `AnimeBox-{version}-macOS-x64.zip` |",
            f"| macOS Apple Silicon | `AnimeBox-{version}-macOS-arm64.zip` |",
            "",
            "Verify downloads with `SHA256SUMS.txt` (e.g. `sha256sum -c SHA256SUMS.txt --ignore-missing`).",
            "Upgrading: keep your `.env`, `data/` and `library/` folders — see the README section *Upgrading*.",
        ]
    )
    return f"{section}\n\n{downloads}\n"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: release_notes.py <version>")
    sys.stdout.reconfigure(encoding="utf-8")
    print(notes(sys.argv[1]))
