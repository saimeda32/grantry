from grantry.admin import Assignment
from grantry.snapshots import diff_assignments, latest_snapshot, save_snapshot


def a(principal, ps, acct_id, acct_name="acct", ptype="GROUP"):
    return Assignment(ptype, f"{principal}-id", principal, ps, acct_id, acct_name)


def test_diff_added_and_removed():
    old = [a("Platform", "ReadOnly", "111"), a("Security", "Audit", "222")]
    new = [a("Platform", "ReadOnly", "111"), a("Data", "Admin", "333")]
    added, removed = diff_assignments(old, new)
    assert [x.principal_name for x in added] == ["Data"]
    assert [x.principal_name for x in removed] == ["Security"]


def test_diff_no_change():
    rows = [a("Platform", "ReadOnly", "111")]
    added, removed = diff_assignments(rows, list(rows))
    assert added == [] and removed == []


def test_save_and_load_latest_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    rows = [a("Platform", "ReadOnly", "111"), a("Data", "Admin", "333")]
    save_snapshot(rows, "2026-07-16T01-00-00Z")
    loaded = latest_snapshot()
    assert loaded is not None
    assert {r.principal_name for r in loaded} == {"Platform", "Data"}


def test_latest_picks_most_recent(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    save_snapshot([a("Old", "ReadOnly", "1")], "2026-07-16T01-00-00Z")
    save_snapshot([a("New", "ReadOnly", "1")], "2026-07-16T02-00-00Z")
    loaded = latest_snapshot()
    assert loaded is not None
    assert loaded[0].principal_name == "New"


def test_latest_none_when_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    assert latest_snapshot() is None
