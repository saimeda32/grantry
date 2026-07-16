"""Generate a starter policy from a user's actual access, so setup is one
command instead of hand-authoring patterns that must match real role names.

The generated policy is safe by default: agents may use read-only roles
anywhere, admin roles and production or management accounts are denied, and the
human keeps broad access. Every real identity is listed as a comment so the
user edits from a working, matched starting point.
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
    lines.append("# Edit freely. Deny beats allow. For agents an unlisted identity is denied;")
    lines.append("# for humans it is allowed. TTLs are capped per section.")
    lines.append("#")
    lines.append("# Your accessible identities:")
    for i in sorted(identities, key=lambda x: x.key):
        lines.append(f"#   {i.key}")
    lines.append("")
    lines.append("agents:")
    lines.append("  allow:")
    if readonly_roles:
        for r in readonly_roles:
            lines.append(f'    - identity: "*/{r}"          # read-only anywhere')
    else:
        lines.append('    # - identity: "*/SomeRole"   # no read-only role detected; add yours')
    lines.append("  deny:")
    for r in admin_roles:
        lines.append(f'    - identity: "*/{r}"')
    for a in sensitive_accounts:
        lines.append(f'    - identity: "{a}/*"           # sensitive account')
    if not admin_roles and not sensitive_accounts:
        lines.append('    # - identity: "*/AdminRole"  # add roles or accounts to deny')
    lines.append("  max_ttl: 15m")
    lines.append("humans:")
    lines.append("  max_ttl: 12h")
    return "\n".join(lines) + "\n"
