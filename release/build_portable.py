from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
WORK = RELEASE / "work"
DIST = RELEASE / "dist"
ARTIFACTS = RELEASE / "artifacts"


def run(*args: str, cwd: Path = ROOT) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def target_name() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "x64"
    if system == "Windows":
        return "AnimeBox-Windows-x64"
    if system == "Darwin":
        return f"AnimeBox-macOS-{arch}"
    if system == "Linux":
        return f"AnimeBox-Linux-{arch}"
    raise RuntimeError(f"Unsupported platform: {system} {machine}")


def find_ffmpeg(explicit: str | None) -> Path:
    candidate = Path(explicit).resolve() if explicit else None
    if candidate and candidate.is_file():
        return candidate
    found = shutil.which("ffmpeg")
    if found:
        return Path(found)
    raise RuntimeError("ffmpeg not found; pass --ffmpeg PATH")


def assemble(ffmpeg: Path) -> tuple[Path, str]:
    name = target_name()
    source = DIST / "AnimeBox"
    target = ARTIFACTS / name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    (target / "data").mkdir()
    (target / "library").mkdir()
    (target / "tools").mkdir()
    shutil.copy2(ROOT / ".env.example", target / ".env")
    shutil.copy2(ROOT / ".env.example", target / ".env.example")
    shutil.copy2(ROOT / "THIRD_PARTY.md", target / "THIRD_PARTY.md")
    shutil.copy2(RELEASE / "PORTABLE_README.txt", target / "README.txt")
    ffmpeg_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    shutil.copy2(ffmpeg, target / "tools" / ffmpeg_name)
    if os.name != "nt":
        (target / "AnimeBox").chmod(0o755)
        (target / "tools" / ffmpeg_name).chmod(0o755)
    return target, name


def archive(target: Path, name: str) -> Path:
    if platform.system() == "Linux":
        output = ARTIFACTS / f"{name}.tar.gz"
        with tarfile.open(output, "w:gz") as tf:
            tf.add(target, arcname=name)
    else:
        output = ARTIFACTS / f"{name}.zip"
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for path in target.rglob("*"):
                zf.write(path, Path(name) / path.relative_to(target))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (output.with_suffix(output.suffix + ".sha256")).write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Build native AnimeBox portable archive")
    parser.add_argument("--ffmpeg", help="Path to native ffmpeg executable")
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    ffmpeg = find_ffmpeg(args.ffmpeg)
    if not args.skip_frontend:
        run("npm", "ci", cwd=ROOT / "frontend")
        run("npm", "run", "build", cwd=ROOT / "frontend")
    if not args.skip_tests:
        run(sys.executable, "-m", "pytest", "-q")
    WORK.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    run(
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--workpath",
        str(WORK),
        "--distpath",
        str(DIST),
        str(RELEASE / "animebox.spec"),
    )
    target, name = assemble(ffmpeg)
    output = archive(target, name)
    print(f"Portable artifact: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
