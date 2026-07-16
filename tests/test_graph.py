from grantry.graphdata import access_surface
from grantry.identity import Identity
from grantry.policy import Policy
from grantry.render import render_access_surface, render_audit

POLICY = """
agents:
  allow:
    - identity: "*/AWSReadOnlyAccess"
  deny:
    - identity: "*prod*/*Admin*"
  max_ttl: 15m
"""


def build_policy(tmp_path):
    p = tmp_path / "policy.yaml"
    p.write_text(POLICY)
    return Policy.load(p)


def idents():
    return [
        Identity("1", "acme-dev", "AWSReadOnlyAccess"),
        Identity("1", "acme-dev", "AWSAdministratorAccess"),
        Identity("2", "acme-prod", "AWSAdministratorAccess"),
    ]


def test_access_surface_allow_and_deny(tmp_path):
    surface = access_surface(idents(), build_policy(tmp_path), "agent")
    by = {(c.account_name, c.role_name): c for c in surface.cells}
    assert by[("acme-dev", "AWSReadOnlyAccess")].allowed is True
    # admin is not read-only and matches no allow -> agent default deny
    assert by[("acme-dev", "AWSAdministratorAccess")].allowed is False
    # prod admin hit the explicit deny rule
    assert by[("acme-prod", "AWSAdministratorAccess")].allowed is False
    assert "deny" in by[("acme-prod", "AWSAdministratorAccess")].reason.lower()
    assert surface.allowed_count == 1
    assert surface.reachable_accounts == 1


def test_render_access_surface_is_self_contained(tmp_path):
    surface = access_surface(idents(), build_policy(tmp_path), "agent")
    html = render_access_surface(surface, "2026-07-16")
    assert "<!doctype html>" in html
    assert "acme-dev" in html and "AWSReadOnlyAccess" in html
    for banned in ("http://", "https://", "<script", "<link ", "@import", "src="):
        assert banned not in html


def test_render_escapes_names(tmp_path):
    evil = [Identity("1", "acc<script>", "role&x")]
    surface = access_surface(evil, build_policy(tmp_path), "agent")
    html = render_access_surface(surface, "2026-07-16")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_audit_self_contained_and_counts():
    entries = [
        {
            "at": "t1",
            "caller": "claude-code",
            "identity": "acme-dev/AWSReadOnlyAccess",
            "allowed": True,
            "reason": "ok",
        },
        {
            "at": "t2",
            "caller": "claude-code",
            "identity": "acme-prod/AWSAdministratorAccess",
            "allowed": False,
            "reason": "denied",
        },
    ]
    html = render_audit(entries, "2026-07-16")
    assert "grants logged" in html
    assert "claude-code" in html
    for banned in ("http://", "https://", "<script", "src="):
        assert banned not in html


def test_render_audit_empty():
    html = render_audit([], "2026-07-16")
    assert "No grants recorded yet." in html
