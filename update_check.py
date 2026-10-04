"""Compare the stamped local version to app_release.json (no auto-download)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from app_version import APP_VERSION, RELEASE_JSON_URL

RELEASE_JSON_NAME = "app_release.json"


def parse_version(text: str) -> tuple[int, ...]:
    parts = [int(p) for p in re.findall(r"\d+", str(text or ""))]
    return tuple(parts) if parts else (0,)


def version_newer(remote: str, installed: str = APP_VERSION) -> bool:
    return parse_version(remote) > parse_version(installed)


def _bundled_release_paths() -> list[Path]:
    import sys

    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", "") or ""
    if meipass:
        roots.append(Path(meipass))
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        roots.append(exe_dir / "_internal")
        roots.append(exe_dir)
    roots.append(Path(__file__).resolve().parent)
    roots.append(Path.cwd())
    out: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        path = root / RELEASE_JSON_NAME
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def read_local_release() -> Optional[dict[str, Any]]:
    for path in _bundled_release_paths():
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and str(data.get("version") or "").strip():
            data = dict(data)
            data["_source"] = str(path)
            return data
    return None


def read_remote_release(url: str = RELEASE_JSON_URL, timeout: float = 12.0) -> Optional[dict[str, Any]]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "TeslaVehicleSearch/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None
    if isinstance(data, dict) and str(data.get("version") or "").strip():
        data = dict(data)
        data["_source"] = url
        return data
    return None


def check_for_updates() -> dict[str, Any]:
    """Return a status dict for Help → Check for updates (never downloads Setup)."""
    installed = APP_VERSION
    remote = read_remote_release()
    source_label = "GitHub"
    if remote is None and RELEASE_JSON_URL.rstrip("/").endswith("/main/app_release.json"):
        # Some CDNs 404 on /main/ briefly for new repos; refs/heads/main is reliable.
        alt = RELEASE_JSON_URL.replace("/main/app_release.json", "/refs/heads/main/app_release.json")
        remote = read_remote_release(alt)
    if remote is None:
        remote = read_local_release()
        source_label = "local app_release.json"
    if remote is None:
        return {
            "ok": False,
            "installed": installed,
            "latest": None,
            "newer": False,
            "message": (
                f"Could not read a release manifest.\n\n"
                f"Installed version: {installed}\n"
                f"Tried GitHub raw URL and the bundled {RELEASE_JSON_NAME}."
            ),
        }
    latest = str(remote.get("version") or "").strip()
    notes = str(remote.get("notes") or "").strip()
    setup = str(remote.get("setup") or "").strip()
    newer = version_newer(latest, installed)
    if newer:
        msg = (
            f"A newer version is available.\n\n"
            f"Installed: {installed}\n"
            f"Latest ({source_label}): {latest}\n"
        )
        if setup:
            msg += f"Setup file: {setup}\n"
        if notes:
            msg += f"\nNotes: {notes}\n"
        msg += "\nThis check does not download or install anything."
    else:
        msg = (
            f"You are up to date.\n\n"
            f"Installed: {installed}\n"
            f"Latest ({source_label}): {latest}\n"
        )
        if notes:
            msg += f"\nNotes: {notes}\n"
    return {
        "ok": True,
        "installed": installed,
        "latest": latest,
        "newer": newer,
        "setup": setup,
        "notes": notes,
        "source": remote.get("_source"),
        "message": msg,
    }
