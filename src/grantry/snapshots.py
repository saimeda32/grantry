"""Snapshot org assignments over time and diff them, so an operator can see who
gained or lost access between two crawls. Snapshots are plain JSON files under
~/.grantry/snapshots/; the diff is a pure function.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from grantry.admin import Assignment
from grantry.config import grantry_home


def _key(a: Assignment) -> tuple[str, str, str, str]:
    # An assignment's identity for diffing: who, which permission set, which
    # account. The human-readable names are what an operator reviews.
    return (a.principal_type, a.principal_name, a.permission_set_name, a.account_id)


def diff_assignments(
    old: list[Assignment], new: list[Assignment]
) -> tuple[list[Assignment], list[Assignment]]:
    """Return (added, removed): assignments present in new but not old, and in
    old but not new. Order is stable (sorted by their key).
    """
    old_keys = {_key(a) for a in old}
    new_keys = {_key(a) for a in new}
    added = sorted((a for a in new if _key(a) not in old_keys), key=_key)
    removed = sorted((a for a in old if _key(a) not in new_keys), key=_key)
    return added, removed


def _snapshot_dir() -> Path:
    d = grantry_home() / "snapshots"
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    return d


def save_snapshot(assignments: list[Assignment], at: str) -> Path:
    """Write a snapshot named by the timestamp `at` (e.g. 2026-07-16T02-30-00Z)."""
    path = _snapshot_dir() / f"{at}.json"
    path.write_text(json.dumps([asdict(a) for a in assignments]))
    return path


def _load(path: Path) -> list[Assignment]:
    rows = json.loads(path.read_text())
    return [Assignment(**r) for r in rows]


def latest_snapshot() -> list[Assignment] | None:
    """The most recent saved snapshot, or None if there are none."""
    files = sorted(_snapshot_dir().glob("*.json"))
    if not files:
        return None
    return _load(files[-1])
