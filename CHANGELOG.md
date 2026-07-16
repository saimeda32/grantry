# Changelog

All notable changes to grantry are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and grantry uses
[semantic versioning](https://semver.org/).

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

[0.4.0]: https://github.com/saimeda32/grantry/releases/tag/v0.4.0
[0.3.0]: https://github.com/saimeda32/grantry/releases/tag/v0.3.0
[0.2.0]: https://github.com/saimeda32/grantry/releases/tag/v0.2.0
[0.1.0]: https://github.com/saimeda32/grantry/releases/tag/v0.1.0
