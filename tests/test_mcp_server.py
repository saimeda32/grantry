import time

from grantry.audit import AuditLog
from grantry.broker import Broker, GrantResult
from grantry.identity import Identity
from grantry.mcp_server import _render_credentials, _render_denied, handle_get_credentials
from grantry.policy import Decision, Policy
from grantry.providers.base import Credentials, Session
from grantry.secrets import SecretStore


class FakeProvider:
    start_url = "https://example.awsapps.com/start"
    region = "us-east-1"

    def name(self):
        return "aws"

    def start_login(self, handler):
        return Session(self.start_url, self.region, "tok", time.time() + 3600)

    def list_identities(self, session):
        return [
            Identity("111122223333", "prod", "ReadOnlyAccess"),
            Identity("111122223333", "prod", "AdminAccess"),
        ]

    def mint(self, session, ident, ttl):
        return Credentials("AKIA", "sec", "sess", 1893456000.0)


POLICY = """
agents:
  allow:
    - identity: "*/ReadOnlyAccess"
  deny:
    - identity: "*/*Admin*"
  max_ttl: 15m
"""


def broker(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    p = tmp_path / "policy.yaml"
    p.write_text(POLICY)
    b = Broker(
        FakeProvider(),
        Policy.load(p),
        AuditLog(),
        SecretStore(),
        now=lambda: 1000.0,
        clock_iso=lambda: "2026-07-15T10:00:00Z",
    )

    class H:
        def on_verification(self, uri, code): ...
        def wait(self): ...

    b.login(H())
    return b


def test_render_credentials_env_block():
    res = GrantResult(
        Credentials("AKIA", "sec", "sess", 1893456000.0),
        Decision(True, "ok", "*/ReadOnlyAccess", 900),
    )
    out = _render_credentials(res)
    assert "AWS_ACCESS_KEY_ID=AKIA" in out
    assert "AWS_SECRET_ACCESS_KEY=sec" in out
    assert "AWS_SESSION_TOKEN=sess" in out


def test_render_denied_has_reason_no_secret():
    res = GrantResult(None, Decision(False, "denied by deny rule '*/*Admin*'", "*/*Admin*", 0))
    out = _render_denied(res)
    assert "denied" in out.lower()
    assert "sec" not in out and "AKIA" not in out


def test_get_credentials_tool_allow(tmp_path, monkeypatch):
    b = broker(tmp_path, monkeypatch)
    out = handle_get_credentials(b, "prod/ReadOnlyAccess", "1h")
    assert "AWS_ACCESS_KEY_ID=AKIA" in out


def test_get_credentials_tool_deny(tmp_path, monkeypatch):
    b = broker(tmp_path, monkeypatch)
    out = handle_get_credentials(b, "prod/AdminAccess", "15m")
    assert "AWS_ACCESS_KEY_ID" not in out
    assert "denied" in out.lower()
