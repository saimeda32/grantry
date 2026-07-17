from grantry.admin import crawl_assignments
from grantry.render import render_assignments


class FakeSSOAdmin:
    def __init__(self):
        self.describe_calls = 0

    def list_instances(self):
        return {"Instances": [{"InstanceArn": "arn:ins", "IdentityStoreId": "d-123"}]}

    def list_permission_sets(self, InstanceArn, NextToken=None):  # noqa: N803
        # two pages to exercise pagination
        if NextToken is None:
            return {"PermissionSets": ["ps-a"], "NextToken": "p2"}
        return {"PermissionSets": ["ps-b"]}

    def describe_permission_set(self, InstanceArn, PermissionSetArn):  # noqa: N803
        names = {"ps-a": "AWSReadOnlyAccess", "ps-b": "AWSAdministratorAccess"}
        return {"PermissionSet": {"Name": names[PermissionSetArn]}}

    def list_permission_sets_provisioned_to_account(self, InstanceArn, AccountId, NextToken=None):  # noqa: N803
        return {"PermissionSets": ["ps-a", "ps-b"]}

    def list_account_assignments(self, InstanceArn, AccountId, PermissionSetArn, NextToken=None):  # noqa: N803
        # same group appears on every account+ps, to prove name caching
        return {"AccountAssignments": [{"PrincipalType": "GROUP", "PrincipalId": "g-1"}]}


class FakeIdentityStore:
    def __init__(self):
        self.describe_calls = 0

    def describe_group(self, IdentityStoreId, GroupId):  # noqa: N803
        self.describe_calls += 1
        return {"DisplayName": "Platform Engineering"}

    def describe_user(self, IdentityStoreId, UserId):  # noqa: N803
        self.describe_calls += 1
        return {"UserName": "someone"}


class FakeOrgs:
    def list_accounts(self, NextToken=None):  # noqa: N803
        if NextToken is None:
            return {"Accounts": [{"Id": "111", "Name": "acme-dev"}], "NextToken": "p2"}
        return {"Accounts": [{"Id": "222", "Name": "acme-prod"}]}


def test_crawl_aggregates_and_caches_principal_names():
    idstore = FakeIdentityStore()
    clients = {"sso-admin": FakeSSOAdmin(), "identitystore": idstore, "organizations": FakeOrgs()}
    seen = []

    def make_client(name):
        return clients[name]

    assignments = crawl_assignments(make_client, on_progress=lambda d, t: seen.append((d, t)))

    # 2 accounts x 2 permission sets x 1 principal = 4 assignments
    assert len(assignments) == 4
    names = {a.principal_name for a in assignments}
    assert names == {"Platform Engineering"}
    accts = {a.account_name for a in assignments}
    assert accts == {"acme-dev", "acme-prod"}
    psets = {a.permission_set_name for a in assignments}
    assert psets == {"AWSReadOnlyAccess", "AWSAdministratorAccess"}
    # the group g-1 was described only ONCE despite 4 assignments (name cache)
    assert idstore.describe_calls == 1
    # progress reported per account
    assert seen[-1] == (2, 2)


class FakeOrgsTagged(FakeOrgs):
    def list_tags_for_resource(self, ResourceId):  # noqa: N803
        tags = {
            "111": [{"Key": "Environment", "Value": "production"}],
            "222": [{"Key": "env", "Value": "sandbox"}],
        }
        return {"Tags": tags.get(ResourceId, [])}


def test_account_env_classification():
    from grantry.admin import _account_env

    class Orgs:
        def __init__(self, tags):
            self._t = tags

        def list_tags_for_resource(self, ResourceId):  # noqa: N803
            return {"Tags": self._t}

    assert _account_env(Orgs([{"Key": "Environment", "Value": "prod"}]), "x") == "prod"
    assert _account_env(Orgs([{"Key": "env", "Value": "staging"}]), "x") == "nonprod"
    assert _account_env(Orgs([{"Key": "Team", "Value": "x"}]), "x") == ""  # no env tag

    class Boom:
        def list_tags_for_resource(self, ResourceId):  # noqa: N803
            raise RuntimeError("AccessDenied")

    assert _account_env(Boom(), "x") is None  # API error -> caller falls back to names


def test_crawl_classifies_accounts_by_environment_tag():
    clients = {
        "sso-admin": FakeSSOAdmin(),
        "identitystore": FakeIdentityStore(),
        "organizations": FakeOrgsTagged(),
    }
    assignments = crawl_assignments(lambda n: clients[n])
    env = {a.account_id: a.account_env for a in assignments}
    assert env["111"] == "prod"  # tagged Environment=production
    assert env["222"] == "nonprod"  # tagged env=sandbox


def test_crawl_falls_back_when_tags_unavailable():
    # FakeOrgs has no list_tags_for_resource, so classification errors and env
    # stays "" (the visualization then guesses from the name).
    clients = {
        "sso-admin": FakeSSOAdmin(),
        "identitystore": FakeIdentityStore(),
        "organizations": FakeOrgs(),
    }
    assignments = crawl_assignments(lambda n: clients[n])
    assert all(a.account_env == "" for a in assignments)


