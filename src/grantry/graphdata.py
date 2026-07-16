"""Pure models for grantry's own visualizations: the policy access surface
(what each caller class may reach) and the audit activity. No IO here; the CLI
reads identities/policy/audit and the renderer turns these into HTML.
"""

from __future__ import annotations

from dataclasses import dataclass

from grantry.identity import Identity
from grantry.policy import Policy


@dataclass(frozen=True)
class Cell:
    account_name: str
    role_name: str
    allowed: bool
    reason: str


@dataclass(frozen=True)
class AccessSurface:
    caller: str
    cells: list[Cell]

    @property
    def accounts(self) -> list[str]:
        return sorted({c.account_name for c in self.cells})

    @property
    def roles(self) -> list[str]:
        return sorted({c.role_name for c in self.cells})

    @property
    def allowed_count(self) -> int:
        return sum(1 for c in self.cells if c.allowed)

    @property
    def reachable_accounts(self) -> int:
        return len({c.account_name for c in self.cells if c.allowed})


def access_surface(identities: list[Identity], policy: Policy, caller: str) -> AccessSurface:
    """Evaluate the policy for every real identity as the given caller class,
    producing the allow/deny grid. TTL is irrelevant to the allow decision, so a
    nominal value is used.
    """
    cells = []
    for ident in sorted(identities, key=lambda x: x.key):
        decision = policy.evaluate(ident, 900, caller)
        cells.append(
            Cell(
                account_name=ident.account_name,
                role_name=ident.role_name,
                allowed=decision.allowed,
                reason=decision.reason,
            )
        )
    return AccessSurface(caller=caller, cells=cells)
