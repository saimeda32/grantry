"""Pure helpers for the human-side commands (run, switch, populate).

Everything here is deterministic and free of network and process side effects,
so it is unit-tested directly. The CLI is a thin shell that calls these.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from datetime import datetime, timezone

# safe_profile_name is the canonical identity spelling, defined once in identity
# so the profile name grantry writes always equals the identity key it shows.
# Re-exported here (import-as form) because the human-side commands and tests
# import it from humanops.
from grantry.identity import safe_profile_name as safe_profile_name
from grantry.providers.base import Credentials


def credential_process_json(creds: Credentials) -> str:
    """Render credentials in the exact JSON shape AWS SDKs expect from a
    credential_process command, so a profile with
    `credential_process = grantry credential-process --identity X` sources its
    credentials through grantry (and every mint is audited).
    """
    import json

    expires = datetime.fromtimestamp(creds.expiration, tz=timezone.utc)
    return json.dumps(
        {
            "Version": 1,
            "AccessKeyId": creds.access_key_id,
            "SecretAccessKey": creds.secret_access_key,
            "SessionToken": creds.session_token,
            "Expiration": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )


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


def parse_profiles(text: str) -> dict[str, dict[str, str]]:
    """Parse an ~/.aws/config body into {profile_name: {key: value}}. Only
    [profile NAME] sections are returned. Tolerant of blank lines and comments.
    """
    profiles: dict[str, dict[str, str]] = {}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            header = stripped[1:-1].strip()
            current = header[len("profile ") :] if header.startswith("profile ") else None
            if current is not None:
                profiles[current] = {}
        elif current is not None and "=" in stripped and not stripped.startswith("#"):
            key, _, value = stripped.partition("=")
            profiles[current][key.strip()] = value.strip()
    return profiles


def strip_profiles(text: str, names: set[str]) -> str:
    """Remove the [profile NAME] sections for the given names, preserving every
    other line (comments and hand-written profiles) verbatim.
    """
    if not names:
        return text
    out: list[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            header = stripped[1:-1].strip()
            name = header[len("profile ") :] if header.startswith("profile ") else None
            skipping = name in names
        elif skipping and stripped == "":
            # A blank line ends the managed block. Stop skipping so comments and
            # blank lines that belong to the NEXT (hand-written) section survive.
            skipping = False
            out.append(line)
            continue
        if not skipping:
            out.append(line)
    return "".join(out)


def append_profiles(text: str, blocks: list[str]) -> str:
    """Append profile blocks to a config body, separated by blank lines."""
    body = text.rstrip("\n")
    parts = [body] if body else []
    parts.extend(blocks)
    return "\n\n".join(parts) + "\n"
