"""Org-wide assignment crawl: who has which permission set in which account.

This is admin-only by construction. It calls the sso-admin, organizations, and
identitystore APIs, which require signed credentials from an account that holds
those permissions (typically the management or a delegated-admin account).
grantry mints those credentials through the normal policy path, so a caller who
cannot assume such a role simply gets nothing; AWS is the gatekeeper.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

ClientFactory = Callable[[str], Any]

# Tag keys that commonly name an account's environment, and values that mean
# production. Used to classify accounts authoritatively, rather than guessing
# from the account name.
_ENV_TAG_KEYS = ("environment", "env", "tier", "stage", "account-type", "accounttype")
_PROD_VALUE = re.compile(r"prod|prd|\blive\b|production", re.IGNORECASE)


@dataclass(frozen=True)
class Assignment:
    principal_type: str
    principal_id: str
    principal_name: str
    permission_set_name: str
    account_id: str
    account_name: str
    account_env: str = ""  # "prod" / "nonprod" from account tags, "" if unknown


@dataclass(frozen=True)
class Enrichment:
    """Optional extra context for the visualization, gathered with more AWS calls.
    Every field is best-effort: a missing permission just leaves it empty.
    """

    group_members: dict[str, list[str]]  # group display name -> member user names
    permission_sets: dict[str, dict[str, Any]]  # ps name -> details (policies, session, ...)
    account_ou: dict[str, str]  # account name -> Organizational Unit name


def _account_env(orgs: Any, account_id: str) -> str | None:
    """Classify an account from its Organizations tags. Returns 'prod' or
    'nonprod' when an environment tag is present, '' when the account has no such
    tag, or None on an API error (e.g. missing organizations:ListTagsForResource),
    which the caller treats as "stop probing and fall back to names".
    """
    try:
        tags = orgs.list_tags_for_resource(ResourceId=account_id).get("Tags", [])
    except Exception:
        return None
    for tag in tags:
        if str(tag.get("Key", "")).lower() in _ENV_TAG_KEYS:
            return "prod" if _PROD_VALUE.search(str(tag.get("Value", ""))) else "nonprod"
    return ""


def _paginate(op: Callable[..., dict[str, Any]], key: str, **kwargs: Any) -> Iterator[Any]:
    token: str | None = None
    while True:
        call = dict(kwargs)
        if token:
            call["NextToken"] = token
        resp = op(**call)
        yield from resp.get(key, [])
        token = resp.get("NextToken")
        if not token:
            return


def _principal_name(
    idstore: Any,
    identity_store_id: str,
    ptype: str,
    pid: str,
    cache: dict[tuple[str, str], str],
) -> str:
    # A group or user appears on many assignments; resolve each unique principal
    # ONCE and cache it. At 10k+ assignments this turns tens of thousands of
    # describe calls into one per distinct principal, which is the difference
    # between a crawl that finishes and one that gets throttled.
    key = (ptype, pid)
    if key in cache:
        return cache[key]
    try:
        if ptype == "GROUP":
            resp = idstore.describe_group(IdentityStoreId=identity_store_id, GroupId=pid)
            name = str(resp.get("DisplayName", pid))
        else:
            resp = idstore.describe_user(IdentityStoreId=identity_store_id, UserId=pid)
            name = str(resp.get("UserName", pid))
    except Exception:
        # A transient failure (throttle, network) must NOT be cached, or the
        # principal is permanently stuck as its raw id for the whole crawl. Fall
        # back to the id for this row only and let a later row retry the lookup.
        return pid
    cache[key] = name
    return name


def crawl_assignments(
    make_client: ClientFactory,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[Assignment]:
    sso = make_client("sso-admin")
    idstore = make_client("identitystore")
    orgs = make_client("organizations")

    instances = sso.list_instances().get("Instances", [])
    if not instances:
        return []
    instance_arn = instances[0]["InstanceArn"]
    identity_store_id = instances[0]["IdentityStoreId"]

    accounts: dict[str, str] = {}
    for acct in _paginate(orgs.list_accounts, "Accounts"):
        accounts[acct["Id"]] = acct.get("Name", acct["Id"])

    # Classify each account from its environment tag, authoritatively. If the
    # caller lacks organizations:ListTagsForResource, stop after the first error
    # and leave the rest unknown (the visualization falls back to the name).
    account_env: dict[str, str] = {}
    probe_tags = True
    for acct_id in accounts:
        env = _account_env(orgs, acct_id) if probe_tags else ""
        if env is None:
            probe_tags = False
            env = ""
        account_env[acct_id] = env

    ps_names: dict[str, str] = {}
    for ps_arn in _paginate(sso.list_permission_sets, "PermissionSets", InstanceArn=instance_arn):
        d = sso.describe_permission_set(InstanceArn=instance_arn, PermissionSetArn=ps_arn)
        ps_names[ps_arn] = d["PermissionSet"]["Name"]

    out: list[Assignment] = []
    name_cache: dict[tuple[str, str], str] = {}
    total_accounts = len(accounts)
    for done, (acct_id, acct_name) in enumerate(accounts.items(), start=1):
        for ps_arn in _paginate(
            sso.list_permission_sets_provisioned_to_account,
            "PermissionSets",
            InstanceArn=instance_arn,
            AccountId=acct_id,
        ):
            for a in _paginate(
                sso.list_account_assignments,
                "AccountAssignments",
                InstanceArn=instance_arn,
                AccountId=acct_id,
                PermissionSetArn=ps_arn,
            ):
                ptype = a["PrincipalType"]
                pid = a["PrincipalId"]
                out.append(
                    Assignment(
                        principal_type=ptype,
                        principal_id=pid,
                        principal_name=_principal_name(
                            idstore, identity_store_id, ptype, pid, name_cache
                        ),
                        permission_set_name=ps_names.get(ps_arn, ps_arn),
                        account_id=acct_id,
                        account_name=acct_name,
                        account_env=account_env.get(acct_id, ""),
                    )
                )
        if on_progress:
            on_progress(done, total_accounts)
    return out


def crawl_enrichment(make_client: ClientFactory, assignments: list[Assignment]) -> Enrichment:
    """Gather optional extra context for the visualization: who is in each group,
    what each permission set actually grants, and each account's OU. Every part is
    best-effort; a missing permission simply leaves that part empty. Runs only for
    the interactive graph, so the extra API calls do not slow snapshots or diffs.
    """
    sso = make_client("sso-admin")
    idstore = make_client("identitystore")
    orgs = make_client("organizations")

    instances = sso.list_instances().get("Instances", [])
    if not instances:
        return Enrichment({}, {}, {})
    instance_arn = instances[0]["InstanceArn"]
    id_store = instances[0]["IdentityStoreId"]
    name_cache: dict[tuple[str, str], str] = {}

    # Group memberships: expand each group to the users in it.
    group_members: dict[str, list[str]] = {}
    groups = {
        (a.principal_id, a.principal_name) for a in assignments if a.principal_type == "GROUP"
    }
    for gid, gname in groups:
        try:
            members = []
            for m in _paginate(
                idstore.list_group_memberships,
                "GroupMemberships",
                IdentityStoreId=id_store,
                GroupId=gid,
            ):
                uid = m.get("MemberId", {}).get("UserId")
                if uid:
                    members.append(_principal_name(idstore, id_store, "USER", uid, name_cache))
            group_members[gname] = sorted(set(members))
        except Exception:
            continue

    # Permission-set details: session duration and the policies each one attaches.
    used_ps = {a.permission_set_name for a in assignments}
    permission_sets: dict[str, dict[str, Any]] = {}
    try:
        for ps_arn in _paginate(
            sso.list_permission_sets, "PermissionSets", InstanceArn=instance_arn
        ):
            d = sso.describe_permission_set(InstanceArn=instance_arn, PermissionSetArn=ps_arn)[
                "PermissionSet"
            ]
            name = d.get("Name", "")
            if name not in used_ps:
                continue
            managed: list[str] = []
            try:
                for p in _paginate(
                    sso.list_managed_policies_in_permission_set,
                    "AttachedManagedPolicies",
                    InstanceArn=instance_arn,
                    PermissionSetArn=ps_arn,
                ):
                    managed.append(str(p.get("Name", "")))
            except Exception:
                pass
            inline = False
            try:
                resp = sso.get_inline_policy_for_permission_set(
                    InstanceArn=instance_arn, PermissionSetArn=ps_arn
                )
                inline = bool(resp.get("InlinePolicy"))
            except Exception:
                pass
            permission_sets[name] = {
                "session_duration": str(d.get("SessionDuration", "")),
                "description": str(d.get("Description", "")),
                "managed": managed,
                "inline": inline,
            }
    except Exception:
        pass

    # Account OU: which Organizational Unit each account sits in.
    account_ou: dict[str, str] = {}
    ou_names: dict[str, str] = {}
    for aid, aname in {(a.account_id, a.account_name) for a in assignments}:
        try:
            parents = orgs.list_parents(ChildId=aid).get("Parents", [])
            if not parents:
                continue
            parent = parents[0]
            if parent.get("Type") == "ROOT":
                account_ou[aname] = "Root"
            elif parent.get("Type") == "ORGANIZATIONAL_UNIT":
                ouid = parent["Id"]
                if ouid not in ou_names:
                    ou = orgs.describe_organizational_unit(OrganizationalUnitId=ouid)
                    ou_names[ouid] = str(ou.get("OrganizationalUnit", {}).get("Name", ouid))
                account_ou[aname] = ou_names[ouid]
        except Exception:
            continue

    return Enrichment(group_members, permission_sets, account_ou)
