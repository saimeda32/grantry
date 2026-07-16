"""Write grantry's SSO token into the AWS CLI's own cache so that, after one
`grantry login`, the native `aws` CLI and every AWS SDK work with no further
grantry involvement.

The AWS CLI's SSO credential provider, given a profile with sso_start_url,
loads ~/.aws/sso/cache/<sha1(start_url)>.json and uses its accessToken to call
GetRoleCredentials. We write exactly that file in the format it expects.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from grantry.providers.base import Session


def sso_cache_path(start_url: str) -> Path:
    key = hashlib.sha1(start_url.encode("utf-8")).hexdigest()  # noqa: S324 - AWS CLI uses sha1
    return Path(os.path.expanduser("~/.aws/sso/cache")) / f"{key}.json"


def write_sso_cache(session: Session) -> None:
    """Write the AWS CLI SSO token cache entry for this session (0600)."""
    path = sso_cache_path(session.start_url)
    path.parent.mkdir(parents=True, exist_ok=True)
    expires = datetime.fromtimestamp(session.expires_at, tz=timezone.utc)
    entry = {
        "startUrl": session.start_url,
        "region": session.region,
        "accessToken": session.access_token,
        "expiresAt": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if session.refresh_token and session.client_id and session.client_secret:
        entry["clientId"] = session.client_id
        entry["clientSecret"] = session.client_secret
        entry["refreshToken"] = session.refresh_token
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(entry, fh)
