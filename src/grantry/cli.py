"""The human CLI and the composition root. Thin over the broker."""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from datetime import datetime, timezone

from grantry.audit import AuditLog
from grantry.broker import Broker, NoSessionError
from grantry.config import state_path
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
    start = args.start_url or os.environ.get("GRANTRY_SSO_START_URL")
    region = args.region or os.environ.get("GRANTRY_SSO_REGION")
    if not start or not region:
        raise SystemExit(
            "Set --start-url and --region, or GRANTRY_SSO_START_URL and GRANTRY_SSO_REGION."
        )
    return start, region


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
        build_mcp(broker).run()
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
