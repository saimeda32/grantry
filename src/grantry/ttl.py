"""Human TTL strings (15m, 1h, 3600s) to and from seconds."""

from __future__ import annotations

import re

_UNITS = {"s": 1, "m": 60, "h": 3600}
_PATTERN = re.compile(r"^(\d+)([smh])$")


def parse_ttl(s: str) -> int:
    m = _PATTERN.match(s)
    if not m:
        raise ValueError(f"invalid ttl {s!r}: want a whole number followed by s, m, or h")
    return int(m.group(1)) * _UNITS[m.group(2)]


def format_ttl(seconds: int) -> str:
    for unit in ("h", "m"):
        size = _UNITS[unit]
        if seconds % size == 0 and seconds >= size:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"
