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
