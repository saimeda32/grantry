"""Remembered Identity Center instance (start URL + region).

Give grantry the instance once; it saves it here and reads it back on every
later command, so you never pass it again. This is not a secret, so it lives as
plain JSON in the state dir, not the keychain.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from grantry.config import state_path

_FILE = "instance.json"


@dataclass(frozen=True)
class InstanceConfig:
    start_url: str
    region: str


def save_instance(start_url: str, region: str) -> None:
    path = state_path(_FILE)
    path.write_text(json.dumps({"start_url": start_url, "region": region}))


def load_instance() -> InstanceConfig | None:
    path = state_path(_FILE)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return InstanceConfig(start_url=data["start_url"], region=data["region"])
