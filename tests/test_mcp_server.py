import time

from grantry.audit import AuditLog
from grantry.broker import Broker, GrantResult
from grantry.identity import Identity
from grantry.mcp_server import (
    _render_credentials,
    _render_denied,
    handle_get_credentials,
    handle_request_login,
)
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

    def refresh(self, session):
        return session

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


class VerifyingProvider:
    """A provider whose start_login drives the device-flow prompt, so the
    request_login handler's notification path is exercised.
    """

    start_url = "https://example.awsapps.com/start"
    region = "us-east-1"

    def name(self):
        return "aws"

    def start_login(self, handler):
        handler.on_verification("https://device.example/verify", "WXYZ-1234")
        handler.wait()
        return Session(self.start_url, self.region, "tok", time.time() + 3600)

    def refresh(self, session):
        return session

    def list_identities(self, session):
        return []

    def mint(self, session, ident, ttl):
        return Credentials("AKIA", "sec", "sess", time.time() + ttl)


def test_request_login_notifies_and_completes(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    (tmp_path / "policy.yaml").write_text(POLICY)
    b = Broker(
        VerifyingProvider(),
        Policy.load(tmp_path / "policy.yaml"),
        AuditLog(),
        SecretStore(),
        clock_iso=lambda: "t",
    )
    seen = []
    out = handle_request_login(b, notify=lambda title, msg: seen.append((title, msg)))
    assert "complete" in out.lower()
    assert seen and "WXYZ-1234" in seen[0][1]
    # The session was persisted, so a subsequent request has a session.
    assert b.cached_session() is not None


def test_caller_label_recorded_in_audit(tmp_path, monkeypatch):
    b = broker(tmp_path, monkeypatch)
    handle_get_credentials(b, "prod/ReadOnlyAccess", "15m", caller_label="claude-code")
    entries = AuditLog().entries()
    assert entries[-1]["caller"] == "claude-code"
    # policy still evaluated as the agent class (deny of AdminAccess still applies)
    handle_get_credentials(b, "prod/AdminAccess", "15m", caller_label="claude-code")
    assert AuditLog().entries()[-1]["allowed"] is False
