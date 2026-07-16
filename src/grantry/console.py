"""Open the AWS console in a browser for an identity, using the federation
sign-in flow. Pure URL construction plus an injectable fetch so the token
exchange is testable without the network.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable

from grantry.providers.base import Credentials

Fetch = Callable[[str], str]

_FEDERATION = "https://signin.aws.amazon.com/federation"
_DEFAULT_DESTINATION = "https://console.aws.amazon.com/"


def federation_session(creds: Credentials) -> str:
    """The JSON session blob the federation endpoint expects."""
    return json.dumps(
        {
            "sessionId": creds.access_key_id,
            "sessionKey": creds.secret_access_key,
            "sessionToken": creds.session_token,
        }
    )


def signin_token_url(session_json: str) -> str:
    q = urllib.parse.urlencode({"Action": "getSigninToken", "Session": session_json})
    return f"{_FEDERATION}?{q}"


def console_url(signin_token: str, destination: str = _DEFAULT_DESTINATION) -> str:
    q = urllib.parse.urlencode(
        {
            "Action": "login",
            "Issuer": "grantry",
            "Destination": destination,
            "SigninToken": signin_token,
        }
    )
    return f"{_FEDERATION}?{q}"


def _default_fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310 - fixed AWS https URL
        data: bytes = resp.read()
        return data.decode("utf-8")


def build_console_url(
    creds: Credentials, destination: str = _DEFAULT_DESTINATION, fetch: Fetch = _default_fetch
) -> str:
    """Exchange credentials for a sign-in token and return the console login URL
    the browser should open.
    """
    body = fetch(signin_token_url(federation_session(creds)))
    token = str(json.loads(body)["SigninToken"])
    return console_url(token, destination)
