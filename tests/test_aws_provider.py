import time

import botocore.session
import pytest

from grantry.providers.aws import AwsProvider
from grantry.providers.base import RefreshExpiredError
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


def test_refresh_invalid_request_requires_new_login():
    # AWS SSO-OIDC's CreateToken returns InvalidRequestException (not just
    # InvalidGrantException) when the refresh token can no longer be used, e.g.
    # once the backing client registration itself has gone stale. grantry must
    # treat this the same as a dead refresh token (RefreshExpiredError), not
    # crash the caller with an unhandled botocore ClientError.
    with FakeSSO() as fake:
        provider = AwsProvider(
            "https://example.awsapps.com/start",
            "us-east-1",
            client_factory=client_factory_for(fake.endpoint),
            poll_interval=0,
        )
        handler = ImmediateHandler()
        session = provider.start_login(handler)

        fake._state.next_refresh_error = (
            400,
            "InvalidRequestException",
            {"error": "invalid_request", "error_description": "Invalid request"},
        )
        with pytest.raises(RefreshExpiredError):
            provider.refresh(session)
