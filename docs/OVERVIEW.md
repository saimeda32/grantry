# grantry, in plain English

## What it is

grantry is a small program that runs on your own machine and hands out AWS
credentials safely. It does two jobs at once:

1. For **you** (a human), it is a clean command line tool for logging into AWS
   Identity Center and using any account and role you have access to, without
   fiddling with profiles.
2. For **AI coding agents** (Claude Code, Cursor, and the like), it is a
   service they can call to get short lived credentials, but only for the
   accounts and roles you have allowed, and only for as long as you permit.

Everything stays on your machine. grantry talks to AWS and to nothing else. No
account, no server, no telemetry. Your tokens live in the operating system
keychain, never in a plain file.

## The problem it solves

Every other credential tool assumes a person is sitting at the keyboard. But
more and more, the thing that needs AWS credentials is an AI agent working on
your behalf. Agents are bad at logging in: they cannot click the "approve this
device" link in a browser, and when a session expires halfway through a task
they simply fail. So people take a shortcut and paste long lived AWS keys into
the agent's environment. That is dangerous. Those keys do not expire, they are
often over privileged, and nothing records what the agent did with them.

grantry removes the shortcut. The agent asks grantry for credentials, grantry
checks your rules, hands over short lived credentials if the rules allow it,
and writes down every request. The agent never holds a long lived key, and you
get a clear log of who asked for what.

## How it is built (the shape)

Think of grantry as one small engine with three doors into it.

```
                  +---------------------------+
      you  --->   |         grantry           |   ---> AWS Identity Center
    (CLI door)    |                           |        (login + credentials)
                  |   +-------------------+   |
   agent  --->    |   |   the broker      |   |
   (MCP door)     |   | provider + policy |   |
                  |   |    + audit        |   |
 native tools --> |   +-------------------+   |
 (credential_     |                           |
   process)       +---------------------------+
                      policy.yaml   audit.jsonl
                      keychain (secrets)
```

The **engine** (called the broker) is the only place credentials are ever
minted. It is made of three parts:

- A **provider** that knows how to talk to a cloud. Today there is one, for
  AWS. It performs the browser login and asks AWS for role credentials. Adding
  Azure or GCP later means writing another provider that answers the same five
  questions; nothing else changes.
- A **policy** that decides whether a request is allowed. You write it once in
  a small file.
- An **audit log** that records every decision.

Around the engine are the three doors:

- **The CLI door** is for you. You type `grantry login`, `grantry ls`, and so
  on.
- **The MCP door** is for agents. MCP is the standard way agents call tools.
  grantry exposes a handful of tools an agent can use to ask for credentials.
- **The `credential_process` door** is for native tools. Add a
  `credential_process = grantry credential-process --identity ...` line to an
  AWS profile and the normal `aws` CLI, boto3, and Terraform fetch their
  credentials through grantry, so every fetch is policy checked and audited.

## The rules file (policy)

You write one file, `~/.grantry/policy.yaml`. It has two sections, one for
agents and one for you.

```yaml
agents:
  allow:
    - identity: "*/AWSReadOnlyAccess"        # read only role in any account
    - identity: "dev-*/AWSPowerUserAccess"   # power user, but only in dev accounts
  deny:
    - identity: "*prod*/*"                    # nothing at all in a prod account
  max_ttl: 15m                                # agent credentials last at most 15 minutes
humans:
  max_ttl: 12h
```

Three simple rules govern it:

1. A **deny** always wins over an allow. If a request matches any deny line, it
   is refused, full stop.
2. For **agents**, anything not explicitly allowed is refused. Safe by default.
3. For **you**, anything not mentioned is allowed, because you are the person
   who wrote the rules.

`grantry init` writes a permissive starter (agents allowed anything) so the tool
works right away, and tells you how to tighten it. If you never run `init`, a
missing policy denies agents by default, so the fail-safe still holds.

Every credential also has a **time limit**. If an agent asks for one hour but
your rule says fifteen minutes, grantry requests the shorter cap. If the policy
file is missing or broken, agents get nothing (humans still work), so a mistake
fails safe.

An identity is written as `account-name/role-name`, and `*` is a wildcard within
a segment (it does not cross the slash), so `dev-*/AWSReadOnlyAccess` means "read
only in any account whose name starts with dev".

## The audit log

Every time an agent or a person asks for credentials, grantry appends one line
to `~/.grantry/audit.jsonl`. Each line records the time, who asked, which
identity, whether it was allowed, which rule decided it, and the time limit
that was applied. It never records the credentials themselves. You can read it
any time with `grantry audit`.

