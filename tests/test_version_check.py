from grantry import version_check as vc


def test_is_newer():
    assert vc.is_newer("0.14.0", "0.13.0")
    assert vc.is_newer("0.13.1", "0.13.0")
    assert vc.is_newer("1.0.0", "0.13.0")
    assert not vc.is_newer("0.13.0", "0.13.0")
    assert not vc.is_newer("0.12.9", "0.13.0")


def test_parse_is_tolerant():
    assert vc._parse("0.13.0") == (0, 13, 0)
    assert vc._parse("1.2") == (1, 2)
    assert vc._parse("1.0.0rc2") == (1, 0, 0)  # suffix truncated to leading digits


def test_cached_latest_fetches_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return "0.14.0"

    assert vc.cached_latest(fetch=fetch, now=lambda: 1000.0) == "0.14.0"
    assert calls["n"] == 1
    # Within the TTL the cached value is served without another fetch.
    assert vc.cached_latest(fetch=fetch, now=lambda: 1000.0 + 3600) == "0.14.0"
    assert calls["n"] == 1


def test_cached_latest_refetches_after_ttl(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    seq = iter(["0.14.0", "0.15.0"])

    def fetch():
        return next(seq)

    assert vc.cached_latest(fetch=fetch, now=lambda: 0.0) == "0.14.0"
    # A day later, it re-fetches.
    assert vc.cached_latest(fetch=fetch, now=lambda: 90_000.0) == "0.15.0"


def test_cached_latest_keeps_last_good_on_failed_fetch(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    assert vc.cached_latest(fetch=lambda: "0.14.0", now=lambda: 0.0) == "0.14.0"
    # A day later the fetch fails; the last known good value is retained.
    assert vc.cached_latest(fetch=lambda: None, now=lambda: 90_000.0) == "0.14.0"


def test_nudge_only_when_newer(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    monkeypatch.delenv("GRANTRY_NO_UPDATE_CHECK", raising=False)
    msg = vc.nudge("0.13.0", fetch=lambda: "0.14.0", now=lambda: 0.0)
    assert msg and "0.14.0" in msg and "pipx upgrade grantry" in msg
    assert vc.nudge("0.14.0", fetch=lambda: "0.14.0", now=lambda: 1.0) is None


def test_nudge_silenced_by_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    monkeypatch.setenv("GRANTRY_NO_UPDATE_CHECK", "1")
    called = {"n": 0}

    def fetch():
        called["n"] += 1
        return "9.9.9"

    assert vc.nudge("0.13.0", fetch=fetch) is None
    assert called["n"] == 0  # opt-out short-circuits before any fetch
