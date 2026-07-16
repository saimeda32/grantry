"""AWS Identity Center provider: OIDC device flow plus role credential minting.

Uses botocore's documented low-level clients only (sso-oidc, sso). No private
botocore attributes and no vendored SDK code.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import botocore.session
from botocore.config import Config
from botocore.exceptions import ClientError

from grantry.identity import Identity
from grantry.providers.base import Credentials, InteractionHandler, Session

ClientFactory = Callable[[str, str], Any]


def _default_client_factory(service_name: str, region_name: str) -> Any:
    session = botocore.session.Session()
    retries = Config(retries={"mode": "standard", "max_attempts": 10})
    return session.create_client(service_name, region_name=region_name, config=retries)


class AwsProvider:
    def __init__(
        self,
        start_url: str,
        region: str,
        *,
        client_factory: ClientFactory | None = None,
        poll_interval: float = 5.0,
    ) -> None:
        self.start_url = start_url
        self.region = region
        self._client_factory = client_factory or _default_client_factory
        self._poll_interval = poll_interval

    def name(self) -> str:
        return "aws"

    def start_login(self, handler: InteractionHandler) -> Session:
        oidc = self._client_factory("sso-oidc", self.region)
        reg = oidc.register_client(clientName="grantry", clientType="public")
        auth = oidc.start_device_authorization(
            clientId=reg["clientId"],
            clientSecret=reg["clientSecret"],
            startUrl=self.start_url,
        )
        handler.on_verification(
            auth.get("verificationUriComplete", auth["verificationUri"]),
            auth["userCode"],
        )
        handler.wait()
        deadline = time.time() + auth["expiresIn"]
        while True:
            try:
                token = oidc.create_token(
                    clientId=reg["clientId"],
                    clientSecret=reg["clientSecret"],
                    grantType="urn:ietf:params:oauth:grant-type:device_code",
                    deviceCode=auth["deviceCode"],
                )
                break
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("AuthorizationPendingException", "authorization_pending"):
                    if time.time() >= deadline:
                        raise TimeoutError("device authorization expired before approval") from e
                    time.sleep(self._poll_interval)
                    continue
                if code in ("SlowDownException", "slow_down"):
                    time.sleep(self._poll_interval + 1)
                    continue
                raise
        return Session(
            start_url=self.start_url,
            region=self.region,
            access_token=token["accessToken"],
            expires_at=time.time() + int(token.get("expiresIn", 3600)),
        )

    def list_identities(self, session: Session) -> list[Identity]:
        sso = self._client_factory("sso", session.region)
        idents: list[Identity] = []
        accounts = self._paginate(
            sso.list_accounts, "accountList", accessToken=session.access_token
        )
        for acct in accounts:
            roles = self._paginate(
                sso.list_account_roles,
                "roleList",
                accessToken=session.access_token,
                accountId=acct["accountId"],
            )
            for role in roles:
                idents.append(
                    Identity(
                        account_id=acct["accountId"],
                        account_name=acct.get("accountName", acct["accountId"]),
                        role_name=role["roleName"],
                    )
                )
        return idents

    def mint(self, session: Session, ident: Identity, ttl: int) -> Credentials:
        sso = self._client_factory("sso", session.region)
        resp = sso.get_role_credentials(
            roleName=ident.role_name,
            accountId=ident.account_id,
            accessToken=session.access_token,
        )
        rc = resp["roleCredentials"]
        return Credentials(
            access_key_id=rc["accessKeyId"],
            secret_access_key=rc["secretAccessKey"],
            session_token=rc["sessionToken"],
            expiration=rc["expiration"] / 1000.0,
        )

    @staticmethod
    def _paginate(op: Callable[..., Any], key: str, **kwargs: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        next_token: str | None = None
        while True:
            call = dict(kwargs)
            if next_token:
                call["nextToken"] = next_token
            resp = op(**call)
            out.extend(resp.get(key, []))
            next_token = resp.get("nextToken")
            if not next_token:
                return out
