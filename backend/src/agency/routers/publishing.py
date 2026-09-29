"""Publishing API — immediate publish, schedule, calendar."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from agency.dependencies import get_current_user, get_current_user_id, get_db, get_org_id
from agency.models.tables import ContentPiece, PlatformAccount
from agency.permissions import Capability, require_cap
from agency.services import url_safety
from agency.services.billing import billing
from agency.services.content_approval import (
    ContentGateError,
    ensure_client_active,
    ensure_publishable,
    ensure_published,
    ensure_schedulable,
)
from agency.services.publishing import publisher
from agency.services.scheduler import scheduler

router = APIRouter(prefix="/publishing", tags=["Publishing"])


class ScheduleRequest(BaseModel):
    scheduled_at: datetime


class MarkPostedRequest(BaseModel):
    """Body of ``POST /{content_id}/mark-posted``.

    The link is **optional** on purpose: forcing it would strand anyone who posted
    from their phone, and the queue would fill with ``approved`` rows that are
    actually live. A wrong record is worse than a missing metric.
    """

    post_url: str | None = None


class PostUrlRequest(BaseModel):
    """Body of ``PATCH /{content_id}/post-url`` — the link, attached after the fact.

    Required here, unlike :class:`MarkPostedRequest`: this route exists precisely to
    supply the link that was skipped, so an empty one is a no-op worth refusing.
    """

    post_url: str


def _merge_metadata(piece: ContentPiece, updates: dict) -> None:
    base = dict(piece.metadata_ or {})
    base.update(updates)
    piece.metadata_ = base


def _piece_to_calendar_item(piece: ContentPiece) -> dict:
    return {
        "id": str(piece.id),
        "title": piece.title,
        "body": piece.body,
        "platform": piece.platform,
        "hashtags": list(piece.hashtags or []),
        "status": piece.status,
        "scheduled_at": piece.scheduled_at.isoformat() if piece.scheduled_at else None,
        "published_at": piece.published_at.isoformat() if piece.published_at else None,
        "client_id": str(piece.client_id),
        "campaign_id": str(piece.campaign_id) if piece.campaign_id else None,
        # ``"manual"`` for a piece a human posted by hand, otherwise ``None``. The
        # Queue and Calendar branch on it so they never say "Publishes <time>" about
        # something the product will not publish.
        "publish_mode": (piece.metadata_ or {}).get("publish_mode"),
    }


# CAPABILITY GATE: publishing posts to a client's live account, so it is
# owner/admin only — a ``member`` may approve copy but may not push it out.
# The gate lives here and nowhere deeper: ``services/scheduler.py::_publish_piece``
# runs on a timer with no user in scope, so the same check inside
# ``services/publishing.py`` would stop scheduled posts going out at 3am.
@router.post(
    "/{content_id}/publish",
    dependencies=[Depends(require_cap(Capability.PUBLISH_WRITE))],
)
async def publish_now(
    content_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Publish now. Only ``approved``/``scheduled`` content; otherwise
    409 ``{"code": "not_approved", "status": <current>}``."""
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id,
            ContentPiece.org_id == org_id,
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    # APPROVAL GATE: this posts to a client's live account. Only content that went
    # through moderated approval may be published — anything else (including an
    # already-published piece, so a double click cannot double-post) is a 409.
    try:
        ensure_publishable(piece)
        await ensure_client_active(db, piece)
    except ContentGateError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None

    if not await billing.check_quota(db, org_id, resource="posts"):
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            "Monthly post limit reached for your plan. Upgrade to publish more.",
        )

    # TENANCY: the ``org_id`` filter is load-bearing, not defence-in-depth — without it a
    # PlatformAccount row belonging to another tenant but carrying this client's id would
    # be selected here and the post published with that tenant's token.
    # ``first()`` (not ``scalar_one_or_none``) because an org may legitimately hold more
    # than one account for a client+platform; newest connection wins instead of a 500.
    acc_result = await db.execute(
        select(PlatformAccount)
        .where(
            PlatformAccount.org_id == org_id,
            PlatformAccount.client_id == piece.client_id,
            PlatformAccount.platform == piece.platform,
            PlatformAccount.status == "connected",
        )
        .order_by(PlatformAccount.created_at.desc())
    )
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No connected platform account for this content's platform",
        )

    content_data = {
        "body": piece.body,
        "hashtags": piece.hashtags or [],
        "title": piece.title,
    }
    credentials = {
        "access_token": account.access_token_enc,
        "page_id": account.account_handle,
    }

    pub_result = await publisher.publish(piece.platform, content_data, credentials)

    if pub_result.get("success"):
        piece.status = "published"
        piece.published_at = datetime.now(UTC)
        _merge_metadata(
            piece,
            {
                "post_id": pub_result.get("post_id"),
                "post_url": pub_result.get("url"),
                # A post that went out is no longer blocked or failing. Leaving
                # either behind would label a live post with a stale warning.
                "publish_blocked": None,
                "publish_error": None,
            },
        )
        await billing.record_post_published(db, org_id)
    else:
        piece.status = "failed"
        _merge_metadata(piece, {"publish_error": pub_result.get("error")})

    await db.commit()

    if not pub_result.get("success"):
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            pub_result.get("error", "Publish failed"),
        )

    return {
        "status": "published",
        "content_id": str(content_id),
        "post_id": pub_result.get("post_id"),
        "url": pub_result.get("url"),
    }


