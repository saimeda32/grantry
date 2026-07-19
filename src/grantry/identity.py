"""The identity a caller assumes: an account plus an Identity Center role.

An identity is spelled 'account.role' everywhere grantry shows it: `grantry ls`,
policy patterns, the audit log, and the profile name written to ~/.aws/config.
Using the same string as the AWS profile name means one identifier works for both
`grantry run <id>` and the native `aws --profile <id>`. The dot is the separator;
the older 'account/role' slash form is still accepted as input so nothing that
was typed or written before keeps breaking.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass

# One identity segment (an account or role name) is safe to type on the command
# line and as an AWS profile name only if it stays within this allow-list. Any
# run of other characters, whitespace included, collapses to a single hyphen. '.'
# is kept because it separates the two segments; '/' is excluded so a sanitized
# name can never contain the legacy separator.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def shell_safe(name: str) -> str:
    """Sanitize one identity segment so it needs no quoting: any run of unsafe
    characters, whitespace included, collapses to a single hyphen and leading or
    trailing hyphens are trimmed. 'Acme Corp Account' becomes 'Acme-Corp-Account'.
    """
    return _UNSAFE.sub("-", name.strip()).strip("-")


def safe_profile_name(account_name: str, role_name: str) -> str:
    """The canonical spelling of an identity: 'account.role', sanitized per
    segment. This is exactly what grantry displays, what you type for
    'grantry run/switch/console', and the profile name grantry writes to
    ~/.aws/config, so the same string also works with the native 'aws --profile'.
    """
    acct = shell_safe(account_name)
    role = shell_safe(role_name)
    return f"{acct or 'account'}.{role or 'role'}"


@dataclass(frozen=True)
class Identity:
    account_id: str
    account_name: str
    role_name: str

    @property
    def key(self) -> str:
        return safe_profile_name(self.account_name, self.role_name)


def matches(pattern: str, ident: Identity) -> bool:
    """Match a policy pattern against an identity, case-insensitively.

    A pattern may separate the account and role segments with '.' (the canonical
    form, e.g. 'prod.AWSReadOnlyAccess') or '/' (also accepted). The account glob
    is matched against the account segment and the role glob against the role
    segment, so a wildcard cannot span the separator ('prod*' cannot leak into
    role names). A pattern that does not segment (like '*ReadOnly*'), or one whose
    segment match fails, falls back to matching the whole 'account.role' key; this
    also lets an exact key paste always resolve.
    """
    key = ident.key.lower()
    pat = pattern.lower()
    acct = shell_safe(ident.account_name).lower()
    role = shell_safe(ident.role_name).lower()
    acct_pat: str | None = None
    role_pat: str | None = None
    if pat.count("/") == 1:
        acct_pat, role_pat = pat.split("/", 1)
    elif "." in pat:
        acct_pat, role_pat = pat.split(".", 1)
    if (
        acct_pat is not None
        and role_pat is not None
        and fnmatch.fnmatch(acct, acct_pat)
        and fnmatch.fnmatch(role, role_pat)
    ):
        return True
    return fnmatch.fnmatch(key, pat)
