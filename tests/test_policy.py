import pytest

from grantry.identity import Identity
from grantry.policy import Policy, PolicyError

POLICY = """
agents:
  allow:
    - identity: "*/ReadOnlyAccess"
    - identity: "dev-*/AWSPowerUserAccess"
  deny:
    - identity: "*prod*/*Admin*"
  max_ttl: 15m
humans:
  max_ttl: 12h
"""


def write(tmp_path, text):
    p = tmp_path / "policy.yaml"
    p.write_text(text)
    return p


def ident(acct, role):
    return Identity(account_id="111122223333", account_name=acct, role_name=role)


def test_agent_allowed_and_ttl_capped(tmp_path):
    pol = Policy.load(write(tmp_path, POLICY))
    d = pol.evaluate(ident("anything", "ReadOnlyAccess"), requested_ttl=3600, caller="agent")
    assert d.allowed
    assert d.capped_ttl == 900
    assert d.matched_rule == "*/ReadOnlyAccess"


def test_agent_ttl_not_raised(tmp_path):
    pol = Policy.load(write(tmp_path, POLICY))
    d = pol.evaluate(ident("dev-x", "AWSPowerUserAccess"), requested_ttl=300, caller="agent")
    assert d.allowed
    assert d.capped_ttl == 300


def test_deny_beats_allow(tmp_path):
    pol = Policy.load(write(tmp_path, POLICY))
    d = pol.evaluate(ident("prod-pay", "SuperAdminAccess"), requested_ttl=300, caller="agent")
    assert not d.allowed
    assert "deny" in d.reason.lower()


def test_agent_unmatched_denied(tmp_path):
    pol = Policy.load(write(tmp_path, POLICY))
    d = pol.evaluate(ident("stg", "AWSDeveloperAccess"), requested_ttl=300, caller="agent")
    assert not d.allowed


def test_human_unmatched_allowed(tmp_path):
    pol = Policy.load(write(tmp_path, POLICY))
    d = pol.evaluate(ident("stg", "AWSDeveloperAccess"), requested_ttl=3600, caller="human")
    assert d.allowed
    assert d.capped_ttl == 3600


def test_missing_file_denies_agents(tmp_path):
    pol = Policy.load(tmp_path / "nope.yaml")
    d = pol.evaluate(ident("dev", "ReadOnlyAccess"), requested_ttl=300, caller="agent")
    assert not d.allowed
    h = pol.evaluate(ident("dev", "ReadOnlyAccess"), requested_ttl=300, caller="human")
    assert h.allowed


def test_malformed_policy_raises(tmp_path):
    with pytest.raises(PolicyError):
        Policy.load(write(tmp_path, "agents: [this is not a mapping]"))
