"""`grantry doctor`: a one-command health check of your grantry setup.

This module holds the pure pieces (the Check record, the tricky predicates, and
rendering); the CLI gathers the runtime state (session, files, env, network) and
assembles the list. Keeping the predicates pure makes the awkward cases
(completion configured-but-not-loaded, version behind) directly unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

_ICON = {"ok": "✓", "warn": "⚠", "fail": "✗"}  # ✓ ⚠ ✗


@dataclass(frozen=True)
class Check:
    level: str  # "ok" | "warn" | "fail"
    name: str  # short label, e.g. "session"
    detail: str  # human message, with a remediation when not ok


def version_check(current: str, latest: str | None) -> Check:
    """Compare the running version to the latest known on PyPI (None = unknown)."""
    from grantry.version_check import is_newer

    if latest is None:
        return Check("warn", "version", f"grantry {current} (could not reach PyPI to check)")
    if is_newer(latest, current):
        return Check(
            "warn",
            "version",
            f"grantry {current} — newer is out ({latest}). Upgrade: pipx upgrade grantry",
        )
    return Check("ok", "version", f"grantry {current} (latest)")


def completion_check(shell: str | None, rc_has_line: bool, loaded: bool) -> Check:
    """Tell the three completion states apart honestly. `loaded` is whether the
    current shell exported GRANTRY_COMPLETION_LOADED (i.e. actually sourced the
    completion), which is the only reliable signal that it is active here."""
    if shell is None:
        return Check(
            "warn", "completion", "could not detect your shell; run 'grantry completion --install'"
        )
    if loaded:
        return Check("ok", "completion", f"active in this {shell} session")
    if rc_has_line:
        return Check(
            "warn",
            "completion",
            f"configured in your {shell} rc but not loaded in this shell. Run: exec {shell}",
        )
    return Check("warn", "completion", "not installed. Run: grantry completion --install")


def render(checks: list[Check]) -> str:
    """A left-aligned checklist with an icon per line."""
    width = max((len(c.name) for c in checks), default=0)
    return "\n".join(f"  {_ICON[c.level]} {c.name.ljust(width)}  {c.detail}" for c in checks)


def exit_code(checks: list[Check]) -> int:
    """Non-zero when anything is a hard failure, so `doctor` is scriptable.
    Warnings (behind on version, completion not reloaded) do not fail."""
    return 1 if any(c.level == "fail" for c in checks) else 0
