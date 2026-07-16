from grantry.instance import InstanceConfig, load_instance, save_instance


def test_save_then_load(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    assert load_instance() is None
    save_instance("https://mlp.awsapps.com/start", "us-east-1")
    got = load_instance()
    assert got == InstanceConfig("https://mlp.awsapps.com/start", "us-east-1")


def test_save_overwrites(tmp_path, monkeypatch):
    monkeypatch.setenv("GRANTRY_HOME", str(tmp_path))
    save_instance("https://a.awsapps.com/start", "us-east-1")
    save_instance("https://b.awsapps.com/start", "us-west-2")
    got = load_instance()
    assert got == InstanceConfig("https://b.awsapps.com/start", "us-west-2")
