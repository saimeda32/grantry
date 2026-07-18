import pytest

from grantry.completion import SHELLS, completion_script
from grantry.idcache import read_keys, write_cache
from grantry.identity import Identity


@pytest.mark.parametrize("shell", SHELLS)
def test_completion_script_is_nonempty_and_names_grantry(shell):
    out = completion_script(shell)
    assert "grantry" in out
    # every shell script wires identity completion through the hidden command
    assert "_complete-identities" in out


def test_completion_script_lists_core_subcommands():
    out = completion_script("bash")
    for cmd in ("login", "run", "switch", "console", "install", "completion"):
        assert cmd in out


@pytest.mark.parametrize("shell", SHELLS)
def test_completion_handles_identity_flags(shell):
    # --as / --identity / --profile must trigger identity completion (so
    # 'admin assignments --as <TAB>' works, not just the positional commands).
    out = completion_script(shell)
    # fish spells long options as "-l as"; bash/zsh use "--as".
    flags = (
        ("-l as", "-l identity", "-l profile")
        if shell == "fish"
        else ("--as", "--identity", "--profile")
    )
    for flag in flags:
        assert flag in out


def test_unknown_shell_raises():
    with pytest.raises(KeyError):
        completion_script("powershell")


def test_idcache_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    write_cache(
        [
            Identity("1", "acme-dev", "AWSReadOnlyAccess"),
            Identity("2", "acme-prod", "AWSPowerUserAccess"),
        ]
    )
    keys = read_keys()
    assert keys == ["acme-dev.AWSReadOnlyAccess", "acme-prod.AWSPowerUserAccess"]


def test_idcache_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    assert read_keys() == []


def test_idcache_corrupt_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    (tmp_path / "identities.json").write_text("{not json", encoding="utf-8")
    assert read_keys() == []
