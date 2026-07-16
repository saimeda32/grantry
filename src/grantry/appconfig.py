"""Optional user defaults from ~/.grantry/config.toml.

Everything here is optional and has a safe fallback, so grantry works with no
config file at all. Example:

    [defaults]
    ttl = "30m"                                     # default lifetime for run/switch/console
    start_url = "https://acme.awsapps.com/start"    # your Identity Center, for first use
    region = "us-east-1"                            # fallback region when none is set otherwise

A missing or malformed file is ignored rather than fatal: bad config must never
stop you getting credentials.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from grantry.config import state_path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised only on Python 3.10
    import tomli as tomllib

_FILE = "config.toml"
_DEFAULT_TTL = "1h"


@dataclass(frozen=True)
class AppConfig:
    ttl: str = _DEFAULT_TTL
    start_url: str | None = None
    region: str | None = None


def _str_or(value: object, fallback: str | None) -> str | None:
    return value if isinstance(value, str) else fallback


def load_config() -> AppConfig:
    path = state_path(_FILE)
    try:
        raw = path.read_bytes()
    except OSError:
        return AppConfig()
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return AppConfig()
    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict):
        return AppConfig()
    return AppConfig(
        ttl=_str_or(defaults.get("ttl"), _DEFAULT_TTL) or _DEFAULT_TTL,
        start_url=_str_or(defaults.get("start_url"), None),
        region=_str_or(defaults.get("region"), None),
    )
