from __future__ import annotations

import sys
from pathlib import Path

from release import portable_main


def test_portable_module_does_not_import_backend_app() -> None:
    assert "backend.main" not in portable_main.__dict__
    assert "app" not in portable_main.__dict__


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

    def fake_run(app, **_kwargs) -> None:
        captured["app"] = app
        captured["cwd"] = Path.cwd()
        captured["data_exists"] = (root / "data").is_dir()
        captured["library_exists"] = (root / "library").is_dir()

    monkeypatch.setattr(portable_main.uvicorn, "run", fake_run)
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
