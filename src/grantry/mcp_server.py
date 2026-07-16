"""The MCP surface. Every caller here is an agent, so policy is enforced with
caller="agent". The render helpers are pure so they can be tested without the
MCP transport.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from grantry.broker import Broker, GrantResult, NoSessionError
from grantry.ttl import parse_ttl


def _render_credentials(result: GrantResult) -> str:
    c = result.credentials
    assert c is not None
    block = (
        f"AWS_ACCESS_KEY_ID={c.access_key_id}\n"
        f"AWS_SECRET_ACCESS_KEY={c.secret_access_key}\n"
        f"AWS_SESSION_TOKEN={c.session_token}\n"
        f"AWS_CREDENTIALS_EXPIRATION={c.expiration}"
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
        """List the account/role identities available through Identity Center."""
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

    return mcp
