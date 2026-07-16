"""A tiny on-disk cache of identity keys.

It exists only to make shell completion fast and offline: a TAB press reads
this file instead of waiting on an AWS API call. It holds nothing secret, just
the `account-name/role-name` strings you already see in `grantry ls`. Writing it
is best effort, because a completion cache is never worth failing a real command
over.
"""

from __future__ import annotations

import contextlib
import json

from grantry.config import state_path
from grantry.identity import Identity

_CACHE = "identities.json"


def write_cache(identities: list[Identity]) -> None:
    try:
        keys = sorted({i.key for i in identities})
        path = state_path(_CACHE)
        path.write_text(json.dumps(keys), encoding="utf-8")
        with contextlib.suppress(OSError):
            path.chmod(0o600)
    except OSError:
        pass


def read_keys() -> list[str]:
    try:
        data = json.loads(state_path(_CACHE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, list):
        return [str(x) for x in data]
    return []
