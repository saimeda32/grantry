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
