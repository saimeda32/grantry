import hashlib
import json
import stat
import sys

from grantry.awscli_cache import sso_cache_path, write_sso_cache
from grantry.providers.base import Session

POSIX = not sys.platform.startswith("win")


def test_cache_path_matches_aws_cli_key(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    url = "https://legalplans.awsapps.com/start"
    expected = hashlib.sha1(url.encode()).hexdigest() + ".json"
    assert sso_cache_path(url).name == expected


def test_write_sso_cache_format_and_perms(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    session = Session(
        "https://legalplans.awsapps.com/start",
        "us-east-1",
        "the-token",
        1893456000.0,
        refresh_token="rt",
        client_id="cid",
        client_secret="csec",
    )
    write_sso_cache(session)
    path = sso_cache_path(session.start_url)
    data = json.loads(path.read_text())
    assert data["startUrl"] == session.start_url
    assert data["region"] == "us-east-1"
    assert data["accessToken"] == "the-token"
    assert data["expiresAt"].endswith("Z")
    # The refresh token and client secret are deliberately NOT written to this
    # plaintext file; grantry owns renewal from the keychain.
    assert "refreshToken" not in data
    assert "clientId" not in data
    assert "clientSecret" not in data
    if POSIX:  # Windows does not use POSIX file modes
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        # the cache directory is private too
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
