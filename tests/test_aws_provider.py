import time

import botocore.session

from grantry.providers.aws import AwsProvider
from tests.fakes.fake_sso import FakeSSO


class ImmediateHandler:
    def __init__(self):
        self.seen = None

    def on_verification(self, uri, code):
        self.seen = (uri, code)

    def wait(self):
        return None


def client_factory_for(endpoint):
    def factory(service_name, region_name):
        session = botocore.session.Session()
        return session.create_client(
            service_name,
            region_name=region_name,
            endpoint_url=endpoint,
            aws_access_key_id="x",
            aws_secret_access_key="y",
        )

    return factory


def test_device_flow_then_mint():
    with FakeSSO() as fake:
        provider = AwsProvider(
            "https://example.awsapps.com/start",
            "us-east-1",
            client_factory=client_factory_for(fake.endpoint),
            poll_interval=0,
        )
        handler = ImmediateHandler()
        session = provider.start_login(handler)
        assert session.access_token == "sso-access-token-value"
        assert session.expires_at > time.time()
        assert handler.seen is not None
        assert handler.seen[1] == "WXYZ-1234"

        idents = provider.list_identities(session)
        keys = {i.key for i in idents}
        assert "prod.ReadOnlyAccess" in keys
        assert "prod.AWSPowerUserAccess" in keys

        prod_ro = next(i for i in idents if i.key == "prod.ReadOnlyAccess")
        creds = provider.mint(session, prod_ro, ttl=900)
        assert creds.access_key_id == "AKIAFAKE"
        assert creds.session_token == "faketoken"

        # The login carried a refresh token; refreshing yields a new access token.
        assert session.refresh_token == "refresh-token-v1"
        renewed = provider.refresh(session)
        assert renewed.access_token == "refreshed-access-token"
        assert renewed.refresh_token == "refresh-token-v2"
