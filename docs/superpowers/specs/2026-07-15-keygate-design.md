# keygate (working name) — design

Date: 2026-07-15. Status: draft pending aws-sso-util audit findings (section 8).

## One sentence

A local credential broker for the agent era: humans get a clean AWS Identity
Center CLI, coding agents get scoped short-lived credentials over MCP, and a
policy file with an audit trail sits between agents and the cloud.

## Why this exists

Every credential tool assumes a human at the terminal (Granted, aws-vault,
aws-sso-cli, the new `aws login`). Coding agents are now the heaviest
consumers of cloud credentials and they are terrible at auth: they cannot
click device-flow links, they stall when SSO tokens expire mid-task, and the
common workaround is pasting long-lived keys into agent environments. Nothing
polices which identities an agent may use, for how long, with what audit
trail. That gap is the product. The multi-cloud credential slot is also
orphaned (Leapp is dead following Noovolari's shutdown), but v1 is AWS only;
other clouds enter through the provider interface on the roadmap.

## Scope

v1 ships AWS Identity Center only. The provider boundary (section 5) is the
only place cloud-specific code lives, so Azure (Entra device code) and GCP
(ADC) are roadmap additions, not rewrites. AI providers are out of scope.

## Architecture: one daemon, three faces

### Core: session daemon

A single binary (`keygate serve`, auto-started on first use) that owns
provider sessions: runs the Identity Center device flow, caches and refreshes
tokens before expiry, and mints role credentials on demand. All secrets live
in the OS keychain (aws-vault/Granted precedent), never plaintext on disk.
State directory holds only non-secret metadata (identity inventory, audit
log, policy).

### Face 1: MCP server (the AI-native core)

Tools exposed to any MCP client (Claude Code, Cursor, custom agents):

- `whoami` — active sessions and their expiry
- `list_identities` — accounts and roles available through Identity Center,
  filtered to what policy allows the caller to see
- `get_credentials(identity, ttl)` — mint short-lived credentials for an
  allowed identity; TTL capped by policy; returns env-shaped credentials
- `request_login()` — agents cannot complete device flows; this notifies the
  human (desktop notification + printed URL), blocks until the human
  completes login or a timeout passes, then resolves
- `check_access(identity)` — preflight without minting

Every `get_credentials` grant is appended to a local audit log: timestamp,
caller (MCP client name/session), identity, TTL, policy rule that allowed it.

### Face 2: policy

`~/.keygate/policy.yaml`, written by the human once:

```yaml
agents:
  allow:
    - identity: "*/ReadOnlyAccess"        # account-pattern/role-pattern
    - identity: "dev-*/AWSPowerUserAccess"
  deny:
    - identity: "*prod*/*Admin*"
  max_ttl: 15m
  require_login_approval: true            # request_login always prompts
humans:
  max_ttl: 12h
```

Deny beats allow; unmatched is denied for agents, allowed for humans. The
broker enforces policy; the agent never sees credentials policy forbids.

### Face 3: human CLI

The aws-sso-util lineage, rebuilt on the daemon:

- `keygate login` — log in to Identity Center, no profile required
- `keygate ls` — accounts and roles you can use (live)
- `keygate switch <identity>` — subshell or env exports for an identity
- `keygate run <identity> -- cmd` — one-off command as an identity
- `keygate populate` — generate AWS config profiles from live access,
  reconciled (adds, updates, prunes stale entries it owns)
- `keygate check` — diagnose configuration and access with distinct exit codes
- `keygate audit` — read the grant log
- `keygate serve --container-endpoint` — expose the ECS-style container
  credentials endpoint on localhost so every AWS SDK picks up credentials
  with one env var, no config files at all

A Claude Code skill ships in-repo (`skills/keygate/`) teaching agents the MCP
verbs and the request_login etiquette.

## Provider boundary

```
type Provider interface {
    Name() string
    Login(ctx, interact InteractionHandler) (Session, error)
    ListIdentities(ctx, Session) ([]Identity, error)
    Credentials(ctx, Session, Identity, ttl) (Credentials, error)
    Refresh(ctx, Session) (Session, error)
}
```

v1 implements `aws` (Identity Center via device authorization grant, role
credentials via sso:GetRoleCredentials). Azure/GCP implement the same five
methods later. Nothing outside the provider package imports an AWS SDK.

## Language and stack

Go. Reasons: single static binary (agents and CI install it with one
download), first-class keychain libraries (99designs/keyring, the same one
aws-vault and Granted use), goroutine-friendly daemon, and the MCP Go SDK is
mature. Distribution: goreleaser binaries + Homebrew tap + `go install`.

## Security model

- Tokens and client registrations: OS keychain only. No plaintext cache
  (differs from aws-sso-util, which caches tokens world-readable-ish in
  ~/.aws/sso/cache).
- Minted credentials: returned to the caller, never persisted by keygate.
- Debug logging never prints secrets (aws-sso-util's credential-process debug
  log famously contains credentials; explicit non-goal here).
- The MCP server binds to stdio (per-client) or localhost with a per-session
  token; never a network interface.
- Policy file changes take effect immediately; an invalid policy fails closed
  for agent callers.
- Audit log is append-only JSONL, 0600.

## Testing bar (full E2E, no exceptions)

- Provider E2E against a fake Identity Center (httptest): device flow,
  token refresh, role credential minting, expiry, error mapping.
- MCP E2E: drive the server over stdio as a real client; policy allow/deny
  matrix; request_login flow with a scripted "human".
- CLI E2E: golden-output tests for ls/switch/run/populate against the fake
  provider; populate reconciliation (add/update/prune) against a temp config.
- Policy engine: table-driven unit tests, every rule combination.
- CI from day one: GitHub Actions, lint (golangci-lint), race detector,
  release dry-run. The aws-sso-util audit's testing findings define the
  anti-checklist.

## Roadmap (post-v1)

1. Azure provider (Entra device code), GCP provider (ADC + workforce
   identity).
2. Team mode: shared policy distribution (signed policy bundles).
3. runclave integration: keygate as runclave's credential injector.
4. Session recording hooks for compliance environments.

## Non-goals

- No SaaS, no telemetry, no network control plane. Local-first.
- No IAM user / long-lived key management (aws-vault's legacy niche).
- No browser extension.
- Not a secrets manager; it brokers cloud sessions only.

## 8. Lessons from aws-sso-util (audit, 2026-07-15)

Full audit of the 8,069-LOC codebase (zero tests, no CI, 26 tool-specific env
vars, vendored botocore internals). What keygate adopts and what it rejects:

### Adopt

- Instance-scoped login (log in once per issuer, everything shares it) with
  zero-arg resolution, but replace regex/env-var guessing with named sessions
  and a printed "why I picked this" provenance trace.
- Library-first split with the CLI as a thin veneer, taken further: command
  bodies are thin over pure planners (compute, then apply), because the
  audit's worst testability offenders were 200-450 line command functions
  mixing env reading, network, and formatting.
- Injectable everything in the auth core: cache, clock, sleep, browser
  handler. The vendored SSOTokenFetcher was the only genuinely testable class
  in the codebase precisely because botocore built it that way.
- A doctor command (`keygate check`) with a stable, documented exit-code
  taxonomy (aws-sso-util's 101/102/103, 20x pattern) and cache-permission
  forensics.
- populate with --dry-run, an ownership marker, and reconciliation. Config
  writes through a real round-tripping layer, never regex line surgery.
- Errors that print the exact command to run next (credential-process's
  best habit), as a uniform contract on every error, with a common base
  error type carrying problem/action/cause.
- Retry hardening by default (standard mode, 10 attempts) respecting
  AWS_RETRY_MODE/AWS_MAX_ATTEMPTS; receivedAt metadata on tokens; run-as
  style scrubbing of ambient AWS_* env before injecting.
- Native-cache interop as a tested contract: keygate reads/refreshes the
  AWS CLI's ~/.aws/sso/cache format so `aws` CLI keeps working, but its own
  secrets live in the keychain.

### Reject

- Vendoring SDK internals. The OIDC device flow is <500 LOC of protocol;
  keygate implements it natively against the public API.
- Plaintext token caches and credential-bearing debug logs (aws-sso-util
  writes credentials into a default-umask log file and tokens to -vv
  output). keygate: secret redaction is a logging-layer invariant, and the
  debug log never contains secrets by construction.
- The env-var jungle (26 vars, three names for one setting). keygate: one
  KEYGATE_ prefix, one documented precedence rule.
- Flag-meaning drift across subcommands (--region meaning two different
  things). One glossary, enforced in review.
- The profile-name mini-DSL (7 naming knobs). One template string plus an
  optional external formatter.
- Shipping a second product inside the first (the CloudFormation macro was
  ~25% of the codebase, its deploy command disabled). keygate stays one
  product; admin tooling is a different repo if it ever exists.
- APIs that return exceptions instead of raising, silent except-pass,
  device-flow polls with no client-side timeout.
