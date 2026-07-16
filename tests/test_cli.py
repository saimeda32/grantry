from grantry.cli import build_broker, main
from grantry.providers.aws import AwsProvider


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
