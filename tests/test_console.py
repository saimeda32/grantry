import urllib.parse

from grantry.console import (
    build_console_url,
    console_url,
    federation_session,
    signin_token_url,
)
from grantry.providers.base import Credentials


def creds():
    return Credentials("AKIA", "sec", "sess", 1893456000.0)


def test_federation_session_shape():
    import json

    s = json.loads(federation_session(creds()))
    assert s == {"sessionId": "AKIA", "sessionKey": "sec", "sessionToken": "sess"}


def test_signin_token_url_encodes_session():
    url = signin_token_url(federation_session(creds()))
    assert url.startswith("https://signin.aws.amazon.com/federation?")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["Action"] == ["getSigninToken"]
    assert "AKIA" in q["Session"][0]


def test_console_url_has_login_action_and_token():
    url = console_url("thetoken", "https://console.aws.amazon.com/ec2/")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["Action"] == ["login"]
    assert q["SigninToken"] == ["thetoken"]
    assert q["Destination"] == ["https://console.aws.amazon.com/ec2/"]
    assert q["Issuer"] == ["grantry"]


def test_build_console_url_uses_injected_fetch():
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return '{"SigninToken": "tok-123"}'

    url = build_console_url(creds(), fetch=fake_fetch)
    # it fetched the getSigninToken endpoint with our session
    assert "getSigninToken" in calls[0]
    # and produced a login URL carrying the returned token
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["SigninToken"] == ["tok-123"]
