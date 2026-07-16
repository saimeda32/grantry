"""Pure helpers for the human-side commands (run, switch, populate).

Everything here is deterministic and free of network and process side effects,
so it is unit-tested directly. The CLI is a thin shell that calls these.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from datetime import datetime, timezone

from grantry.providers.base import Credentials


def env_from_credentials(creds: Credentials, region: str) -> dict[str, str]:
    """Build the AWS_* environment a subprocess or subshell needs to act as an
    identity. AWS_CREDENTIALS_EXPIRATION is ISO-8601 so SDKs refresh correctly.
    """
    expires = datetime.fromtimestamp(creds.expiration, tz=timezone.utc)
    return {
        "AWS_ACCESS_KEY_ID": creds.access_key_id,
        "AWS_SECRET_ACCESS_KEY": creds.secret_access_key,
        "AWS_SESSION_TOKEN": creds.session_token,
        "AWS_CREDENTIALS_EXPIRATION": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "AWS_DEFAULT_REGION": region,
        "AWS_REGION": region,
    }


def format_exports(env: dict[str, str]) -> str:
    """Render an env dict as shell export lines, safely quoted, so a caller can
    `eval "$(grantry switch <identity>)"` to adopt the identity in the shell.
    """
    return "\n".join(f"export {k}={shlex.quote(v)}" for k, v in env.items())


def profile_block(
    profile_name: str,
    account_id: str,
    role_name: str,
    start_url: str,
    sso_region: str,
    region: str,
) -> str:
    """Render one ~/.aws/config profile stanza for an identity. The
    grantry_managed marker lets populate reconcile only the profiles it owns.
    """
    return "\n".join(
        [
            f"[profile {profile_name}]",
            f"sso_start_url = {start_url}",
            f"sso_region = {sso_region}",
            f"sso_account_id = {account_id}",
            f"sso_role_name = {role_name}",
            f"region = {region}",
            "grantry_managed = true",
        ]
    )


@dataclass(frozen=True)
class ReconcilePlan:
    to_add: set[str] = field(default_factory=set)
    to_prune: set[str] = field(default_factory=set)
    kept: set[str] = field(default_factory=set)


def reconcile(existing: dict[str, dict[str, str]], desired: set[str]) -> ReconcilePlan:
    """Diff the desired profile set against what exists, touching only profiles
    grantry owns (marked grantry_managed). Hand-written profiles are never
    pruned. Returns which to add, prune, and keep.
    """
    managed = {name for name, body in existing.items() if body.get("grantry_managed") == "true"}
    to_add = {name for name in desired if name not in existing}
    to_prune = managed - desired
    kept = managed & desired
    return ReconcilePlan(to_add=to_add, to_prune=to_prune, kept=kept)
