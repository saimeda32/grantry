"""The broker composes a provider, the policy engine, and the audit log into a
single grant path. Nothing mints credentials except grant(), and grant() never
mints without an allow decision.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass

from grantry.audit import AuditLog
from grantry.identity import Identity
from grantry.policy import Decision, Policy
from grantry.providers.base import Credentials, InteractionHandler, Provider, Session
from grantry.secrets import SecretStore, token_name


class NoSessionError(Exception):
    pass


@dataclass(frozen=True)
class GrantResult:
    credentials: Credentials | None
    decision: Decision


class Broker:
    def __init__(
        self,
        provider: Provider,
        policy: Policy,
        audit: AuditLog,
        secrets: SecretStore,
        *,
        clock_iso: Callable[[], str],
        now: Callable[[], float] = time.time,
    ) -> None:
        self._provider = provider
        self._policy = policy
        self._audit = audit
        self._secrets = secrets
        self._now = now
        self._clock_iso = clock_iso

    def _start_url(self) -> str:
        return self._provider.start_url

    def login(self, handler: InteractionHandler) -> Session:
        session = self._provider.start_login(handler)
        self._secrets.put(
            token_name(self._start_url()),
            json.dumps(
                {
                    "start_url": session.start_url,
                    "region": session.region,
                    "access_token": session.access_token,
                    "expires_at": session.expires_at,
                }
            ),
        )
        return session

    def cached_session(self) -> Session | None:
        raw = self._secrets.get(token_name(self._start_url()))
        if not raw:
            return None
        data = json.loads(raw)
        if data["expires_at"] <= self._now():
            return None
        return Session(
            start_url=data["start_url"],
            region=data["region"],
            access_token=data["access_token"],
            expires_at=data["expires_at"],
        )

    def identities(self) -> list[Identity]:
        session = self.cached_session()
        if session is None:
            raise NoSessionError("no active session; run login first")
        return self._provider.list_identities(session)

    def would_allow(self, ident_key: str, caller: str) -> Decision:
        """Evaluate policy for an identity key without minting. Requires a session."""
        session = self.cached_session()
        if session is None:
            raise NoSessionError("no active session; run login first")
        ident = self._find(session, ident_key)
        if ident is None:
            return Decision(False, f"unknown identity {ident_key!r}", None, 0)
        return self._policy.evaluate(ident, 900, caller)

    def grant(
        self,
        ident_key: str,
        requested_ttl: int,
        caller: str,
        caller_label: str | None = None,
    ) -> GrantResult:
        # caller is the policy CLASS ("agent" or "human") that selects the rule
        # section. caller_label is WHO specifically asked (e.g. "claude-code"),
        # recorded in the audit. It defaults to the class when not given.
        label = caller_label or caller
        session = self.cached_session()
        if session is None:
            raise NoSessionError("no active session; run login first")
        ident = self._find(session, ident_key)
        if ident is None:
            unknown = Identity("unknown", *_split_key(ident_key))
            decision = Decision(False, f"unknown identity {ident_key!r}", None, 0)
            self._audit.record(label, unknown, decision, at=self._clock_iso())
            return GrantResult(None, decision)
        decision = self._policy.evaluate(ident, requested_ttl, caller)
        self._audit.record(label, ident, decision, at=self._clock_iso())
        if not decision.allowed:
            return GrantResult(None, decision)
        creds = self._provider.mint(session, ident, decision.capped_ttl)
        return GrantResult(creds, decision)

    def _find(self, session: Session, ident_key: str) -> Identity | None:
        return next(
            (i for i in self._provider.list_identities(session) if i.key == ident_key), None
        )


def _split_key(key: str) -> tuple[str, str]:
    if "/" in key:
        acct, role = key.split("/", 1)
        return acct, role
    return key, ""
