from grantry.humanops import (
    append_profiles,
    env_from_credentials,
    format_exports,
    parse_profiles,
    profile_block,
    reconcile,
    strip_profiles,
)
from grantry.providers.base import Credentials


def test_env_from_credentials():
    creds = Credentials("AKIA", "sec", "sess", 1893456000.0)
    env = env_from_credentials(creds, "us-east-1")
    assert env["AWS_ACCESS_KEY_ID"] == "AKIA"
    assert env["AWS_SECRET_ACCESS_KEY"] == "sec"
    assert env["AWS_SESSION_TOKEN"] == "sess"
    assert env["AWS_DEFAULT_REGION"] == "us-east-1"
    assert env["AWS_REGION"] == "us-east-1"


def test_format_exports_is_shell_evalable():
    env = {"AWS_ACCESS_KEY_ID": "AKIA", "AWS_SESSION_TOKEN": "a b$c"}
    out = format_exports(env)
    # Safe values stay bare; values with shell metacharacters are quoted safely.
    assert "export AWS_ACCESS_KEY_ID=AKIA" in out
    assert "export AWS_SESSION_TOKEN='a b$c'" in out


def test_profile_block():
    block = profile_block(
        "prod.ReadOnlyAccess",
        "111122223333",
        "ReadOnlyAccess",
        "https://mlp.awsapps.com/start",
        "us-east-1",
        "us-west-2",
    )
    assert "[profile prod.ReadOnlyAccess]" in block
    assert "sso_account_id = 111122223333" in block
    assert "sso_role_name = ReadOnlyAccess" in block
    assert "sso_start_url = https://mlp.awsapps.com/start" in block
    assert "region = us-west-2" in block
    assert "grantry_managed = true" in block


def test_reconcile_add_update_prune():
    # existing: two grantry-managed profiles and one hand-written the tool must not touch.
    existing = {
        "prod.ReadOnlyAccess": {"grantry_managed": "true", "sso_role_name": "ReadOnlyAccess"},
        "old.Role": {"grantry_managed": "true"},  # no longer accessible -> prune
        "my-hand-written": {"region": "us-east-1"},  # not managed -> keep untouched
    }
    desired = {"prod.ReadOnlyAccess", "new.Role"}
    plan = reconcile(existing, desired)
    assert plan.to_add == {"new.Role"}
    assert plan.to_prune == {"old.Role"}
    assert "my-hand-written" not in plan.to_prune
    assert plan.kept == {"prod.ReadOnlyAccess"}


CONFIG = """# my aws config
[profile hand-written]
region = us-east-1

[profile prod.ReadOnlyAccess]
sso_role_name = ReadOnlyAccess
grantry_managed = true
"""


def test_parse_profiles():
    profiles = parse_profiles(CONFIG)
    assert set(profiles) == {"hand-written", "prod.ReadOnlyAccess"}
    assert profiles["prod.ReadOnlyAccess"]["grantry_managed"] == "true"
    assert profiles["hand-written"]["region"] == "us-east-1"


def test_strip_profiles_preserves_others_and_comments():
    out = strip_profiles(CONFIG, {"prod.ReadOnlyAccess"})
    assert "# my aws config" in out
    assert "[profile hand-written]" in out
    assert "[profile prod.ReadOnlyAccess]" not in out
    assert "grantry_managed" not in out


def test_append_profiles():
    out = append_profiles("[profile a]\nregion = x\n", ["[profile b]\nregion = y"])
    assert "[profile a]" in out
    assert "[profile b]" in out
    assert out.endswith("\n")


def test_safe_profile_name_sanitizes():
    from grantry.humanops import safe_profile_name

    assert safe_profile_name("mlp-dev", "AWSReadOnlyAccess") == "mlp-dev.AWSReadOnlyAccess"
    # whitespace and special chars collapse to a single hyphen
    assert safe_profile_name("Prod Account", "Admin Access") == "Prod-Account.Admin-Access"
    assert safe_profile_name("acct (main)", "role/x") == "acct-main.role-x"
    # never produces an empty side
    assert safe_profile_name("  ", "  ") == "account.role"
