# Security Policy

grantry brokers cloud credentials, so security reports are taken seriously.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Instead, use GitHub's
private vulnerability reporting for this repository (the "Report a vulnerability"
button under the Security tab), or email the maintainer.

Include the version, your platform, and steps to reproduce. Never include real
credentials or tokens in a report.

You can expect an acknowledgement within a few days.

## What grantry does to protect you

- Secrets (SSO tokens) are stored in the OS keychain, never in a plain file.
- Logging redacts anything that looks like a credential, in one place, so no
  call site can leak a token.
- The MCP server speaks over stdio to the agent that started it. It is not a
  network service.
- Minted credentials are short lived and scoped to what the policy allows, and
  are never persisted by grantry.
- The audit log records every grant decision and never contains a credential.

## What grantry's policy does and does not control

Please read this before relying on grantry as a security control. grantry is
strongest as an audit and convenience layer. Its policy gate is real but has
limits you must understand.

**The policy gate only covers the MCP door.** grantry decides what an agent may
mint *through the MCP tools*. It cannot stop an agent that also has a shell. If
you run `grantry populate` (which writes profiles to `~/.aws/config`) and login
(which writes the SSO token to `~/.aws/sso/cache/`), then an agent with a Bash
tool can run `aws --profile <anything>` and reach any role you can, bypassing
the policy and the audit log entirely. To make the gate a real boundary, the
agent must run with no ambient AWS access (for example in a sandbox or
container with a clean home directory), so that grantry's MCP tools are its
only path to credentials. Without that isolation, treat grantry as audit and
convenience, not containment.

**The MCP tool returns credentials as text to the agent.** `get_credentials`
hands the agent an `AWS_...` block so it can act. That text enters the agent's
context and is sent to whatever model provider the agent uses. If that matters
to you, do not expose long-lived or high-privilege identities to agents through
grantry, and prefer running the agent in a sandbox that consumes the
credentials without echoing them back to the model.

## Known limitations

- The AWS CLI token cache that grantry writes for native interop
  (`~/.aws/sso/cache/`) contains the access token in plain text, because that is
  the format the AWS CLI requires. It is the same file `aws sso login` writes,
  with 0600 permissions in a 0700 directory. grantry deliberately does NOT write
  the refresh token or client secret there; those stay in the OS keychain.
- grantry cannot shorten an SSO credential below the lifetime AWS issues it
  with. A `max_ttl` in the policy caps what grantry will grant, but the
  credential AWS returns lives for the permission set's full session duration.
  The advisory grantry prints says so. The real control for short sessions is
  the permission set session duration in IAM Identity Center. Do not rely on
  `max_ttl` as a hard time bound on an issued credential.
- The policy `agents:` section applies to every agent equally. The per-agent
  label (`GRANTRY_AGENT_LABEL`) is an audit tag only; it is set by the agent and
  is not a trust boundary. You cannot grant one agent more than another today.
