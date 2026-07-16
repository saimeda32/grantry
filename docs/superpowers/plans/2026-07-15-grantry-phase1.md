# grantry Phase 1 (AWS vertical slice) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local credential broker that logs into AWS Identity Center via the OIDC device flow, stores secrets in the OS keychain, mints short-lived role credentials on demand, and exposes those grants to AI agents over MCP subject to a policy file, with every grant audited.

**Architecture:** A pure core (identity model, policy engine, audit log) with zero network or OS coupling, wrapped by two adapters: an AWS provider that speaks the SSO OIDC + SSO APIs through botocore's low-level clients, and a keychain-backed secret store. An asyncio MCP server composes them: it resolves identities, checks policy, mints credentials, and appends audit records. Everything network-facing is tested against a fake Identity Center (an in-process HTTP server), never real AWS.

**Tech Stack (all latest as of 2026-07-15):** Python >=3.10 (CI tests 3.10 and 3.14), uv (project + venv), ruff 0.15+ (lint+format), mypy 2.3+ strict, pytest 9.1+ + pytest-asyncio 1.4+, botocore 1.43+ (low-level clients only), keyring 25.7+ (OS keychain), the official `mcp` 1.28+ Python SDK, PyYAML 6.0.3+.

## Global Constraints

- Python floor: **3.10**. Everything must run on 3.10+.
- Secrets (SSO tokens, client registrations, minted credentials in transit) live in the **OS keychain via `keyring`**. Never write a secret to a plaintext file, a log, or the state directory.
- Logging is **secret-redacting by construction**: the logging setup installs a filter; no call site is trusted to redact. No token or credential ever reaches any log at any level.
- **No reaching into botocore internals.** Use documented low-level clients (`session.create_client("sso-oidc")`, `"sso"`) only. Do not import `botocore.credentials` providers or private attributes.
- State dir is `~/.grantry/` (override with `GRANTRY_HOME`). It holds only non-secret data: `policy.yaml`, `audit.jsonl` (mode 0600), cached identity inventory. Env prefix is `GRANTRY_` and nothing else; one documented precedence rule (CLI arg > `GRANTRY_*` env > config file).
- **Fail closed**: an unreadable or invalid policy denies every agent request. Deny rules beat allow rules. An identity matched by no rule is denied for agent callers.
- Every network-facing behavior has a fake-server E2E test. No mocking of our own code to fake a passing test.
- Commit after every green step. Commits authored as `saimeda32 <mskmeda4@gmail.com>`, conventional-commit style, no AI trailers, no em dashes in messages or code comments.

---

### Task 1: Project scaffolding, tooling, and CI

**Files:**
- Create: `pyproject.toml`
- Create: `src/grantry/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`
- Create: `.github/workflows/ci.yml`
- Create: `.gitignore`
- Create: `README.md`
- Create: `ruff.toml`

**Interfaces:**
- Produces: an installed `grantry` package importable as `import grantry`, `grantry.__version__` (str). The uv project layout every later task builds in.

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "grantry"
version = "0.1.0"
description = "Local credential broker for humans and AI agents, AWS-first"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "Apache-2.0" }
authors = [{ name = "Sai Kiran Meda" }]
dependencies = [
    "botocore>=1.43",
    "keyring>=25.7",
    "mcp>=1.28",
    "pyyaml>=6.0.3",
]

[project.scripts]
grantry = "grantry.cli:main"

[dependency-groups]
dev = [
    "pytest>=9.1",
    "pytest-asyncio>=1.4",
    "mypy>=2.3",
    "ruff>=0.15",
    "types-pyyaml>=6.0.12",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.mypy]
python_version = "3.10"
strict = true
files = ["src", "tests"]
```

- [ ] **Step 2: Write ruff.toml**

```toml
target-version = "py310"
line-length = 100

[lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
```

- [ ] **Step 3: Write .gitignore**

```
.venv/
__pycache__/
*.pyc
.mypy_cache/
.ruff_cache/
.pytest_cache/
dist/
```

- [ ] **Step 4: Write the package init with a version**

`src/grantry/__init__.py`:
```python
"""grantry: a local credential broker for humans and AI agents."""

__version__ = "0.1.0"
```

Empty `tests/__init__.py` and a one-line `README.md` (`# grantry`).

- [ ] **Step 5: Write the smoke test**

`tests/test_smoke.py`:
```python
import grantry


def test_version_is_a_string():
    assert isinstance(grantry.__version__, str)
    assert grantry.__version__
```

- [ ] **Step 6: Write CI workflow**

`.github/workflows/ci.yml`:
```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.10", "3.14"]
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v3
      - name: Set up Python
        run: uv python install ${{ matrix.python }}
      - name: Sync
        run: uv sync --all-extras --dev
      - name: Ruff
        run: uv run ruff check .
      - name: Ruff format check
        run: uv run ruff format --check .
      - name: Mypy
        run: uv run mypy
      - name: Pytest
        run: uv run pytest -q
```

- [ ] **Step 7: Sync and run the full gate**

Run: `cd /Users/skiranmeda/sai-git/grantry && uv sync --all-extras --dev && uv run ruff check . && uv run mypy && uv run pytest -q`
Expected: ruff clean, mypy `Success: no issues found`, pytest `1 passed`.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "chore: scaffold grantry project, tooling, and CI"
```

---

### Task 2: State home and config resolution

**Files:**
- Create: `src/grantry/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `grantry_home() -> pathlib.Path` — returns `$GRANTRY_HOME` or `~/.grantry`, creating it (mode 0700) if absent.
  - `state_path(name: str) -> pathlib.Path` — a path inside the home for a named file.

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
import os
import stat

from grantry.config import grantry_home, state_path


def test_home_honors_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path / "gh"))
    home = grantry_home()
    assert home == tmp_path / "gh"
    assert home.is_dir()
    assert stat.S_IMODE(home.stat().st_mode) == 0o700


