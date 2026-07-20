"""Project-scope "gated" companion files for `grantry install --gated`.

Gating makes the broker the only place an agent can get AWS credentials. It does
this by starving the agent's shell of ambient AWS credentials, not by banning the
`aws` command: the agent still runs `aws`/boto3 normally, but only ever with the
short-lived, policy-checked, audited credentials grantry issues.

Two levers, both written at project scope (the current directory) and both
idempotent:

- Blank the ambient AWS_* variables in the agent's own shell environment and set
  GRANTRY_CALLER=agent, so any `grantry run` the agent shells out to is evaluated
  under the deny-by-default agents policy. Where a client exposes a file-writable
  agent-shell env (Claude Code settings.json; the VS Code forks'
  terminal.integrated.env.*) this is automatable; where it does not (Copilot CLI,
  Claude Desktop) gating falls back to steering only.
- A steering note in the client's instructions file telling the agent to fetch
  credentials through grantry's get_credentials tool.

This is defense-in-depth, NOT a guarantee. It cannot remove ~/.aws/credentials,
the SSO token cache, or an instance role, and it does not control network egress
(an agent can still reach the instance metadata endpoint). The only airtight
boundary is running the agent with no ambient credentials at all. Callers should
say so plainly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The ambient AWS variables to blank in the agent's shell, plus the marker that
# forces any shelled `grantry run` under the agents policy. An empty string is
# treated as "unset" by the clients whose env blocks we write.
GATED_ENV: dict[str, str] = {
    "AWS_ACCESS_KEY_ID": "",
    "AWS_SECRET_ACCESS_KEY": "",
    "AWS_SESSION_TOKEN": "",
    "AWS_PROFILE": "",
    "AWS_DEFAULT_PROFILE": "",
    "GRANTRY_CALLER": "agent",
}

# A stable marker so steering is written once and never duplicated on re-run.
STEER_MARKER = "<!-- grantry:gated -->"

_VSCODE_ENV_KEYS = (
    "terminal.integrated.env.osx",
    "terminal.integrated.env.linux",
    "terminal.integrated.env.windows",
)


def merge_env_claude(config: dict[str, Any]) -> dict[str, Any]:
    """Merge the gated env into a Claude Code settings.json under its top-level
    `env` key, leaving every other setting untouched.
    """
    result = dict(config)
    result["env"] = {**(result.get("env") or {}), **GATED_ENV}
    return result


def merge_env_vscode(config: dict[str, Any]) -> dict[str, Any]:
    """Merge the gated env into a VS Code-style settings.json under each
    terminal.integrated.env.<os> key (written for all three OSes so a committed
    file is portable), leaving every other setting untouched.
    """
    result = dict(config)
    for key in _VSCODE_ENV_KEYS:
        result[key] = {**(result.get(key) or {}), **GATED_ENV}
    return result


def steering_body() -> str:
    """The steering note, carrying the idempotency marker on its first line."""
    return (
        f"{STEER_MARKER}\n"
        "## AWS access via grantry\n"
        "Get AWS credentials only through the grantry MCP tool `get_credentials` "
        "(it is policy-checked and audited). In this project the shell's ambient "
        "AWS credentials are intentionally blanked, so `aws --profile` and `~/.aws` "
        "profiles will not work. Once you hold credentials issued by grantry you may "
        "run `aws` and boto3 normally."
    )


def steering_mdc() -> str:
    """The steering note as a Cursor .mdc rule (frontmatter + body)."""
    return (
        "---\n"
        "description: Get AWS credentials through grantry, not ambient profiles\n"
        "alwaysApply: true\n"
        "---\n"
        f"{steering_body()}\n"
    )


def append_steering(existing: str, block: str) -> tuple[str, bool]:
    """Append a steering block to an instructions file's text unless the marker is
    already present. Returns (new_text, changed).
    """
    if STEER_MARKER in existing:
        return existing, False
    if existing.strip() == "":
        return block.rstrip("\n") + "\n", True
    sep = "\n" if existing.endswith("\n") else "\n\n"
    return existing + sep + block.rstrip("\n") + "\n", True


@dataclass(frozen=True)
class GatingAction:
    kind: str  # "env-claude" | "env-vscode" | "steer-md" | "steer-mdc"
    path: str  # relative to the current directory


@dataclass(frozen=True)
class GatingPlan:
    actions: tuple[GatingAction, ...]
    # A caveat printed when this client cannot have its shell creds starved by a
    # file (so gating is steering-only, or a no-op).
    note: str | None = None


def gating_plan(client_key: str) -> GatingPlan:
    """The project-scope files `--gated` should write for a given client. Env
    starvation where the client supports a file-writable agent-shell env, plus a
    steering note; steering-only or a note where it does not.
    """
    if client_key == "claude-code":
        return GatingPlan(
            (
                GatingAction("env-claude", ".claude/settings.json"),
                GatingAction("steer-md", "CLAUDE.md"),
            )
        )
    if client_key == "vscode":
        return GatingPlan(
            (
                GatingAction("env-vscode", ".vscode/settings.json"),
                GatingAction("steer-md", ".github/copilot-instructions.md"),
            )
        )
    if client_key == "cursor":
        return GatingPlan(
            (
                GatingAction("env-vscode", ".vscode/settings.json"),
                GatingAction("steer-mdc", ".cursor/rules/grantry.mdc"),
            )
        )
    if client_key == "windsurf":
        return GatingPlan(
            (
                GatingAction("env-vscode", ".vscode/settings.json"),
                GatingAction("steer-md", ".windsurf/rules/grantry.md"),
            )
        )
    if client_key == "copilot-cli":
        return GatingPlan(
            (GatingAction("steer-md", ".github/copilot-instructions.md"),),
            note=(
                "Copilot CLI has no file-writable shell environment, so grantry cannot "
                "blank ambient AWS credentials for it. Launch it from a shell that has "
                "none (no AWS_* vars, no ~/.aws), or the gate will not hold."
            ),
        )
    if client_key == "claude-desktop":
        return GatingPlan(
            (),
            note="Claude Desktop has no shell tool, so there is nothing to gate.",
        )
    return GatingPlan(())
