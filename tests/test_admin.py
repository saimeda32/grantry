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
            return {"Accounts": [{"Id": "111", "Name": "mlp-dev"}], "NextToken": "p2"}
        return {"Accounts": [{"Id": "222", "Name": "mlp-prod"}]}


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
    assert accts == {"mlp-dev", "mlp-prod"}
    psets = {a.permission_set_name for a in assignments}
    assert psets == {"AWSReadOnlyAccess", "AWSAdministratorAccess"}
    # the group g-1 was described only ONCE despite 4 assignments (name cache)
    assert idstore.describe_calls == 1
    # progress reported per account
    assert seen[-1] == (2, 2)


def test_no_instances_returns_empty():
    class NoInst:
        def list_instances(self):
            return {"Instances": []}

    assert crawl_assignments(lambda n: NoInst()) == []


def test_render_assignments_self_contained():
    from grantry.admin import Assignment

    rows = [
        Assignment("GROUP", "g1", "Platform Eng", "AWSReadOnlyAccess", "111", "mlp-dev"),
        Assignment("USER", "u1", "casey", "AWSAdministratorAccess", "222", "mlp-prod"),
    ]
    html = render_assignments(rows, "2026-07-16")
    assert "Organization access map" in html
    assert "Platform Eng" in html
    for banned in ("http://", "https://", "<script", "src="):
        assert banned not in html
