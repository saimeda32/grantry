"""The human CLI and the composition root. Thin over the broker."""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

from grantry.audit import AuditLog
from grantry.broker import Broker, NoSessionError
from grantry.completion import SHELLS
from grantry.config import state_path
from grantry.humanops import (
    append_profiles,
    env_from_credentials,
    format_exports,
    parse_profiles,
    profile_block,
    reconcile,
    safe_profile_name,
    strip_profiles,
)
from grantry.instance import load_instance, save_instance
from grantry.logging_setup import configure_logging
from grantry.mcp_install import CLIENTS, config_path, grantry_command, merge_server, server_entry
from grantry.mcp_server import build_mcp
from grantry.policy import Policy
from grantry.providers.aws import AwsProvider
from grantry.providers.base import InteractionHandler
from grantry.secrets import SecretStore


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TerminalHandler(InteractionHandler):
    def on_verification(self, verification_uri: str, user_code: str) -> None:
        import webbrowser

        # The URL already carries the code, so approving is usually one click.
        # Skip the auto-open on headless boxes or when the user opts out.
        opened = False
        if os.environ.get("GRANTRY_NO_BROWSER") != "1":
            with contextlib.suppress(Exception):
                opened = webbrowser.open(verification_uri)
        if opened:
            print(f"Opened your browser to approve this login (code {user_code}).")
            print(f"If it did not open, visit:\n  {verification_uri}")
        else:
            print(f"To authorize, open:\n  {verification_uri}\nand confirm the code: {user_code}")

    def wait(self) -> None:
        # No prompt to press: the provider polls until you approve in the browser.
        print("Waiting for you to approve in the browser...")


def build_broker(start_url: str, region: str) -> Broker:
    from grantry.awscli_cache import write_sso_cache

    provider = AwsProvider(start_url, region)
    policy = Policy.load(state_path("policy.yaml"))
    return Broker(
        provider,
        policy,
        AuditLog(),
        SecretStore(),
        clock_iso=_iso_now,
        on_session=write_sso_cache,
    )


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
    # Last resort: defaults from ~/.grantry/config.toml, if the user set them.
    # This only fires when nothing else is known, so it never overrides a flag,
    # an env var, or a remembered instance.
    from grantry.appconfig import load_config

    cfg = load_config()
    start = start or cfg.start_url
    region = region or cfg.region
    # If we have one half and a terminal, ask for the other rather than failing
    # a first login just because one flag was forgotten.
    if sys.stdin.isatty():
        if start and not region:
            region = input("SSO region (e.g. us-east-1): ").strip() or None
        elif region and not start:
            start = input("Identity Center start URL: ").strip() or None
    if start and region:
        save_instance(start, region)
        return start, region
    raise SystemExit(
        "No Identity Center instance known yet. Pass --start-url and --region once "
        "(or set GRANTRY_SSO_START_URL and GRANTRY_SSO_REGION); grantry will remember it."
    )


def main(argv: list[str] | None = None) -> int:
    # Turn a Ctrl-C into a clean message and the conventional 130 exit code,
    # instead of dumping a Python traceback the user did not ask to see.
    try:
        return _run(argv)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


