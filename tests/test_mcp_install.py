from typing import Any

from grantry.mcp_install import CLIENTS, merge_server, server_entry


def test_server_entry_includes_label_and_instance():
    entry = server_entry(
        "py", ["-m", "grantry", "mcp"], "cursor", "https://mlp.awsapps.com/start", "us-east-1"
    )
    assert entry["command"] == "py"
    assert entry["args"] == ["-m", "grantry", "mcp"]
    assert entry["env"]["GRANTRY_AGENT_LABEL"] == "cursor"
    assert entry["env"]["GRANTRY_SSO_START_URL"] == "https://mlp.awsapps.com/start"
    assert entry["env"]["GRANTRY_SSO_REGION"] == "us-east-1"


def test_server_entry_omits_instance_when_unknown():
    entry = server_entry("py", [], "claude-code", None, None)
    assert "GRANTRY_SSO_START_URL" not in entry["env"]


def test_merge_adds_without_clobbering_others():
    config: dict[str, Any] = {"mcpServers": {"other": {"command": "x"}}, "unrelated": True}
    entry = {"command": "py", "args": [], "env": {}}
    out = merge_server(config, "mcpServers", "grantry", entry)
    assert out["mcpServers"]["other"] == {"command": "x"}  # preserved
    assert out["mcpServers"]["grantry"] == entry  # added
    assert out["unrelated"] is True  # top-level preserved
    # original not mutated
    assert "grantry" not in config["mcpServers"]


def test_merge_updates_existing_grantry():
    config = {"mcpServers": {"grantry": {"command": "old"}}}
    entry = {"command": "new", "args": [], "env": {}}
    out = merge_server(config, "mcpServers", "grantry", entry)
    assert out["mcpServers"]["grantry"] == entry


def test_merge_creates_root_when_absent():
    out = merge_server({}, "servers", "grantry", {"command": "py"})
    assert out["servers"]["grantry"] == {"command": "py"}


def test_registry_has_the_common_clients():
    assert {"claude-code", "claude-desktop", "cursor", "windsurf", "vscode"} <= set(CLIENTS)
    assert CLIENTS["vscode"].root == "servers"  # VS Code uses "servers"


def test_install_command_writes_and_preserves(tmp_path, monkeypatch):
    import json

    from grantry.cli import _cmd_install

    # Point Cursor's config at a temp file with an existing server.
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    monkeypatch.setitem(
        CLIENTS, "cursor", CLIENTS["cursor"].__class__("cursor", "Cursor", str(cfg), "mcpServers")
    )
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))

    code = _cmd_install(["cursor"], dry_run=False)
    assert code == 0
    written = json.loads(cfg.read_text())
    assert written["mcpServers"]["other"] == {"command": "x"}  # preserved
    assert "grantry" in written["mcpServers"]
    assert written["mcpServers"]["grantry"]["env"]["GRANTRY_AGENT_LABEL"] == "cursor"


def test_install_dry_run_writes_nothing(tmp_path, monkeypatch):
    import json

    from grantry.cli import _cmd_install

    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {}}))
    before = cfg.read_text()
    monkeypatch.setitem(
        CLIENTS, "cursor", CLIENTS["cursor"].__class__("cursor", "Cursor", str(cfg), "mcpServers")
    )
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))

    code = _cmd_install(["cursor"], dry_run=True)
    assert code == 0
    assert cfg.read_text() == before


def test_install_unknown_client_errors(tmp_path, monkeypatch):
    from grantry.cli import _cmd_install

    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    assert _cmd_install(["nope"], dry_run=False) == 2


def test_remove_server():
    from grantry.mcp_install import remove_server

    config = {"mcpServers": {"grantry": {"command": "x"}, "other": {"command": "y"}}}
    updated, present = remove_server(config, "mcpServers", "grantry")
    assert present is True
    assert "grantry" not in updated["mcpServers"]
    assert updated["mcpServers"]["other"] == {"command": "y"}
    # removing when absent reports False
    _, present2 = remove_server({"mcpServers": {}}, "mcpServers", "grantry")
    assert present2 is False
