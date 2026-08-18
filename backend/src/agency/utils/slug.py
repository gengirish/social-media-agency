"""Org slug generation for the client portal.

``Organization.slug`` is the *only* key the portal resolves on, because portal routes
are unauthenticated: whatever column identifies an org there has to be unique, or one
org's slug can shadow another's namespace. ``name`` and ``domain`` are both non-unique,
which is why neither is usable for this.
"""

import re
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_NON_SLUG = re.compile(r"[^a-z0-9]+")
MAX_SLUG_LENGTH = 64

# Reserved because a portal URL is ``/portal/{slug}`` and these would collide with
# frontend routes or read as something the org does not own.
RESERVED_SLUGS = frozenset({"admin", "api", "portal", "sign-in", "sign-up", "static", "www"})


def slugify(value: str) -> str:
    """Lowercase, hyphen-separated, ASCII-only. Empty input yields ``"org"``."""
    slug = _NON_SLUG.sub("-", value.strip().lower()).strip("-")[:MAX_SLUG_LENGTH].strip("-")
    return slug or "org"


async def unique_org_slug(db: AsyncSession, name: str) -> str:
    """A slug derived from ``name`` that no other organization holds.

    Collisions get a short random suffix rather than a counter — a counter needs a
    read-then-write that two concurrent signups can both pass.
    """
    from agency.models.tables import Organization

    base = slugify(name)
    candidate = base if base not in RESERVED_SLUGS else f"{base}-org"

    for _ in range(5):
        existing = await db.execute(
            select(Organization.id).where(Organization.slug == candidate)
        )
        if existing.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base[: MAX_SLUG_LENGTH - 7]}-{uuid4().hex[:6]}"

    return f"org-{uuid4().hex[:12]}"
