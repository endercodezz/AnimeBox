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
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
WORK = RELEASE / "work"
DIST = RELEASE / "dist"
ARTIFACTS = RELEASE / "artifacts"


def run(*args: str, cwd: Path = ROOT) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def output(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def target_name(explicit: str | None = None) -> str:
    if explicit:
        if Path(explicit).name != explicit or explicit in {".", ".."} or not explicit.startswith("AnimeBox-"):
            raise ValueError("target name must be an AnimeBox-* directory name without path separators")
        return explicit
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


def macos_dependencies(binary: Path) -> list[tuple[str, Path]]:
    dependencies: list[tuple[str, Path]] = []
    lines = output("otool", "-L", str(binary)).splitlines()[1:]
    dylib_id = output("otool", "-D", str(binary)).splitlines()[1:]
    own_id = dylib_id[0].strip() if dylib_id else None
    for line in lines:
        load_path = line.strip().split(" (compatibility version", 1)[0]
        if load_path == own_id or load_path.startswith(("/usr/lib/", "/System/Library/")):
            continue
        if load_path.startswith(("@loader_path/", "@executable_path/", "@rpath/")):
            raise RuntimeError(f"cannot resolve existing relative dependency {load_path} in {binary}")
        path = Path(load_path)
        if not path.is_file():
            raise RuntimeError(f"missing FFmpeg dependency {load_path}")
        dependencies.append((load_path, path.resolve()))
    return dependencies


def bundle_macos_ffmpeg(ffmpeg: Path, tools: Path) -> Path:
    executable = tools / "ffmpeg"
    shutil.copy2(ffmpeg, executable)
    executable.chmod(0o755)

    library_dir = tools / "lib"
    library_dir.mkdir()
    queue = deque([executable])
    dependencies_by_binary: dict[Path, list[tuple[str, Path]]] = {}
    copied: dict[Path, Path] = {}

    while queue:
        binary = queue.popleft()
        dependencies = macos_dependencies(binary)
        dependencies_by_binary[binary] = dependencies
        for _load_path, dependency in dependencies:
            if dependency in copied:
                continue
            destination = library_dir / dependency.name
            conflicting = next((source for source, target in copied.items() if target == destination), None)
            if conflicting:
                raise RuntimeError(
                    f"FFmpeg dependency name collision: {conflicting} and {dependency} both map to {destination.name}"
                )
            shutil.copy2(dependency, destination)
            copied[dependency] = destination
            queue.append(destination)

    for binary, dependencies in dependencies_by_binary.items():
        for load_path, dependency in dependencies:
            bundled = copied[dependency]
            relative = f"@loader_path/lib/{bundled.name}" if binary == executable else f"@loader_path/{bundled.name}"
            run("install_name_tool", "-change", load_path, relative, str(binary))
        if binary != executable:
            run("install_name_tool", "-id", f"@loader_path/{binary.name}", str(binary))

    for binary in [*copied.values(), executable]:
        run("codesign", "--force", "--sign", "-", "--timestamp=none", str(binary))
    validate_macos_ffmpeg(executable)
    return executable


def validate_macos_ffmpeg(executable: Path) -> None:
    binaries = [executable, *sorted((executable.parent / "lib").glob("*.dylib"))]
    for binary in binaries:
        for dependency in output("otool", "-L", str(binary)).splitlines()[1:]:
            load_path = dependency.strip().split(" (compatibility version", 1)[0]
            if load_path.startswith(("/usr/lib/", "/System/Library/", "@loader_path/")):
                continue
            raise RuntimeError(f"non-portable Mach-O dependency in {binary}: {load_path}")
        run("codesign", "--verify", "--strict", str(binary))
    run(str(executable), "-version")


def assemble(ffmpeg: Path, explicit_name: str | None = None) -> tuple[Path, str]:
    name = target_name(explicit_name)
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
    if platform.system() == "Darwin":
        scripts_dir = target / "scripts"
        scripts_dir.mkdir()
        shutil.copy2(ROOT / "scripts" / "grant-macos-permissions.sh", scripts_dir)
    ffmpeg_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    if platform.system() == "Darwin":
        bundle_macos_ffmpeg(ffmpeg, target / "tools")
    else:
        shutil.copy2(ffmpeg, target / "tools" / ffmpeg_name)
    if os.name != "nt":
        (target / "AnimeBox").chmod(0o755)
        (target / "tools" / ffmpeg_name).chmod(0o755)
        if platform.system() == "Darwin":
            (target / "scripts" / "grant-macos-permissions.sh").chmod(0o755)
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
    parser.add_argument("--target-name", help="Override artifact name, for example AnimeBox-SteamDeck-x64")
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    ffmpeg = find_ffmpeg(args.ffmpeg)
    if not args.skip_frontend:
        npm = "npm.cmd" if os.name == "nt" else "npm"
        run(npm, "ci", cwd=ROOT / "frontend")
        run(npm, "run", "build", cwd=ROOT / "frontend")
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
    target, name = assemble(ffmpeg, args.target_name)
    output = archive(target, name)
    print(f"Portable artifact: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
