"""Is a newer grantry on PyPI? Checked cheaply and never fatally.

`grantry doctor` does a live check; the post-login nudge uses a once-a-day cache
so it never slows a command or hammers PyPI, and honors GRANTRY_NO_UPDATE_CHECK.
Every network path degrades to "unknown" (None) rather than raising.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from collections.abc import Callable
from typing import Any

from grantry.config import state_path

_PYPI_JSON = "https://pypi.org/pypi/grantry/json"
_CACHE_FILE = ".version-check"
_TTL_SECONDS = 86_400  # re-check PyPI at most once a day for the passive nudge


def _parse(version: str) -> tuple[int, ...]:
    """A tolerant version tuple: '0.13.0' -> (0, 13, 0). Non-numeric suffixes on a
    segment (e.g. '1rc2') are truncated to their leading digits."""
    parts: list[int] = []
    for seg in version.strip().split("."):
        digits = ""
        for ch in seg:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    """True if `latest` is a strictly higher version than `current`."""
    try:
        return _parse(latest) > _parse(current)
    except Exception:
        return False


def fetch_latest(timeout: float = 2.0) -> str | None:
    """The newest grantry version on PyPI, or None on any error (offline, timeout,
    unexpected payload). Never raises."""
    import urllib.request

    try:
        with urllib.request.urlopen(_PYPI_JSON, timeout=timeout) as resp:
            data = json.loads(resp.read())
        version = data["info"]["version"]
        return version if isinstance(version, str) else None
    except Exception:
        return None


def cached_latest(
    fetch: Callable[[], str | None] = fetch_latest,
    now: Callable[[], float] = time.time,
) -> str | None:
    """The latest version, served from a once-a-day cache. Re-fetches when the
    cache is stale and persists the result (a failed fetch still stamps the time,
    so we do not retry on every command). None if never successfully fetched."""
    path = state_path(_CACHE_FILE)
    stamp = now()
    prev: dict[str, Any] = {}
    try:
        if path.exists():
            prev = json.loads(path.read_text())
            if stamp - float(prev.get("at", 0)) < _TTL_SECONDS:
                latest = prev.get("latest")
                return latest if isinstance(latest, str) else None
    except Exception:
        prev = {}
    latest = fetch()
    if latest is None and isinstance(prev.get("latest"), str):
        latest = prev["latest"]  # keep the last known good value on a failed fetch
    with contextlib.suppress(OSError):
        path.write_text(json.dumps({"at": stamp, "latest": latest}))
    return latest


def nudge(
    current: str,
    fetch: Callable[[], str | None] = fetch_latest,
    now: Callable[[], float] = time.time,
) -> str | None:
    """A one-line upgrade message if a newer version is known, else None. Silenced
    by GRANTRY_NO_UPDATE_CHECK. Uses the daily cache, so it is cheap to call."""
    if os.environ.get("GRANTRY_NO_UPDATE_CHECK"):
        return None
    latest = cached_latest(fetch=fetch, now=now)
    if latest and is_newer(latest, current):
        return f"grantry {latest} is available (you have {current}). Upgrade: pipx upgrade grantry"
    return None
