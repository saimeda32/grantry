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

## Known limitations

- The AWS CLI token cache that grantry writes for native interop
  (`~/.aws/sso/cache/`) contains the access token in plain text, because that is
  the format the AWS CLI requires. It is the same file `aws sso login` writes,
  with the same 0600 permissions.
- grantry cannot shorten an SSO credential below the lifetime AWS issues it
  with. The real control for short sessions is the permission set session
  duration in IAM Identity Center.
