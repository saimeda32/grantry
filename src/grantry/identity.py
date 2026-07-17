"""The identity a caller assumes: an account plus an Identity Center role."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass

_WHITESPACE = re.compile(r"\s+")


def shell_safe(name: str) -> str:
    """Make a name easy to type on the command line: collapse any run of
    whitespace to a single hyphen, so 'Acme Corp Account' becomes
    'Acme-Corp-Account' and no quoting is needed. Credentials are minted by
    account id, so this only affects the human-facing name, never the lookup.
    """
    return _WHITESPACE.sub("-", name.strip())


@dataclass(frozen=True)
class Identity:
    account_id: str
    account_name: str
    role_name: str

    @property
    def key(self) -> str:
        return f"{shell_safe(self.account_name)}/{shell_safe(self.role_name)}"


def matches(pattern: str, ident: Identity) -> bool:
    """Match a policy pattern against an identity, case-insensitively.

    A pattern with a single '/' is matched segment by segment: the part before
    the slash against the account name, the part after against the role name.
    This stops a wildcard from spanning the separator (so 'prod*' cannot leak
    across the '/' into role names). A pattern with no '/' is matched against the
    whole 'account/role' key, for convenience patterns like '*ReadOnly*'. Names
    are matched in their shell-safe form, matching what 'grantry ls' prints.
    """
    key = ident.key.lower()
    pat = pattern.lower()
    acct = shell_safe(ident.account_name).lower()
    role = shell_safe(ident.role_name).lower()
    if pat.count("/") == 1 and "/" not in acct:
        acct_pat, role_pat = pat.split("/", 1)
        return fnmatch.fnmatch(acct, acct_pat) and fnmatch.fnmatch(role, role_pat)
    return fnmatch.fnmatch(key, pat)
