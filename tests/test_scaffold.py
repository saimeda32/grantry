from grantry.identity import Identity
from grantry.policy import Policy
from grantry.scaffold import scaffold_policy


def idents():
    return [
        Identity("1", "mlp-dev", "AWSReadOnlyAccess"),
        Identity("1", "mlp-dev", "AWSAdministratorAccess"),
        Identity("2", "mlp-prod", "AWSPowerUserAccess"),
        Identity("3", "mlp-master", "AWSAdministratorAccess"),
        Identity("4", "mlp-log", "XSOARArchivalsS3Access"),  # a custom role
    ]


def test_starter_is_permissive():
    out = scaffold_policy(idents(), "2026-07-16")
    allow_section = out.split("deny:")[0]
    assert '- identity: "*/*"' in allow_section
    assert "PERMISSIVE" in out


def test_warns_how_to_restrict():
    out = scaffold_policy(idents(), "2026-07-16")
    assert "Restrict me" in out
    # restrictive rules are offered as commented guidance
    assert '#   - identity: "*/AWSReadOnlyAccess"' in out
    assert '#   - identity: "*/AWSAdministratorAccess"' in out
    assert "mlp-prod/*" in out


def test_lists_all_identities_as_comments():
    out = scaffold_policy(idents(), "2026-07-16")
    for i in idents():
        assert f"#   {i.key}" in out


def test_generated_policy_is_valid_and_allows_agents(tmp_path):
    # the permissive starter must parse and actually allow an agent
    p = tmp_path / "policy.yaml"
    p.write_text(scaffold_policy(idents(), "2026-07-16"))
    pol = Policy.load(p)
    d = pol.evaluate(Identity("9", "any", "AnyRole"), 900, caller="agent")
    assert d.allowed
