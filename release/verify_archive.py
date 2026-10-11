"""Verify a portable AnimeBox archive before it is published.

Checks that every required file is present, that no developer/agent state or
user data leaked into the archive, and that the ``.sha256`` sidecar matches.

Usage: python release/verify_archive.py release/artifacts/AnimeBox-2.0.0-Linux-x64.tar.gz
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

NAME_RE = re.compile(r"^AnimeBox-(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)-(Windows-x64|Linux-x64|Linux-arm64|macOS-x64|macOS-arm64)$")

FORBIDDEN_PARTS = {".tmp", ".claude", ".codex", ".cursor", ".references", ".git", "node_modules", "__pycache__", ".venv"}
FORBIDDEN_SUFFIXES = (".db", ".db-wal", ".db-shm", ".part.mp4", ".part.mkv", ".log")


def members(archive: Path) -> list[str]:
    if archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, "r:gz") as tf:
            return [m.name + ("/" if m.isdir() else "") for m in tf.getmembers()]
    with zipfile.ZipFile(archive) as zf:
        return zf.namelist()


def verify(archive: Path) -> list[str]:
    problems: list[str] = []
    stem = archive.name.removesuffix(".tar.gz").removesuffix(".zip")
    match = NAME_RE.match(stem)
    if not match:
        return [f"archive name {archive.name!r} does not follow AnimeBox-<version>-<Platform>-<arch>"]
    platform = match.group(2)
    windows = platform.startswith("Windows")
    if platform.startswith("Linux") != archive.name.endswith(".tar.gz"):
        problems.append("Linux archives must be .tar.gz, others .zip")

    names = {n.replace("\\", "/") for n in members(archive)}
    files = {n for n in names if not n.endswith("/")}
    dirs = {n.rstrip("/") for n in names if n.endswith("/")} | {str(PurePosixPath(f).parent) for f in files}

    def has_file(rel: str) -> bool:
        return f"{stem}/{rel}" in files

    exe = "AnimeBox.exe" if windows else "AnimeBox"
    ffmpeg = "tools/ffmpeg.exe" if windows else "tools/ffmpeg"
    required = [exe, ffmpeg, "tools/FFMPEG-NOTICE.txt", ".env", ".env.example", "README.txt", "THIRD_PARTY.md", "LICENSE.txt"]
    for rel in required:
        if not has_file(rel):
            problems.append(f"missing {rel}")
    if not any(f.startswith(f"{stem}/") and f.endswith("frontend/dist/index.html") for f in files):
        problems.append("missing bundled frontend (frontend/dist/index.html)")
    if not any(f.startswith(f"{stem}/") and "/frontend/dist/assets/" in f and f.endswith(".js") for f in files):
        problems.append("missing frontend JavaScript bundle")
    for folder in ("data", "library"):
        if f"{stem}/{folder}" not in dirs:
            problems.append(f"missing {folder}/ directory")
    if platform.startswith("macOS") and not has_file("scripts/grant-macos-permissions.sh"):
        problems.append("missing scripts/grant-macos-permissions.sh")

    for name in sorted(files):
        if not name.startswith(f"{stem}/"):
            problems.append(f"file outside the top-level folder: {name}")
            continue
        rel = PurePosixPath(name[len(stem) + 1 :])
        if FORBIDDEN_PARTS & set(rel.parts):
            problems.append(f"forbidden path in archive: {rel}")
        if rel.name.lower().endswith(FORBIDDEN_SUFFIXES):
            problems.append(f"user/runtime data in archive: {rel}")
        if rel.parts[:1] == ("library",) and rel.name != ".gitkeep":
            problems.append(f"library content in archive: {rel}")

    sidecar = archive.with_name(archive.name + ".sha256")
    if not sidecar.is_file():
        problems.append(f"missing checksum file {sidecar.name}")
    else:
        expected = sidecar.read_text(encoding="utf-8").split()[0]
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        if expected != actual:
            problems.append("checksum file does not match archive")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--version", help="Expected version in archive names")
    args = parser.parse_args()
    failed = False
    for archive in args.archives:
        problems = verify(archive)
        if args.version and f"AnimeBox-{args.version}-" not in archive.name:
            problems.append(f"archive version does not match {args.version}")
        if problems:
            failed = True
            print(f"FAIL {archive.name}")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(f"OK   {archive.name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