# CAPABILITY GATE: ``publish.manual``, not ``publish.write``. This route calls no
# publisher and needs no connected account — a human already posted, and all that
# happens here is bookkeeping. ``publish.write`` is withheld from ``member`` because
# publishing posts to a live client account; that premise is absent here, so a
# ``member`` (who already holds ``content.approve``) may record it. ``viewer`` may not.
@router.post(
    "/{content_id}/mark-posted",
    dependencies=[Depends(require_cap(Capability.PUBLISH_MANUAL))],
)
async def mark_posted(
    content_id: UUID,
    body: MarkPostedRequest,
    user_id: UUID = Depends(get_current_user_id),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Record that a human posted this piece by hand ("Post it yourself").

    Nothing is sent anywhere. Only ``approved``/``scheduled`` content, on a channel
    the org registered as manual, and it still costs a post against the plan —
    otherwise manual mode would be an unlimited free tier.

    - not ``approved``/``scheduled`` → 409 ``{"code": "not_approved", "status": <current>}``
      (an already-``published`` piece included, so a double click cannot double-count)
    - archived client → 409 ``{"code": "client_archived"}``
    - no ``manual`` channel for this client+platform → 400
    - plan exhausted → 402, and nothing is written
    """
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id,
            ContentPiece.org_id == org_id,
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    # APPROVAL GATE: manual mode is not a moderation bypass. Only content a human
    # approved may be recorded as posted, and an already-``published`` piece is
    # refused so a double click cannot double-count against the plan.
    try:
        ensure_publishable(piece)
        await ensure_client_active(db, piece)
    except ContentGateError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None

    # TENANCY: the ``org_id`` filter is load-bearing, not defence-in-depth — without it
    # another tenant's manual channel carrying this client's id would satisfy the check,
    # and this org could mark posts done on a channel it never registered.
    acc_result = await db.execute(
        select(PlatformAccount.id)
        .where(
            PlatformAccount.org_id == org_id,
            PlatformAccount.client_id == piece.client_id,
            PlatformAccount.platform == piece.platform,
            PlatformAccount.status == "manual",
        )
        .order_by(PlatformAccount.created_at.desc())
    )
    if acc_result.scalars().first() is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No manually managed channel for this content's platform. "
            "Add the page in Setup › Accounts first.",
        )

    # The link is only ever rendered as a link and opened in a new tab, so it gets the
    # shape check (scheme / credentials / host / port) and not ``assert_public_url``:
    # that one resolves the host, which would make recording a post do a DNS lookup and
    # fail on a link that is fine but momentarily unresolvable. Same call the manual
    # channel's ``profile_url`` goes through in ``routers/setup.py``.
    post_url = (body.post_url or "").strip() or None
    if post_url:
        try:
            post_url = url_safety.assert_safe_link(post_url)
        except url_safety.UnsafeURLError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None

    # QUOTA: ``posts_limit`` is the product's only usage meter and the plan copy sells
    # it as published posts. A free manual post would make manual mode an unlimited
    # free tier. Checked before anything is written, so a 402 leaves the row untouched.
    if not await billing.check_quota(db, org_id, resource="posts"):
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            "Monthly post limit reached for your plan. Upgrade to record more posts.",
        )

    piece.status = "published"
    piece.published_at = datetime.now(UTC)
    _merge_metadata(
        piece,
        {
            "publish_mode": "manual",
            # Self-reported, so who said it matters.
            "posted_by": str(user_id),
            "post_url": post_url,
            # A post that is live is no longer blocked or failing. Leaving either
            # behind would label a live post with a stale warning.
            "publish_blocked": None,
            "publish_error": None,
        },
    )
    await billing.record_post_published(db, org_id)
    await db.commit()

    return {
        "status": "published",
        "content_id": str(content_id),
        "publish_mode": "manual",
        "post_url": post_url,
    }


# CAPABILITY GATE: ``publish.manual``, the same bookkeeping capability as
# ``mark-posted`` — this route posts nothing either, it writes down where a post a
# human already made ended up. ``member`` holds it, ``viewer`` does not.
@router.patch(
    "/{content_id}/post-url",
    dependencies=[Depends(require_cap(Capability.PUBLISH_MANUAL))],
)
async def set_post_url(
    content_id: UUID,
    body: PostUrlRequest,
    user_id: UUID = Depends(get_current_user_id),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Attach the link to a post that is already live ("Add link").

    The link is optional at ``mark-posted`` time, because forcing it would strand
    anyone who posted from their phone. This is how it arrives later, and the
    affordance never expires.

    **This is the one field an edit may change without re-moderation.** Everywhere
    else, editing an approved piece resets it to ``draft`` so the copy is checked
    again (``services/content_approval.py::apply_content_edit``). That reasoning does
    not apply here: the link is a *record of reality*, not the copy. Nothing about
    what was published changes, so ``status``, ``published_at`` and the moderation
    record are all left exactly as they are.

    - not ``published`` → 409 ``{"code": "not_published", "status": <current>}``
    - an unsafe link → 400, and nothing is written
    """
    # TENANCY: the ``org_id`` filter is load-bearing, not defence-in-depth — without it
    # any caller could write a link of their choosing onto another tenant's published
    # post, which the Queue then renders and their colleagues click.
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id,
            ContentPiece.org_id == org_id,
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    # Only a live post has a link to record. Checked before the URL so the caller hears
    # the real reason rather than a URL complaint about a piece that is not live anyway.
    try:
        ensure_published(piece)
    except ContentGateError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None

    # Shape check only, as in ``mark_posted``: the browser opens this link, the server
    # never fetches it, and ``assert_public_url`` would resolve the host — making a link
    # pasted from a phone fail for being momentarily unresolvable.
    try:
        post_url = url_safety.assert_safe_link(body.post_url)
    except url_safety.UnsafeURLError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None

    # ``post_url`` and nothing else. No status change, no ``published_at`` touch, no
    # reset to ``draft``.
    _merge_metadata(piece, {"post_url": post_url, "post_url_by": str(user_id)})
    await db.commit()

    return {"content_id": str(content_id), "post_url": post_url}


# CAPABILITY GATE: scheduling is publishing with a delay — the scheduler posts
# whatever is ``scheduled`` when it comes due — so it needs the same capability.
@router.post(
    "/{content_id}/schedule",
    dependencies=[Depends(require_cap(Capability.PUBLISH_WRITE))],
)
async def schedule_content(
    content_id: UUID,
    body: ScheduleRequest,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Schedule (or reschedule). Only ``approved``/``scheduled`` content; otherwise
    409 ``{"code": "not_approved", "status": <current>}``. Platforms with no working
    publisher → 409 ``{"code": "platform_unavailable"}`` — unless the channel is
    manual, where the due time is a reminder to a human and no publisher is needed."""
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id,
            ContentPiece.org_id == org_id,
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found")

    # APPROVAL GATE: the scheduler publishes whatever is ``scheduled`` when it comes
    # due, so scheduling is the last point a human-approval check can happen.
    try:
        await ensure_schedulable(db, piece)
        await ensure_client_active(db, piece)
    except ContentGateError as exc:
        raise HTTPException(exc.status_code, exc.detail) from None

    out = await scheduler.schedule_content(db, content_id, body.scheduled_at)
    if out.get("error"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, out["error"])
    return out


@router.get("/calendar")
async def get_calendar(
    start: datetime = Query(..., description="Range start (UTC)"),
    end: datetime = Query(..., description="Range end (UTC)"),
    client_id: UUID | None = Query(None, description="Only this client's posts"),
    include_pending: bool = Query(
        False, description="Also return drafts/approved posts with a planned day, and failed ones"
    ),
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    # ``client_id`` needs no separate ownership check: the query is already
    # ``org_id``-filtered, so a foreign client id simply matches nothing.
    pieces = await scheduler.get_calendar(
        db, org_id, start, end, client_id=client_id, include_pending=include_pending
    )
    return {"items": [_piece_to_calendar_item(p) for p in pieces]}