def _run(argv: list[str] | None = None) -> int:
    from grantry.appconfig import load_config

    app_cfg = load_config()
    default_ttl = app_cfg.ttl
    parser = argparse.ArgumentParser(prog="grantry")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    parser.add_argument("--start-url", default=None)
    parser.add_argument("--region", default=None)
    # A shared parent so the instance flags also work AFTER the subcommand
    # (grantry login --start-url ...), which is the order people naturally type.
    # SUPPRESS on the default means "not given here" does not clobber a value given
    # before the subcommand, so both orders work. help=SUPPRESS keeps these off
    # every subcommand's help: grantry remembers the instance after the first
    # login, so there is no reason to advertise them on ls, admin, run, and so on.
    inst = argparse.ArgumentParser(add_help=False)
    inst.add_argument("--start-url", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    inst.add_argument("--region", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    p_login = sub.add_parser("login", parents=[inst], help="log in to Identity Center")
    p_login.add_argument(
        "--force-refresh", action="store_true", help="ignore any cached session and log in again"
    )
    p_login.add_argument(
        "--no-populate",
        action="store_true",
        help="do not write ~/.aws/config profiles after logging in",
    )
    sub.add_parser("logout", help="clear the saved session for the current instance")
    sub.add_parser("version", help="print the grantry version")
    sub.add_parser("instances", help="list remembered Identity Center instances")
    p_use = sub.add_parser("use", help="switch the current instance by name or prefix")
    p_use.add_argument("name", nargs="?", default=None)
    sub.add_parser("ls", parents=[inst])
    p_audit = sub.add_parser("audit", help="print or visualize the grant history")
    p_audit.add_argument("--visualize", action="store_true", help="write an HTML timeline instead")
    p_audit.add_argument("-o", "--out", default="grantry-audit.html")
    sub.add_parser("mcp", parents=[inst])
    p_graph = sub.add_parser(
        "graph", parents=[inst], help="write an HTML map of what agents can reach"
    )
    p_graph.add_argument("--caller", choices=["agent", "human"], default="agent")
    p_graph.add_argument("-o", "--out", default="grantry-access.html")
    p_run = sub.add_parser("run", parents=[inst], help="run a command as an identity")
    p_run.add_argument("identity", nargs="?", default=None)
    p_run.add_argument("--ttl", default=default_ttl)
    p_run.add_argument("cmd", nargs=argparse.REMAINDER)
    p_switch = sub.add_parser(
        "switch", parents=[inst], help="print shell exports to adopt an identity"
    )
    p_switch.add_argument("identity", nargs="?", help="omit to pick interactively")
    p_switch.add_argument("--ttl", default=default_ttl)
    p_credproc = sub.add_parser(
        "credential-process",
        parents=[inst],
        help="emit credentials as JSON for an AWS config credential_process entry",
    )
    p_credproc.add_argument("--identity", required=True)
    p_credproc.add_argument("--ttl", default=default_ttl)
    p_credproc.add_argument(
        "--caller",
        choices=["human", "agent"],
        default=None,
        help="policy class to evaluate as (default: human, or agent if GRANTRY_CALLER=agent)",
    )
    p_console = sub.add_parser(
        "console", parents=[inst], help="open the AWS console in a browser as an identity"
    )
    p_console.add_argument("identity", nargs="?", help="omit to pick interactively")
    p_console.add_argument("--ttl", default=default_ttl)
    p_console.add_argument("--destination", default=None, help="a console URL to land on")
    p_console.add_argument(
        "--print", dest="print_url", action="store_true", help="print the URL instead of opening"
    )
    p_pop = sub.add_parser(
        "populate", parents=[inst], help="write ~/.aws/config profiles for your access"
    )
    p_pop.add_argument("--dry-run", action="store_true")
    p_pop.add_argument("--workload-region", default=None)
    p_check = sub.add_parser("check", parents=[inst], help="diagnose configuration and access")
    p_check.add_argument(
        "--sandbox",
        action="store_true",
        help="check whether an agent here has ambient AWS access that bypasses the policy gate",
    )
    sub.add_parser(
        "status", parents=[inst], help="a quick overview of your session, access, and policy"
    )
    p_init = sub.add_parser(
        "init", parents=[inst], help="generate a starter policy from your real access"
    )
    p_init.add_argument("--force", action="store_true", help="overwrite an existing policy")
    p_admin = sub.add_parser(
        "admin", parents=[inst], help="administrator commands (need management access)"
    )
    admin_sub = p_admin.add_subparsers(dest="admin_command", required=True)
    p_assign = admin_sub.add_parser("assignments", help="crawl who-has-what across the org")
    p_assign.add_argument(
        "--as",
        dest="as_identity",
        default=None,
        help="admin identity to crawl with, as account/role; omit to pick interactively",
    )
    p_assign.add_argument("--ttl", default=default_ttl)
    p_assign.add_argument("--visualize", action="store_true")
    p_assign.add_argument("-o", "--out", default="grantry-assignments.html")
    p_assign.add_argument(
        "--snapshot", action="store_true", help="save this crawl for later comparison"
    )
    p_assign.add_argument(
        "--diff", action="store_true", help="compare this crawl to the last snapshot"
    )
    p_install = sub.add_parser(
        "install", help="add grantry to an AI client's MCP config (auto-detects all if none named)"
    )
    p_install.add_argument(
        "clients", nargs="*", help="claude-code, cursor, vscode, ... (blank = all found)"
    )
    p_install.add_argument("--dry-run", action="store_true")
    p_uninstall = sub.add_parser("uninstall", help="remove grantry from an AI client's MCP config")
    p_uninstall.add_argument(
        "clients", nargs="*", help="claude-code, cursor, ... (blank = all found)"
    )
    p_completion = sub.add_parser(
        "completion", help="print a shell completion script (bash, zsh, or fish)"
    )
    p_completion.add_argument("shell", nargs="?", choices=SHELLS, default=None)
    # Internal: feeds identity names to the completion scripts. Reads a cache, so
    # it is instant and never touches the network. Omitting help keeps it out of
    # the help listing, and metavar keeps it out of the usage line.
    sub.add_parser("_complete-identities")

    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    if args.command == "version":
        from grantry import __version__

        print(f"grantry {__version__}")
        return 0

    if args.command == "completion":
        from grantry.completion import completion_script

        shell = args.shell or os.path.basename(os.environ.get("SHELL", ""))
        if shell not in SHELLS:
            print(
                f"Could not detect your shell. Pass one of: {', '.join(SHELLS)}.", file=sys.stderr
            )
            return 2
        print(completion_script(shell), end="")
        return 0

    if args.command == "_complete-identities":
        from grantry.idcache import read_keys

        for key in read_keys():
            print(key)
        return 0

    if args.command == "instances":
        from grantry.instance import list_instances

        rows = list_instances()
        if not rows:
            print("No instances remembered yet. Run 'grantry login' first.")
            return 1
        for name, cfg, is_current in rows:
            marker = "*" if is_current else " "
            print(f"{marker} {name}  {cfg.start_url}  ({cfg.region})")
        return 0

    if args.command == "use":
        from grantry.instance import list_instances, use_instance
        from grantry.pick import choose

        target: str | None = args.name
        if target is None:
            rows = list_instances()
            if not rows:
                print("No instances remembered yet. Run 'grantry login' first.")
                return 1
            target = choose([n for n, _cfg, _cur in rows])
            if target is None:
                print("No instance chosen.")
                return 1
        chosen = use_instance(target)
        if chosen is None:
            print(f"No single instance matches {target!r}. See 'grantry instances'.")
            return 1
        print(f"Now using {chosen.start_url} ({chosen.region}).")
        return 0

    if args.command == "audit":
        entries = AuditLog().entries()
        if args.visualize:
            from grantry.render import render_audit

            html = render_audit(entries, _iso_now()[:10])
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(html)
            print(f"Wrote audit timeline ({len(entries)} grants) to {args.out}")
            return 0
        for e in entries:
            verdict = "allow" if e["allowed"] else "deny"
            print(f"{e['at']} {e['caller']} {e['identity']} {verdict} ({e['reason']})")
        return 0

    if args.command == "install":
        return _cmd_install(args.clients, args.dry_run)

    if args.command == "uninstall":
        return _cmd_uninstall(args.clients)

    # The sandbox check inspects this environment for ambient AWS access. It must
    # work with no configured instance, since it is meant to run inside an agent's
    # sandbox where grantry may never have been pointed anywhere.
    if args.command == "check" and args.sandbox:
        return _cmd_sandbox_check()

    start, region = _instance(args)
    broker = build_broker(start, region)

    if args.command == "login":
        if not args.force_refresh and broker.cached_session() is not None:
            print("Already logged in. Use --force-refresh to log in again.")
            return 0
        session = broker.login(TerminalHandler())
        print(f"Logged in to {session.start_url}.")
        skip_populate = args.no_populate or os.environ.get("GRANTRY_NO_POPULATE") == "1"
        if skip_populate:
            # Still warm the completion cache so TAB works right away. Best effort:
            # a slow or failed listing must never turn a successful login into an error.
            with contextlib.suppress(Exception):
                broker.identities()
        else:
            # Write ~/.aws/config profiles for every account and role, so the native
            # aws CLI, boto3, and Terraform work too, whether or not you use grantry.
            # This reconciles safely (it never touches your hand-written profiles) and
            # also warms the completion cache. Best effort, so it cannot fail the login.
            with contextlib.suppress(Exception):
                _cmd_populate(broker, start, region, None, dry_run=False)
        print("The native 'aws' CLI, boto3, and Terraform can use this session too.")
        if skip_populate:
            print("Run 'grantry populate' to write matching ~/.aws/config profiles.")
        print(
            "Next: 'grantry ls' to see your roles, then 'grantry run <id> -- <cmd>', "
            "'grantry console', or 'grantry switch'."
        )
        return 0

    if args.command == "logout":
        from grantry.awscli_cache import sso_cache_path

        had = broker.logout()
        cache = sso_cache_path(start)
        if cache.exists():
            cache.unlink()
        print("Logged out." if had else "No active session to clear.")
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
        ident = _resolve_identity(broker, args.identity)
        if ident is None:
            return 1
        return _cmd_switch(broker, region, ident, args.ttl)

    if args.command == "credential-process":
        return _cmd_credential_process(broker, args.identity, args.ttl, args.caller)

    if args.command == "console":
        ident = _resolve_identity(broker, args.identity)
        if ident is None:
            return 1
        return _cmd_console(broker, ident, args.ttl, args.destination, args.print_url)

    if args.command == "populate":
        return _cmd_populate(broker, start, region, args.workload_region, args.dry_run)

    if args.command == "check":
        return _cmd_check(broker)

    if args.command == "status":
        return _cmd_status(broker)

    if args.command == "init":
        return _cmd_init(broker, args.force)

    if args.command == "graph":
        return _cmd_graph(broker, args.caller, args.out)

    if args.command == "admin":
        if args.admin_command == "assignments":
            if sum([args.snapshot, args.diff, args.visualize]) > 1:
                print("Pick only one of --snapshot, --diff, or --visualize.")
                return 2
            return _cmd_admin_assignments(
                broker,
                region,
                args.as_identity,
                args.ttl,
                args.visualize,
                args.out,
                args.snapshot,
                args.diff,
            )
        return 2

    return 2


def _cmd_admin_assignments(
    broker: Broker,
    region: str,
    as_identity: str | None,
    ttl: str,
    visualize: bool,
    out: str,
    snapshot: bool = False,
    diff: bool = False,
) -> int:
    import sys as _sys

    from grantry.admin import crawl_assignments

    ident = _resolve_identity(broker, as_identity)
    if ident is None:
        return 1
    code, creds = _human_credentials(broker, ident, ttl)
    if code != 0 or creds is None:
        return code
    from grantry.providers.base import Credentials

    assert isinstance(creds, Credentials)

    import botocore.session
    from botocore.config import Config

    cfg = Config(retries={"mode": "standard", "max_attempts": 10})

    def make_client(service: str) -> Any:  # noqa: ANN401
        session = botocore.session.Session()
        return session.create_client(
            service,
            region_name=region,
            aws_access_key_id=creds.access_key_id,
            aws_secret_access_key=creds.secret_access_key,
            aws_session_token=creds.session_token,
            config=cfg,
        )

    def progress(done: int, total: int) -> None:
        print(f"\rCrawling accounts {done}/{total}...", end="", file=_sys.stderr, flush=True)

    try:
        assignments = crawl_assignments(make_client, on_progress=progress)
    except Exception as e:  # surface AWS access errors clearly
        print(f"\nCrawl failed: {e}", file=_sys.stderr)
        print("The identity you crawled with may lack sso-admin/organizations access.")
        return 1
    print("", file=_sys.stderr)

    if diff:
        from grantry.snapshots import diff_assignments, latest_snapshot, save_snapshot

        previous = latest_snapshot()
        if previous is None:
            print("No earlier snapshot to compare against. Saving this one as the baseline.")
            save_snapshot(assignments, _iso_now().replace(":", "-"))
            return 0
        added, removed = diff_assignments(previous, assignments)
        if not added and not removed:
            print("No access changes since the last snapshot.")
        for a in added:
            print(f"+ {a.principal_name} gained {a.permission_set_name} on {a.account_name}")
        for a in removed:
            print(f"- {a.principal_name} lost {a.permission_set_name} on {a.account_name}")
        print(f"\n{len(added)} added, {len(removed)} removed.")
        save_snapshot(assignments, _iso_now().replace(":", "-"))
        return 0

    if snapshot:
        from grantry.snapshots import save_snapshot

        path = save_snapshot(assignments, _iso_now().replace(":", "-"))
        print(f"Saved a snapshot of {len(assignments)} assignments to {path}")
        return 0

    if visualize:
        from grantry.render import render_assignments

        html = render_assignments(assignments, _iso_now()[:10])
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"Wrote {len(assignments)} assignments to {out}")
        return 0

    print("principal_type,principal_name,permission_set,account_id,account_name")
    for a in assignments:
        print(
            f"{a.principal_type},{a.principal_name},{a.permission_set_name},"
            f"{a.account_id},{a.account_name}"
        )
    return 0


def _cmd_graph(broker: Broker, caller: str, out: str) -> int:
    from grantry.graphdata import access_surface
    from grantry.render import render_access_surface

    try:
        idents = broker.identities()
    except NoSessionError:
        print("No active session. Run 'grantry login' first.")
        return 1
    policy = Policy.load(state_path("policy.yaml"))
    surface = access_surface(idents, policy, caller)
    html = render_access_surface(surface, _iso_now()[:10])
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(
        f"Wrote access surface for {caller}s to {out} "
        f"({surface.allowed_count} of {len(surface.cells)} identities allowed, "
        f"{surface.reachable_accounts} accounts reachable)."
    )
    return 0


def _cmd_init(broker: Broker, force: bool) -> int:
    from grantry.scaffold import scaffold_policy

    path = state_path("policy.yaml")
    if path.exists() and not force:
        print(f"A policy already exists at {path}. Re-run with --force to overwrite it.")
        return 1
    try:
        idents = broker.identities()
    except NoSessionError:
        print("No active session. Run 'grantry login' first.")
        return 1
    text = scaffold_policy(idents, _iso_now()[:10])
    path.write_text(text)
    print(f"Wrote a starter policy from your {len(idents)} identities to {path}.")
    print("Heads up: this starter is PERMISSIVE. Agents may use any role you can.")
    print(f"To restrict them, edit {path} and replace the '*/*' allow with the")
    print("specific accounts and roles they should have. Your identities are listed there.")
    return 0


def _cli_caller(explicit: str | None = None) -> str:
    """Which policy class a CLI credential request is evaluated under.

    A human at the keyboard is trusted, so CLI commands default to the 'humans'
    section (default-allow). But the CLI cannot tell a human apart from an AI
    agent that has a shell, so an agent could otherwise run
    'grantry run <anything>' and escape its deny-by-default 'agents' rules.
    Setting GRANTRY_CALLER=agent in the agent's environment makes every grantry
    command evaluate under the 'agents' policy, closing that gap. An explicit
    --caller (where a command offers one) still wins.
    """
    if explicit in ("agent", "human"):
        assert explicit is not None
        return explicit
    if os.environ.get("GRANTRY_CALLER") == "agent":
        return "agent"
    return "human"


def _human_credentials(
    broker: Broker, ident_key: str, ttl: str, caller: str | None = None
) -> tuple[int, object]:
    """Grant an identity. Returns (exit_code, credentials_or_None). exit_code is
    0 on success, non-zero with a printed reason otherwise.
    """
    from grantry.ttl import parse_ttl

    resolved = _cli_caller(caller)
    try:
        seconds = parse_ttl(ttl)
    except ValueError as e:
        print(f"Invalid ttl: {e}")
        return 2, None
    try:
        result = broker.grant(ident_key, seconds, caller=resolved)
    except NoSessionError:
        print("No active session. Run 'grantry login' first.")
        return 1, None
    except Exception as e:  # a real AWS failure (throttling, network, denied API)
        print(f"Could not get credentials: {e}")
        print("Run 'grantry check' to diagnose your session and access.")
        return 1, None
    if result.credentials is None:
        reason = result.decision.reason
        print(f"Denied: {reason}")
        if "unknown identity" in reason:
            print("See 'grantry ls' for valid identities (they look like account/role).")
        else:
            print("This is blocked by your policy. Review it with 'grantry status'.")
        return 1, None
    if result.advisory:
        print(f"note: {result.advisory}", file=sys.stderr)
    return 0, result.credentials


def _resolve_identity(broker: Broker, identity: str | None) -> str | None:
    """Return the identity to use: the given one, or an interactive pick when it
    was omitted. Prints a clear reason and returns None when it cannot resolve.
    """
    if identity:
        return identity
    from grantry.pick import choose

    try:
        idents = broker.identities()
    except NoSessionError:
        print("No active session. Run 'grantry login' first.")
        return None
    keys = sorted(i.key for i in idents)
    if not keys:
        print("No identities available.")
        return None
    chosen = choose(keys)
    if chosen is None:
        print("No identity chosen. Pass one explicitly, e.g. 'grantry switch acct/Role'.")
    return chosen


def _cmd_console(
    broker: Broker, ident_key: str, ttl: str, destination: str | None, print_url: bool
) -> int:
    import webbrowser

    from grantry.console import build_console_url
    from grantry.providers.base import Credentials

    code, creds = _human_credentials(broker, ident_key, ttl)
    if code != 0 or creds is None:
        return code
    assert isinstance(creds, Credentials)
    try:
        url = build_console_url(creds, destination) if destination else build_console_url(creds)
    except Exception as e:
        print(f"Could not build the console sign-in URL: {e}")
        return 1
    if print_url:
        print(url)
        return 0
    print(f"Opening the AWS console as {ident_key} in your browser.")
    webbrowser.open(url)
    return 0


def _cmd_credential_process(broker: Broker, ident_key: str, ttl: str, caller: str | None) -> int:
    # The AWS SDK spec: on success print the credential JSON to stdout and exit
    # 0; on failure print a human message to stderr and exit non-zero. Nothing
    # but the JSON may go to stdout, so all messages here use stderr.
    from grantry.humanops import credential_process_json
    from grantry.providers.base import Credentials
    from grantry.ttl import parse_ttl

    resolved = _cli_caller(caller)
    try:
        seconds = parse_ttl(ttl)
    except ValueError as e:
        print(f"Invalid ttl: {e}", file=sys.stderr)
        return 2
    try:
        result = broker.grant(ident_key, seconds, caller=resolved)
    except NoSessionError:
        print("No active grantry session. Run 'grantry login' first.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"grantry could not get credentials: {e}", file=sys.stderr)
        return 1
    if result.credentials is None:
        print(f"Denied by policy: {result.decision.reason}", file=sys.stderr)
        return 1
    assert isinstance(result.credentials, Credentials)
    print(credential_process_json(result.credentials))
    return 0


def _cmd_run(broker: Broker, region: str, ident_key: str | None, ttl: str, cmd: list[str]) -> int:
    # argparse REMAINDER keeps a leading "--"; drop it.
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if ident_key is None:
        print("Usage: grantry run <identity> -- <command>")
        print("See 'grantry ls' for identities, or 'grantry switch' to pick one interactively.")
        return 2
    if not cmd:
        print(f"Nothing to run. Usage: grantry run {ident_key} -- <command>")
        return 2
    code, creds = _human_credentials(broker, ident_key, ttl)
    if code != 0 or creds is None:
        return code
    from grantry.providers.base import Credentials

    assert isinstance(creds, Credentials)
    child_env = {**os.environ, **env_from_credentials(creds, region)}
    try:
        completed = subprocess.run(cmd, env=child_env, check=False)
    except FileNotFoundError:
        print(f"Command not found: {cmd[0]}")
        return 127
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
        name = safe_profile_name(i.account_name, i.role_name)
        desired[name] = profile_block(
            name, i.account_id, i.role_name, start_url, sso_region, region
        )
    existing = _read_aws_config()
    # A profile name that already exists but is NOT grantry-managed is a
    # hand-written profile. Never overwrite it; skip it and tell the user, so
    # populate can never silently clobber their own config.
    conflicts = sorted(
        n for n in desired if n in existing and existing[n].get("grantry_managed") != "true"
    )
    for n in conflicts:
        del desired[n]
    plan = reconcile(existing, set(desired))
    if dry_run:
        for name in sorted(plan.to_add):
            print(f"+ {name}")
        for name in sorted(plan.kept):
            print(f"= {name} (unchanged)")
        for name in sorted(plan.to_prune):
            print(f"- {name} (would remove)")
        for name in conflicts:
            print(f"! {name} (skipped: a hand-written profile with this name already exists)")
        print(
            f"\n{len(plan.to_add)} to add, {len(plan.kept)} kept, "
            f"{len(plan.to_prune)} to remove, {len(conflicts)} skipped. "
            "Re-run without --dry-run to apply."
        )
        return 0
    _write_aws_config(desired, plan.to_prune)
    msg = f"Wrote {len(desired)} profiles, removed {len(plan.to_prune)} stale ones."
    if conflicts:
        msg += (
            f" Skipped {len(conflicts)} name(s) that collide with your hand-written "
            f"profiles: {', '.join(conflicts)}."
        )
    print(msg)
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
        print("Your session looks present but has expired. Run 'grantry login --force-refresh'.")
        return 202
    except Exception as e:
        print(f"Could not list your access: {e}")
        print("Check your network and that the SSO region is correct, then try again.")
        return 203
    print(f"Access OK: {len(idents)} identities reachable.")
    return 0


def _cmd_sandbox_check() -> int:
    """Report ambient AWS access an agent in this environment could use to go
    around grantry's policy gate. Exit 0 means none was found (the gate is a real
    boundary here); exit 211 means some was found. Meant to be run inside the
    agent's sandbox, so it needs no session or configured instance.
    """
    import pathlib

    findings: list[str] = []

    ambient_env = [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
        "AWS_DEFAULT_PROFILE",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
    ]
    for name in ambient_env:
        if os.environ.get(name):
            findings.append(f"environment variable {name} is set")

    home = pathlib.Path.home()
    creds = pathlib.Path(
        os.environ.get("AWS_SHARED_CREDENTIALS_FILE") or (home / ".aws" / "credentials")
    )
    try:
        if creds.is_file() and creds.stat().st_size > 0:
            findings.append(f"a static credentials file exists at {creds}")
    except OSError:
        pass

    cfg = pathlib.Path(os.environ.get("AWS_CONFIG_FILE") or (home / ".aws" / "config"))
    try:
        text = cfg.read_text(encoding="utf-8") if cfg.is_file() else ""
    except OSError:
        text = ""
    if "grantry_managed = true" in text:
        findings.append(
            f"grantry-populated profiles exist in {cfg}; an agent with a shell could "
            "run 'aws --profile ...' directly, around the MCP gate"
        )
    elif "[profile" in text or "[default]" in text:
        findings.append(f"AWS profiles in {cfg} may provide ambient access")

    if os.environ.get("GRANTRY_CALLER") != "agent":
        findings.append(
            "GRANTRY_CALLER is not 'agent', so grantry's own CLI (run, switch, console, "
            "credential-process) would be evaluated as a trusted human. Set "
            "GRANTRY_CALLER=agent so it is gated by your agents policy."
        )

    if not findings:
        print("Sandbox check passed: no ambient AWS access detected.")
        print("grantry's MCP tools (or a credential_process profile with --caller agent) are the")
        print("only path to credentials here, so the policy gate is a real boundary.")
        return 0

    print("Sandbox check found ambient AWS access an agent could use to bypass the policy gate:")
    for item in findings:
        print(f"  - {item}")
    print("")
    print("For the gate to be a real boundary, run the agent with none of the above: no AWS_*")
    print("credential env vars, no static credentials file, and no native profiles. Give it only")
    print("grantry's MCP server, or a credential_process profile with --caller agent.")
    return 211


def _human_duration(seconds: float) -> str:
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    if minutes:
        return f"{minutes}m"
    return "under a minute"


def _cmd_status(broker: Broker) -> int:
    import time

    from grantry import __version__
    from grantry.idcache import read_keys
    from grantry.instance import list_instances, load_instance

    print(f"grantry {__version__}")

    inst = load_instance()
    if inst is None:
        print("Instance:  not configured. Run 'grantry login --start-url ... --region ...'.")
    else:
        others = max(0, len(list_instances()) - 1)
        extra = f", {others} other remembered" if others else ""
        print(f"Instance:  {inst.start_url} (region {inst.region}){extra}")

    session = broker.cached_session()
    if session is None:
        print("Session:   logged out. Run 'grantry login'.")
    else:
        remaining = session.expires_at - time.time()
        if remaining <= 0:
            print("Session:   expired. Run 'grantry login --force-refresh'.")
        else:
            print(f"Session:   active, expires in {_human_duration(remaining)}.")

    keys = read_keys()
    if keys:
        print(f"Access:    {len(keys)} identities cached (from your last 'grantry ls').")
    else:
        print("Access:    none cached yet. Run 'grantry ls' to load your identities.")

    policy = state_path("policy.yaml")
    if policy.exists():
        print(f"Policy:    {policy}")
    else:
        print("Policy:    none yet, so agents are denied by default. Run 'grantry init'.")

    print(f"Audit:     {len(AuditLog().entries())} grants recorded.")
    return 0


def _cmd_install(client_keys: list[str], dry_run: bool) -> int:
    import json

    saved = load_instance()
    start_url = saved.start_url if saved else None
    region = saved.region if saved else None
    command, cmd_args = grantry_command()

    if client_keys:
        unknown = [k for k in client_keys if k not in CLIENTS]
        if unknown:
            print(f"Unknown client(s): {', '.join(unknown)}. Known: {', '.join(sorted(CLIENTS))}")
            return 2
        targets = [CLIENTS[k] for k in client_keys]
    else:
        # Auto-detect: a client counts as present if its config file exists, or
        # its parent directory does (installed but no MCP config yet).
        targets = [
            c
            for c in CLIENTS.values()
            if os.path.exists(config_path(c)) or os.path.isdir(os.path.dirname(config_path(c)))
        ]
        if not targets:
            print(
                "No known AI clients detected. Name one explicitly, e.g. 'grantry install cursor'."
            )
            return 1

    changed = 0
    for client in targets:
        path = config_path(client)
        config: dict[str, Any] = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                content = fh.read().strip()
                config = json.loads(content) if content else {}
        # Each client tags its own attribution label.
        client_entry = server_entry(command, cmd_args, client.key, start_url, region)
        merged = merge_server(config, client.root, "grantry", client_entry)
        if dry_run:
            print(f"[dry-run] would write grantry to {client.label} at {path}")
            continue
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2)
            fh.write("\n")
        print(f"Added grantry to {client.label} ({path}). Restart {client.label} to load it.")
        changed += 1
    if changed and not dry_run:
        policy = state_path("policy.yaml")
        print()
        if not policy.exists():
            print("Agents are denied by default until you set a policy. Run 'grantry init', then")
            print("edit it to allow the accounts and roles they may use.")
        else:
            print(f"Agents follow the policy at {policy}. Edit it to change what they may use.")
        print("If the agent also has a shell, set GRANTRY_CALLER=agent in its environment and run")
        print("'grantry check --sandbox' inside it so the policy is a real boundary.")
    if not start_url:
        print(
            "\nNote: no Identity Center instance saved yet. Run "
            "'grantry --start-url <url> --region <region> login' so agents inherit it."
        )
    return 0 if (dry_run or changed) else 1


def _cmd_uninstall(client_keys: list[str]) -> int:
    import json

    from grantry.mcp_install import remove_server

    if client_keys:
        unknown = [k for k in client_keys if k not in CLIENTS]
        if unknown:
            print(f"Unknown client(s): {', '.join(unknown)}. Known: {', '.join(sorted(CLIENTS))}")
            return 2
        targets = [CLIENTS[k] for k in client_keys]
    else:
        targets = [c for c in CLIENTS.values() if os.path.exists(config_path(c))]
        if not targets:
            print("No AI client configs found.")
            return 1

    removed = 0
    for client in targets:
        path = config_path(client)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            content = fh.read().strip()
        config: dict[str, Any] = json.loads(content) if content else {}
        updated, present = remove_server(config, client.root, "grantry")
        if not present:
            continue
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(updated, fh, indent=2)
            fh.write("\n")
        print(f"Removed grantry from {client.label} ({path}).")
        removed += 1
    if removed == 0:
        print("grantry was not configured in any of those clients.")
        return 1
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
