# Contributing to grantry

Thanks for your interest. grantry is a small, focused tool, and contributions
are welcome.

## Ground rules

- grantry stays local first. No feature should add a server, telemetry, or a
  network call to anything other than the cloud provider itself.
- Secrets belong in the OS keychain. Never write a secret to a file or a log.
- Product code is fully typed and passes `mypy` in strict mode.
- Every change ships with a test. Network facing code is tested against a fake
  server, never against a real account.
- Prose and comments use plain English and no em dashes.

## Getting set up

grantry uses [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/saimeda32/grantry
cd grantry
uv sync --all-extras --dev
```

## The checks

Run all of these before opening a pull request. CI runs the same on macOS,
Linux, and Windows across Python 3.10 and 3.14.

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q
```

## Workflow

1. Fork the repository and create a branch with a clear name, for example
   `feat/azure-provider` or `fix/refresh-race`.
2. Write a failing test, then the code to make it pass.
3. Keep the change focused. One idea per pull request.
4. Make sure the checks above pass.
5. Open a pull request and describe what changed and why.

## Adding a cloud provider

A provider lives in `src/grantry/providers/` and implements the small `Provider`
protocol in `providers/base.py`: `name`, `start_login`, `refresh`,
`list_identities`, and `mint`. Nothing outside the provider package should
import a cloud SDK. Add a fake server under `tests/fakes/` and test the login
and mint flow end to end against it.

## Reporting bugs

Open an issue with the command you ran, what you expected, and what happened.
Never paste real credentials or tokens.
