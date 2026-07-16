"""The human CLI and the composition root. Thin over the broker."""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import sys
from datetime import datetime, timezone

from grantry.audit import AuditLog
from grantry.broker import Broker, NoSessionError
from grantry.config import state_path
from grantry.humanops import (
    append_profiles,
    env_from_credentials,
    format_exports,
    parse_profiles,
    profile_block,
    reconcile,
    strip_profiles,
)
from grantry.instance import load_instance, save_instance
from grantry.logging_setup import configure_logging
from grantry.mcp_server import build_mcp
from grantry.policy import Policy
from grantry.providers.aws import AwsProvider
from grantry.providers.base import InteractionHandler
from grantry.secrets import SecretStore


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TerminalHandler(InteractionHandler):
    def on_verification(self, verification_uri: str, user_code: str) -> None:
        print(f"To authorize, open:\n  {verification_uri}\nand confirm the code: {user_code}")

    def wait(self) -> None:
        with contextlib.suppress(EOFError):
            input("Press Enter after you have approved in the browser... ")


def build_broker(start_url: str, region: str) -> Broker:
    provider = AwsProvider(start_url, region)
    policy = Policy.load(state_path("policy.yaml"))
    return Broker(provider, policy, AuditLog(), SecretStore(), clock_iso=_iso_now)


