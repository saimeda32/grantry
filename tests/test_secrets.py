from grantry.secrets import SecretStore, token_name


def test_roundtrip():
    s = SecretStore()
    s.put("k", "v")
    assert s.get("k") == "v"


def test_missing_is_none():
    assert SecretStore().get("nope") is None


def test_delete():
    s = SecretStore()
    s.put("k", "v")
    s.delete("k")
    assert s.get("k") is None


def test_token_name_is_stable_and_scoped():
    a = token_name("https://example.awsapps.com/start")
    b = token_name("https://example.awsapps.com/start")
    c = token_name("https://other.awsapps.com/start")
    assert a == b
    assert a != c
    assert a.startswith("sso-token:")
