import time

from grantry.audit import AuditLog
from grantry.broker import Broker, NoSessionError
from grantry.identity import Identity
from grantry.policy import Policy
from grantry.providers.base import Credentials, Session
from grantry.secrets import SecretStore


class FakeProvider:
    def __init__(self):
        self.start_url = "https://example.awsapps.com/start"
        self.region = "us-east-1"
        self._idents = [
            Identity("111122223333", "prod", "ReadOnlyAccess"),
            Identity("111122223333", "prod", "AdminAccess"),
        ]

    def name(self):
        return "aws"

    def start_login(self, handler):
        return Session(self.start_url, self.region, "tok", time.time() + 3600)

    def list_identities(self, session):
        return self._idents

    def mint(self, session, ident, ttl):
        # A real SSO provider ignores ttl and returns AWS's fixed ~1h lifetime.
        return Credentials("AKIA", "sec", "sess", 1000.0 + 3600)


POLICY = """
agents:
  allow:
    - identity: "*/ReadOnlyAccess"
  deny:
    - identity: "*/*Admin*"
  max_ttl: 15m
humans:
  max_ttl: 12h
"""


def build(tmp_path, monkeypatch, policy_text=POLICY):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    p = tmp_path / "policy.yaml"
    p.write_text(policy_text)
    return Broker(
        provider=FakeProvider(),
        policy=Policy.load(p),
        audit=AuditLog(),
        secrets=SecretStore(),
        now=lambda: 1000.0,
        clock_iso=lambda: "2026-07-15T10:00:00Z",
    )


class H:
    def on_verification(self, uri, code): ...
    def wait(self): ...


def test_login_caches_session(tmp_path, monkeypatch):
    broker = build(tmp_path, monkeypatch)
    broker.login(H())
    s = broker.cached_session()
    assert s is not None
    assert s.access_token == "tok"


def test_identities_requires_session(tmp_path, monkeypatch):
    broker = build(tmp_path, monkeypatch)
    try:
        broker.identities()
        raise AssertionError("expected NoSessionError")
    except NoSessionError:
        pass


def test_agent_grant_allowed_mints_and_audits(tmp_path, monkeypatch):
    broker = build(tmp_path, monkeypatch)
    broker.login(H())
    res = broker.grant("prod/ReadOnlyAccess", requested_ttl=3600, caller="agent")
    assert res.decision.allowed
    assert res.credentials is not None
    assert res.credentials.access_key_id == "AKIA"
    entries = AuditLog().entries()
    assert entries[-1]["identity"] == "prod/ReadOnlyAccess"
    assert entries[-1]["allowed"] is True


def test_agent_grant_denied_mints_nothing(tmp_path, monkeypatch):
    broker = build(tmp_path, monkeypatch)
    broker.login(H())
    res = broker.grant("prod/AdminAccess", requested_ttl=3600, caller="agent")
    assert not res.decision.allowed
    assert res.credentials is None
    assert AuditLog().entries()[-1]["allowed"] is False


def test_unknown_identity_denied(tmp_path, monkeypatch):
    broker = build(tmp_path, monkeypatch)
    broker.login(H())
    res = broker.grant("prod/NopeAccess", requested_ttl=60, caller="agent")
    assert not res.decision.allowed
    assert res.credentials is None


def test_advisory_when_aws_outlives_cap(tmp_path, monkeypatch):
    # now=1000, policy caps agents to 15m, AWS returns a 1h credential.
    broker = build(tmp_path, monkeypatch)
    broker.login(H())
    res = broker.grant("prod/ReadOnlyAccess", requested_ttl=900, caller="agent")
    assert res.decision.capped_ttl == 900
    assert res.credentials is not None
    assert res.advisory is not None
    assert "advisory" in res.advisory.lower()
    assert "session duration" in res.advisory.lower()
    # The reported expiration is AWS's real one, not the capped window.
    assert res.credentials.expiration == 1000.0 + 3600


def test_no_advisory_when_within_cap(tmp_path, monkeypatch):
    # Human section caps at 12h, so a 1h AWS credential is within the cap.
    broker = build(tmp_path, monkeypatch)
    broker.login(H())
    res = broker.grant("prod/ReadOnlyAccess", requested_ttl=43200, caller="human")
    assert res.advisory is None
