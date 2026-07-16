# grantry

A local credential broker for humans and AI agents, AWS-first.

grantry logs into AWS Identity Center once and hands out short-lived
credentials on demand. Humans get a clean command line. AI coding agents get
the same credentials over MCP, but only for the accounts and roles you allow,
only for as long as you permit, and every request is written to an audit log.

Everything stays on your machine. grantry talks to AWS and nothing else. No
account, no server, no telemetry. Tokens live in the OS keychain, never in a
plain file, and no secret is ever written to a log.

## Why

Every other credential tool assumes a person is at the keyboard. But agents are
now heavy users of cloud credentials, and they are bad at logging in: they
cannot click a device-flow link, and they stall when a session expires. The
common workaround is pasting long-lived keys into the agent's environment,
which never expire and are never audited. grantry removes that shortcut: the
agent asks, grantry checks your rules, and hands over short-lived credentials
or a clear refusal.

## Install

```bash
uvx grantry --help        # run without installing
# or
pipx install grantry
```

## Point it at your Identity Center

Set two values, once:

```bash
export GRANTRY_SSO_START_URL=https://your-org.awsapps.com/start
export GRANTRY_SSO_REGION=us-east-1
```

(Or pass `--start-url` and `--region` on any command.)

## Commands

```bash
grantry login     # log in to Identity Center (opens a browser code prompt)
grantry ls        # list the account/role identities you can use
grantry audit     # print the grant history
grantry mcp       # run grantry as an MCP server for agents (stdio)
```

## Let an agent use it

Point your MCP client at `grantry mcp`. It exposes four tools:

- `whoami` reports whether a session is active and when it expires.
- `list_identities` lists the account/role names the agent could request.
- `get_credentials(identity, ttl)` mints short-lived credentials for an allowed
  identity, or returns a short refusal with the reason. Nothing is minted on a
  refusal.
- `check_access(identity)` reports whether policy would allow an identity,
  without minting.

## Policy

Write `~/.grantry/policy.yaml`. See [examples/policy.yaml](examples/policy.yaml):

```yaml
agents:
  allow:
    - identity: "*/ReadOnlyAccess"
    - identity: "dev-*/AWSPowerUserAccess"
  deny:
    - identity: "*prod*/*Admin*"
  max_ttl: 15m
humans:
  max_ttl: 12h
```

Three rules govern it:

1. A deny always beats an allow.
2. For agents, anything not allowed is refused (safe by default).
3. For you, anything not mentioned is allowed.

Every credential is time-capped to its section's `max_ttl`. If the policy file
is missing or invalid, agents get nothing and humans still work, so a mistake
fails safe.

An identity is `account-name/role-name`, and `*` is a wildcard, so
`dev-*/ReadOnlyAccess` means read-only in any account whose name starts with
`dev`.

## Security

- Secrets live only in the OS keychain. Nothing sensitive is written to a file
  or a log; redaction happens in one place, automatically.
- The MCP server is not a network service. It talks to the agent that started
  it over stdio.
- Credentials are short-lived and scoped to what policy allows.
- Every grant is recorded in `~/.grantry/audit.jsonl` (mode 0600), and never
  includes the credentials themselves.

## Status

Phase 1: AWS Identity Center, the CLI, and the MCP server. The provider layer
is written so Azure and GCP can be added without touching the engine, policy,
audit, or MCP surface. See `docs/OVERVIEW.md` for the full picture and roadmap.

## License

Apache-2.0.
