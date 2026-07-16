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
    main(["--start-url", "https://mlp.awsapps.com/start", "--region", "us-east-1", "ls"])
    saved = load_instance()
    assert saved is not None
    assert saved.start_url == "https://mlp.awsapps.com/start"
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
    start_url = "https://mlp.awsapps.com/start"
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

    code = _cmd_populate(b, "https://mlp.awsapps.com/start", "us-east-1", None, dry_run=False)
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

    code = _cmd_populate(b, "https://mlp.awsapps.com/start", "us-east-1", None, dry_run=True)
    out = capsys.readouterr().out
    assert code == 0
    assert "+ prod.ReadOnlyAccess" in out
    assert cfg.read_text() == before  # dry run changed nothing
