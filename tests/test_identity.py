from grantry.identity import Identity, matches


def ident(acct="prod", role="ReadOnlyAccess", aid="111122223333"):
    return Identity(account_id=aid, account_name=acct, role_name=role)


def test_key():
    assert ident("dev", "Admin").key == "dev/Admin"


def test_exact_match():
    assert matches("prod/ReadOnlyAccess", ident("prod", "ReadOnlyAccess"))


def test_role_glob():
    assert matches("*/ReadOnlyAccess", ident("anything", "ReadOnlyAccess"))
    assert not matches("*/ReadOnlyAccess", ident("anything", "AdminAccess"))


def test_account_glob():
    assert matches("dev-*/AWSPowerUserAccess", ident("dev-payments", "AWSPowerUserAccess"))
    assert not matches("dev-*/AWSPowerUserAccess", ident("prod-payments", "AWSPowerUserAccess"))


def test_both_globs():
    assert matches("*prod*/*Admin*", ident("prod-payments", "SuperAdminAccess"))


def test_case_insensitive():
    assert matches("*/readonlyaccess", ident("prod", "ReadOnlyAccess"))


def test_no_slash_matches_whole_key():
    assert matches("prod/ReadOnlyAccess", ident("prod", "ReadOnlyAccess"))
    assert matches("*ReadOnly*", ident("prod", "ReadOnlyAccess"))
