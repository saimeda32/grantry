import json
import stat
import sys

from grantry.audit import AuditLog
from grantry.identity import Identity
from grantry.policy import Decision

POSIX = not sys.platform.startswith("win")


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
    assert e["identity"] == "prod.ReadOnlyAccess"
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
    if POSIX:  # Windows does not use POSIX file modes
        mode = stat.S_IMODE((tmp_path / "audit.jsonl").stat().st_mode)
        assert mode == 0o600


def test_appends(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    log = AuditLog()
    for i in range(3):
        log.record("a", Identity("1", "p", "R"), Decision(True, "ok", "r", 60), at=f"t{i}")
    assert len(log.entries()) == 3
    for line in (tmp_path / "audit.jsonl").read_text().splitlines():
        json.loads(line)
