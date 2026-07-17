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