def test_home_defaults_to_dot_grantry(tmp_path, monkeypatch):
    monkeypatch.delenv("GRANTRY_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert grantry_home() == tmp_path / ".grantry"


def test_state_path_is_inside_home(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    assert state_path("audit.jsonl") == tmp_path / "audit.jsonl"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_config.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'grantry.config'`.

- [ ] **Step 3: Implement config.py**

```python
"""State home and path resolution. No secrets are ever stored here."""

from __future__ import annotations

import os
import pathlib


def grantry_home() -> pathlib.Path:
    override = os.environ.get("GRANTRY_HOME")
    home = pathlib.Path(override) if override else pathlib.Path.home() / ".grantry"
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    return home


def state_path(name: str) -> pathlib.Path:
    return grantry_home() / name
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_config.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/grantry/config.py tests/test_config.py
git commit -m "feat: state home and path resolution under GRANTRY_HOME"
```

---

### Task 3: Identity model and glob matching

**Files:**
- Create: `src/grantry/identity.py`
- Create: `tests/test_identity.py`

**Interfaces:**
- Produces:
  - `Identity` dataclass (frozen): `account_id: str`, `account_name: str`, `role_name: str`. Property `key -> str` returns `"{account_name}/{role_name}"`.
  - `matches(pattern: str, ident: Identity) -> bool` — matches a `"account-glob/role-glob"` pattern against an identity's key using shell globbing (`fnmatch`), case-insensitive. A pattern with no `/` matches the whole key.

- [ ] **Step 1: Write the failing test**

`tests/test_identity.py`:
```python
from grantry.identity import Identity, matches


def ident(acct="prod", role="ReadOnlyAccess", aid="111122223333"):
    return Identity(account_id=aid, account_name=acct, role_name=role)


def test_key():
    assert ident("dev", "Admin").key == "dev/Admin"


def test_exact_match():
    assert matches("prod/ReadOnlyAccess", ident("prod", "ReadOnlyAccess"))


def test_role_glob():
    assert matches("*/ReadOnlyAccess", ident("anything", "ReadOnlyAccess"))
    assert not matches("*/ReadOnlyAccess", ident("anything", "AdminAccess"))


def test_account_glob():
    assert matches("dev-*/AWSPowerUserAccess", ident("dev-payments", "AWSPowerUserAccess"))
    assert not matches("dev-*/AWSPowerUserAccess", ident("prod-payments", "AWSPowerUserAccess"))


def test_both_globs():
    assert matches("*prod*/*Admin*", ident("prod-payments", "SuperAdminAccess"))


def test_case_insensitive():
    assert matches("*/readonlyaccess", ident("prod", "ReadOnlyAccess"))


def test_no_slash_matches_whole_key():
    assert matches("prod/ReadOnlyAccess", ident("prod", "ReadOnlyAccess"))
    assert matches("*ReadOnly*", ident("prod", "ReadOnlyAccess"))
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_identity.py -q`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement identity.py**

```python
"""The identity a caller assumes: an account plus an Identity Center role."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    account_id: str
    account_name: str
    role_name: str

    @property
    def key(self) -> str:
        return f"{self.account_name}/{self.role_name}"


def matches(pattern: str, ident: Identity) -> bool:
    return fnmatch.fnmatch(ident.key.lower(), pattern.lower())
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_identity.py -q`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/grantry/identity.py tests/test_identity.py
git commit -m "feat: identity model and glob matching"
```

---

### Task 4: TTL parsing

**Files:**
- Create: `src/grantry/ttl.py`
- Create: `tests/test_ttl.py`

**Interfaces:**
- Produces:
  - `parse_ttl(s: str) -> int` — parse `"15m"`, `"1h"`, `"3600s"`, `"12h"` to seconds. Raises `ValueError` on garbage.
  - `format_ttl(seconds: int) -> str` — inverse, chooses the largest whole unit (`900 -> "15m"`).

- [ ] **Step 1: Write the failing test**

`tests/test_ttl.py`:
```python
import pytest

from grantry.ttl import format_ttl, parse_ttl


@pytest.mark.parametrize(
    "text,secs",
    [("15m", 900), ("1h", 3600), ("3600s", 3600), ("12h", 43200), ("45s", 45)],
)
def test_parse(text, secs):
    assert parse_ttl(text) == secs


@pytest.mark.parametrize("bad", ["", "15", "m", "1d", "-5m", "1.5h", "abc"])
def test_parse_rejects(bad):
    with pytest.raises(ValueError):
        parse_ttl(bad)


@pytest.mark.parametrize("secs,text", [(900, "15m"), (3600, "1h"), (45, "45s"), (43200, "12h")])
def test_format(secs, text):
    assert format_ttl(secs) == text
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_ttl.py -q`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement ttl.py**

```python
"""Human TTL strings (15m, 1h, 3600s) to and from seconds."""

from __future__ import annotations

import re

_UNITS = {"s": 1, "m": 60, "h": 3600}
_PATTERN = re.compile(r"^(\d+)([smh])$")


def parse_ttl(s: str) -> int:
    m = _PATTERN.match(s)
    if not m:
        raise ValueError(f"invalid ttl {s!r}: want a whole number followed by s, m, or h")
    return int(m.group(1)) * _UNITS[m.group(2)]


def format_ttl(seconds: int) -> str:
    for unit in ("h", "m"):
        size = _UNITS[unit]
        if seconds % size == 0 and seconds >= size:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_ttl.py -q`
Expected: `15 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/grantry/ttl.py tests/test_ttl.py
git commit -m "feat: TTL string parsing and formatting"
```

---

### Task 5: Policy engine

**Files:**
- Create: `src/grantry/policy.py`
- Create: `tests/test_policy.py`

**Interfaces:**
- Consumes: `Identity`, `matches` (Task 3), `parse_ttl` (Task 4).
- Produces:
  - `Decision` dataclass (frozen): `allowed: bool`, `reason: str`, `matched_rule: str | None`, `capped_ttl: int` (seconds; the smaller of the request and the policy max; 0 when denied).
  - `Policy` class with `Policy.load(path: pathlib.Path) -> Policy` (a missing file yields a deny-all agent policy; a malformed file raises `PolicyError`), and `evaluate(ident: Identity, requested_ttl: int, caller: str = "agent") -> Decision`. `caller` is `"agent"` or `"human"`.
  - `PolicyError(Exception)`.
  - Semantics: deny rules win; for agents an unmatched identity is denied; for humans an unmatched identity is allowed. TTL is capped to the section's `max_ttl`.

- [ ] **Step 1: Write the failing test**

`tests/test_policy.py`:
```python
import pytest

from grantry.identity import Identity
from grantry.policy import Policy, PolicyError

POLICY = """
agents:
  allow:
    - identity: "*/ReadOnlyAccess"
    - identity: "dev-*/AWSPowerUserAccess"
  deny:
    - identity: "*prod*/*Admin*"
  max_ttl: 15m
humans:
  max_ttl: 12h
"""


def write(tmp_path, text):
    p = tmp_path / "policy.yaml"
    p.write_text(text)
    return p


def ident(acct, role):
    return Identity(account_id="111122223333", account_name=acct, role_name=role)


def test_agent_allowed_and_ttl_capped(tmp_path):
    pol = Policy.load(write(tmp_path, POLICY))
    d = pol.evaluate(ident("anything", "ReadOnlyAccess"), requested_ttl=3600, caller="agent")
    assert d.allowed
    assert d.capped_ttl == 900  # capped to 15m
    assert d.matched_rule == "*/ReadOnlyAccess"


def test_agent_ttl_not_raised(tmp_path):
    pol = Policy.load(write(tmp_path, POLICY))
    d = pol.evaluate(ident("dev-x", "AWSPowerUserAccess"), requested_ttl=300, caller="agent")
    assert d.allowed
    assert d.capped_ttl == 300  # request below cap is kept


def test_deny_beats_allow(tmp_path):
    pol = Policy.load(write(tmp_path, POLICY))
    # Matches allow (*/ReadOnlyAccess? no) but matches deny *prod*/*Admin*
    d = pol.evaluate(ident("prod-pay", "SuperAdminAccess"), requested_ttl=300, caller="agent")
    assert not d.allowed
    assert "deny" in d.reason.lower()


def test_agent_unmatched_denied(tmp_path):
    pol = Policy.load(write(tmp_path, POLICY))
    d = pol.evaluate(ident("stg", "AWSDeveloperAccess"), requested_ttl=300, caller="agent")
    assert not d.allowed


def test_human_unmatched_allowed(tmp_path):
    pol = Policy.load(write(tmp_path, POLICY))
    d = pol.evaluate(ident("stg", "AWSDeveloperAccess"), requested_ttl=3600, caller="human")
    assert d.allowed
    assert d.capped_ttl == 3600


def test_missing_file_denies_agents(tmp_path):
    pol = Policy.load(tmp_path / "nope.yaml")
    d = pol.evaluate(ident("dev", "ReadOnlyAccess"), requested_ttl=300, caller="agent")
    assert not d.allowed
    # but humans still work with a sane default cap
    h = pol.evaluate(ident("dev", "ReadOnlyAccess"), requested_ttl=300, caller="human")
    assert h.allowed


def test_malformed_policy_raises(tmp_path):
    with pytest.raises(PolicyError):
        Policy.load(write(tmp_path, "agents: [this is not a mapping]"))
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_policy.py -q`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement policy.py**

```python
"""The policy layer between callers and the cloud. Fail closed for agents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from grantry.identity import Identity, matches
from grantry.ttl import parse_ttl

_DEFAULT_AGENT_TTL = 900  # 15m
_DEFAULT_HUMAN_TTL = 43200  # 12h


class PolicyError(Exception):
    pass


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    matched_rule: str | None
    capped_ttl: int


@dataclass(frozen=True)
class _Section:
    allow: list[str]
    deny: list[str]
    max_ttl: int
    default_allow: bool


class Policy:
    def __init__(self, agents: _Section, humans: _Section, exists: bool) -> None:
        self._agents = agents
        self._humans = humans
        self._exists = exists

    @classmethod
    def load(cls, path: Path) -> Policy:
        if not path.exists():
            return cls(
                agents=_Section([], [], _DEFAULT_AGENT_TTL, default_allow=False),
                humans=_Section([], [], _DEFAULT_HUMAN_TTL, default_allow=True),
                exists=False,
            )
        try:
            raw = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError as e:
            raise PolicyError(f"policy.yaml is not valid YAML: {e}") from e
        if not isinstance(raw, dict):
            raise PolicyError("policy.yaml must be a mapping with agents/humans sections")
        return cls(
            agents=cls._section(raw.get("agents"), _DEFAULT_AGENT_TTL, default_allow=False),
            humans=cls._section(raw.get("humans"), _DEFAULT_HUMAN_TTL, default_allow=True),
            exists=True,
        )

    @staticmethod
    def _section(node: Any, default_ttl: int, *, default_allow: bool) -> _Section:
        if node is None:
            return _Section([], [], default_ttl, default_allow)
        if not isinstance(node, dict):
            raise PolicyError("each policy section must be a mapping")
        allow = Policy._patterns(node.get("allow"))
        deny = Policy._patterns(node.get("deny"))
        max_ttl = default_ttl
        if "max_ttl" in node:
            try:
                max_ttl = parse_ttl(str(node["max_ttl"]))
            except ValueError as e:
                raise PolicyError(str(e)) from e
        return _Section(allow, deny, max_ttl, default_allow)

    @staticmethod
    def _patterns(node: Any) -> list[str]:
        if node is None:
            return []
        if not isinstance(node, list):
            raise PolicyError("allow/deny must be a list of {identity: pattern} entries")
        out: list[str] = []
        for entry in node:
            if not isinstance(entry, dict) or "identity" not in entry:
                raise PolicyError("each allow/deny entry needs an 'identity' pattern")
            out.append(str(entry["identity"]))
        return out

    def evaluate(self, ident: Identity, requested_ttl: int, caller: str = "agent") -> Decision:
        section = self._humans if caller == "human" else self._agents
        for pattern in section.deny:
            if matches(pattern, ident):
                return Decision(False, f"denied by deny rule {pattern!r}", pattern, 0)
        capped = min(requested_ttl, section.max_ttl)
        for pattern in section.allow:
            if matches(pattern, ident):
                return Decision(True, f"allowed by rule {pattern!r}", pattern, capped)
        if section.default_allow:
            return Decision(True, "allowed by default (human)", None, capped)
        return Decision(False, "no allow rule matched (agent default deny)", None, 0)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_policy.py -q`
Expected: `7 passed`.

- [ ] **Step 5: Run mypy on the module**

Run: `uv run mypy`
Expected: `Success: no issues found`.

- [ ] **Step 6: Commit**

```bash
git add src/grantry/policy.py tests/test_policy.py
git commit -m "feat: policy engine with deny-beats-allow and TTL caps, fail closed for agents"
```

---

### Task 6: Audit log

**Files:**
- Create: `src/grantry/audit.py`
- Create: `tests/test_audit.py`

**Interfaces:**
- Consumes: `state_path` (Task 2), `Decision` (Task 5), `Identity` (Task 3).
- Produces:
  - `AuditLog` class over a JSONL file at `state_path("audit.jsonl")` (created 0600).
    - `record(caller: str, ident: Identity, decision: Decision, at: str) -> None` — append one line. `at` is an ISO-8601 timestamp string (passed in, never generated inside, so tests are deterministic).
    - `entries() -> list[dict]` — read all records back.
  - A record never contains a credential or token: only caller, identity key, allowed bool, reason, matched rule, capped ttl, timestamp.

- [ ] **Step 1: Write the failing test**

`tests/test_audit.py`:
```python
import json
import stat

from grantry.audit import AuditLog
from grantry.identity import Identity
from grantry.policy import Decision


def test_record_and_read(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    log = AuditLog()
    ident = Identity("111122223333", "prod", "ReadOnlyAccess")
    dec = Decision(True, "allowed by rule '*/ReadOnlyAccess'", "*/ReadOnlyAccess", 900)
    log.record("claude-code", ident, dec, at="2026-07-15T10:00:00Z")

    entries = log.entries()
    assert len(entries) == 1
    e = entries[0]
    assert e["caller"] == "claude-code"
    assert e["identity"] == "prod/ReadOnlyAccess"
    assert e["account_id"] == "111122223333"
    assert e["allowed"] is True
    assert e["matched_rule"] == "*/ReadOnlyAccess"
    assert e["capped_ttl"] == 900
    assert e["at"] == "2026-07-15T10:00:00Z"


def test_no_secret_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    log = AuditLog()
    ident = Identity("111122223333", "prod", "ReadOnlyAccess")
    log.record("agent", ident, Decision(False, "denied", None, 0), at="2026-07-15T10:00:00Z")
    raw = (tmp_path / "audit.jsonl").read_text().lower()
    for banned in ("secret", "token", "accesskey", "sessiontoken"):
        assert banned not in raw


def test_file_is_0600(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    log = AuditLog()
    log.record("a", Identity("1", "p", "R"), Decision(True, "ok", "r", 60), at="t")
    mode = stat.S_IMODE((tmp_path / "audit.jsonl").stat().st_mode)
    assert mode == 0o600


def test_appends(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    log = AuditLog()
    for i in range(3):
        log.record("a", Identity("1", "p", "R"), Decision(True, "ok", "r", 60), at=f"t{i}")
    assert len(log.entries()) == 3
    # each line is independently valid JSON
    for line in (tmp_path / "audit.jsonl").read_text().splitlines():
        json.loads(line)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_audit.py -q`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement audit.py**

```python
"""Append-only audit of every grant decision. Never contains a secret."""

from __future__ import annotations

import json
import os
from typing import Any

from grantry.config import state_path
from grantry.identity import Identity
from grantry.policy import Decision


class AuditLog:
    def __init__(self) -> None:
        self._path = state_path("audit.jsonl")
        if not self._path.exists():
            # Create with 0600 before anything is written.
            fd = os.open(self._path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)

    def record(self, caller: str, ident: Identity, decision: Decision, at: str) -> None:
        entry: dict[str, Any] = {
            "at": at,
            "caller": caller,
            "identity": ident.key,
            "account_id": ident.account_id,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "matched_rule": decision.matched_rule,
            "capped_ttl": decision.capped_ttl,
        }
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, separators=(",", ":")) + "\n")

    def entries(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_audit.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/grantry/audit.py tests/test_audit.py
git commit -m "feat: append-only audit log, 0600, secret-free by construction"
```

---

### Task 7: Secret-redacting logging setup

**Files:**
- Create: `src/grantry/logging_setup.py`
- Create: `tests/test_logging_setup.py`

**Interfaces:**
- Produces:
  - `configure_logging(verbosity: int = 0) -> None` — installs a root handler whose filter redacts anything that looks like a credential. Verbosity 0 = WARNING, 1 = INFO, 2+ = DEBUG.
  - `redact(text: str) -> str` — replace values of sensitive keys (accessKeyId, secretAccessKey, sessionToken, accessToken, clientSecret, refreshToken) and long base64-ish blobs with `***`.

- [ ] **Step 1: Write the failing test**

`tests/test_logging_setup.py`:
```python
import logging

from grantry.logging_setup import configure_logging, redact


def test_redacts_known_keys():
    text = 'accessKeyId=AKIAEXAMPLE secretAccessKey=abc/def+ghiJKL sessionToken=zzzz'
    out = redact(text)
    assert "AKIAEXAMPLE" not in out
    assert "abc/def+ghiJKL" not in out
    assert "zzzz" not in out
    assert "***" in out


def test_redacts_json_shape():
    text = '{"accessToken": "verylongtokenvalue1234567890abcdef", "region": "us-east-1"}'
    out = redact(text)
    assert "verylongtokenvalue1234567890abcdef" not in out
    assert "us-east-1" in out  # non-secret survives


def test_handler_filter_redacts(capsys):
    configure_logging(verbosity=2)
    logging.getLogger("grantry.test").debug("token=supersecretvalue1234567890abcd")
    err = capsys.readouterr().err
    assert "supersecretvalue1234567890abcd" not in err
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_logging_setup.py -q`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement logging_setup.py**

```python
"""Logging whose handler redacts secrets by construction. No call site is trusted."""

from __future__ import annotations

import logging
import re

_KEYS = "accessKeyId|secretAccessKey|sessionToken|accessToken|clientSecret|refreshToken"
_KV = re.compile(rf'(?i)("?({_KEYS})"?\s*[=:]\s*"?)([^"\s,}}]+)')
# Any long token-like run (>=20 chars of base64/hex-ish material).
_BLOB = re.compile(r"[A-Za-z0-9/+_-]{20,}")


def redact(text: str) -> str:
    text = _KV.sub(lambda m: m.group(1) + "***", text)
    text = _BLOB.sub("***", text)
    return text


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.getMessage()))
        record.args = ()
        return True


def configure_logging(verbosity: int = 0) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    handler = logging.StreamHandler()
    handler.addFilter(_RedactFilter())
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_logging_setup.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/grantry/logging_setup.py tests/test_logging_setup.py
git commit -m "feat: secret-redacting logging so no call site can leak a token"
```

---

### Task 8: Keychain-backed secret store

**Files:**
- Create: `src/grantry/secrets.py`
- Create: `tests/test_secrets.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Produces:
  - `SecretStore` class wrapping `keyring` under service name `"grantry"`.
    - `put(name: str, value: str) -> None`
    - `get(name: str) -> str | None`
    - `delete(name: str) -> None`
  - `token_name(start_url: str) -> str` — a stable keychain entry name for a start URL's SSO token (`"sso-token:" + sha256(start_url)[:16]`).
- Consumes: nothing from earlier tasks.
- The conftest installs an in-memory keyring backend so tests never touch the real OS keychain.

- [ ] **Step 1: Write conftest with an in-memory keyring**

`tests/conftest.py`:
```python
import keyring
import pytest
from keyring.backend import KeyringBackend


class MemoryKeyring(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self._store.get((service, username))

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def delete_password(self, service, username):
        self._store.pop((service, username), None)


@pytest.fixture(autouse=True)
def memory_keyring():
    backend = MemoryKeyring()
    previous = keyring.get_keyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)
```

- [ ] **Step 2: Write the failing test**

`tests/test_secrets.py`:
```python
from grantry.secrets import SecretStore, token_name


def test_roundtrip():
    s = SecretStore()
    s.put("k", "v")
    assert s.get("k") == "v"


def test_missing_is_none():
    assert SecretStore().get("nope") is None


def test_delete():
    s = SecretStore()
    s.put("k", "v")
    s.delete("k")
    assert s.get("k") is None


def test_token_name_is_stable_and_scoped():
    a = token_name("https://example.awsapps.com/start")
    b = token_name("https://example.awsapps.com/start")
    c = token_name("https://other.awsapps.com/start")
    assert a == b
    assert a != c
    assert a.startswith("sso-token:")
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_secrets.py -q`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 4: Implement secrets.py**

```python
"""OS-keychain secret storage. Secrets never touch the state directory or a log."""

from __future__ import annotations

import hashlib

import keyring

_SERVICE = "grantry"


class SecretStore:
    def put(self, name: str, value: str) -> None:
        keyring.set_password(_SERVICE, name, value)

    def get(self, name: str) -> str | None:
        return keyring.get_password(_SERVICE, name)

    def delete(self, name: str) -> None:
        keyring.delete_password(_SERVICE, name)


def token_name(start_url: str) -> str:
    digest = hashlib.sha256(start_url.encode("utf-8")).hexdigest()[:16]
    return f"sso-token:{digest}"
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_secrets.py -q`
Expected: `4 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/grantry/secrets.py tests/test_secrets.py tests/conftest.py
git commit -m "feat: keychain-backed secret store with in-memory test backend"
```

---

### Task 9: AWS provider — device flow and credential minting against a fake Identity Center

**Files:**
- Create: `src/grantry/providers/__init__.py`
- Create: `src/grantry/providers/base.py`
- Create: `src/grantry/providers/aws.py`
- Create: `tests/fakes/fake_sso.py`
- Create: `tests/test_aws_provider.py`

**Interfaces:**
- Consumes: `Identity` (Task 3), `SecretStore` + `token_name` (Task 8).
- Produces:
  - `base.py`:
    - `Session` dataclass (frozen): `start_url: str`, `region: str`, `access_token: str`, `expires_at: float` (epoch seconds).
    - `Credentials` dataclass (frozen): `access_key_id: str`, `secret_access_key: str`, `session_token: str`, `expiration: float`.
    - `Provider` Protocol: `name() -> str`, `start_login(handler) -> Session`, `list_identities(session) -> list[Identity]`, `mint(session, ident, ttl) -> Credentials`.
    - `InteractionHandler` Protocol: `on_verification(verification_uri: str, user_code: str) -> None` and `def wait(self) -> None` (called to block until user confirms; the CLI blocks on Enter/timeout, tests return immediately).
  - `aws.py`: `AwsProvider(start_url, region, *, client_factory=None)`. `client_factory(service_name, endpoint_url)` defaults to botocore session clients; tests inject one pointed at the fake server. Implements the device authorization grant against `sso-oidc` (`register_client`, `start_device_authorization`, poll `create_token`) and identity listing + `get_role_credentials` against `sso`.
  - `tests/fakes/fake_sso.py`: `FakeSSO` context manager starting a threaded HTTP server that speaks the sso-oidc + sso JSON protocol (register_client, start_device_authorization, create_token with one AuthorizationPending then success, list_accounts, list_account_roles, get_role_credentials). Exposes `.endpoint`.

- [ ] **Step 1: Write the fake Identity Center server**

`tests/fakes/fake_sso.py`:
```python
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# One shared state object the handler mutates so create_token pends once.
class _State:
    def __init__(self) -> None:
        self.token_polls = 0


def _make_handler(state: _State):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silence
            pass

        def _send(self, code, body):
            payload = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            _ = self.rfile.read(length)
            path = self.path
            if path.endswith("/client/register"):
                self._send(200, {"clientId": "cid", "clientSecret": "csecret",
                                 "clientIdIssuedAt": 0, "clientSecretExpiresAt": 9999999999})
            elif path.endswith("/device_authorization"):
                self._send(200, {"deviceCode": "dc", "userCode": "WXYZ-1234",
                                 "verificationUri": "https://device.example/verify",
                                 "verificationUriComplete": "https://device.example/verify?code=WXYZ-1234",
                                 "expiresIn": 600, "interval": 1})
            elif path.endswith("/token"):
                state.token_polls += 1
                if state.token_polls < 2:
                    self._send(400, {"error": "authorization_pending",
                                     "error_description": "pending"})
                else:
                    self._send(200, {"accessToken": "sso-access-token-value",
                                     "tokenType": "Bearer", "expiresIn": 3600})
            else:
                self._send(404, {"error": "not_found"})

        def do_GET(self):  # noqa: N802
            path = self.path
            if "/assignment/accounts" in path:
                self._send(200, {"accountList": [
                    {"accountId": "111122223333", "accountName": "prod"},
                    {"accountId": "444455556666", "accountName": "dev-payments"}]})
            elif "/assignment/roles" in path:
                self._send(200, {"roleList": [
                    {"roleName": "ReadOnlyAccess", "accountId": "111122223333"},
                    {"roleName": "AWSPowerUserAccess", "accountId": "111122223333"}]})
            elif "/federation/credentials" in path:
                self._send(200, {"roleCredentials": {
                    "accessKeyId": "AKIAFAKE", "secretAccessKey": "fakesecret",
                    "sessionToken": "faketoken", "expiration": 1893456000000}})
            else:
                self._send(404, {"error": "not_found"})

    return Handler


class FakeSSO:
    def __init__(self) -> None:
        self._state = _State()
        self._server = HTTPServer(("127.0.0.1", 0), _make_handler(self._state))
        host, port = self._server.server_address
        self.endpoint = f"http://{host}:{port}"

    def __enter__(self) -> FakeSSO:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
```

- [ ] **Step 2: Write base.py**

```python
"""Provider protocol and the value types every cloud adapter returns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from grantry.identity import Identity


@dataclass(frozen=True)
class Session:
    start_url: str
    region: str
    access_token: str
    expires_at: float


@dataclass(frozen=True)
class Credentials:
    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: float


class InteractionHandler(Protocol):
    def on_verification(self, verification_uri: str, user_code: str) -> None: ...
    def wait(self) -> None: ...


class Provider(Protocol):
    def name(self) -> str: ...
    def start_login(self, handler: InteractionHandler) -> Session: ...
    def list_identities(self, session: Session) -> list[Identity]: ...
    def mint(self, session: Session, ident: Identity, ttl: int) -> Credentials: ...
```

Empty `src/grantry/providers/__init__.py`.

- [ ] **Step 3: Write the failing provider test**

`tests/test_aws_provider.py`:
```python
import time

import botocore.session

from grantry.providers.aws import AwsProvider
from tests.fakes.fake_sso import FakeSSO


class ImmediateHandler:
    def __init__(self):
        self.seen = None

    def on_verification(self, uri, code):
        self.seen = (uri, code)

    def wait(self):
        return None


def client_factory_for(endpoint):
    def factory(service_name, region_name):
        session = botocore.session.Session()
        return session.create_client(
            service_name, region_name=region_name, endpoint_url=endpoint,
            aws_access_key_id="x", aws_secret_access_key="y",
        )
    return factory


def test_device_flow_then_mint():
    with FakeSSO() as fake:
        provider = AwsProvider(
            "https://example.awsapps.com/start", "us-east-1",
            client_factory=client_factory_for(fake.endpoint), poll_interval=0,
        )
        handler = ImmediateHandler()
        session = provider.start_login(handler)
        assert session.access_token == "sso-access-token-value"
        assert session.expires_at > time.time()
        assert handler.seen[1] == "WXYZ-1234"

        idents = provider.list_identities(session)
        keys = {i.key for i in idents}
        assert "prod/ReadOnlyAccess" in keys
        assert "prod/AWSPowerUserAccess" in keys

        prod_ro = next(i for i in idents if i.key == "prod/ReadOnlyAccess")
        creds = provider.mint(session, prod_ro, ttl=900)
        assert creds.access_key_id == "AKIAFAKE"
        assert creds.session_token == "faketoken"
```

- [ ] **Step 4: Run to verify it fails**

Run: `uv run pytest tests/test_aws_provider.py -q`
Expected: FAIL, `ModuleNotFoundError: grantry.providers.aws`.

- [ ] **Step 5: Implement aws.py**

```python
"""AWS Identity Center provider: OIDC device flow plus role credential minting.

Uses botocore's documented low-level clients only (sso-oidc, sso). No private
botocore attributes and no vendored SDK code.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import botocore.session
from botocore.config import Config
from botocore.exceptions import ClientError

from grantry.identity import Identity
from grantry.providers.base import Credentials, InteractionHandler, Session

ClientFactory = Callable[[str, str], Any]


def _default_client_factory(service_name: str, region_name: str) -> Any:
    session = botocore.session.Session()
    retries = Config(retries={"mode": "standard", "max_attempts": 10})
    return session.create_client(service_name, region_name=region_name, config=retries)


class AwsProvider:
    def __init__(
        self,
        start_url: str,
        region: str,
        *,
        client_factory: ClientFactory | None = None,
        poll_interval: float = 5.0,
    ) -> None:
        self.start_url = start_url
        self.region = region
        self._client_factory = client_factory or _default_client_factory
        self._poll_interval = poll_interval

    def name(self) -> str:
        return "aws"

    def start_login(self, handler: InteractionHandler) -> Session:
        oidc = self._client_factory("sso-oidc", self.region)
        reg = oidc.register_client(clientName="grantry", clientType="public")
        auth = oidc.start_device_authorization(
            clientId=reg["clientId"],
            clientSecret=reg["clientSecret"],
            startUrl=self.start_url,
        )
        handler.on_verification(
            auth.get("verificationUriComplete", auth["verificationUri"]),
            auth["userCode"],
        )
        handler.wait()
        deadline = time.time() + auth["expiresIn"]
        while True:
            try:
                token = oidc.create_token(
                    clientId=reg["clientId"],
                    clientSecret=reg["clientSecret"],
                    grantType="urn:ietf:params:oauth:grant-type:device_code",
                    deviceCode=auth["deviceCode"],
                )
                break
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("AuthorizationPendingException", "authorization_pending"):
                    if time.time() >= deadline:
                        raise TimeoutError("device authorization expired before approval") from e
                    time.sleep(self._poll_interval)
                    continue
                if code in ("SlowDownException", "slow_down"):
                    time.sleep(self._poll_interval + 1)
                    continue
                raise
        return Session(
            start_url=self.start_url,
            region=self.region,
            access_token=token["accessToken"],
            expires_at=time.time() + int(token.get("expiresIn", 3600)),
        )

    def list_identities(self, session: Session) -> list[Identity]:
        sso = self._client_factory("sso", session.region)
        idents: list[Identity] = []
        accounts = self._paginate(
            sso.list_accounts, "accountList", accessToken=session.access_token
        )
        for acct in accounts:
            roles = self._paginate(
                sso.list_account_roles,
                "roleList",
                accessToken=session.access_token,
                accountId=acct["accountId"],
            )
            for role in roles:
                idents.append(
                    Identity(
                        account_id=acct["accountId"],
                        account_name=acct.get("accountName", acct["accountId"]),
                        role_name=role["roleName"],
                    )
                )
        return idents

    def mint(self, session: Session, ident: Identity, ttl: int) -> Credentials:
        sso = self._client_factory("sso", session.region)
        resp = sso.get_role_credentials(
            roleName=ident.role_name,
            accountId=ident.account_id,
            accessToken=session.access_token,
        )
        rc = resp["roleCredentials"]
        return Credentials(
            access_key_id=rc["accessKeyId"],
            secret_access_key=rc["secretAccessKey"],
            session_token=rc["sessionToken"],
            expiration=rc["expiration"] / 1000.0,  # ms epoch to seconds
        )

    @staticmethod
    def _paginate(op: Callable[..., Any], key: str, **kwargs: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        next_token: str | None = None
        while True:
            call = dict(kwargs)
            if next_token:
                call["nextToken"] = next_token
            resp = op(**call)
            out.extend(resp.get(key, []))
            next_token = resp.get("nextToken")
            if not next_token:
                return out
```

- [ ] **Step 6: Run to verify it passes**

Run: `uv run pytest tests/test_aws_provider.py -q`
Expected: `1 passed`. (The fake pends `create_token` once then succeeds, exercising the poll loop with `poll_interval=0`.)

- [ ] **Step 7: Run mypy and ruff**

Run: `uv run mypy && uv run ruff check .`
Expected: both clean.

- [ ] **Step 8: Commit**

```bash
git add src/grantry/providers tests/fakes/fake_sso.py tests/test_aws_provider.py
git commit -m "feat: AWS provider device flow and credential minting, fake-SSO E2E"
```

---

### Task 10: Broker — compose provider, policy, audit into one grant path

**Files:**
- Create: `src/grantry/broker.py`
- Create: `tests/test_broker.py`

**Interfaces:**
- Consumes: everything above (`AwsProvider`/`Provider`, `Policy`, `AuditLog`, `SecretStore`, `token_name`, `Session`, `Credentials`, `Identity`, `parse_ttl`).
- Produces:
  - `GrantResult` dataclass (frozen): `credentials: Credentials | None`, `decision: Decision`.
  - `Broker` class:
    - `__init__(self, provider: Provider, policy: Policy, audit: AuditLog, secrets: SecretStore, *, now: Callable[[], float] = time.time, clock_iso: Callable[[], str])`.
    - `login(handler) -> Session` — runs the provider login and persists the token to the keychain under `token_name(start_url)`; returns the session.
    - `cached_session() -> Session | None` — reload a non-expired session from the keychain, or None.
    - `identities() -> list[Identity]` — list identities using the cached session (raises `NoSessionError` if none).
    - `grant(ident_key: str, requested_ttl: int, caller: str) -> GrantResult` — resolve the key to an identity, evaluate policy, mint on allow, audit always, and return the result. On deny, credentials is None and nothing is minted.
  - `NoSessionError(Exception)`.

- [ ] **Step 1: Write the failing test**

`tests/test_broker.py`:
```python
import time

from grantry.audit import AuditLog
from grantry.broker import Broker, NoSessionError
from grantry.identity import Identity
from grantry.policy import Policy
from grantry.providers.base import Credentials, Session
from grantry.secrets import SecretStore


class FakeProvider:
    def __init__(self):
        self.start_url = "https://example.awsapps.com/start"
        self.region = "us-east-1"
        self._idents = [
            Identity("111122223333", "prod", "ReadOnlyAccess"),
            Identity("111122223333", "prod", "AdminAccess"),
        ]

    def name(self):
        return "aws"

    def start_login(self, handler):
        return Session(self.start_url, self.region, "tok", time.time() + 3600)

    def list_identities(self, session):
        return self._idents

    def mint(self, session, ident, ttl):
        return Credentials("AKIA", "sec", "sess", time.time() + ttl)


POLICY = """
agents:
  allow:
    - identity: "*/ReadOnlyAccess"
  deny:
    - identity: "*/*Admin*"
  max_ttl: 15m
humans:
  max_ttl: 12h
"""


def build(tmp_path, monkeypatch, policy_text=POLICY):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    p = tmp_path / "policy.yaml"
    p.write_text(policy_text)
    clock = {"n": 1000.0}
    return Broker(
        provider=FakeProvider(),
        policy=Policy.load(p),
        audit=AuditLog(),
        secrets=SecretStore(),
        now=lambda: clock["n"],
        clock_iso=lambda: "2026-07-15T10:00:00Z",
    )


class H:
    def on_verification(self, uri, code): ...
    def wait(self): ...


def test_login_caches_session(tmp_path, monkeypatch):
    broker = build(tmp_path, monkeypatch)
    broker.login(H())
    s = broker.cached_session()
    assert s is not None
    assert s.access_token == "tok"


def test_identities_requires_session(tmp_path, monkeypatch):
    broker = build(tmp_path, monkeypatch)
    try:
        broker.identities()
        assert False, "expected NoSessionError"
    except NoSessionError:
        pass


def test_agent_grant_allowed_mints_and_audits(tmp_path, monkeypatch):
    broker = build(tmp_path, monkeypatch)
    broker.login(H())
    res = broker.grant("prod/ReadOnlyAccess", requested_ttl=3600, caller="agent")
    assert res.decision.allowed
    assert res.credentials is not None
    assert res.credentials.access_key_id == "AKIA"
    entries = AuditLog().entries()
    assert entries[-1]["identity"] == "prod/ReadOnlyAccess"
    assert entries[-1]["allowed"] is True


def test_agent_grant_denied_mints_nothing(tmp_path, monkeypatch):
    broker = build(tmp_path, monkeypatch)
    broker.login(H())
    res = broker.grant("prod/AdminAccess", requested_ttl=3600, caller="agent")
    assert not res.decision.allowed
    assert res.credentials is None
    assert AuditLog().entries()[-1]["allowed"] is False


def test_unknown_identity_denied(tmp_path, monkeypatch):
    broker = build(tmp_path, monkeypatch)
    broker.login(H())
    res = broker.grant("prod/NopeAccess", requested_ttl=60, caller="agent")
    assert not res.decision.allowed
    assert res.credentials is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_broker.py -q`
Expected: FAIL, `ModuleNotFoundError: grantry.broker`.

- [ ] **Step 3: Implement broker.py**

```python
"""The broker composes a provider, the policy engine, and the audit log into a
single grant path. Nothing mints credentials except grant(), and grant() never
mints without an allow decision.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass

from grantry.audit import AuditLog
from grantry.identity import Identity
from grantry.policy import Decision, Policy
from grantry.providers.base import Credentials, InteractionHandler, Provider, Session
from grantry.secrets import SecretStore, token_name


class NoSessionError(Exception):
    pass


@dataclass(frozen=True)
class GrantResult:
    credentials: Credentials | None
    decision: Decision


class Broker:
    def __init__(
        self,
        provider: Provider,
        policy: Policy,
        audit: AuditLog,
        secrets: SecretStore,
        *,
        now: Callable[[], float] = time.time,
        clock_iso: Callable[[], str],
    ) -> None:
        self._provider = provider
        self._policy = policy
        self._audit = audit
        self._secrets = secrets
        self._now = now
        self._clock_iso = clock_iso

    def _start_url(self) -> str:
        # Providers carry their own start_url; the Protocol does not expose it,
        # so we read the attribute the AWS provider sets.
        return getattr(self._provider, "start_url")

    def login(self, handler: InteractionHandler) -> Session:
        session = self._provider.start_login(handler)
        self._secrets.put(
            token_name(self._start_url()),
            json.dumps(
                {
                    "start_url": session.start_url,
                    "region": session.region,
                    "access_token": session.access_token,
                    "expires_at": session.expires_at,
                }
            ),
        )
        return session

    def cached_session(self) -> Session | None:
        raw = self._secrets.get(token_name(self._start_url()))
        if not raw:
            return None
        data = json.loads(raw)
        if data["expires_at"] <= self._now():
            return None
        return Session(
            start_url=data["start_url"],
            region=data["region"],
            access_token=data["access_token"],
            expires_at=data["expires_at"],
        )

    def identities(self) -> list[Identity]:
        session = self.cached_session()
        if session is None:
            raise NoSessionError("no active session; run login first")
        return self._provider.list_identities(session)

    def grant(self, ident_key: str, requested_ttl: int, caller: str) -> GrantResult:
        session = self.cached_session()
        if session is None:
            raise NoSessionError("no active session; run login first")
        ident = next((i for i in self._provider.list_identities(session) if i.key == ident_key), None)
        if ident is None:
            unknown = Identity("unknown", *_split_key(ident_key))
            decision = Decision(False, f"unknown identity {ident_key!r}", None, 0)
            self._audit.record(caller, unknown, decision, at=self._clock_iso())
            return GrantResult(None, decision)
        decision = self._policy.evaluate(ident, requested_ttl, caller)
        self._audit.record(caller, ident, decision, at=self._clock_iso())
        if not decision.allowed:
            return GrantResult(None, decision)
        creds = self._provider.mint(session, ident, decision.capped_ttl)
        return GrantResult(creds, decision)


def _split_key(key: str) -> tuple[str, str]:
    if "/" in key:
        acct, role = key.split("/", 1)
        return acct, role
    return key, ""
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_broker.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Run the full suite + gate**

Run: `uv run pytest -q && uv run mypy && uv run ruff check .`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/grantry/broker.py tests/test_broker.py
git commit -m "feat: broker composing provider, policy, and audit into one grant path"
```

---

### Task 11: MCP server surface

**Files:**
- Create: `src/grantry/mcp_server.py`
- Create: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `Broker`, `GrantResult`, `NoSessionError` (Task 10), `parse_ttl`/`format_ttl` (Task 4).
- Produces:
  - `build_mcp(broker: Broker) -> Server` where `Server` is the `mcp` SDK server, registering tools:
    - `whoami()` -> text: active session start_url + expiry, or "no active session".
    - `list_identities()` -> text: the identity keys the caller could request (all listed; policy is enforced at grant time, and denials are visible there).
    - `get_credentials(identity: str, ttl: str = "15m")` -> text: on allow, the env-var block `AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_SESSION_TOKEN=... AWS_CREDENTIALS_EXPIRATION=...`; on deny, a one-line explanation with the policy reason (no credentials).
    - `check_access(identity: str)` -> text: whether policy would allow the identity for an agent, without minting.
  - `_render_credentials(result: GrantResult) -> str` and `_render_denied(result: GrantResult) -> str` as pure helpers so rendering is unit-testable without the MCP transport.
- The MCP callers are always `caller="agent"`.

- [ ] **Step 1: Write the failing test (pure render helpers + tool dispatch)**

`tests/test_mcp_server.py`:
```python
import time

from grantry.audit import AuditLog
from grantry.broker import Broker
from grantry.identity import Identity
from grantry.mcp_server import _render_credentials, _render_denied, handle_get_credentials
from grantry.policy import Decision, Policy
from grantry.providers.base import Credentials, Session
from grantry.secrets import SecretStore


class FakeProvider:
    start_url = "https://example.awsapps.com/start"
    region = "us-east-1"

    def name(self):
        return "aws"

    def start_login(self, handler):
        return Session(self.start_url, self.region, "tok", time.time() + 3600)

    def list_identities(self, session):
        return [Identity("111122223333", "prod", "ReadOnlyAccess"),
                Identity("111122223333", "prod", "AdminAccess")]

    def mint(self, session, ident, ttl):
        return Credentials("AKIA", "sec", "sess", 1893456000.0)


POLICY = """
agents:
  allow:
    - identity: "*/ReadOnlyAccess"
  deny:
    - identity: "*/*Admin*"
  max_ttl: 15m
"""


def broker(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    p = tmp_path / "policy.yaml"
    p.write_text(POLICY)
    b = Broker(FakeProvider(), Policy.load(p), AuditLog(), SecretStore(),
               now=lambda: 1000.0, clock_iso=lambda: "2026-07-15T10:00:00Z")

    class H:
        def on_verification(self, uri, code): ...
        def wait(self): ...

    b.login(H())
    return b


def test_render_credentials_env_block():
    from grantry.broker import GrantResult
    res = GrantResult(Credentials("AKIA", "sec", "sess", 1893456000.0),
                      Decision(True, "ok", "*/ReadOnlyAccess", 900))
    out = _render_credentials(res)
    assert "AWS_ACCESS_KEY_ID=AKIA" in out
    assert "AWS_SECRET_ACCESS_KEY=sec" in out
    assert "AWS_SESSION_TOKEN=sess" in out


def test_render_denied_has_reason_no_secret():
    from grantry.broker import GrantResult
    res = GrantResult(None, Decision(False, "denied by deny rule '*/*Admin*'", "*/*Admin*", 0))
    out = _render_denied(res)
    assert "denied" in out.lower()
    assert "sec" not in out and "AKIA" not in out


def test_get_credentials_tool_allow(tmp_path, monkeypatch):
    b = broker(tmp_path, monkeypatch)
    out = handle_get_credentials(b, "prod/ReadOnlyAccess", "1h")
    assert "AWS_ACCESS_KEY_ID=AKIA" in out
    # 1h requested but policy caps at 15m; minted anyway, credentials present


def test_get_credentials_tool_deny(tmp_path, monkeypatch):
    b = broker(tmp_path, monkeypatch)
    out = handle_get_credentials(b, "prod/AdminAccess", "15m")
    assert "AWS_ACCESS_KEY_ID" not in out
    assert "denied" in out.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_mcp_server.py -q`
Expected: FAIL, `ModuleNotFoundError: grantry.mcp_server`.

- [ ] **Step 3: Implement mcp_server.py**

```python
"""The MCP surface. Every caller here is an agent, so policy is enforced with
caller="agent". Rendering helpers are pure so they can be tested without the
MCP transport.
"""

from __future__ import annotations

from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from grantry.broker import Broker, GrantResult, NoSessionError
from grantry.ttl import parse_ttl


def _render_credentials(result: GrantResult) -> str:
    c = result.credentials
    assert c is not None
    return (
        f"AWS_ACCESS_KEY_ID={c.access_key_id}\n"
        f"AWS_SECRET_ACCESS_KEY={c.secret_access_key}\n"
        f"AWS_SESSION_TOKEN={c.session_token}\n"
        f"AWS_CREDENTIALS_EXPIRATION={c.expiration}"
    )


def _render_denied(result: GrantResult) -> str:
    return f"Denied: {result.decision.reason}. No credentials were issued."


def handle_get_credentials(broker: Broker, identity: str, ttl: str) -> str:
    try:
        seconds = parse_ttl(ttl)
    except ValueError as e:
        return f"Invalid ttl: {e}"
    try:
        result = broker.grant(identity, seconds, caller="agent")
    except NoSessionError:
        return "No active AWS session. Ask a human to run 'grantry login' or call request_login."
    if result.credentials is None:
        return _render_denied(result)
    return _render_credentials(result)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_mcp(broker: Broker) -> FastMCP:
    mcp = FastMCP("grantry")

    @mcp.tool()
    def whoami() -> str:
        """Report the active AWS session and its expiry."""
        session = broker.cached_session()
        if session is None:
            return "No active session."
        return f"Session for {session.start_url} (region {session.region})."

    @mcp.tool()
    def list_identities() -> str:
        """List the account/role identities available through Identity Center."""
        try:
            idents = broker.identities()
        except NoSessionError:
            return "No active session. Ask a human to run 'grantry login'."
        return "\n".join(sorted(i.key for i in idents)) or "No identities available."

    @mcp.tool()
    def get_credentials(identity: str, ttl: str = "15m") -> str:
        """Mint short-lived AWS credentials for an identity, subject to policy."""
        return handle_get_credentials(broker, identity, ttl)

    @mcp.tool()
    def check_access(identity: str) -> str:
        """Report whether policy would allow this identity for an agent, without minting."""
        try:
            idents = broker.identities()
        except NoSessionError:
            return "No active session."
        match = next((i for i in idents if i.key == identity), None)
        if match is None:
            return f"Unknown identity {identity!r}."
        decision = broker._policy.evaluate(match, parse_ttl("15m"), caller="agent")
        verdict = "ALLOWED" if decision.allowed else "DENIED"
        return f"{verdict}: {decision.reason}"

    return mcp
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_mcp_server.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Full gate**

Run: `uv run pytest -q && uv run mypy && uv run ruff check .`
Expected: all green. (If mypy flags `broker._policy` access in `check_access`, add a public `Broker.would_allow(identity, caller)` method and call that instead; update the test accordingly.)

- [ ] **Step 6: Commit**

```bash
git add src/grantry/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: MCP server surface (whoami, list_identities, get_credentials, check_access)"
```

---

### Task 12: Minimal CLI entry and end-to-end wiring test

**Files:**
- Create: `src/grantry/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything. `configure_logging` (Task 7), `AwsProvider` (Task 9), `Broker` (Task 10), `build_mcp` (Task 11), `Policy`, `AuditLog`, `SecretStore`, `state_path`.
- Produces:
  - `main(argv: list[str] | None = None) -> int` — an argparse CLI with subcommands: `login` (device flow, prints the verification URL and code, waits for Enter), `ls` (print identity keys), `audit` (print the audit log), `mcp` (run the MCP server over stdio). Reads `GRANTRY_SSO_START_URL` and `GRANTRY_SSO_REGION` (the only two env vars needed to point at an instance) or `--start-url`/`--region`.
  - `build_broker(start_url: str, region: str) -> Broker` — the composition root, reused by every subcommand and the test.
- A `TerminalHandler` implementing `InteractionHandler` that prints the URL/code and blocks on `input()`.

- [ ] **Step 1: Write the failing wiring test**

`tests/test_cli.py`:
```python
from grantry.cli import build_broker
from grantry.providers.aws import AwsProvider


def test_build_broker_wires_aws_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    (tmp_path / "policy.yaml").write_text("agents:\n  max_ttl: 15m\n")
    broker = build_broker("https://example.awsapps.com/start", "us-east-1")
    assert isinstance(broker._provider, AwsProvider)
    # No session yet: cached_session is None.
    assert broker.cached_session() is None


def test_main_ls_without_session_reports_cleanly(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    monkeypatch.setenv("GRANTRY_SSO_START_URL", "https://example.awsapps.com/start")
    monkeypatch.setenv("GRANTRY_SSO_REGION", "us-east-1")
    from grantry.cli import main
    rc = main(["ls"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "login" in out.lower()  # tells the user to log in
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cli.py -q`
Expected: FAIL, `ModuleNotFoundError: grantry.cli`.

- [ ] **Step 3: Implement cli.py**

```python
"""The human CLI and the composition root. Thin over the broker."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from grantry.audit import AuditLog
from grantry.broker import Broker, NoSessionError
from grantry.logging_setup import configure_logging
from grantry.mcp_server import build_mcp
from grantry.policy import Policy
from grantry.providers.aws import AwsProvider
from grantry.providers.base import InteractionHandler
from grantry.secrets import SecretStore
from grantry.config import state_path


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TerminalHandler(InteractionHandler):
    def on_verification(self, verification_uri: str, user_code: str) -> None:
        print(f"To authorize, open:\n  {verification_uri}\nand confirm the code: {user_code}")

    def wait(self) -> None:
        try:
            input("Press Enter after you have approved in the browser... ")
        except EOFError:
            pass


def build_broker(start_url: str, region: str) -> Broker:
    provider = AwsProvider(start_url, region)
    policy = Policy.load(state_path("policy.yaml"))
    return Broker(provider, policy, AuditLog(), SecretStore(), clock_iso=_iso_now)


def _instance(args: argparse.Namespace) -> tuple[str, str]:
    start = args.start_url or os.environ.get("GRANTRY_SSO_START_URL")
    region = args.region or os.environ.get("GRANTRY_SSO_REGION")
    if not start or not region:
        raise SystemExit(
            "Set --start-url and --region, or GRANTRY_SSO_START_URL and GRANTRY_SSO_REGION."
        )
    return start, region


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="grantry")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    parser.add_argument("--start-url", default=None)
    parser.add_argument("--region", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login")
    sub.add_parser("ls")
    sub.add_parser("audit")
    sub.add_parser("mcp")

    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    if args.command == "audit":
        for e in AuditLog().entries():
            verdict = "allow" if e["allowed"] else "deny"
            print(f"{e['at']} {e['caller']} {e['identity']} {verdict} ({e['reason']})")
        return 0

    start, region = _instance(args)
    broker = build_broker(start, region)

    if args.command == "login":
        session = broker.login(TerminalHandler())
        print(f"Logged in to {session.start_url}.")
        return 0

    if args.command == "ls":
        try:
            idents = broker.identities()
        except NoSessionError:
            print("No active session. Run 'grantry login' first.")
            return 1
        for i in sorted(idents, key=lambda x: x.key):
            print(i.key)
        return 0

    if args.command == "mcp":
        build_mcp(broker).run()
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_cli.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Full gate**

Run: `uv run pytest -q && uv run mypy && uv run ruff check . && uv run ruff format --check .`
Expected: all green. Run `uv run ruff format .` first if the format check fails, then re-run.

- [ ] **Step 6: Commit**

```bash
git add src/grantry/cli.py tests/test_cli.py
git commit -m "feat: human CLI (login, ls, audit, mcp) and composition root"
```

---

### Task 13: Full-slice E2E — login to grant over the fake server

**Files:**
- Create: `tests/test_e2e_slice.py`

**Interfaces:**
- Consumes: `build_broker` pattern, `AwsProvider` with an injected `client_factory`, `FakeSSO`, `Broker`, `handle_get_credentials`.
- Produces: one test proving the whole slice: device-flow login through the fake server, then an agent `get_credentials` call that policy allows returns a real env block, and one it denies returns no secret and audits the denial.

- [ ] **Step 1: Write the end-to-end test**

`tests/test_e2e_slice.py`:
```python
import botocore.session

from grantry.audit import AuditLog
from grantry.broker import Broker
from grantry.mcp_server import handle_get_credentials
from grantry.policy import Policy
from grantry.providers.aws import AwsProvider
from grantry.secrets import SecretStore
from tests.fakes.fake_sso import FakeSSO

POLICY = """
agents:
  allow:
    - identity: "*/ReadOnlyAccess"
  deny:
    - identity: "*/*PowerUser*"
  max_ttl: 15m
"""


class H:
    def on_verification(self, uri, code): ...
    def wait(self): ...


def factory_for(endpoint):
    def factory(service_name, region_name):
        s = botocore.session.Session()
        return s.create_client(service_name, region_name=region_name, endpoint_url=endpoint,
                               aws_access_key_id="x", aws_secret_access_key="y")
    return factory


def test_login_then_agent_grant_allow_and_deny(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    (tmp_path / "policy.yaml").write_text(POLICY)

    with FakeSSO() as fake:
        provider = AwsProvider("https://example.awsapps.com/start", "us-east-1",
                               client_factory=factory_for(fake.endpoint), poll_interval=0)
        broker = Broker(provider, Policy.load(tmp_path / "policy.yaml"),
                        AuditLog(), SecretStore(), clock_iso=lambda: "2026-07-15T10:00:00Z")
        broker.login(H())

        allowed = handle_get_credentials(broker, "prod/ReadOnlyAccess", "1h")
        assert "AWS_ACCESS_KEY_ID=AKIAFAKE" in allowed
        assert "AWS_SESSION_TOKEN=faketoken" in allowed

        denied = handle_get_credentials(broker, "prod/AWSPowerUserAccess", "15m")
        assert "AWS_ACCESS_KEY_ID" not in denied
        assert "denied" in denied.lower()

        audit = AuditLog().entries()
        assert audit[-1]["allowed"] is False
        assert audit[-1]["identity"] == "prod/AWSPowerUserAccess"
        assert audit[-2]["allowed"] is True
```

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/test_e2e_slice.py -q`
Expected: `1 passed`.

- [ ] **Step 3: Full suite + gate one last time**

Run: `uv run pytest -q && uv run mypy && uv run ruff check . && uv run ruff format --check .`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e_slice.py
git commit -m "test: full-slice E2E from device-flow login to policed agent grant"
```

---

### Task 14: README and example policy

**Files:**
- Modify: `README.md`
- Create: `examples/policy.yaml`

**Interfaces:** none (docs).

- [ ] **Step 1: Write examples/policy.yaml**

```yaml
# grantry policy: what agents and humans may do.
# Deny beats allow. An identity matched by no rule is denied for agents,
# allowed for humans. TTLs are capped to each section's max_ttl.
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

- [ ] **Step 2: Write README.md**

Cover: what grantry is (one paragraph, agent-era credential broker, fully local), install (`uvx grantry` / `pipx install grantry`), the two env vars (`GRANTRY_SSO_START_URL`, `GRANTRY_SSO_REGION`), the four commands (`login`, `ls`, `audit`, `mcp`), how to wire the `mcp` subcommand into an MCP client, the policy file with the example, and the security stance (keychain only, no plaintext secrets, no network beyond AWS, audit log at `~/.grantry/audit.jsonl`). No em dashes.

- [ ] **Step 3: Commit**

```bash
git add README.md examples/policy.yaml
git commit -m "docs: README and example policy"
```

---

## Notes for the executor

- Run every command from the repo root `/Users/skiranmeda/sai-git/grantry`.
- If `uv run mypy` flags the `getattr(self._provider, "start_url")` in the broker or `broker._policy` in the MCP server, promote those to explicit public methods (`Provider.start_url` as a Protocol member, `Broker.would_allow`) rather than suppressing the error. Keep the tests aligned.
- The fake SSO server's paths (`/token`, `/device_authorization`, `/assignment/accounts`, `/federation/credentials`) mirror the real sso-oidc and sso endpoint shapes closely enough for botocore's request routing when `endpoint_url` is set; if a botocore version routes a differently-named path, print the failing request path from the fake handler and adjust the suffix check.
- This plan is Phase 1. The human `switch`/`run`/`populate` commands, the container-credentials endpoint, `request_login` blocking flow, and the Azure/GCP providers are later plans.
