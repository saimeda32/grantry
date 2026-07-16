import json

from grantry.instance import (
    InstanceConfig,
    list_instances,
    load_instance,
    save_instance,
    use_instance,
)


def test_save_then_load(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    assert load_instance() is None
    save_instance("https://acme.awsapps.com/start", "us-east-1")
    got = load_instance()
    assert got == InstanceConfig("https://acme.awsapps.com/start", "us-east-1")


def test_multiple_instances_and_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    save_instance("https://alpha.awsapps.com/start", "us-east-1")
    save_instance("https://beta.awsapps.com/start", "us-west-2")
    # the most recent save is current
    cur = load_instance()
    assert cur is not None and cur.start_url == "https://beta.awsapps.com/start"

    names = [n for n, _c, _cur in list_instances()]
    assert names == ["alpha", "beta"]

    # switch back to alpha by prefix
    got = use_instance("alph")
    assert got is not None and got.region == "us-east-1"
    after = load_instance()
    assert after is not None and after.start_url == "https://alpha.awsapps.com/start"


def test_use_unknown_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    save_instance("https://alpha.awsapps.com/start", "us-east-1")
    assert use_instance("nope") is None


def test_migrates_legacy_single_instance_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    (tmp_path / "instance.json").write_text(
        json.dumps({"start_url": "https://legacy.awsapps.com/start", "region": "eu-west-1"})
    )
    got = load_instance()
    assert got is not None
    assert got.start_url == "https://legacy.awsapps.com/start"
    assert [n for n, _c, _cur in list_instances()] == ["legacy"]
