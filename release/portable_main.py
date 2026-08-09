from __future__ import annotations

import asyncio
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn


BANNER = r"""
                 _                  ____
     /\         (_)                |  _ \
    /  \   _ __  _ _ __ ___   ___  | |_) | _____  __
   / /\ \ | '_ \| | '_ ` _ \ / _ \ |  _ < / _ \ \/ /
  / ____ \| | | | | | | | | |  __/ | |_) | (_) >  <
 /_/    \_\_| |_|_|_| |_| |_|\___| |____/ \___/_/\_\

"""


def print_banner() -> None:
    print(BANNER, flush=True)


def portable_root() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def ensure_runtime_files(root: Path) -> None:
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "library").mkdir(parents=True, exist_ok=True)
    env_path = root / ".env"
    if not env_path.exists():
        example = Path(getattr(sys, "_MEIPASS", root)) / ".env.example"
        if example.is_file():
            env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")


def configured_port(root: Path) -> int:
    env_path = root / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("PORT="):
                try:
                    return int(line.split("=", 1)[1].strip())
                except ValueError:
                    pass
    return 8787


def port_available(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def wait_and_open(url: str) -> None:
    health = f"{url}/api/health"
    for _ in range(120):
        try:
            with urllib.request.urlopen(health, timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            time.sleep(0.25)
    logging.error("AnimeBox did not become ready at %s", url)


def main() -> int:
    print_banner()
    root = portable_root()
    ensure_runtime_files(root)
    os.chdir(root)

    from backend.main import app, enable_shutdown, wait_for_shutdown

    enable_shutdown()

    log_path = root / "data" / "animebox.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")],
    )
    port = configured_port(root)
    if not port_available(port):
        url = f"http://127.0.0.1:{port}"
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=2) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return 0
        except OSError:
            pass
        logging.error("Port %s is already used. Change PORT in .env.", port)
        return 1

    url = f"http://127.0.0.1:{port}"
    logging.info("Starting AnimeBox at %s", url)
    threading.Thread(target=wait_and_open, args=(url,), daemon=True).start()

    async def serve() -> None:
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info"))
        server_task = asyncio.create_task(server.serve())
        shutdown_task = asyncio.create_task(wait_for_shutdown())
        done, pending = await asyncio.wait({server_task, shutdown_task}, return_when=asyncio.FIRST_COMPLETED)
        if shutdown_task in done:
            server.should_exit = True
        await server_task
        for task in pending:
            task.cancel()

    asyncio.run(serve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
