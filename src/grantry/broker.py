"""The broker composes a provider, the policy engine, and the audit log into a
single grant path. Nothing mints credentials except grant(), and grant() never
mints without an allow decision.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from grantry.audit import AuditLog
from grantry.config import state_path
from grantry.idcache import write_cache as write_id_cache
from grantry.identity import Identity
from grantry.policy import Decision, Policy
from grantry.providers.base import (
    Credentials,
    InteractionHandler,
    Provider,
    RefreshExpiredError,
    Session,
)
from grantry.secrets import SecretStore, token_name
from grantry.ttl import format_ttl

# AWS-issued SSO credentials cannot be shortened client-side (the reserved SSO
# roles do not trust re-assumption). When AWS hands back a credential that
# outlives the policy cap by more than this margin, grantry adds an advisory so
# the operator knows the cap is advisory and where the real control lives.
_ADVISORY_MARGIN = 60


class NoSessionError(Exception):
    pass


@contextlib.contextmanager
def _refresh_lock(path: str, wait: float = 15.0, stale: float = 90.0) -> Iterator[bool]:
    """A tiny cross-process advisory lock for token refresh.

    Yields True if this call created (holds) the lock, False if it gave up
    waiting and is proceeding without it. The lock file is removed on exit ONLY
    by the process that created it, so a waiter that gives up never deletes the
    holder's lock. A lock whose file is older than `stale` is assumed to belong
    to a crashed process and is broken; `stale` is much larger than `wait` so a
    slow-but-alive holder (throttled create_token retries) is never mistaken for
    a dead one.
    """
    start = time.time()
    acquired = False
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            acquired = True
            break
        except FileExistsError:
            broke_stale = False
            with contextlib.suppress(OSError):
                if time.time() - os.path.getmtime(path) > stale:
                    os.unlink(path)
                    broke_stale = True
            if broke_stale:
                continue
            if time.time() - start > wait:
                break  # proceed without the lock rather than hang forever
            time.sleep(0.1)
    try:
        yield acquired
    finally:
        if acquired:
            with contextlib.suppress(OSError):
                os.unlink(path)


@dataclass(frozen=True)
class GrantResult:
    credentials: Credentials | None
    decision: Decision
    advisory: str | None = None


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
        on_session: Callable[[Session], None] | None = None,
    ) -> None:
        self._provider = provider
        self._policy = policy
        self._audit = audit
        self._secrets = secrets
        self._now = now
        self._clock_iso = clock_iso
        # Fired whenever a fresh session is obtained (login or refresh). The CLI
        # uses it to mirror the token into the AWS CLI cache for native use.
        self._on_session = on_session

    def _start_url(self) -> str:
        return self._provider.start_url

    def login(self, handler: InteractionHandler) -> Session:
        session = self._provider.start_login(handler)
        self._persist(session)
        if self._on_session:
            self._on_session(session)
        return session

    def _persist(self, session: Session) -> None:
        self._secrets.put(
            token_name(self._start_url()),
            json.dumps(
                {
                    "start_url": session.start_url,
                    "region": session.region,
                    "access_token": session.access_token,
                    "expires_at": session.expires_at,
                    "refresh_token": session.refresh_token,
                    "client_id": session.client_id,
                    "client_secret": session.client_secret,
                }
            ),
        )

    def logout(self) -> bool:
        """Forget the current instance's session: delete the keychain token.
        Returns True if a session was present. The provider-side AWS CLI cache
        is cleared by the caller via the on_session sink's counterpart.
        """
        name = token_name(self._start_url())
        had = self._secrets.get(name) is not None
        if had:
            self._secrets.delete(name)
        return had

    def cached_session(self) -> Session | None:
        raw = self._secrets.get(token_name(self._start_url()))
        if not raw:
            return None
        data = json.loads(raw)
        session = Session(
            start_url=data["start_url"],
            region=data["region"],
            access_token=data["access_token"],
            expires_at=data["expires_at"],
            refresh_token=data.get("refresh_token"),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
        )
        if session.expires_at > self._now():
            return session
        # Expired: renew silently if we have a refresh token, else require login.
        if not session.refresh_token:
            return None
        # Multiple agents share one token. Serialize refresh with a lock so two
        # processes do not both spend the rotating refresh token; the loser
        # re-reads the token the winner just persisted.
        with _refresh_lock(self._lock_path()):
            latest = self._load_raw()
            if latest is not None and latest.expires_at > self._now():
                return latest
            try:
                renewed = self._provider.refresh(session)
            except RefreshExpiredError:
                # The refresh token is genuinely dead; a new login is required.
                return None
            except Exception:
                # A transient failure (network, throttle). Do NOT discard the
                # session; re-raise so the caller can surface it and retry,
                # rather than forcing a full browser login over a blip.
                raise
            self._persist(renewed)
            if self._on_session:
                self._on_session(renewed)
            return renewed

    def _lock_path(self) -> str:
        import hashlib

        digest = hashlib.sha1(self._start_url().encode()).hexdigest()[:16]
        return str(state_path(f"refresh-{digest}.lock"))

    def _load_raw(self) -> Session | None:
        raw = self._secrets.get(token_name(self._start_url()))
        if not raw:
            return None
        data = json.loads(raw)
        return Session(
            start_url=data["start_url"],
            region=data["region"],
            access_token=data["access_token"],
            expires_at=data["expires_at"],
            refresh_token=data.get("refresh_token"),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
        )

    def identities(self) -> list[Identity]:
        session = self.cached_session()
        if session is None:
            raise NoSessionError("no active session; run login first")
        idents = self._provider.list_identities(session)
        write_id_cache(idents)
        return idents

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
        advisory = self._advisory(creds, decision.capped_ttl)
        return GrantResult(creds, decision, advisory=advisory)

    def _advisory(self, creds: Credentials, capped_ttl: int) -> str | None:
        real_remaining = creds.expiration - self._now()
        if real_remaining <= capped_ttl + _ADVISORY_MARGIN:
            return None
        return (
            f"AWS issued these credentials valid for about {format_ttl(int(real_remaining))}; "
            f"the policy cap of {format_ttl(capped_ttl)} is advisory. AWS does not allow "
            f"shortening SSO credentials client-side. To enforce shorter sessions, lower the "
            f"permission set's session duration in IAM Identity Center."
        )

    def _find(self, session: Session, ident_key: str) -> Identity | None:
        from grantry.humanops import safe_profile_name
        from grantry.identity import shell_safe

        idents = self._provider.list_identities(session)
        # Exact "account/role" match first.
        for i in idents:
            if i.key == ident_key:
                return i
        # Also accept the "account.role" profile-name form that 'populate' writes
        # to ~/.aws/config, and the raw spaced name a user might paste from the
        # AWS console, case-insensitively. i.key is already shell-safe (spaces
        # collapsed to hyphens), so we shell-safe the input before comparing;
        # that way "Acme Corp/Admin" and "Acme-Corp/Admin" both resolve.
        wanted = ident_key.lower()
        safe_wanted = shell_safe(ident_key).lower()
        for i in idents:
            if i.key.lower() in (wanted, safe_wanted):
                return i
            if safe_profile_name(i.account_name, i.role_name).lower() == wanted:
                return i
        return None


def _split_key(key: str) -> tuple[str, str]:
    if "/" in key:
        acct, role = key.split("/", 1)
        return acct, role
    return key, ""
