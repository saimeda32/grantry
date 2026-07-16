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
    """Match a policy pattern against an identity, case-insensitively.

    A pattern with a single '/' is matched segment by segment: the part before
    the slash against the account name, the part after against the role name.
    This stops a wildcard from spanning the separator (so 'prod*' cannot leak
    across the '/' into role names). A pattern with no '/' is matched against the
    whole 'account/role' key, for convenience patterns like '*ReadOnly*'.
    """
    key = ident.key.lower()
    pat = pattern.lower()
    if pat.count("/") == 1 and ident.account_name.count("/") == 0:
        acct_pat, role_pat = pat.split("/", 1)
        return fnmatch.fnmatch(ident.account_name.lower(), acct_pat) and fnmatch.fnmatch(
            ident.role_name.lower(), role_pat
        )
    return fnmatch.fnmatch(key, pat)