## The commands

### For you (the human)

- **`grantry login`**
  Logs you into AWS Identity Center. It prints a link and a code; you approve in
  your browser once, and grantry remembers the session (in the keychain). You
  log in to the whole Identity Center at once, not to a single account.

- **`grantry ls`**
  Lists every account and role you can use, one `account/role` per line.

- **`grantry run <identity> -- <command>`**
  Runs a single command as a chosen identity without changing anything else, for
  example `grantry run prod/AWSReadOnlyAccess -- aws s3 ls`.

- **`grantry switch [identity]`**
  Prints shell exports to adopt an identity for the rest of your session. Omit
  the identity to pick one from an interactive menu.

- **`grantry console [identity]`**
  Opens the AWS console in your browser signed in as that identity. Omit the
  identity to pick one.

- **`grantry credential-process --identity <id>`**
  Emits credentials as JSON for an AWS config `credential_process` entry, so the
  native `aws` CLI, boto3, and Terraform route through grantry and are audited.

- **`grantry populate`**
  Writes profiles into your `~/.aws/config` for every account and role you can
  use, so the normal `aws` CLI keeps working. It adds new ones, updates changed
  ones, and prunes stale ones it created before. `--dry-run` previews first.

- **`grantry init`**
  Generates a starter `policy.yaml` from your real access.

- **`grantry check`**
  A doctor command. It diagnoses "why can't I log in" or "can I reach this
  account and role" and returns clear, script friendly exit codes.

- **`grantry audit`**
  Prints the grant history in plain lines, or writes an HTML timeline with
  `--visualize`.

- **`grantry graph`**
  Writes an interactive HTML map of what your agents can reach under the policy.

- **`grantry instances` / `grantry use <name>`**
  List the Identity Center orgs grantry remembers, or switch between them.

- **`grantry logout`**
  Clears the saved session for the current instance.

### For agents

- **`grantry mcp`**
  Starts grantry as an MCP server so an agent can call it. It exposes these
  tools to the agent:
  - `whoami` tells the agent whether a session is active and when it expires.
  - `list_identities` shows the account and role names it could ask for.
  - `get_credentials(identity, ttl)` is the main one: the agent names an
    identity and a time limit, grantry checks the policy, and either returns a
    ready to use block of `AWS_...` environment variables or a short refusal
    with the reason. No credentials on a refusal.
  - `check_access(identity)` lets the agent ask "would this be allowed?" before
    it tries, so it can plan instead of failing.
  - `request_login` is for when no one is logged in. The agent calls it, grantry
    pops a desktop notification and waits, you approve the login once, and the
    agent's original request continues on its own.

- **`grantry install [client]` / `grantry uninstall [client]`**
  Wires grantry into an AI client's MCP config (Claude Code, Claude Desktop,
  Cursor, Windsurf, VS Code), or removes it. Auto detects every client if you
  name none. Each client gets its own audit label.

### For admins

- **`grantry admin assignments --as <identity>`**
  Crawls who has what across the whole organization and can write an interactive
  graph with `--visualize`. `--snapshot` saves the crawl; `--diff` shows what
  changed since the last snapshot. Only an identity that can assume a management
  or delegated admin role gets any data.

### On the roadmap

- **Azure and GCP providers.** The same commands, with a new provider file.
  The engine, policy, audit, and MCP doors are unchanged.
- **Team mode.** A shared, signed policy file so a lead sets the rules once.
- **runclave integration.** grantry injects credentials into runclave's
  sandboxed agents, so the two tools work as a pair.

## Why this is safe by design

- Secrets only ever live in the OS keychain. Nothing sensitive is written to a
  file or a log. The logging is built so that even a careless debug line cannot
  leak a token; redaction happens in one place, automatically.
- The MCP door is not a network service. It talks directly to the agent that
  started it, or over local machine only, never over the network.
- Credentials are short lived and scoped. An agent gets the minimum, for the
  minimum time, and only what you allowed.
- Everything is written down. If you ever wonder what an agent did, the audit
  log has every request.

## How we are building it

Small pieces, each tested before the next is written, each committed on its
own. The plain parts (the rules engine, the identity matching, the audit log)
are pure logic and easy to test. The parts that talk to AWS are tested against
a pretend AWS that runs inside the test, so the whole login and credential flow
is proven without ever touching a real account. Continuous integration runs the
lint, type check, and tests on every change from day one. The detailed step by
step build is in
`docs/superpowers/plans/2026-07-15-grantry-phase1.md`.
