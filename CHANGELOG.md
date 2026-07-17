# Changelog

All notable changes to grantry are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and grantry uses
[semantic versioning](https://semver.org/).

## [0.10.0] - 2026-07-16

### Added
- The org access graph now gathers extra context during `--visualize` (best
  effort; a missing permission just leaves that part out):
  - **Group membership** — selecting a group lists the users in it.
  - **Permission-set details** — selecting a permission set shows its session
    duration, attached AWS managed policies, and whether it has an inline policy.
  - **Account OU** — each account shows its Organizational Unit, and its
    environment from the tag when known.
  - **Provenance** — the header records the identity the crawl ran as.

## [0.9.0] - 2026-07-16

### Added
- Richer org access graph (`grantry admin assignments --visualize`):
  - Permission-set nodes are colour-coded by privilege level (admin, power,
    developer, read-only, other), and production accounts are flagged.
  - Production accounts are classified authoritatively from their AWS
    Organizations `Environment`-style tag (the crawl reads account tags when it
    can), falling back to the account name only when no tag is available, and the
    page says so when it is guessing.
  - Risk KPIs: admin grants, admin-in-prod, and principals with admin.
  - Filter chips to show/hide by privilege level and to show production accounts
    only.
  - Export the assignments as CSV and the graph as SVG.
  - Scroll to zoom and drag to pan the graph, with a reset-view button.

## [0.8.4] - 2026-07-16

### Added
- Built-in live-filter identity picker: when you omit the identity (or `--profile`
  value), grantry now shows the list and narrows it as you type, with arrow keys
  and Enter, without needing `fzf` installed. fzf is still used when present; a
  plain numbered menu remains the fallback where raw-mode input is unavailable.

## [0.8.3] - 2026-07-16

### Added
- Accept the aws-familiar `--profile` (and `--identity`, `--as`) flags wherever
  grantry takes an identity: `switch`, `console`, `credential-process`, and
  `admin assignments`. `run` takes the `account.role` profile-name form
  positionally (`grantry run prod.ReadOnlyAccess -- ...`).

## [0.8.2] - 2026-07-16

### Changed
- The "Wrote ... to <file>" messages (`admin assignments --visualize`, `graph`,
  `audit --visualize`) now print a green, clickable link to the file when writing
  to a terminal, and a plain path when piped.
- The numbered identity picker now draws in the terminal's alternate screen, so
  the whole list disappears once you choose instead of leaving dozens of lines
  scrolled up behind you.

## [0.8.1] - 2026-07-16

### Added
- `grantry --version` / `-V` now work, in addition to the `grantry version`
  subcommand.

## [0.8.0] - 2026-07-16

### Changed
- Stop making you repeat what grantry already knows, from a UX sweep:
  - Identities now resolve from the `account.role` profile-name form too (what
    `populate` writes to `~/.aws/config`), not only the `account/role` form, so a
    name copied from either place works.
  - `admin assignments --as` is optional and opens the identity picker; `use` and
    `completion` are the same (pick an instance, infer the shell from `$SHELL`).
  - `--start-url` / `--region` no longer clutter every subcommand's help, and a
    first login with only one of them prompts for the other instead of exiting.
  - `grantry install` now tells you agents are denied until you write a policy and
    to set `GRANTRY_CALLER=agent`; login points to `ls`/`run`/`console`/`switch`.
  - "unknown identity" and policy denials now name the next command to run, and a
    bare `grantry run` prints usage instead of a raw argparse error.
  - `admin assignments` rejects more than one of `--snapshot`/`--diff`/`--visualize`
    instead of silently ignoring the extras.

## [0.7.0] - 2026-07-16

### Security
- Closed a policy-gate escalation: an agent with a shell could run
  `grantry run <account/role>` (or `switch`/`console`/`credential-process`) and
  be evaluated as a trusted human, reaching anything you can and bypassing its
  deny-by-default `agents` rules. Set `GRANTRY_CALLER=agent` in the agent's
  environment and every grantry command now evaluates under the `agents` policy,
  not only the MCP tools. `grantry check --sandbox` also flags when that marker
  is missing. (Fully airtight only with the agent isolated from ambient AWS; a
  malicious agent with a full shell could unset the variable.)

## [0.6.0] - 2026-07-16

### Added
- `grantry login` now writes `~/.aws/config` profiles for every account and role
  after logging in, so the native `aws` CLI, boto3, and Terraform work right away
  with `aws --profile <account>.<role>`. It reconciles safely and never touches
  your hand-written profiles. Pass `--no-populate` (or set `GRANTRY_NO_POPULATE=1`)
  to skip it.

### Changed
- `grantry login` now opens your browser to the approval page automatically (the
  URL already carries the code) and waits for approval by polling, instead of
  asking you to press Enter. Set `GRANTRY_NO_BROWSER=1` for headless or SSH use.
- Pressing Ctrl-C prints a clean "Cancelled." and exits 130 instead of dumping a
  Python traceback.

### Fixed
- Corrected the install docs to lead with persistent `uv tool install` / `pipx`
  (not ephemeral `uvx`), and fixed a mypy failure on Python 3.10 in CI.

## [0.5.0] - 2026-07-16

### Added
- `grantry status`: a one-glance overview of your instance, session expiry,
  cached access, policy state, and audit count.
- `grantry check --sandbox`: reports any ambient AWS access (credential env vars,
  a static credentials file, or native profiles) that would let an agent go
  around the policy gate, and exits non-zero if it finds any. Run it inside the
  agent's environment to prove the gate is a real boundary there.
- `~/.grantry/config.toml` for optional defaults (`ttl`, `start_url`, `region`).
  Flags, environment variables, and a remembered instance always win over it.
- GitHub Copilot CLI is now a supported `grantry install` target (`copilot-cli`).
- `grantry login` warms the completion cache, so TAB works right after your first
  login, not only after the first `ls`.

### Changed
- `grantry --help` is cleaner: the internal completion helper is hidden and the
  command list is no longer dumped into the usage line.
- CI actions updated off the deprecated Node 20 runtime (checkout v7, setup-uv v8).

### Housekeeping
- Added a demo to the README and a `.pre-commit-config.yaml`.
- Removed internal planning docs from the published tree.

## [0.4.0] - 2026-07-15

### Added
- Shell completion for bash, zsh, and fish. Run `grantry completion <shell>` and
  source it. Completing an identity argument (for `run`, `switch`, `console`, and
  `credential-process --identity`) fills in your real `account/role` names from a
  local cache, so pressing TAB never waits on the network.

### Changed
- `grantry init` now writes a permissive starter policy so agents work right
  away, with loud instructions on how to restrict it. If you never run `init`, a
  missing policy still denies agents by default, so the fail-safe holds.

### Documentation
- Rewrote `docs/OVERVIEW.md` to match the shipped command set.
- Refreshed the project site with an animated terminal demo and the current
  feature set (console, credential-process, snapshots).

## [0.3.0] - 2026-07-15

### Added
- `grantry console` opens the AWS console in your browser as any identity, with
  `--print` and `--destination`.
- `grantry credential-process` so the native aws CLI, boto3, and Terraform can
  fetch credentials through grantry, policy checked and audited.
- Interactive identity picker (fzf or a numbered menu) for `switch` and
  `console` when you omit the identity.
- `grantry admin assignments --snapshot` and `--diff` to track how org access
  changes over time.

## [0.2.0] - 2026-07-15

### Added
- `grantry logout`, `login --force-refresh`, `version`, and multi-org
  `instances` / `use`.
- `grantry uninstall` to remove grantry from an AI client's MCP config.

### Fixed
- Refresh-lock correctness and refresh error handling.
- Per-segment policy matching, so `*` does not cross the account/role slash.
- Kept the refresh token out of the plaintext AWS cache and redacted tokens in
  exception tracebacks.

### Security
- Pinned all CI actions to commit SHAs and committed the lockfile for
  reproducible, supply-chain-hardened builds.

## [0.1.0] - 2026-07-15

### Added
- The broker: one grant path composing an AWS provider, the policy engine, and
  the audit log.
- AWS provider using the OIDC device flow against IAM Identity Center, with
  silent token refresh and AWS CLI cache interop.
- Policy engine: deny beats allow, agents deny-by-default, humans allow-by-default,
  fail closed, and honest TTL caps.
- MCP server exposing `whoami`, `list_identities`, `get_credentials`,
  `check_access`, and `request_login`.
- Human CLI: `login`, `ls`, `run`, `switch`, `populate`, `check`, `audit`,
  `init`, and `graph`.
- `grantry install` to wire grantry into AI clients' MCP config.
- `grantry admin assignments` to crawl who-has-what across the org, scaling to
  10k+ assignments, with an interactive `--visualize` graph.

[0.10.0]: https://github.com/saimeda32/grantry/releases/tag/v0.10.0
[0.9.0]: https://github.com/saimeda32/grantry/releases/tag/v0.9.0
[0.8.4]: https://github.com/saimeda32/grantry/releases/tag/v0.8.4
[0.8.3]: https://github.com/saimeda32/grantry/releases/tag/v0.8.3
[0.8.2]: https://github.com/saimeda32/grantry/releases/tag/v0.8.2
[0.8.1]: https://github.com/saimeda32/grantry/releases/tag/v0.8.1
[0.8.0]: https://github.com/saimeda32/grantry/releases/tag/v0.8.0
[0.7.0]: https://github.com/saimeda32/grantry/releases/tag/v0.7.0
[0.6.0]: https://github.com/saimeda32/grantry/releases/tag/v0.6.0
[0.5.0]: https://github.com/saimeda32/grantry/releases/tag/v0.5.0
[0.4.0]: https://github.com/saimeda32/grantry/releases/tag/v0.4.0
[0.3.0]: https://github.com/saimeda32/grantry/releases/tag/v0.3.0
[0.2.0]: https://github.com/saimeda32/grantry/releases/tag/v0.2.0
[0.1.0]: https://github.com/saimeda32/grantry/releases/tag/v0.1.0
