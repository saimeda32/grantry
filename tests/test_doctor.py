from grantry.doctor import Check, completion_check, exit_code, render, version_check


def test_version_check_states():
    assert version_check("0.13.0", "0.13.0").level == "ok"
    behind = version_check("0.12.0", "0.13.0")
    assert behind.level == "warn" and "0.13.0" in behind.detail and "pipx upgrade" in behind.detail
    unknown = version_check("0.13.0", None)
    assert unknown.level == "warn" and "could not reach PyPI" in unknown.detail


def test_completion_check_three_states():
    active = completion_check("zsh", rc_has_line=True, loaded=True)
    assert active.level == "ok" and "active" in active.detail

    not_reloaded = completion_check("zsh", rc_has_line=True, loaded=False)
    assert not_reloaded.level == "warn" and "exec zsh" in not_reloaded.detail

    not_installed = completion_check("zsh", rc_has_line=False, loaded=False)
    assert not_installed.level == "warn" and "completion --install" in not_installed.detail

    unknown_shell = completion_check(None, rc_has_line=False, loaded=False)
    assert unknown_shell.level == "warn"


def test_exit_code_fails_only_on_hard_failure():
    assert exit_code([Check("ok", "a", ""), Check("warn", "b", "")]) == 0
    assert exit_code([Check("ok", "a", ""), Check("fail", "b", "")]) == 1


def test_render_aligns_and_uses_icons():
    out = render([Check("ok", "version", "x"), Check("fail", "session", "y")])
    assert "✓ version" in out
    assert "✗ session" in out


def test_cmd_doctor_reports_no_instance_as_failure(tmp_path, monkeypatch, capsys):
    from grantry.cli import main

    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    # Keep the network out: force the version check to a known value.
    import grantry.version_check as vc

    monkeypatch.setattr(vc, "fetch_latest", lambda *a, **k: "0.0.0")

    rc = main(["doctor"])
    out = capsys.readouterr().out
    assert rc == 1  # no instance configured -> hard failure
    assert "instance" in out and "session" in out and "completion" in out
