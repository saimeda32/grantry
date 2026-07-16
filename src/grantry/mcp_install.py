"""One-command install of grantry into an AI client's MCP config.

Each client keeps a JSON config with a map of MCP servers under a root key
(most use "mcpServers"; VS Code uses "servers"). This module holds the client
registry and the pure merge logic; the CLI does the file IO.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Client:
    key: str  # the name you pass on the CLI, e.g. "cursor"
    label: str  # human name
    path: str  # config path, may contain ~ and be OS-specific
    root: str  # top-level key holding the server map


def _mac_app_support(*parts: str) -> str:
    return os.path.join("~", "Library", "Application Support", *parts)


# Config locations verified 2026-07. Where a client is unavailable on the
# platform its path simply will not exist and auto-detect skips it.
CLIENTS: dict[str, Client] = {
    "claude-code": Client("claude-code", "Claude Code", "~/.claude.json", "mcpServers"),
    "claude-desktop": Client(
        "claude-desktop",
        "Claude Desktop",
        _mac_app_support("Claude", "claude_desktop_config.json"),
        "mcpServers",
    ),
    "cursor": Client("cursor", "Cursor", "~/.cursor/mcp.json", "mcpServers"),
    "windsurf": Client("windsurf", "Windsurf", "~/.codeium/windsurf/mcp_config.json", "mcpServers"),
    "vscode": Client("vscode", "VS Code", ".vscode/mcp.json", "servers"),
}


def config_path(client: Client) -> str:
    return os.path.expanduser(client.path)


def grantry_command() -> tuple[str, list[str]]:
    """The command an MCP client should run to start grantry. Uses the current
    interpreter with `-m grantry` so it works with no PATH assumptions.
    """
    return sys.executable, ["-m", "grantry", "mcp"]


def server_entry(
    command: str,
    args: list[str],
    label: str,
    start_url: str | None,
    region: str | None,
) -> dict[str, Any]:
    env: dict[str, str] = {"GRANTRY_AGENT_LABEL": label}
    if start_url:
        env["GRANTRY_SSO_START_URL"] = start_url
    if region:
        env["GRANTRY_SSO_REGION"] = region
    return {"command": command, "args": args, "env": env}


def merge_server(
    config: dict[str, Any], root: str, name: str, entry: dict[str, Any]
) -> dict[str, Any]:
    """Return a new config with grantry added or updated under the root key,
    leaving every other server and top-level key untouched.
    """
    result = dict(config)
    servers = dict(result.get(root) or {})
    servers[name] = entry
    result[root] = servers
    return result
