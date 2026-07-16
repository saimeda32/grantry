import hashlib
import json
import stat

from grantry.awscli_cache import sso_cache_path, write_sso_cache
from grantry.providers.base import Session


def test_cache_path_matches_aws_cli_key(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    url = "https://legalplans.awsapps.com/start"
    expected = hashlib.sha1(url.encode()).hexdigest() + ".json"
    assert sso_cache_path(url).name == expected


def test_write_sso_cache_format_and_perms(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    session = Session(
        "https://legalplans.awsapps.com/start", "us-east-1", "the-token", 1893456000.0,
        refresh_token="rt", client_id="cid", client_secret="csec",
    )
    write_sso_cache(session)
    path = sso_cache_path(session.start_url)
    data = json.loads(path.read_text())
    assert data["startUrl"] == session.start_url
    assert data["region"] == "us-east-1"
    assert data["accessToken"] == "the-token"
    assert data["expiresAt"].endswith("Z")
    # refresh fields included when present
    assert data["clientId"] == "cid"
    assert data["refreshToken"] == "rt"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_write_without_refresh_omits_client_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    session = Session("https://x.awsapps.com/start", "us-east-1", "tok", 1893456000.0)
    write_sso_cache(session)
    data = json.loads(sso_cache_path(session.start_url).read_text())
    assert "clientId" not in data
    assert data["accessToken"] == "tok"
