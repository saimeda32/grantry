import time

from grantry.audit import AuditLog
from grantry.broker import Broker
from grantry.cli import _cmd_populate, _cmd_run, _cmd_switch, build_broker, main
from grantry.identity import Identity
from grantry.policy import Policy
from grantry.providers.aws import AwsProvider
from grantry.providers.base import Credentials, Session
from grantry.secrets import SecretStore


def test_build_broker_wires_aws_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    (tmp_path / "policy.yaml").write_text("agents:\n  max_ttl: 15m\n")
    broker = build_broker("https://example.awsapps.com/start", "us-east-1")
    assert isinstance(broker._provider, AwsProvider)
    assert broker.cached_session() is None


def test_main_ls_without_session_reports_cleanly(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    monkeypatch.setenv("GRANTRY_SSO_START_URL", "https://example.awsapps.com/start")
    monkeypatch.setenv("GRANTRY_SSO_REGION", "us-east-1")
    rc = main(["ls"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "login" in out.lower()


def test_instance_is_remembered_after_first_use(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    monkeypatch.delenv("GRANTRY_SSO_START_URL", raising=False)
    monkeypatch.delenv("GRANTRY_SSO_REGION", raising=False)
    from grantry.instance import load_instance

    # First run supplies the instance via flags; it should be remembered.
    main(["--start-url", "https://acme.awsapps.com/start", "--region", "us-east-1", "ls"])
    saved = load_instance()
    assert saved is not None
    assert saved.start_url == "https://acme.awsapps.com/start"
    assert saved.region == "us-east-1"

    # A later run with no flags and no env must still resolve (from the saved file).
    rc = main(["ls"])
    assert rc == 1  # no session yet, but it did NOT raise "no instance known"


def test_no_instance_anywhere_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    monkeypatch.delenv("GRANTRY_SSO_START_URL", raising=False)
    monkeypatch.delenv("GRANTRY_SSO_REGION", raising=False)
    import pytest

    with pytest.raises(SystemExit):
        main(["ls"])


class FakeProvider:
    start_url = "https://acme.awsapps.com/start"
    region = "us-east-1"

    def name(self):
        return "aws"

    def start_login(self, handler):
        return Session(self.start_url, self.region, "tok", time.time() + 3600)

    def refresh(self, session):
        return session

    def list_identities(self, session):
        return [
            Identity("111122223333", "prod", "ReadOnlyAccess"),
            Identity("444455556666", "dev-pay", "AWSPowerUserAccess"),
        ]

    def mint(self, session, ident, ttl):
        return Credentials("AKIA", "sec", "sess", time.time() + 3600)


def _fake_broker(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    (tmp_path / "policy.yaml").write_text("humans:\n  max_ttl: 12h\n")
    b = Broker(
        FakeProvider(),
        Policy.load(tmp_path / "policy.yaml"),
        AuditLog(),
        SecretStore(),
        clock_iso=lambda: "t",
    )

    class H:
        def on_verification(self, uri, code): ...
        def wait(self): ...

    b.login(H())
    return b


def _login_env(tmp_path, monkeypatch):
    import grantry.cli as climod

    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    monkeypatch.setenv("GRANTRY_SSO_START_URL", "https://acme.awsapps.com/start")
    monkeypatch.setenv("GRANTRY_SSO_REGION", "us-east-1")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))
    monkeypatch.delenv("GRANTRY_NO_POPULATE", raising=False)
    (tmp_path / "policy.yaml").write_text("humans:\n  max_ttl: 12h\n")

    def fake_build(start, region):
        return Broker(
            FakeProvider(),
            Policy.load(tmp_path / "policy.yaml"),
            AuditLog(),
            SecretStore(),
            clock_iso=lambda: "t",
        )

    monkeypatch.setattr(climod, "build_broker", fake_build)


def test_login_warms_completion_cache(tmp_path, monkeypatch, capsys):
    from grantry.idcache import read_keys

    _login_env(tmp_path, monkeypatch)
    rc = main(["login"])
    assert rc == 0
    keys = read_keys()
    assert "prod/ReadOnlyAccess" in keys
    assert "dev-pay/AWSPowerUserAccess" in keys


def test_login_populates_aws_config(tmp_path, monkeypatch, capsys):
    _login_env(tmp_path, monkeypatch)
    rc = main(["login"])
    assert rc == 0
    body = (tmp_path / "config").read_text()
    assert "[profile prod.ReadOnlyAccess]" in body
    assert "[profile dev-pay.AWSPowerUserAccess]" in body


def test_login_no_populate_skips_config_but_warms_cache(tmp_path, monkeypatch, capsys):
    from grantry.idcache import read_keys

    _login_env(tmp_path, monkeypatch)
    rc = main(["login", "--no-populate"])
    assert rc == 0
    assert not (tmp_path / "config").exists()  # no profiles written
    assert "prod/ReadOnlyAccess" in read_keys()  # cache still warmed


def test_main_handles_keyboard_interrupt(monkeypatch, capsys):
    import grantry.cli as climod

    def boom(argv):
        raise KeyboardInterrupt

    monkeypatch.setattr(climod, "_run", boom)
    rc = climod.main(["version"])
    err = capsys.readouterr().err
    assert rc == 130
    assert "Cancelled" in err


def test_login_handler_auto_opens_browser(monkeypatch):
    import webbrowser

    from grantry.cli import TerminalHandler

    opened = []

    def fake_open(url):
        opened.append(url)
        return True

    monkeypatch.setattr(webbrowser, "open", fake_open)
    monkeypatch.delenv("GRANTRY_NO_BROWSER", raising=False)
    url = "https://x.awsapps.com/start/#/device?user_code=AB-CD"
    TerminalHandler().on_verification(url, "AB-CD")
    assert opened == [url]


def test_login_handler_respects_no_browser(monkeypatch, capsys):
    import webbrowser

    from grantry.cli import TerminalHandler

    opened = []

    def fake_open(url):
        opened.append(url)
        return True

    monkeypatch.setattr(webbrowser, "open", fake_open)
    monkeypatch.setenv("GRANTRY_NO_BROWSER", "1")
    TerminalHandler().on_verification("https://x/verify?code=AB", "AB")
    out = capsys.readouterr().out
    assert opened == []
    assert "AB" in out  # falls back to printing the code to type


def test_run_executes_command_with_credentials(tmp_path, monkeypatch, capfd):
    b = _fake_broker(tmp_path, monkeypatch)
    # Print one of the injected env vars from the child to prove it is set.
    # capfd (not capsys) captures the child process's real stdout fd.
    code = _cmd_run(
        b,
        "us-east-1",
        "prod/ReadOnlyAccess",
        "1h",
        ["--", "python", "-c", "import os;print(os.environ['AWS_ACCESS_KEY_ID'])"],
    )
    out = capfd.readouterr().out
    assert code == 0
    assert "AKIA" in out


def test_cli_caller_resolution(monkeypatch):
    from grantry.cli import _cli_caller

    monkeypatch.delenv("GRANTRY_CALLER", raising=False)
    assert _cli_caller() == "human"
    assert _cli_caller("agent") == "agent"
    assert _cli_caller("human") == "human"
    monkeypatch.setenv("GRANTRY_CALLER", "agent")
    assert _cli_caller() == "agent"
    assert _cli_caller("human") == "human"  # an explicit flag still wins


def test_run_as_human_is_allowed_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("GRANTRY_CALLER", raising=False)
    b = _fake_broker(tmp_path, monkeypatch)  # policy has no agents allow rules
    code = _cmd_run(b, "us-east-1", "prod/ReadOnlyAccess", "1h", ["--", "true"])
    assert code == 0  # humans section is default-allow


def test_run_with_agent_env_is_denied_by_policy(tmp_path, monkeypatch, capsys):
    # The escalation the security review flagged: an agent with a shell running
    # 'grantry run <anything>' must NOT get the human default-allow when the env
    # marks it as an agent. With no agents allow rules, this is denied.
    b = _fake_broker(tmp_path, monkeypatch)
    monkeypatch.setenv("GRANTRY_CALLER", "agent")
    code = _cmd_run(b, "us-east-1", "prod/ReadOnlyAccess", "1h", ["--", "true"])
    out = capsys.readouterr().out
    assert code == 1
    assert "Denied" in out


def test_credential_process_agent_env_is_denied(tmp_path, monkeypatch, capsys):
    from grantry.cli import _cmd_credential_process

    b = _fake_broker(tmp_path, monkeypatch)
    monkeypatch.setenv("GRANTRY_CALLER", "agent")
    code = _cmd_credential_process(b, "prod/ReadOnlyAccess", "1h", None)
    err = capsys.readouterr().err
    assert code == 1
    assert "Denied" in err


def test_run_dot_profile_name_resolves(tmp_path, monkeypatch, capfd):
    # A name copied from ~/.aws/config (account.role, dot form) must resolve to
    # the same identity as the account/role slash form.
    b = _fake_broker(tmp_path, monkeypatch)
    code = _cmd_run(
        b,
        "us-east-1",
        "prod.ReadOnlyAccess",  # profile-name form, not prod/ReadOnlyAccess
        "1h",
        ["--", "python", "-c", "import os;print(os.environ['AWS_ACCESS_KEY_ID'])"],
    )
    out = capfd.readouterr().out
    assert code == 0
    assert "AKIA" in out


def test_switch_accepts_profile_flag(tmp_path, monkeypatch, capsys):
    # aws-style --profile (and the dot profile-name form) resolve the identity.
    b = _fake_broker(tmp_path, monkeypatch)
    code = _cmd_switch(b, "us-east-1", "prod.ReadOnlyAccess", "1h")
    out = capsys.readouterr().out
    assert code == 0
    assert "export AWS_ACCESS_KEY_ID=AKIA" in out


def test_run_without_identity_gives_clean_message(tmp_path, monkeypatch, capsys):
    b = _fake_broker(tmp_path, monkeypatch)
    code = _cmd_run(b, "us-east-1", None, "1h", ["--", "true"])
    out = capsys.readouterr().out
    assert code == 2
    assert "grantry ls" in out and "grantry switch" in out


def test_unknown_identity_error_points_to_ls(tmp_path, monkeypatch, capsys):
    b = _fake_broker(tmp_path, monkeypatch)
    code = _cmd_run(b, "us-east-1", "nope/Nope", "1h", ["--", "true"])
    out = capsys.readouterr().out
    assert code == 1
    assert "grantry ls" in out


def test_completion_infers_shell_from_env(monkeypatch, capsys):
    monkeypatch.setenv("SHELL", "/bin/zsh")
    rc = main(["completion"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "compdef _grantry_complete grantry" in out


def test_admin_conflicting_modes_rejected(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    monkeypatch.setenv("GRANTRY_SSO_START_URL", "https://acme.awsapps.com/start")
    monkeypatch.setenv("GRANTRY_SSO_REGION", "us-east-1")
    rc = main(["admin", "assignments", "--as", "x/y", "--snapshot", "--diff"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "only one" in out.lower()


def test_switch_prints_exports(tmp_path, monkeypatch, capsys):
    b = _fake_broker(tmp_path, monkeypatch)
    code = _cmd_switch(b, "us-east-1", "prod/ReadOnlyAccess", "1h")
    out = capsys.readouterr().out
    assert code == 0
    assert "export AWS_ACCESS_KEY_ID=AKIA" in out
    assert "export AWS_SESSION_TOKEN=sess" in out


def test_populate_reconciles_config(tmp_path, monkeypatch, capsys):
    b = _fake_broker(tmp_path, monkeypatch)
    cfg = tmp_path / "config"
    cfg.write_text(
        "[profile hand-written]\nregion = us-east-1\n\n"
        "[profile stale.Role]\ngrantry_managed = true\n"
    )
    monkeypatch.setenv("AWS_CONFIG_FILE", str(cfg))

    code = _cmd_populate(b, "https://acme.awsapps.com/start", "us-east-1", None, dry_run=False)
    assert code == 0
    body = cfg.read_text()
    # New managed profiles written:
    assert "[profile prod.ReadOnlyAccess]" in body
    assert "[profile dev-pay.AWSPowerUserAccess]" in body
    # Hand-written profile preserved:
    assert "[profile hand-written]" in body
    # Stale managed profile pruned:
    assert "[profile stale.Role]" not in body


def test_populate_dry_run_writes_nothing(tmp_path, monkeypatch, capsys):
    b = _fake_broker(tmp_path, monkeypatch)
    cfg = tmp_path / "config"
    cfg.write_text("[profile hand-written]\nregion = us-east-1\n")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(cfg))
    before = cfg.read_text()

    code = _cmd_populate(b, "https://acme.awsapps.com/start", "us-east-1", None, dry_run=True)
    out = capsys.readouterr().out
    assert code == 0
    assert "+ prod.ReadOnlyAccess" in out
    assert cfg.read_text() == before  # dry run changed nothing


def test_file_link_plain_when_piped():
    # Under pytest stdout is not a TTY, so the path stays plain for clean scripts.
    from grantry.cli import _file_link

    assert _file_link("out.html") == "out.html"


def test_file_link_green_and_clickable_on_tty(monkeypatch):
    import sys as _sys

    from grantry.cli import _file_link

    monkeypatch.setattr(_sys.stdout, "isatty", lambda: True)
    out = _file_link("out.html")
    assert "\033]8;;file://" in out  # OSC 8 hyperlink to the file
    assert "\033[32m" in out  # green
    assert out.endswith("\033]8;;\033\\")  # closes the hyperlink


def test_version_command(capsys):
    rc = main(["version"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("grantry ")


def test_did_you_mean_misspelled_top_level_command(capsys):
    import pytest

    with pytest.raises(SystemExit):
        main(["swich"])
    assert "Did you mean 'switch'" in capsys.readouterr().err


def test_did_you_mean_misspelled_subcommand(capsys):
    import pytest

    with pytest.raises(SystemExit):
        main(["admin", "assigments"])
    assert "Did you mean 'assignments'" in capsys.readouterr().err


def test_version_flag(capsys):
    import pytest

    # argparse's version action prints and exits 0.
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert capsys.readouterr().out.startswith("grantry ")


def test_completion_command(capsys):
    rc = main(["completion", "bash"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "complete -F _grantry_complete grantry" in out


def test_completion_at_a_prompt_shows_guidance(monkeypatch, capsys):
    import sys

    monkeypatch.setenv("SHELL", "/bin/zsh")
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)  # pretend we are a terminal
    rc = main(["completion"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "grantry completion --install" in out
    assert "_grantry_complete" not in out  # guidance, not the raw script


def test_completion_install_appends_to_rc(tmp_path, monkeypatch, capsys):
    rc = tmp_path / ".zshrc"
    rc.write_text("# existing\n")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/zsh")
    rc2 = main(["completion", "--install"])
    body = rc.read_text()
    assert rc2 == 0
    assert "source <(grantry completion zsh)" in body
    assert "# existing" in body  # did not clobber
    # idempotent: a second install does not add it twice
    main(["completion", "zsh", "--install"])
    assert body.count("grantry completion zsh") == rc.read_text().count("grantry completion zsh")


def test_complete_identities_reads_cache(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    from grantry.idcache import write_cache
    from grantry.identity import Identity

    write_cache([Identity("1", "acme-dev", "AWSReadOnlyAccess")])
    rc = main(["_complete-identities"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "acme-dev/AWSReadOnlyAccess" in out


def test_complete_identities_empty_without_cache(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    rc = main(["_complete-identities"])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_human_duration():
    from grantry.cli import _human_duration

    assert _human_duration(7 * 3600 + 12 * 60) == "7h 12m"
    assert _human_duration(3 * 3600) == "3h"
    assert _human_duration(45 * 60) == "45m"
    assert _human_duration(30) == "under a minute"


def test_status_overview_logged_out(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    monkeypatch.setenv("GRANTRY_SSO_START_URL", "https://example.awsapps.com/start")
    monkeypatch.setenv("GRANTRY_SSO_REGION", "us-east-1")
    rc = main(["status"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "grantry " in out
    assert "Instance:" in out
    assert "logged out" in out.lower()
    assert "Policy:" in out
    assert "Audit:" in out


def test_instances_and_use(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    from grantry.instance import save_instance

    save_instance("https://alpha.awsapps.com/start", "us-east-1")
    save_instance("https://beta.awsapps.com/start", "us-west-2")
    assert main(["instances"]) == 0
    out = capsys.readouterr().out
    assert "alpha" in out and "beta" in out
    assert "* beta" in out  # beta is current (saved last)
    assert main(["use", "alpha"]) == 0
    assert main(["instances"]) == 0
    assert "* alpha" in capsys.readouterr().out


def test_uninstall_removes_grantry(tmp_path, monkeypatch):
    import json

    from grantry.cli import _cmd_uninstall
    from grantry.mcp_install import CLIENTS

    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps({"mcpServers": {"grantry": {"command": "x"}, "other": {"command": "y"}}})
    )
    monkeypatch.setitem(
        CLIENTS, "cursor", CLIENTS["cursor"].__class__("cursor", "Cursor", str(cfg), "mcpServers")
    )
    assert _cmd_uninstall(["cursor"]) == 0
    written = json.loads(cfg.read_text())
    assert "grantry" not in written["mcpServers"]
    assert "other" in written["mcpServers"]


def test_credential_process_outputs_json(tmp_path, monkeypatch, capsys):
    import json

    from grantry.cli import _cmd_credential_process

    b = _fake_broker(tmp_path, monkeypatch)
    code = _cmd_credential_process(b, "prod/ReadOnlyAccess", "1h", "human")
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert data["Version"] == 1
    assert data["AccessKeyId"] == "AKIA"


def test_credential_process_denied_to_stderr(tmp_path, monkeypatch, capsys):
    from grantry.cli import _cmd_credential_process

    b = _fake_broker(tmp_path, monkeypatch)
    # agent caller with a policy that only allows humans by default -> denied
    code = _cmd_credential_process(b, "prod/ReadOnlyAccess", "1h", "agent")
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""  # nothing on stdout on failure
    assert "denied" in captured.err.lower()
