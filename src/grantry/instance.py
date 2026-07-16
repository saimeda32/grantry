"""Remembered Identity Center instances (start URL + region).

grantry remembers every instance you log in to, and which one is current, so
people who work across more than one AWS organization can switch without
re-typing the start URL. This is not a secret, so it lives as plain JSON in the
state dir, not the keychain.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from grantry.config import state_path

_FILE = "instances.json"
_LEGACY = "instance.json"


@dataclass(frozen=True)
class InstanceConfig:
    start_url: str
    region: str


def _short_name(start_url: str) -> str:
    # A friendly handle derived from the start URL host, e.g.
    # https://acme.awsapps.com/start -> "acme".
    host = start_url.split("://", 1)[-1].split("/", 1)[0]
    return host.split(".", 1)[0] or host


def _read() -> dict[str, Any]:
    path = state_path(_FILE)
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            # A corrupt or hand-mangled state file must not crash every command.
            return {"current": None, "instances": {}}
        if not isinstance(loaded, dict) or "instances" not in loaded:
            return {"current": None, "instances": {}}
        result: dict[str, Any] = loaded
        return result
    # Migrate the old single-instance file if present.
    legacy = state_path(_LEGACY)
    if legacy.exists():
        data = json.loads(legacy.read_text())
        name = _short_name(data["start_url"])
        migrated = {
            "current": name,
            "instances": {name: {"start_url": data["start_url"], "region": data["region"]}},
        }
        state_path(_FILE).write_text(json.dumps(migrated))
        return migrated
    return {"current": None, "instances": {}}


def _write(data: dict[str, Any]) -> None:
    state_path(_FILE).write_text(json.dumps(data))


def save_instance(start_url: str, region: str) -> None:
    """Record an instance and make it current."""
    data = _read()
    name = _short_name(start_url)
    data["instances"][name] = {"start_url": start_url, "region": region}
    data["current"] = name
    _write(data)


def load_instance() -> InstanceConfig | None:
    """The current instance, or None if grantry has never been pointed anywhere."""
    data = _read()
    current = data.get("current")
    if not current or current not in data["instances"]:
        return None
    entry = data["instances"][current]
    return InstanceConfig(start_url=entry["start_url"], region=entry["region"])


def list_instances() -> list[tuple[str, InstanceConfig, bool]]:
    """All known instances as (name, config, is_current), sorted by name."""
    data = _read()
    current = data.get("current")
    out = []
    for name in sorted(data["instances"]):
        entry = data["instances"][name]
        out.append((name, InstanceConfig(entry["start_url"], entry["region"]), name == current))
    return out


def use_instance(name: str) -> InstanceConfig | None:
    """Make the named instance current (accepts a unique prefix). Returns it, or
    None if the name matches no known instance.
    """
    data = _read()
    # An exact name always wins, even if it is also a prefix of another (e.g.
    # 'prod' when both 'prod' and 'prod2' exist).
    if name in data["instances"]:
        chosen = name
    else:
        prefixed = [n for n in data["instances"] if n.startswith(name)]
        if len(prefixed) != 1:
            return None
        chosen = prefixed[0]
    data["current"] = chosen
    _write(data)
    entry = data["instances"][chosen]
    return InstanceConfig(entry["start_url"], entry["region"])
