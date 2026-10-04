"""Stamp installer version into Help/About and app_release.json.

Used by build_setup.bat so cmd.exe never has to parse python -c quotes.

Env:
  TESLA_SEARCH_APP_VER      version string (required for stamp/release)
  TESLA_SEARCH_BUILD_NAME   exe/folder name (default Tesla Search)
  TESLA_SEARCH_SETUP_NAME   setup basename without .exe (default TeslaSearch_Setup)

Actions:
  auto     print auto version yyyy.mm.dd.hhmm (local date and 24-hour time)
  print    print current app_version.APP_VERSION
  stamp    write TESLA_SEARCH_APP_VER into app_version.py (+ packaged copy)
  release  write app_release.json
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_VERSION = ROOT / "app_version.py"
_APP_VER_RE = re.compile(r"""APP_VERSION\s*=\s*['\"][^'\"]*['\"]""")
_DUNDER_VER_RE = re.compile(r"""__version__\s*=\s*['\"][^'\"]*['\"]""")


def _auto_version(when: datetime | None = None) -> str:
    d = when or datetime.now()
    return f"{d.year:04d}.{d.month:02d}.{d.day:02d}.{d.hour:02d}{d.minute:02d}"


def _current_version() -> str:
    text = SRC_VERSION.read_text(encoding="utf-8")
    match = re.search(r"""APP_VERSION\s*=\s*['\"]([^'\"]*)['\"]""", text)
    if match:
        return match.group(1)
    match = re.search(r"""__version__\s*=\s*['\"]([^'\"]*)['\"]""", text)
    return match.group(1) if match else "0.0.0.0000"


def _setup_basename(build_name: str) -> str:
    env = os.environ.get("TESLA_SEARCH_SETUP_NAME", "").strip()
    if env:
        return env[:-4] if env.lower().endswith(".exe") else env
    # Prefer compact installer name without spaces.
    compact = "".join(ch for ch in build_name if ch.isalnum() or ch in "-_") or "TeslaSearch"
    if not compact.lower().endswith("_setup"):
        compact = f"{compact}_Setup"
    return compact


def _packaged_version_paths(build_name: str) -> list[Path]:
    named = ROOT / "dist" / build_name / "_internal" / "app_version.py"
    found = [named]
    dist = ROOT / "dist"
    if dist.is_dir():
        for path in sorted(dist.glob("*/_internal/app_version.py")):
            if path not in found:
                found.append(path)
    return found


def _ensure_packaged_version(build_name: str) -> Path | None:
    for path in _packaged_version_paths(build_name):
        if path.is_file():
            return path
    internal = ROOT / "dist" / build_name / "_internal"
    if not internal.is_dir():
        dist = ROOT / "dist"
        if dist.is_dir():
            matches = sorted(p for p in dist.glob("*/_internal") if p.is_dir())
            if len(matches) == 1:
                internal = matches[0]
    if not internal.is_dir():
        return None
    dest = internal / "app_version.py"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC_VERSION, dest)
    print(f"        Copied About source into ONEDIR {dest}")
    return dest


def _stamp_about(version: str, build_name: str) -> None:
    text = SRC_VERSION.read_text(encoding="utf-8")
    new, nsub = _APP_VER_RE.subn(f"APP_VERSION = {version!r}", text, count=1)
    if nsub != 1:
        raise SystemExit("could not find APP_VERSION in app_version.py")
    new2, n2 = _DUNDER_VER_RE.subn(f"__version__ = APP_VERSION", new, count=1)
    if n2:
        new = new2
    else:
        # Keep __version__ string in sync if it was a literal.
        new, _ = re.subn(
            r"""__version__\s*=\s*['\"][^'\"]*['\"]""",
            f"__version__ = {version!r}",
            new,
            count=1,
        )
    SRC_VERSION.write_text(new, encoding="utf-8")
    print(f"        Wrote {SRC_VERSION} -> {version}")
    pack = _ensure_packaged_version(build_name)
    if pack is None:
        print("        Note: dist ONEDIR not found (run build_exe.bat first)")
        return
    ptext = pack.read_text(encoding="utf-8")
    pnew, pn = _APP_VER_RE.subn(f"APP_VERSION = {version!r}", ptext, count=1)
    if pn:
        pnew2, pn2 = _DUNDER_VER_RE.subn("__version__ = APP_VERSION", pnew, count=1)
        if pn2:
            pnew = pnew2
        pack.write_text(pnew, encoding="utf-8")
        print(f"        Wrote packaged About source {pack}")
    else:
        print("        WARNING: packaged app_version.py has no APP_VERSION assignment")


def _write_release(version: str, build_name: str) -> None:
    setup = _setup_basename(build_name)
    if not setup.lower().endswith(".exe"):
        setup = f"{setup}.exe"
    path = ROOT / "app_release.json"
    path.write_text(
        json.dumps(
            {
                "version": version,
                "setup": setup,
                "notes": "",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"        {path.resolve()} version={version} setup={setup}")


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in {"auto", "print", "stamp", "release"}:
        print("usage: stamp_setup_version.py auto|print|stamp|release", file=sys.stderr)
        return 2
    action = argv[0]
    build_name = os.environ.get("TESLA_SEARCH_BUILD_NAME", "Tesla Search").strip() or "Tesla Search"
    version = os.environ.get("TESLA_SEARCH_APP_VER", "").strip()
    if action == "auto":
        print(_auto_version())
        return 0
    if action == "print":
        print(_current_version())
        return 0
    if not version:
        print("ERROR: TESLA_SEARCH_APP_VER is empty", file=sys.stderr)
        return 1
    if action == "stamp":
        _stamp_about(version, build_name)
        return 0
    _write_release(version, build_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
