"""Application version metadata (Help → About and installer stamp).

build_setup.bat / scripts/stamp_setup_version.py rewrite APP_VERSION (and
__version__) as a calendar stamp Year.MM.DD.HHMM. When frozen, About re-reads
this file from the ONEDIR _internal folder so the stamped value is visible.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

APP_VERSION = '2026.10.03.2132'
__version__ = APP_VERSION

APP_NAME = "Tesla Vehicle Search"
APP_DESCRIPTION = (
    "Find the best Tesla vehicle deals from Tesla's public US inventory "
    "across locations, ranked by lowest effective price."
)
APP_PUBLISHER = "bpnguyengit"

# GitHub raw URL used by Help → Check for updates (falls back to bundled JSON).
RELEASE_JSON_URL = (
    "https://raw.githubusercontent.com/bpnguyengit/Tesla-vehicle-Search/refs/heads/main/app_release.json"
)

_VER_RE = re.compile(
    r"""(?:APP_VERSION|__version__)\s*=\s*['\"]([^'\"]*)['\"]"""
)


def _version_candidates() -> list[Path]:
    out: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", "") or ""
    if meipass:
        out.append(Path(meipass) / "app_version.py")
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        out.append(exe_dir / "_internal" / "app_version.py")
        out.append(exe_dir / "app_version.py")
    try:
        out.append(Path(__file__).resolve())
    except Exception:
        pass
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in out:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def _refresh_version() -> None:
    global APP_VERSION, __version__
    for path in _version_candidates():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        # Prefer APP_VERSION assignment when both exist.
        match = re.search(r"""APP_VERSION\s*=\s*['\"]([^'\"]*)['\"]""", text)
        if not match:
            match = re.search(r"""__version__\s*=\s*['\"]([^'\"]*)['\"]""", text)
        if match and match.group(1).strip():
            APP_VERSION = match.group(1).strip()
            __version__ = APP_VERSION
            return


_refresh_version()
