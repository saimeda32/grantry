"""Generate a starter policy from a user's actual access.

The starter is PERMISSIVE on purpose: agents may use any role, so grantry works
the moment you install it. The generated file explains, loudly, how to restrict
it, and lists every identity you have so tightening it is a copy-and-edit job.
If you never run `grantry init`, the engine denies agents by default (a missing
policy is fail-closed); the permissive default is only what `init` writes.
"""

from __future__ import annotations

from grantry.identity import Identity

_READONLY = "readonly"
_ADMIN = "admin"
_SENSITIVE_ACCOUNTS = ("prod", "master")


def scaffold_policy(identities: list[Identity], generated_on: str) -> str:
    roles = sorted({i.role_name for i in identities})
    accounts = sorted({i.account_name for i in identities})
    readonly_roles = [r for r in roles if _READONLY in r.lower()]
    admin_roles = [r for r in roles if _ADMIN in r.lower()]
    sensitive_accounts = [a for a in accounts if any(s in a.lower() for s in _SENSITIVE_ACCOUNTS)]

    lines: list[str] = []
    lines.append(f"# grantry policy, generated from your access on {generated_on}.")
    lines.append("#")
    lines.append("# THIS STARTER IS PERMISSIVE: agents may use ANY role you can, so grantry")
    lines.append("# works right away. To restrict what your agents can do, replace the")
    lines.append('#   - identity: "*/*"')
    lines.append("# line below with the specific accounts and roles you want to allow, and")
    lines.append("# add deny rules. A pattern is account-name/role-name; * is a wildcard")
    lines.append("# within a segment. Deny beats allow. For agents, anything not allowed is")
    lines.append("# denied once you remove the */* line.")
    lines.append("#")
    lines.append("# A safer starting point, if you want it, is to delete the */* allow and")
    lines.append("# uncomment these instead:")
    if readonly_roles:
        for r in readonly_roles:
            lines.append(f'#   - identity: "*/{r}"          # read-only anywhere')
    else:
        lines.append('#   - identity: "*/AWSReadOnlyAccess"   # your read-only role')
    lines.append("# with these denies:")
    for r in admin_roles:
        lines.append(f'#   - identity: "*/{r}"')
    for a in sensitive_accounts:
        lines.append(f'#   - identity: "{a}/*"           # sensitive account')
    lines.append("#")
    lines.append("# Your accessible identities:")
    for i in sorted(identities, key=lambda x: x.key):
        lines.append(f"#   {i.key}")
    lines.append("")
    lines.append("agents:")
    lines.append("  allow:")
    lines.append('    - identity: "*/*"          # PERMISSIVE: any account, any role. Restrict me.')
    lines.append("  deny: []")
    lines.append("  max_ttl: 15m")
    lines.append("humans:")
    lines.append("  max_ttl: 12h")
    return "\n".join(lines) + "\n"
