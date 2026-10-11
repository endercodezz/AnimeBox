from __future__ import annotations

import sys
from pathlib import Path

from release import portable_main


def test_portable_module_does_not_import_backend_app() -> None:
    assert "backend.main" not in portable_main.__dict__
    assert "app" not in portable_main.__dict__


def test_print_banner_outputs_animebox_art(capsys) -> None:
    portable_main.print_banner()

    output = capsys.readouterr().out
    assert "_                  ____" in output
    assert "| |_) | _____" in output
    assert output.endswith("\n")


def test_main_prepares_root_before_importing_app(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "AnimeBox"
    foreign_cwd = tmp_path / "foreign"
    root.mkdir()
    foreign_cwd.mkdir()
    monkeypatch.chdir(foreign_cwd)
    monkeypatch.setattr(portable_main, "portable_root", lambda: root)
    monkeypatch.setattr(portable_main, "port_available", lambda _port: True)
    monkeypatch.setattr(portable_main.threading.Thread, "start", lambda _self: None)

    imported = sys.modules.get("backend.main")
    sys.modules.pop("backend.main", None)
    captured: dict[str, object] = {}

    class FakeServer:
        should_exit = False

        def __init__(self, config) -> None:
            captured["app"] = config.app
            captured["cwd"] = Path.cwd()
            captured["data_exists"] = (root / "data").is_dir()
            captured["library_exists"] = (root / "library").is_dir()

        async def serve(self) -> None:
            return None

    monkeypatch.setattr(portable_main.uvicorn, "Server", FakeServer)
    try:
        assert portable_main.main() == 0
    finally:
        if imported is not None:
            sys.modules["backend.main"] = imported
        else:
            sys.modules.pop("backend.main", None)

    assert captured["cwd"] == root
    assert captured["data_exists"] is True
    assert captured["library_exists"] is True


def test_file_logging_is_written_even_after_backend_configured_console(tmp_path: Path) -> None:
    import logging

    from backend.main import configure_logging

    configure_logging()  # backend import already installed console handlers in 1.x, silencing basicConfig
    log_path = tmp_path / "animebox.log"
    before = list(logging.getLogger().handlers)
    portable_main.setup_file_logging(log_path)
    try:
        logging.getLogger("animebox.test").warning("proxy http://user:secret@proxy.example:8080 failed")
        configure_logging()
        logging.getLogger("animebox.test").warning("proxy http://user:secret@proxy.example:8080 failed")
        for handler in logging.getLogger().handlers:
            handler.flush()
        text = log_path.read_text(encoding="utf-8")
        assert "failed" in text
        assert text.strip().splitlines()[-1].count("secret") == 0  # redaction applies to the file handler
    finally:
        for handler in list(logging.getLogger().handlers):
            if handler not in before:
                logging.getLogger().removeHandler(handler)
                handler.close()
