# -*- mode: python ; coding: utf-8 -*-
# PyInstaller one-folder build for Tesla Vehicle Search

import os
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
_raw = os.environ.get("TESLA_SEARCH_BUILD_NAME", "Tesla Search").strip() or "Tesla Search"
_BUILD_NAME = "".join(ch for ch in _raw if ch.isalnum() or ch in "-_ ") or "Tesla Search"
_BUILD_NAME = " ".join(_BUILD_NAME.split())
block_cipher = None


def _runtime_datas():
    items = []
    for name in ("app_version.py", "app_release.json", "inventory.py", "update_check.py"):
        p = ROOT / name
        if p.is_file():
            items.append((str(p), "."))
    return items


a = Analysis(
    [str(ROOT / "tesla_search.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=_runtime_datas(),
    hiddenimports=[
        "inventory",
        "app_version",
        "update_check",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tests", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=_BUILD_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=_BUILD_NAME,
)
