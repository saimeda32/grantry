"""The identity a caller assumes: an account plus an Identity Center role."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    account_id: str
    account_name: str
    role_name: str

    @property
    def key(self) -> str:
        return f"{self.account_name}/{self.role_name}"


def matches(pattern: str, ident: Identity) -> bool:
    return fnmatch.fnmatch(ident.key.lower(), pattern.lower())
