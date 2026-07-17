# grantry roadmap

This page shows the direction for grantry. It is a plan, not a promise. Priorities
and timing can change, so dates are left off on purpose. Items move from Later to
Next to Now as work starts.

grantry stays free and open source, local first, with no account, no server, and
no telemetry.

## Now

Work that is in progress or up next.

- Make the policy gate a real boundary. Pair grantry with an isolated sandbox
  (the companion project runclave) so an agent can only get credentials through
  grantry and cannot go around it.
- Make login fast on large organizations by loading your roles in the background.
- Show access changes on the graph. Render a snapshot diff so added and removed
  access are highlighted.
- Make the project easy to trust: a clear security policy and build provenance.

## Next

Planned once the Now items land.

- Better access review in the graph:
  - Show group members even when a group is synced from an outside identity
    provider such as Okta, Entra ID, or Active Directory.
  - Flag risky access automatically, for example admin in production, accounts
    nobody can reach, groups that have access but no members, and principals with
    very broad reach.
  - Add a report command that outputs the crawl as JSON for pipelines, plus
    scheduled snapshots with change alerts.

## Later

Bigger steps for further out.

- Support more clouds behind the same commands, policy, and audit. Azure first
  (Entra ID and Azure RBAC), then Google Cloud.
- Team mode: one shared, signed policy that every teammate's grantry enforces,
  with no server in the middle.
- Easier installs, such as Homebrew, as the project grows.

## Already shipped

Where grantry is today.

- One login to AWS IAM Identity Center, with short lived credentials for you and
  for your AI agents over MCP.
- A YAML policy that decides which accounts and roles agents may use, with an
  append only audit log.
- Native tooling support: the aws CLI, boto3, and Terraform work through
  populated profiles and credential_process.
- An interactive organization access graph: who can reach what, colored by
  privilege level, with risk counts, search, a table view, and CSV or SVG export.
- Shell completion, an identity picker, a sandbox check, and support for macOS,
  Linux, and Windows.

## Have an idea?

Open a discussion or an issue on GitHub. Reactions on issues help show what
matters most.
