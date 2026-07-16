"""State home and path resolution. No secrets are ever stored here."""

from __future__ import annotations

import os
import pathlib


def grantry_home() -> pathlib.Path:
    override = os.environ.get("GRANTRY_HOME")
    home = pathlib.Path(override) if override else pathlib.Path.home() / ".grantry"
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    return home


def state_path(name: str) -> pathlib.Path:
    return grantry_home() / name
