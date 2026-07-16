"""Write grantry's SSO token into the AWS CLI's own cache so that, after one
`grantry login`, the native `aws` CLI and every AWS SDK work with no further
grantry involvement.

The AWS CLI's SSO credential provider, given a profile with sso_start_url,
loads ~/.aws/sso/cache/<sha1(start_url)>.json and uses its accessToken to call
GetRoleCredentials. We write exactly that file in the format it expects.
"""

from __future__ import annotations

import contextlib
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
    """Write the AWS CLI SSO token cache entry for this session.

    We deliberately write ONLY the access token and its expiry, not the refresh
    token or client secret. The AWS CLI uses the access token until it expires;
    it does not need the refresh material because grantry owns renewal (from the
    keychain). Keeping the long-lived refresh token out of this plaintext file
    limits what an attacker or a backup tool can read to a short-lived token.
    """
    path = sso_cache_path(session.start_url)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Tighten the cache dir even if it pre-existed with a looser mode.
    with contextlib.suppress(OSError):
        os.chmod(path.parent, 0o700)
    expires = datetime.fromtimestamp(session.expires_at, tz=timezone.utc)
    entry = {
        "startUrl": session.start_url,
        "region": session.region,
        "accessToken": session.access_token,
        "expiresAt": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    # Repair perms even if the file pre-existed. fchmod is absent on Windows,
    # where the create mode is applied instead, so guard for its absence.
    fchmod = getattr(os, "fchmod", None)
    if fchmod is not None:
        with contextlib.suppress(OSError):
            fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(entry, fh)
