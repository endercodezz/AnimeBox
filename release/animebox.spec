# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
anicli_datas, anicli_binaries, anicli_hidden = collect_all("anicli_api")
hiddenimports = sorted(set(
    anicli_hidden
    + collect_submodules("anicli_api.source", on_error="raise")
    + collect_submodules("anicli_api.player", on_error="raise")
    + ["aiosqlite", "sqlalchemy.dialects.sqlite.aiosqlite"]
    # httpx imports these lazily (HTTP/2 transport, SOCKS proxies); PyInstaller cannot see them.
    + collect_submodules("h2") + collect_submodules("hpack") + collect_submodules("hyperframe")
    + ["socksio", "brotli"]
    + collect_submodules("backend")
))

datas = anicli_datas + [
    (str(ROOT / "frontend" / "dist"), "frontend/dist"),
    (str(ROOT / ".env.example"), "."),
    (str(ROOT / "THIRD_PARTY.md"), "."),
    (str(ROOT / "README.md"), "."),
]

a = Analysis(
    [str(ROOT / "release" / "portable_main.py")],
    pathex=[str(ROOT)],
    binaries=anicli_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AnimeBox",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AnimeBox",
)
