from grantry.identity import Identity
from grantry.scaffold import scaffold_policy


def idents():
    return [
        Identity("1", "mlp-dev", "AWSReadOnlyAccess"),
        Identity("1", "mlp-dev", "AWSAdministratorAccess"),
        Identity("2", "mlp-prod", "AWSPowerUserAccess"),
        Identity("3", "mlp-master", "AWSAdministratorAccess"),
        Identity("4", "mlp-log", "XSOARArchivalsS3Access"),  # a custom role
    ]


def test_readonly_allowed():
    out = scaffold_policy(idents(), "2026-07-16")
    assert '- identity: "*/AWSReadOnlyAccess"' in out.split("deny:")[0]


def test_admin_and_sensitive_accounts_denied():
    out = scaffold_policy(idents(), "2026-07-16")
    deny = out.split("deny:")[1]
    assert '- identity: "*/AWSAdministratorAccess"' in deny
    assert '"mlp-prod/*"' in deny
    assert '"mlp-master/*"' in deny


def test_custom_role_is_listed_not_auto_allowed():
    out = scaffold_policy(idents(), "2026-07-16")
    # The custom role appears in the identity comment list...
    assert "#   mlp-log/XSOARArchivalsS3Access" in out
    # ...but is neither allowed nor denied by a rule (agent default-deny keeps it safe).
    assert '"*/XSOARArchivalsS3Access"' not in out


def test_lists_all_identities_as_comments():
    out = scaffold_policy(idents(), "2026-07-16")
    for i in idents():
        assert f"#   {i.key}" in out
