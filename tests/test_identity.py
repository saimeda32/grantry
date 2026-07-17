from grantry.identity import Identity, matches, shell_safe


def ident(acct="prod", role="ReadOnlyAccess", aid="111122223333"):
    return Identity(account_id=aid, account_name=acct, role_name=role)


def test_key():
    assert ident("dev", "Admin").key == "dev/Admin"


def test_shell_safe_collapses_whitespace():
    assert shell_safe("Acme Corp Account") == "Acme-Corp-Account"
    assert shell_safe("  padded  name  ") == "padded-name"
    assert shell_safe("tab\tseparated") == "tab-separated"
    assert shell_safe("already-fine") == "already-fine"


def test_key_has_no_spaces():
    # An account name with spaces must produce a quote-free identity key.
    assert ident("Acme Corp Account", "Admin Access").key == "Acme-Corp-Account/Admin-Access"


def test_spaced_name_matches_hyphenated_pattern():
    # A policy written against the displayed (hyphenated) name matches the
    # identity whose raw account name still carries spaces.
    assert matches("Acme-Corp-Account/*", ident("Acme Corp Account", "ReadOnlyAccess"))
    assert matches("*/Admin-Access", ident("prod", "Admin Access"))


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


def test_star_does_not_cross_slash():
    # 'prod*' must match the account segment only, not leak into the role.
    assert matches("prod*/AWSReadOnlyAccess", ident("prod-payments", "AWSReadOnlyAccess"))
    # a bare 'prod*' (no slash) matches the whole key, so it still matches broadly
    assert matches("prod*", ident("prod-payments", "AnyRole"))
    # but an account-scoped pattern will not match a role via the wildcard
    assert not matches("*/ReadOnly", ident("acct", "AWSReadOnlyAccess"))  # role must match fully
    assert matches("*/*ReadOnly*", ident("acct", "AWSReadOnlyAccess"))


def test_segment_match_is_independent():
    assert matches("dev-*/AWSPowerUserAccess", ident("dev-x", "AWSPowerUserAccess"))
    assert not matches("dev-*/AWSPowerUserAccess", ident("prod-x", "AWSPowerUserAccess"))
    assert not matches("dev-*/AWSPowerUserAccess", ident("dev-x", "AWSAdminAccess"))