def _instance(args: argparse.Namespace) -> tuple[str, str]:
    # Resolution order: CLI flag, then env var, then the instance saved on a
    # previous run. You provide it once (flag or env); grantry remembers it.
    saved = load_instance()
    start = args.start_url or os.environ.get("GRANTRY_SSO_START_URL")
    region = args.region or os.environ.get("GRANTRY_SSO_REGION")
    if start and region:
        # An explicit instance was given: remember it for next time.
        if saved is None or saved.start_url != start or saved.region != region:
            save_instance(start, region)
        return start, region
    if saved is not None:
        # Fall back to the remembered instance, letting a partial flag override.
        return start or saved.start_url, region or saved.region
    raise SystemExit(
        "No Identity Center instance known yet. Pass --start-url and --region once "
        "(or set GRANTRY_SSO_START_URL and GRANTRY_SSO_REGION); grantry will remember it."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="grantry")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    parser.add_argument("--start-url", default=None)
    parser.add_argument("--region", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login")
    sub.add_parser("ls")
    sub.add_parser("audit")
    sub.add_parser("mcp")
    p_run = sub.add_parser("run", help="run a command as an identity")
    p_run.add_argument("identity")
    p_run.add_argument("--ttl", default="1h")
    p_run.add_argument("cmd", nargs=argparse.REMAINDER)
    p_switch = sub.add_parser("switch", help="print shell exports to adopt an identity")
    p_switch.add_argument("identity")
    p_switch.add_argument("--ttl", default="1h")
    p_pop = sub.add_parser("populate", help="write ~/.aws/config profiles for your access")
    p_pop.add_argument("--dry-run", action="store_true")
    p_pop.add_argument("--workload-region", default=None)
    sub.add_parser("check", help="diagnose configuration and access")

    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    if args.command == "audit":
        for e in AuditLog().entries():
            verdict = "allow" if e["allowed"] else "deny"
            print(f"{e['at']} {e['caller']} {e['identity']} {verdict} ({e['reason']})")
        return 0

    start, region = _instance(args)
    broker = build_broker(start, region)

    if args.command == "login":
        session = broker.login(TerminalHandler())
        print(f"Logged in to {session.start_url}.")
        return 0

    if args.command == "ls":
        try:
            idents = broker.identities()
        except NoSessionError:
            print("No active session. Run 'grantry login' first.")
            return 1
        for i in sorted(idents, key=lambda x: x.key):
            print(i.key)
        return 0

    if args.command == "mcp":
        label = os.environ.get("GRANTRY_AGENT_LABEL", "agent")
        build_mcp(broker, caller_label=label).run()
        return 0

    if args.command == "run":
        return _cmd_run(broker, region, args.identity, args.ttl, args.cmd)

    if args.command == "switch":
        return _cmd_switch(broker, region, args.identity, args.ttl)

    if args.command == "populate":
        return _cmd_populate(broker, start, region, args.workload_region, args.dry_run)

    if args.command == "check":
        return _cmd_check(broker)

    return 2


def _human_credentials(broker: Broker, ident_key: str, ttl: str) -> tuple[int, object]:
    """Grant an identity as a human. Returns (exit_code, credentials_or_None).
    exit_code is 0 on success, non-zero with a printed reason otherwise.
    """
    from grantry.ttl import parse_ttl

    try:
        seconds = parse_ttl(ttl)
    except ValueError as e:
        print(f"Invalid ttl: {e}")
        return 2, None
    try:
        result = broker.grant(ident_key, seconds, caller="human")
    except NoSessionError:
        print("No active session. Run 'grantry login' first.")
        return 1, None
    if result.credentials is None:
        print(f"Denied: {result.decision.reason}")
        return 1, None
    if result.advisory:
        print(f"note: {result.advisory}", file=sys.stderr)
    return 0, result.credentials


def _cmd_run(broker: Broker, region: str, ident_key: str, ttl: str, cmd: list[str]) -> int:
    # argparse REMAINDER keeps a leading "--"; drop it.
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("Nothing to run. Usage: grantry run <identity> -- <command>")
        return 2
    code, creds = _human_credentials(broker, ident_key, ttl)
    if code != 0 or creds is None:
        return code
    from grantry.providers.base import Credentials

    assert isinstance(creds, Credentials)
    child_env = {**os.environ, **env_from_credentials(creds, region)}
    completed = subprocess.run(cmd, env=child_env, check=False)
    return completed.returncode


def _cmd_switch(broker: Broker, region: str, ident_key: str, ttl: str) -> int:
    code, creds = _human_credentials(broker, ident_key, ttl)
    if code != 0 or creds is None:
        return code
    from grantry.providers.base import Credentials

    assert isinstance(creds, Credentials)
    print(format_exports(env_from_credentials(creds, region)))
    print(
        f'# to adopt {ident_key} in this shell: eval "$(grantry switch {ident_key})"',
        file=sys.stderr,
    )
    return 0


def _cmd_populate(
    broker: Broker, start_url: str, sso_region: str, workload_region: str | None, dry_run: bool
) -> int:
    region = workload_region or sso_region
    try:
        idents = broker.identities()
    except NoSessionError:
        print("No active session. Run 'grantry login' first.")
        return 1
    desired = {}
    for i in sorted(idents, key=lambda x: x.key):
        name = f"{i.account_name}.{i.role_name}"
        desired[name] = profile_block(
            name, i.account_id, i.role_name, start_url, sso_region, region
        )
    existing = _read_aws_config()
    plan = reconcile(existing, set(desired))
    if dry_run:
        for name in sorted(plan.to_add):
            print(f"+ {name}")
        for name in sorted(plan.kept):
            print(f"= {name} (unchanged)")
        for name in sorted(plan.to_prune):
            print(f"- {name} (would remove)")
        print(
            f"\n{len(plan.to_add)} to add, {len(plan.kept)} kept, "
            f"{len(plan.to_prune)} to remove. Re-run without --dry-run to apply."
        )
        return 0
    _write_aws_config(desired, plan.to_prune)
    print(f"Wrote {len(desired)} profiles, removed {len(plan.to_prune)} stale ones.")
    return 0


def _cmd_check(broker: Broker) -> int:
    session = broker.cached_session()
    if session is None:
        print("No active session. Run 'grantry login'.")
        return 201
    print(f"Session OK for {session.start_url} (region {session.region}).")
    try:
        idents = broker.identities()
    except NoSessionError:
        print("Session present but identity listing failed; try 'grantry login --force'.")
        return 202
    print(f"Access OK: {len(idents)} identities reachable.")
    return 0


def _aws_config_path() -> str:
    return os.environ.get("AWS_CONFIG_FILE") or os.path.expanduser("~/.aws/config")


def _read_aws_config() -> dict[str, dict[str, str]]:
    path = _aws_config_path()
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return parse_profiles(fh.read())


def _write_aws_config(desired: dict[str, str], to_prune: set[str]) -> None:
    path = _aws_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    # Remove the managed profiles we are about to rewrite plus the stale ones,
    # leaving hand-written profiles and comments untouched.
    text = strip_profiles(text, set(desired) | to_prune)
    text = append_profiles(text, [desired[name] for name in sorted(desired)])
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


if __name__ == "__main__":
    sys.exit(main())