class FakeSSOEnrich(FakeSSOAdmin):
    def describe_permission_set(self, InstanceArn, PermissionSetArn):  # noqa: N803
        d = super().describe_permission_set(InstanceArn, PermissionSetArn)
        d["PermissionSet"]["SessionDuration"] = "PT12H"
        return d

    def list_managed_policies_in_permission_set(
        self, InstanceArn, PermissionSetArn, NextToken=None
    ):  # noqa: N803
        m = {"ps-a": [{"Name": "ReadOnlyAccess"}], "ps-b": [{"Name": "AdministratorAccess"}]}
        return {"AttachedManagedPolicies": m.get(PermissionSetArn, [])}

    def get_inline_policy_for_permission_set(self, InstanceArn, PermissionSetArn):  # noqa: N803
        return {"InlinePolicy": "{...}" if PermissionSetArn == "ps-b" else ""}


class FakeIDEnrich(FakeIdentityStore):
    def list_group_memberships(self, IdentityStoreId, GroupId, NextToken=None):  # noqa: N803
        return {"GroupMemberships": [{"MemberId": {"UserId": "u-1"}}]}


class FakeOrgsEnrich(FakeOrgs):
    def list_parents(self, ChildId, NextToken=None):  # noqa: N803
        return {"Parents": [{"Id": "ou-1", "Type": "ORGANIZATIONAL_UNIT"}]}

    def describe_organizational_unit(self, OrganizationalUnitId):  # noqa: N803
        return {"OrganizationalUnit": {"Name": "Workloads"}}


def test_crawl_enrichment_gathers_members_psets_and_ous():
    from grantry.admin import Assignment, crawl_enrichment

    clients = {
        "sso-admin": FakeSSOEnrich(),
        "identitystore": FakeIDEnrich(),
        "organizations": FakeOrgsEnrich(),
    }
    assignments = [
        Assignment("GROUP", "g-1", "Platform", "AWSAdministratorAccess", "111", "acme-prod"),
        Assignment("USER", "u-9", "casey", "AWSReadOnlyAccess", "111", "acme-prod"),
    ]
    e = crawl_enrichment(lambda n: clients[n], assignments)
    assert e.group_members["Platform"] == ["someone"]  # member u-1 -> describe_user
    assert e.permission_sets["AWSAdministratorAccess"]["session_duration"] == "PT12H"
    assert "AdministratorAccess" in e.permission_sets["AWSAdministratorAccess"]["managed"]
    assert e.permission_sets["AWSAdministratorAccess"]["inline"] is True
    assert e.account_ou["acme-prod"] == "Workloads"


def test_render_injects_enrichment_and_provenance():
    from grantry.admin import Assignment, Enrichment

    e = Enrichment(
        group_members={"Platform": ["casey"]},
        permission_sets={
            "AWSAdministratorAccess": {
                "session_duration": "PT12H",
                "managed": ["AdministratorAccess"],
                "inline": True,
                "description": "",
            }
        },
        account_ou={"acme-prod": "Workloads"},
    )
    rows = [
        Assignment("GROUP", "g1", "Platform", "AWSAdministratorAccess", "111", "acme-prod", "prod")
    ]
    html = render_assignments(rows, "2026-07-16", enrichment=e, crawled_as="acme-mgmt/AWSAdmin")
    assert "/*MEMBERS*/" not in html and "const MEMBERS = " in html
    assert "Workloads" in html
    assert "acme-mgmt/AWSAdmin" in html
    assert "PT12H" in html


def test_no_instances_returns_empty():
    class NoInst:
        def list_instances(self):
            return {"Instances": []}

    assert crawl_assignments(lambda n: NoInst()) == []


def test_render_assignments_is_interactive_graph():
    from grantry.admin import Assignment

    rows = [
        Assignment("GROUP", "g1", "Platform Eng", "AWSReadOnlyAccess", "111", "acme-dev"),
        Assignment("USER", "u1", "casey", "AWSAdministratorAccess", "222", "acme-prod"),
    ]
    html = render_assignments(rows, "2026-07-16")
    # the injected data is present and the graph JS is there (node-link, not a table)
    assert "/*DATA*/" not in html
    assert '"Platform Eng"' in html
    assert "Organization Access Graph" in html
    assert "const DATA = [" in html
    # self-contained: no external scripts, styles, imports, or fetches. (The SVG
    # xmlns namespace URL is not a network request, so we ban the request forms.)
    for banned in ("<script src", "<link ", "@import", "fetch(", "https://cdn", 'src="http'):
        assert banned not in html


def test_render_assignments_escapes_script_breakout():
    from grantry.admin import Assignment

    evil = [Assignment("USER", "u1", "</script><b>x", "role", "111", "acct")]
    html = render_assignments(evil, "2026-07-16")
    # the template legitimately contains its own </script>; the injected data must not add one
    assert "</script><b>x" not in html
    assert "\\u003c/script>" in html
