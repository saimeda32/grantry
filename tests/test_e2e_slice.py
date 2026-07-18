import botocore.session

from grantry.audit import AuditLog
from grantry.broker import Broker
from grantry.mcp_server import handle_get_credentials
from grantry.policy import Policy
from grantry.providers.aws import AwsProvider
from grantry.secrets import SecretStore
from tests.fakes.fake_sso import FakeSSO

POLICY = """
agents:
  allow:
    - identity: "*/ReadOnlyAccess"
  deny:
    - identity: "*/*PowerUser*"
  max_ttl: 15m
"""


class H:
    def on_verification(self, uri, code): ...
    def wait(self): ...


def factory_for(endpoint):
    def factory(service_name, region_name):
        s = botocore.session.Session()
        return s.create_client(
            service_name,
            region_name=region_name,
            endpoint_url=endpoint,
            aws_access_key_id="x",
            aws_secret_access_key="y",
        )

    return factory


def test_login_then_agent_grant_allow_and_deny(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    (tmp_path / "policy.yaml").write_text(POLICY)

    with FakeSSO() as fake:
        provider = AwsProvider(
            "https://example.awsapps.com/start",
            "us-east-1",
            client_factory=factory_for(fake.endpoint),
            poll_interval=0,
        )
        broker = Broker(
            provider,
            Policy.load(tmp_path / "policy.yaml"),
            AuditLog(),
            SecretStore(),
            clock_iso=lambda: "2026-07-15T10:00:00Z",
        )
        broker.login(H())

        allowed = handle_get_credentials(broker, "prod/ReadOnlyAccess", "1h")
        assert "AWS_ACCESS_KEY_ID=AKIAFAKE" in allowed
        assert "AWS_SESSION_TOKEN=faketoken" in allowed

        denied = handle_get_credentials(broker, "prod/AWSPowerUserAccess", "15m")
        assert "AWS_ACCESS_KEY_ID" not in denied
        assert "denied" in denied.lower()

        audit = AuditLog().entries()
        assert audit[-1]["allowed"] is False
        assert audit[-1]["identity"] == "prod.AWSPowerUserAccess"
        assert audit[-2]["allowed"] is True
