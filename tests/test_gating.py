import json

from grantry.gating import (
    GATED_ENV,
    STEER_MARKER,
    append_steering,
    gating_plan,
    merge_env_claude,
    merge_env_vscode,
    steering_body,
    steering_mdc,
)


def test_gated_env_blanks_creds_and_marks_agent():
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
        assert GATED_ENV[k] == ""
    assert GATED_ENV["GRANTRY_CALLER"] == "agent"


def test_merge_env_claude_preserves_other_settings():
    out = merge_env_claude({"model": "opus", "env": {"KEEP": "1"}})
    assert out["model"] == "opus"
    assert out["env"]["KEEP"] == "1"  # existing env untouched
    assert out["env"]["AWS_PROFILE"] == ""
    assert out["env"]["GRANTRY_CALLER"] == "agent"


def test_merge_env_vscode_writes_all_three_os_keys():
    out = merge_env_vscode({"editor.fontSize": 14})
    assert out["editor.fontSize"] == 14
    for key in (
        "terminal.integrated.env.osx",
        "terminal.integrated.env.linux",
        "terminal.integrated.env.windows",
    ):
        assert out[key]["AWS_ACCESS_KEY_ID"] == ""
        assert out[key]["GRANTRY_CALLER"] == "agent"


def test_steering_carries_marker():
    assert STEER_MARKER in steering_body()
    assert STEER_MARKER in steering_mdc()
    assert steering_mdc().startswith("---\n")  # cursor frontmatter


def test_append_steering_is_idempotent():
    first, changed1 = append_steering("# My rules\n", steering_body())
    assert changed1
    assert STEER_MARKER in first
    assert first.startswith("# My rules")  # preserved existing content
    second, changed2 = append_steering(first, steering_body())
    assert not changed2
    assert second == first  # no duplicate block


def test_append_steering_into_empty():
    out, changed = append_steering("", steering_body())
    assert changed
    assert out.startswith(STEER_MARKER)


def test_gating_plan_claude_code():
    plan = gating_plan("claude-code")
    kinds = {a.kind: a.path for a in plan.actions}
    assert kinds["env-claude"] == ".claude/settings.json"
    assert kinds["steer-md"] == "CLAUDE.md"
    assert plan.note is None


def test_gating_plan_vscode_forks_use_terminal_env():
    for key in ("vscode", "cursor", "windsurf"):
        plan = gating_plan(key)
        assert any(a.kind == "env-vscode" for a in plan.actions), key


def test_gating_plan_copilot_cli_is_steer_only_with_note():
    plan = gating_plan("copilot-cli")
    assert [a.kind for a in plan.actions] == ["steer-md"]
    assert plan.note and "no file-writable shell" in plan.note


def test_gating_plan_claude_desktop_is_noop_with_note():
    plan = gating_plan("claude-desktop")
    assert plan.actions == ()
    assert plan.note and "no shell tool" in plan.note


def test_install_gated_writes_project_files(tmp_path, monkeypatch, capsys):
    from grantry.cli import main

    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "fakehome"))
    monkeypatch.chdir(tmp_path)

    rc = main(["install", "claude-code", "--gated"])
    assert rc == 0

    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert settings["env"]["AWS_ACCESS_KEY_ID"] == ""
    assert settings["env"]["GRANTRY_CALLER"] == "agent"
    claude_md = (tmp_path / "CLAUDE.md").read_text()
    assert STEER_MARKER in claude_md

    # Re-running is idempotent: no duplicated steering block.
    rc2 = main(["install", "claude-code", "--gated"])
    assert rc2 == 0
    assert (tmp_path / "CLAUDE.md").read_text().count(STEER_MARKER) == 1


def test_install_without_gated_writes_no_project_files(tmp_path, monkeypatch):
    from grantry.cli import main

    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "fakehome"))
    monkeypatch.chdir(tmp_path)

    rc = main(["install", "claude-code"])
    assert rc == 0
    assert not (tmp_path / ".claude" / "settings.json").exists()
    assert not (tmp_path / "CLAUDE.md").exists()
