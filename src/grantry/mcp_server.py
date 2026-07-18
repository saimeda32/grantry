"""The MCP surface. Every caller here is an agent, so policy is enforced with
caller="agent". The render helpers are pure so they can be tested without the
MCP transport.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP

from grantry.broker import Broker, GrantResult, NoSessionError
from grantry.providers.base import InteractionHandler
from grantry.ttl import parse_ttl

Notifier = Callable[[str, str], None]


def _desktop_notify(title: str, message: str) -> None:
    # Best-effort desktop notification so a human sees the login prompt even
    # though the MCP server has no terminal of its own. Silent if unavailable.
    cmd: list[str] | None = None
    if sys.platform == "darwin" and shutil.which("osascript"):
        # Pass message and title as AppleScript arguments, never interpolated
        # into the script text, so a quote in either cannot break out and run
        # arbitrary AppleScript.
        cmd = [
            "osascript",
            "-e",
            "on run {m, t}",
            "-e",
            "display notification m with title t",
            "-e",
            "end run",
            message,
            title,
        ]
    elif shutil.which("notify-send"):
        cmd = ["notify-send", title, message]
    if cmd is not None:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(cmd, check=False, timeout=5)


class _PendingLogin:
    def __init__(self) -> None:
        self.thread: threading.Thread | None = None
        self.uri: str | None = None
        self.code: str | None = None
        self.error: str | None = None
        self.prompted = threading.Event()


# Module-level default so a single MCP server tracks one in-flight login.
_DEFAULT_LOGIN_STATE: dict[str, Any] = {}


def handle_request_login(
    broker: Broker,
    notify: Notifier = _desktop_notify,
    state: dict[str, Any] | None = None,
) -> str:
    """Start a login WITHOUT blocking the tool call. It kicks off the device
    flow on a background thread, surfaces the browser prompt to the human, and
    returns immediately with the URL and code so the agent can relay them. The
    agent then calls get_credentials again once the human approves. Repeated
    calls while a login is already waiting return the same prompt rather than
    starting a second flow.
    """
    state = state if state is not None else _DEFAULT_LOGIN_STATE
    existing = state.get("pending")
    if existing is not None and existing.thread is not None and existing.thread.is_alive():
        if existing.uri:
            return (
                f"A login is already waiting for approval. Ask the human to open "
                f"{existing.uri} and enter code {existing.code}, then call get_credentials again."
            )
        return "A login is already starting. Wait a moment, then call whoami to check."

    pending = _PendingLogin()
    state["pending"] = pending

    class _Handler(InteractionHandler):
        def on_verification(self, verification_uri: str, user_code: str) -> None:
            pending.uri, pending.code = verification_uri, user_code
            msg = f"Open {verification_uri} and enter code {user_code}"
            notify("grantry login required", msg)
            print(f"grantry: {msg}", file=sys.stderr, flush=True)
            pending.prompted.set()

        def wait(self) -> None:
            return None

    def _run() -> None:
        try:
            broker.login(_Handler())
        except Exception as e:  # captured for the next status check, never raised here
            pending.error = str(e)

    pending.thread = threading.Thread(target=_run, daemon=True)
    pending.thread.start()
    # Wait only for the prompt to appear (seconds), never for the human.
    pending.prompted.wait(timeout=10)
    if pending.error:
        return f"Login could not be started: {pending.error}"
    if pending.uri:
        return (
            f"Ask the human to open {pending.uri} and enter code {pending.code}. "
            "Once they approve in the browser, call get_credentials again; the "
            "session will be ready. No need to wait on this call."
        )
    return (
        "Login starting. Ask the human to watch for a browser prompt, then retry get_credentials."
    )


def _render_credentials(result: GrantResult) -> str:
    c = result.credentials
    assert c is not None
    # AWS_CREDENTIALS_EXPIRATION must be ISO-8601 for SDKs to parse it (a raw
    # epoch float is rejected), matching what the CLI's switch/run emit.
    expires = datetime.fromtimestamp(c.expiration, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    block = (
        f"AWS_ACCESS_KEY_ID={c.access_key_id}\n"
        f"AWS_SECRET_ACCESS_KEY={c.secret_access_key}\n"
        f"AWS_SESSION_TOKEN={c.session_token}\n"
        f"AWS_CREDENTIALS_EXPIRATION={expires}"
    )
    if result.advisory:
        block += f"\n# note: {result.advisory}"
    return block


def _render_denied(result: GrantResult) -> str:
    return f"Denied: {result.decision.reason}. No credentials were issued."


def handle_get_credentials(
    broker: Broker, identity: str, ttl: str, caller_label: str = "agent"
) -> str:
    try:
        seconds = parse_ttl(ttl)
    except ValueError as e:
        return f"Invalid ttl: {e}"
    try:
        result = broker.grant(identity, seconds, caller="agent", caller_label=caller_label)
    except NoSessionError:
        return "No active AWS session. Ask a human to run 'grantry login' or call request_login."
    if result.credentials is None:
        return _render_denied(result)
    return _render_credentials(result)


def build_mcp(broker: Broker, caller_label: str = "agent") -> FastMCP:
    # caller_label identifies WHICH agent this server serves, recorded in the
    # audit log. Each agent sets it via GRANTRY_AGENT_LABEL in its MCP config,
    # so "who requested credentials" is answerable per agent, not just "agent".
    mcp = FastMCP("grantry")

    @mcp.tool()
    def whoami() -> str:
        """Report the active AWS session and its expiry."""
        session = broker.cached_session()
        if session is None:
            return "No active session."
        return f"Session for {session.start_url} (region {session.region})."

    @mcp.tool()
    def list_identities() -> str:
        """List the account.role identities available through Identity Center."""
        try:
            idents = broker.identities()
        except NoSessionError:
            return "No active session. Ask a human to run 'grantry login'."
        return "\n".join(sorted(i.key for i in idents)) or "No identities available."

    @mcp.tool()
    def get_credentials(identity: str, ttl: str = "15m") -> str:
        """Mint short-lived AWS credentials for an identity, subject to policy."""
        return handle_get_credentials(broker, identity, ttl, caller_label=caller_label)

    @mcp.tool()
    def check_access(identity: str) -> str:
        """Report whether policy would allow this identity for an agent, without minting."""
        try:
            decision = broker.would_allow(identity, caller="agent")
        except NoSessionError:
            return "No active session."
        verdict = "ALLOWED" if decision.allowed else "DENIED"
        return f"{verdict}: {decision.reason}"

    @mcp.tool()
    def request_login() -> str:
        """Ask the human to log in when no session is active. Notifies them and
        waits for browser approval, then resolves so the agent can retry."""
        return handle_request_login(broker)

    return mcp
