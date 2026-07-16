# grantry

**A local credential broker for humans and AI agents. AWS first.**

grantry logs you into AWS IAM Identity Center once, then hands out short lived
credentials on demand. You get a clean command line. Your AI coding agents get
the same credentials over MCP, but only for the accounts and roles you allow,
only for as long as you permit, and every request is written to an audit log.

Everything stays on your machine. grantry talks to AWS and nothing else. No
account, no server, no telemetry. Tokens live in the OS keychain, never in a
plain file, and no secret is ever written to a log.

[![CI](https://github.com/saimeda32/grantry/actions/workflows/ci.yml/badge.svg)](https://github.com/saimeda32/grantry/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

![grantry in action](docs/demo.gif)

---

## Why grantry exists

Every other credential tool assumes a person is at the keyboard. But agents are
now heavy users of cloud credentials, and they are bad at logging in. They
cannot click a device flow link, and they stall when a session expires. The
common workaround is pasting long lived keys into the agent's environment.
Those keys never expire and are never audited. That is a real security problem.

grantry removes the workaround. The agent asks, grantry checks your rules, and
hands over short lived credentials or a clear refusal. You keep one login, one
policy, and one audit trail across every agent on your machine.

## Install

Install grantry as a persistent command with either tool:

```bash
uv tool install grantry
# or
pipx install grantry
```

Now `grantry --help` works from anywhere. To try it once without installing
(this runs in a throwaway environment and does not add `grantry` to your PATH):

```bash
uvx grantry --help
```

Or from source:

```bash
git clone https://github.com/saimeda32/grantry
cd grantry
uv sync
uv run grantry --help
```

Works on macOS, Linux, and Windows. Python 3.10 or newer.

Homebrew is not provided. grantry is a Python CLI, so `uv tool install` and
`pipx` are the fast, idiomatic way to get it, and they work the same on macOS and
Linux. (A Homebrew formula would compile several dependencies from source on
every install and is not worth the friction for a single-maintainer tap.)

## Quick start

```bash
# 1. Point grantry at your Identity Center, just once. It remembers.
grantry login --start-url https://your-org.awsapps.com/start --region us-east-1

# 2. See what you can reach.
grantry ls

# 3. Generate a starter policy from your real access, then edit it.
grantry init

# 4. Run any command as a role.
grantry run my-dev/AWSReadOnlyAccess -- aws s3 ls
```

`grantry login` also writes matching profiles into `~/.aws/config` for every
account and role you can reach, so the native `aws` CLI, boto3, and Terraform
work with no grantry in the loop: just `aws --profile <account>.<role> ...`. Use
either grantry or the plain AWS tooling, whichever you prefer. It reconciles
safely and never touches profiles you wrote by hand. Pass `--no-populate` (or set
`GRANTRY_NO_POPULATE=1`) if you would rather manage `~/.aws/config` yourself and
run `grantry populate` on demand.

### Route native tools through grantry (audited)

If you want every native credential fetch to go through grantry, so it is
checked against your policy and written to the audit log, add a
`credential_process` profile instead of a plain SSO profile:

```ini
[profile prod-readonly]
credential_process = grantry credential-process --identity prod/AWSReadOnlyAccess
region = us-east-1
```

Now `aws --profile prod-readonly ...`, boto3, and Terraform all get their
credentials from grantry. This is also how you make grantry a real boundary for
a sandboxed agent: give the sandbox only a `credential_process` profile with
`--caller agent`, and the agent cannot reach anything the policy denies.

### Tab-complete your identities

You do not have to type `account/role` by hand. Turn on shell completion once and
TAB fills in your real identities for `run`, `switch`, `console`, and
`credential-process`:

```bash
# bash: add to ~/.bashrc
source <(grantry completion bash)
# zsh: add to ~/.zshrc
source <(grantry completion zsh)
# fish: add to ~/.config/fish/config.fish
grantry completion fish | source
```

Completion reads a local cache of your identities, so pressing TAB never waits on
the network. The cache refreshes whenever you run `grantry ls`. You can also skip
typing entirely: `grantry switch` and `grantry console` with no identity open an
interactive picker.

### Optional defaults

If you get tired of passing the same flags, set defaults in
`~/.grantry/config.toml`. Every key is optional:

```toml
[defaults]
ttl = "30m"                                   # default lifetime for run/switch/console
start_url = "https://your-org.awsapps.com/start"  # so you can skip it on first login
region = "us-east-1"
```

These are only fallbacks. A flag, an environment variable, or the instance grantry
already remembered always wins.

## Commands

| Command | What it does |
|---|---|
| `grantry login` | Log in to Identity Center once, for all accounts and roles. |
| `grantry ls` | List the account and role identities you can use. |
| `grantry run <id> -- <cmd>` | Run a command as a chosen identity. |
| `grantry switch [id]` | Print shell exports to adopt an identity. Omit the id to pick interactively. |
| `grantry console [id]` | Open the AWS console in your browser as an identity. Omit the id to pick. |
| `grantry credential-process --identity <id>` | Emit credentials as JSON for an AWS config `credential_process` entry, so native `aws`/boto3/Terraform route through grantry. |
| `grantry populate` | Write `~/.aws/config` profiles for your access. Adds, updates, and prunes only its own profiles. |
| `grantry check` | Diagnose your session and access, with clear exit codes. Add `--sandbox` to check whether an agent here has ambient AWS access that bypasses the gate. |
| `grantry status` | A quick overview: instance, session expiry, cached access, policy, audit count. |
| `grantry init` | Generate a working policy from your real access. |
| `grantry audit` | Print the grant history, or write an HTML timeline with `--visualize`. |
| `grantry graph` | Write an HTML map of what your agents can reach under the policy. |
| `grantry mcp` | Run grantry as an MCP server for agents. |
| `grantry install [client]` | Add grantry to an AI client's MCP config. Auto detects all if none named. |
| `grantry admin assignments --as <id>` | Crawl who has what across the whole org. Admin only. Add `--snapshot` to save it, or `--diff` to see what changed since the last snapshot. |
| `grantry logout` | Clear the saved session for the current instance. |
| `grantry instances` / `grantry use <name>` | List remembered orgs, or switch between them. |
| `grantry install` / `grantry uninstall` | Add or remove grantry from an AI client's MCP config. |
| `grantry completion <shell>` | Print a shell completion script for bash, zsh, or fish. |
| `grantry version` | Print the version. |

## Use it with your AI agents

One command wires grantry into your AI clients:

```bash
grantry install            # auto detect every client you have
grantry install cursor     # or a specific one
grantry install --dry-run  # preview without writing
```

Supported: `claude-code`, `claude-desktop`, `cursor`, `windsurf`, `vscode`,
`copilot-cli`.
grantry is added without touching your other MCP servers, and each client gets
its own audit label. Restart the client to load it.

The agent then has four tools: `whoami`, `list_identities`,
`get_credentials(identity, ttl)`, and `check_access(identity)`. If no one is
logged in, the agent can call `request_login`, which notifies you and waits for
your approval, then resumes on its own.

## Policy

Write `~/.grantry/policy.yaml`, or let `grantry init` generate it from your real
access. See [examples/policy.yaml](examples/policy.yaml).

```yaml
agents:
  allow:
    - identity: "*/AWSReadOnlyAccess"        # read-only role in ANY account
    - identity: "sandbox/*"                   # ANY role, but only in the sandbox account
    - identity: "dev-*/AWSPowerUserAccess"    # power-user role, only in dev-* accounts
  deny:
    - identity: "*prod*/*"                     # nothing at all in production accounts
    - identity: "*/AWSAdministratorAccess"     # no admin role, in any account
  max_ttl: 15m
humans:
  max_ttl: 12h
```

Every identity is `account-name/role-name`, so you scope by account, by role,
or both. `*` is a wildcard within a segment and does not cross the slash, so
`sandbox/*` means every role in the `sandbox` account, `*/AWSReadOnlyAccess`
means the read-only role in every account, and `dev-*/AWSPowerUserAccess` means
that role only in accounts whose name starts with `dev`.

Three rules govern it:

1. A deny always beats an allow.
2. For agents, anything not allowed is refused. Safe by default.
3. For you, anything not mentioned is allowed.

A note on TTL and AWS: grantry cannot shorten an SSO credential below the
lifetime AWS issues it with, because the reserved SSO roles do not allow client
side re assumption. grantry reports the real AWS expiration and adds an advisory
when a credential outlives your policy cap. The real control for short sessions
is the permission set session duration, set by an admin in IAM Identity Center.

## Admin: see who has what across the org

```bash
grantry admin assignments --as your-mgmt/AWSAdministratorAccess --visualize
```

This crawls the whole organization and writes an interactive graph of
principals, permission sets, and accounts, with the links between them. It is
safe to offer because AWS is the gatekeeper: only an identity that can assume a
management or delegated admin role gets any data. The crawl caches principal
names and uses retry hardening, so it handles organizations with thousands of
assignments.

## How your data is stored

grantry uses no database. It is a single user local tool.

- **Secrets** (SSO tokens) live in the OS keychain, through `keyring`.
- **State** lives as plain files in `~/.grantry/`: `instance.json`,
  `policy.yaml`, and an append only `audit.jsonl` (mode 0600).
- **Interop**: `grantry login` also writes the AWS CLI token cache in
  `~/.aws/sso/cache/`, the same file `aws sso login` writes, so the native
  tools work.

Everything survives reboots. To remove grantry state: `grantry logout` and
`rm -rf ~/.grantry`.

## Security

- Secrets (SSO tokens, refresh tokens) live in the OS keychain. Logging redacts
  tokens in one place, including exception tracebacks.
- The MCP server is not a network service. It talks to the agent that started
  it over stdio.
- Every grant is recorded in `~/.grantry/audit.jsonl`, and never includes the
  credentials themselves.

Read this honestly before relying on grantry as a control: the policy gate only
covers the MCP door. An agent that also has a shell could otherwise run
`grantry run <account/role>` (evaluated as a trusted human) or, if you have run
`grantry populate`, use `aws --profile ...` directly, bypassing the gate. Set
`GRANTRY_CALLER=agent` in the agent's environment so every grantry command is
evaluated under your deny-by-default `agents` policy, and run the agent with no
ambient AWS access. Run `grantry check --sandbox` inside the agent's environment
to verify that: it reports any credential env vars, static credentials file, or
native profiles that would let the agent go around grantry, and exits non-zero if
it finds any, so you can wire it into a sandbox startup check. And
`get_credentials` returns credentials as text into the agent's context. See
[SECURITY.md](SECURITY.md) for the full picture and to report a vulnerability.

## Roadmap

grantry v1 covers AWS Identity Center. The provider layer is written so Azure
and GCP can be added without touching the engine, policy, audit, or MCP
surface. Team mode (shared, signed policy) comes after that.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: fork, branch, write a test,
keep `ruff`, `mypy`, and `pytest` green, open a pull request. By taking part you
agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Notable changes are recorded
in the [changelog](CHANGELOG.md).

## License

[Apache 2.0](LICENSE).
