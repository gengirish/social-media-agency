"""Capability matrix and the router-level gate that enforces it.

The single source of truth for *what a seat may do*. Two independent axes decide
it:

* ``users.role`` — the seat permission (``owner`` / ``admin`` / ``member`` / ``viewer``).
* ``organization.account_type`` — the account shape (``personal`` / ``business``),
  which subtracts the capabilities a solo account has no use for.

Three rules hold this module together; none of them is stylistic.

**The role is read from the database, never from the JWT.** ``get_current_user``
returns the token payload in both auth modes, so ``user["role"]`` there is as old
as the token. A demotion has to take effect before the token expires, and a
deleted user's unexpired token must not keep its privileges. That costs one
indexed read per gated request.

**The gate fails closed.** No ``users`` row, a row belonging to another org, an
inactive row, an unknown role string — all four resolve to the empty capability
set, which denies everything. There is deliberately no fallback to the token's
``role`` claim: the fallback would reinstate exactly the staleness the database
read exists to remove.

**Gates belong in routers, never in services.** ``services/scheduler.py`` publishes
on a timer and the agent pipeline writes content — both run with no user in scope.
A capability check inside ``services/publishing.py`` would break the scheduler at
3am. The service layer stays user-agnostic; the router is the gate.

Import direction is ``permissions`` → ``dependencies``, never the reverse.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Literal, cast, get_args
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.dependencies import get_current_user_id, get_db, get_org_id
from agency.models.tables import Organization, User


class Capability(StrEnum):
    """Everything a gated route can ask for. Adding one is a product decision."""

    READ = "read"
    CAMPAIGN_RUN = "campaign.run"
    CONTENT_APPROVE = "content.approve"
    PUBLISH_WRITE = "publish.write"
    CONTENT_OVERRIDE = "content.override"
    OAUTH_CONNECT = "oauth.connect"
    TEAM_MANAGE = "team.manage"
    BILLING_MANAGE = "billing.manage"


Role = Literal["owner", "admin", "member", "viewer"]
ROLES: tuple[Role, ...] = get_args(Role)

AccountType = Literal["personal", "business"]
ACCOUNT_TYPES: tuple[AccountType, ...] = get_args(AccountType)

#: The matrix. ``member`` may approve because approving is a human saying the copy
#: is fine and a member is a human; it may not publish or override, because publish
#: posts to a live client account and override bypasses moderation entirely.
CAPS: dict[Role, frozenset[Capability]] = {
    "owner": frozenset(
        {
            Capability.READ,
            Capability.CAMPAIGN_RUN,
            Capability.CONTENT_APPROVE,
            Capability.PUBLISH_WRITE,
            Capability.CONTENT_OVERRIDE,
            Capability.OAUTH_CONNECT,
            Capability.TEAM_MANAGE,
            Capability.BILLING_MANAGE,
        }
    ),
    "admin": frozenset(
        {
            Capability.READ,
            Capability.CAMPAIGN_RUN,
            Capability.CONTENT_APPROVE,
            Capability.PUBLISH_WRITE,
            Capability.CONTENT_OVERRIDE,
            Capability.OAUTH_CONNECT,
            Capability.TEAM_MANAGE,
        }
    ),
    "member": frozenset(
        {
            Capability.READ,
            Capability.CAMPAIGN_RUN,
            Capability.CONTENT_APPROVE,
        }
    ),
    "viewer": frozenset({Capability.READ}),
}

#: What ``account_type='personal'`` takes away: **nothing**, deliberately.
#:
#: This held ``team.manage`` until 260924, which deadlocked the account model. A
#: new org starts ``'personal'``; ``account_type`` only flips to ``'business'`` on
#: the first successful invite; and the invite route is gated on ``team.manage``.
#: So a personal org could never invite anyone and could therefore never become a
#: business one. Inviting a teammate *is* the upgrade — not something the upgrade
#: unlocks.
#:
#: Capabilities now depend on role alone. ``account_type`` drives UI affordances
#: (the nav hides Team for a solo account) and the one-way flip, not permissions.
#: The parameter and the subtraction survive so that a genuine personal-only
#: restriction has somewhere to live.
PERSONAL_DENIED: frozenset[Capability] = frozenset()

#: Pre-RBAC role strings still sitting in live rows. The migration rewrites them;
#: this map keeps a row that escaped it from silently losing every capability.
LEGACY_ROLE_MAP: dict[str, Role] = {"manager": "admin", "content_creator": "member"}

#: Where the resolved set is cached. ``request.state`` and nowhere else — a
#: module-level dict would outlive the request and survive a role change.
_STATE_ATTR = "rbac_capabilities"

_FORBIDDEN_CODE = "insufficient_permissions"


def normalize_role(role: str | None) -> Role | None:
    """Map a stored role string onto the four-role vocabulary, or ``None``.

    ``None`` means "not a role this system knows", which callers must treat as
    no capabilities rather than as a default.
    """
    if not role:
        return None
    candidate = LEGACY_ROLE_MAP.get(role, role)
    if candidate in CAPS:
        # No cast: ``CAPS`` is keyed by ``Role``, so membership narrows ``candidate``
        # on its own. mypy >= 1.20 reports an explicit cast here as redundant.
        return candidate
    return None


def capabilities_for(role: str, account_type: str) -> frozenset[Capability]:
    """The capability set for a ``(role, account_type)`` pair.

    An unrecognised role yields the empty set. An unrecognised *account type* is
    treated as ``personal`` — the narrower of the two — so a malformed column
    value subtracts capabilities rather than granting them.
    """
    normalized = normalize_role(role)
    if normalized is None:
        return frozenset()
    caps = CAPS[normalized]
    if account_type != "business":
        caps = caps - PERSONAL_DENIED
    return caps


def forbidden(cap: Capability) -> HTTPException:
    """The single 403 shape every gate raises."""
    return HTTPException(
        status.HTTP_403_FORBIDDEN,
        detail={"code": _FORBIDDEN_CODE, "required": str(cap)},
    )


async def resolve_capabilities(
    request: Request,
    user_id: UUID,
    org_id: UUID,
    db: AsyncSession,
) -> frozenset[Capability]:
    """Load the caller's capabilities, once per request.

    The ``users`` row must match **both** the token's subject and the request's
    org — there is no row-level security in this database, so a row found by id
    alone could belong to another tenant.
    """
    cached = getattr(request.state, _STATE_ATTR, None)
    if cached is not None:
        return cast(frozenset[Capability], cached)

    result = await db.execute(
        select(User.role, Organization.account_type)
        .join(Organization, Organization.id == User.org_id)
        .where(
            User.id == user_id,
            User.org_id == org_id,
            User.is_active.is_(True),
        )
    )
    row = result.first()
    caps: frozenset[Capability] = (
        frozenset() if row is None else capabilities_for(row[0], row[1])
    )
    setattr(request.state, _STATE_ATTR, caps)
    return caps


async def ensure_cap(
    cap: Capability,
    request: Request,
    user_id: UUID,
    org_id: UUID,
    db: AsyncSession,
) -> frozenset[Capability]:
    """Check a capability from *inside* a handler, after reading a request flag.

    Needed where the requirement depends on the body or query string — approving
    with ``?override=true`` needs ``content.override``, plain approval does not.
    Reuses the per-request cache, so it costs no extra read.
    """
    caps = await resolve_capabilities(request, user_id, org_id, db)
    if cap not in caps:
        raise forbidden(cap)
    return caps


def require_cap(
    cap: Capability,
) -> Callable[[Request, UUID, UUID, AsyncSession], Awaitable[frozenset[Capability]]]:
    """A FastAPI dependency that admits only callers holding ``cap``.

    Usage::

        @router.post("/{content_id}/publish",
                     dependencies=[Depends(require_cap(Capability.PUBLISH_WRITE))])
    """

    async def checker(
        request: Request,
        user_id: UUID = Depends(get_current_user_id),
        org_id: UUID = Depends(get_org_id),
        db: AsyncSession = Depends(get_db),
    ) -> frozenset[Capability]:
        caps = await resolve_capabilities(request, user_id, org_id, db)
        if cap not in caps:
            raise forbidden(cap)
        return caps

    return checker
