"""Provider protocol and the value types every cloud adapter returns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from grantry.identity import Identity


@dataclass(frozen=True)
class Session:
    start_url: str
    region: str
    access_token: str
    expires_at: float


@dataclass(frozen=True)
class Credentials:
    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: float


class InteractionHandler(Protocol):
    def on_verification(self, verification_uri: str, user_code: str) -> None: ...
    def wait(self) -> None: ...


class Provider(Protocol):
    def name(self) -> str: ...
    def start_login(self, handler: InteractionHandler) -> Session: ...
    def list_identities(self, session: Session) -> list[Identity]: ...
    def mint(self, session: Session, ident: Identity, ttl: int) -> Credentials: ...
