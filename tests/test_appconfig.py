from grantry.appconfig import load_config
from grantry.cli import main
from grantry.instance import load_instance


def test_missing_config_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    cfg = load_config()
    assert cfg.ttl == "1h"
    assert cfg.start_url is None
    assert cfg.region is None


def test_reads_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    (tmp_path / "config.toml").write_text(
        "[defaults]\n"
        'ttl = "30m"\n'
        'start_url = "https://acme.awsapps.com/start"\n'
        'region = "us-west-2"\n'
    )
    cfg = load_config()
    assert cfg.ttl == "30m"
    assert cfg.start_url == "https://acme.awsapps.com/start"
    assert cfg.region == "us-west-2"


def test_malformed_config_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    (tmp_path / "config.toml").write_text("this is [ not valid toml")
    assert load_config().ttl == "1h"


def test_wrong_types_fall_back(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    (tmp_path / "config.toml").write_text("[defaults]\nttl = 30\n")  # int, not str
    assert load_config().ttl == "1h"


def test_config_provides_instance_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    monkeypatch.delenv("GRANTRY_SSO_START_URL", raising=False)
    monkeypatch.delenv("GRANTRY_SSO_REGION", raising=False)
    (tmp_path / "config.toml").write_text(
        '[defaults]\nstart_url = "https://acme.awsapps.com/start"\nregion = "us-east-1"\n'
    )
    # No flags, no env, no saved instance: config must satisfy the instance so
    # this does NOT raise "no instance known". It still returns 1 (no session).
    rc = main(["ls"])
    assert rc == 1
    saved = load_instance()
    assert saved is not None
    assert saved.start_url == "https://acme.awsapps.com/start"
    assert saved.region == "us-east-1"
