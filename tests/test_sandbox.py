from grantry.cli import main

_AMBIENT = [
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
]


def _clean_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("GRANTRY_CALLER", "agent")
    for name in _AMBIENT:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("AWS_CONFIG_FILE", raising=False)
    monkeypatch.delenv("AWS_SHARED_CREDENTIALS_FILE", raising=False)


def test_sandbox_clean_passes(tmp_path, monkeypatch, capsys):
    _clean_env(monkeypatch, tmp_path)
    rc = main(["check", "--sandbox"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "passed" in out.lower()


def test_sandbox_flags_missing_caller_marker(tmp_path, monkeypatch, capsys):
    _clean_env(monkeypatch, tmp_path)
    monkeypatch.delenv("GRANTRY_CALLER", raising=False)  # the only gap
    rc = main(["check", "--sandbox"])
    out = capsys.readouterr().out
    assert rc == 211
    assert "GRANTRY_CALLER" in out


def test_sandbox_detects_env_credentials(tmp_path, monkeypatch, capsys):
    _clean_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
    rc = main(["check", "--sandbox"])
    out = capsys.readouterr().out
    assert rc == 211
    assert "AWS_ACCESS_KEY_ID" in out


def test_sandbox_detects_populated_profiles(tmp_path, monkeypatch, capsys):
    _clean_env(monkeypatch, tmp_path)
    cfg = tmp_path / "config"
    cfg.write_text("[profile dev]\ngrantry_managed = true\n")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(cfg))
    rc = main(["check", "--sandbox"])
    out = capsys.readouterr().out
    assert rc == 211
    assert "gate" in out.lower()
