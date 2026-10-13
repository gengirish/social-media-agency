"""Media generation quota. Separate from the text generation counter, on purpose.

STAGE 1 CONTRACT — signatures and semantics are frozen; bodies are Phase 3.
Fill these in place. Do not change a signature, and do not edit `billing.py`,
`config.py` or `tables.py`: everything this module needs already exists there
(``media_credits_limit_for``, ``video_limits_for``, ``media_credit_weight``,
``Subscription.media_credits_used`` / ``videos_used``). If something seems
missing, report it rather than editing a shared file — another agent is in it.

Why not ``generation_quota.py``: one video can cost an order of magnitude more
than one LLM call. Charging both against ``generations_used`` lets an
agency-tier org (``generations_limit`` 9999 at $168/mo) run up provider spend
far above its revenue, and the meter would read as if nothing unusual happened.

Two steps, like the text quota: ``require_media_credits`` before calling the
provider, ``charge_media_credits`` only after a usable result came back.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import Subscription


def media_quota_exceeded(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_402_PAYMENT_REQUIRED,
        detail={"code": "media_credit_quota_exceeded", "message": detail},
    )


def video_not_in_plan(detail: str) -> HTTPException:
    """Distinct code from a quota error: the UI must offer an upgrade, not a wait."""
    return HTTPException(
        status.HTTP_402_PAYMENT_REQUIRED,
        detail={"code": "media_video_not_in_plan", "message": detail},
    )


async def require_media_credits(db: AsyncSession, org_id: UUID, kind: str) -> Subscription:
    """402 unless the org can generate one ``kind`` right now.

    Checks, in this order:

    1. a subscription exists;
    2. ``kind`` is video → the tier allows video at all (``video_limits_for``),
       else :func:`video_not_in_plan`;
    3. ``kind`` is video → ``videos_used`` is under the tier's clip cap. The cap
       applies on **every** tier including agency, whose 9999 is a sentinel
       meaning unlimited — and unlimited video generation is unbounded loss;
    4. ``media_credits_used + media_credit_weight(kind)`` fits inside
       ``media_credits_limit_for(sub)``. Weight-aware, not a bare ``< limit``:
       a 10-credit video must not slip through on the last credit.

    Returns the subscription so the caller can avoid a second load.
    """
    raise NotImplementedError("Phase 3")


async def charge_media_credits(db: AsyncSession, org_id: UUID, kind: str) -> int:
    """Charge one successful generation. Returns the credits actually charged.

    **Must be atomic**, unlike ``charge_generation``. That one tolerates a
    two-statement check-then-increment because overshooting an Amplify pack by
    one costs pennies; overshooting video costs real money. Use a conditional
    update —

        UPDATE subscription
           SET media_credits_used = media_credits_used + :weight,
               videos_used = videos_used + :is_video
         WHERE org_id = :org_id
           AND media_credits_used + :weight <= :limit
     RETURNING media_credits_used

    — and treat zero rows as a lost race: raise :func:`media_quota_exceeded`.
    The caller has already generated at that point, so log it (``media_charge_lost_race``)
    and do not save the asset; a charge that did not land must not become free
    media. Caller commits.
    """
    raise NotImplementedError("Phase 3")
