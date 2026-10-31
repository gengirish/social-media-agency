"""Client review links — a client approves or asks for changes without a login.

Replaces the org-slug portal (``/portal/{org_slug}``), which answered to anyone who
knew an agency's slug with **every** client's drafts and let them approve any of
them. A review link is the opposite shape:

* **One client.** Every query below filters on the link's ``org_id`` *and*
  ``client_id`` (and ``campaign_id`` when the link was made for one campaign). A
  content id from another client, campaign or org is a 404, never a decision.
* **A secret, not a name.** The URL carries a random token; only its SHA-256 is
  stored, the same pattern as ``services/api_keys.py``. Read access to the table is
  not the power to approve a client's posts, and a lost link cannot be shown again —
  the agency revokes it and makes another.
* **It ends.** Links expire (default 14 days, at most 30) and can be revoked. Both
  answer 410 so the page can say *why* it stopped working.

Approving goes through :func:`~agency.services.content_approval.approve_content_piece`
with ``override=False`` — the same moderation as the dashboard, and a client can
never wave a flag through. "Request changes" leaves the piece ``draft`` (Pending in
the Queue) with the comment in ``metadata.client_review``: ``rejected`` is not shown
on any Queue tab, so using it would make the client's feedback disappear.

Either decision notifies the person who made the link, linking to the Queue.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import (
    Campaign,
    Client,
    ClientReviewLink,
    ContentPiece,
    Organization,
    User,
)
from agency.services.content_approval import (
    APPROVED_VIA_CLIENT_LINK,
    ContentGateError,
    approve_content_piece,
    empty_content_reason,
)
from agency.services.notifications import create_notification
from agency.services.white_label import agency_branding

logger = structlog.get_logger()

TOKEN_PREFIX: Final = "rv_"
DEFAULT_TTL_DAYS: Final = 14
MAX_TTL_DAYS: Final = 30
COMMENT_MAX_CHARS: Final = 2000
NAME_MAX_CHARS: Final = 120
#: How many pieces one review page lists. A client reviews a batch, not an archive.
ITEM_LIMIT: Final = 100

DECISION_APPROVE: Final = "approve"
DECISION_REQUEST_CHANGES: Final = "request_changes"
DECISIONS: Final = frozenset({DECISION_APPROVE, DECISION_REQUEST_CHANGES})

#: ``metadata.client_review.decision`` values.
REVIEW_APPROVED: Final = "approved"
REVIEW_CHANGES_REQUESTED: Final = "changes_requested"
#: The client said yes but a gate stopped it (moderation, unscreened media): the
#: piece is still Pending and the agency has to look before anything moves.
REVIEW_APPROVAL_HELD: Final = "approval_held"

class ReviewLinkError(Exception):
    """A review-link refusal. ``detail`` is the structured API error body."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(code)
        self.status_code = status_code
        self.detail = {"code": code, "message": message}


@dataclass
class ResolvedLink:
    link: Any  # ClientReviewLink row; Any for the classic-Column reason in content_approval
    org: Any
    client: Any
    campaign: Any | None


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(value: datetime | None) -> datetime | None:
    """SQLite hands timezone columns back naive; every value written here is UTC."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    aware = _aware(value)
    return aware.isoformat() if aware else None


def link_state(link: Any, now: datetime | None = None) -> str:
    """``active``, ``revoked`` or ``expired`` — revocation wins, it is the deliberate act."""
    now = now or datetime.now(UTC)
    if link.revoked_at is not None:
        return "revoked"
    expires = _aware(link.expires_at)
    if expires is not None and expires <= now:
        return "expired"
    return "active"


def serialize_link(link: Any, *, campaign_name: str | None = None) -> dict[str, Any]:
    return {
        "id": str(link.id),
        "client_id": str(link.client_id),
        "campaign_id": str(link.campaign_id) if link.campaign_id else None,
        "campaign_name": campaign_name,
        "state": link_state(link),
        "expires_at": _iso(link.expires_at),
        "revoked_at": _iso(link.revoked_at),
        "last_used_at": _iso(link.last_used_at),
        "created_at": _iso(link.created_at),
    }


# ---------------------------------------------------------------------------
# Agency side (authenticated; the router supplies org_id from the token)
# ---------------------------------------------------------------------------
async def create_review_link(
    db: AsyncSession,
    *,
    org_id: UUID,
    client_id: UUID,
    campaign_id: UUID | None,
    created_by: UUID | None,
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> tuple[dict[str, Any], str]:
    """Create a link; returns ``(serialized link, raw token)``. The token is shown once.

    TENANCY: ``client_id`` and ``campaign_id`` arrive from the request, so both are
    resolved against ``org_id`` here (404 across orgs), and the campaign must belong
    to that client — otherwise a link for client A could be scoped to client B's
    campaign and list B's drafts.
    """
    if not 1 <= ttl_days <= MAX_TTL_DAYS:
        raise ReviewLinkError(
            400, "invalid_ttl", f"A review link can last 1 to {MAX_TTL_DAYS} days."
        )

    client = (
        await db.execute(
            select(Client).where(Client.id == client_id, Client.org_id == org_id)
        )
    ).scalar_one_or_none()
    if client is None:
        raise ReviewLinkError(404, "client_not_found", "Client not found.")
    if not client.is_active:
        raise ReviewLinkError(
            409, "client_archived", "This client is archived. Restore it to share posts."
        )

    campaign_name: str | None = None
    if campaign_id is not None:
        campaign = (
            await db.execute(
                select(Campaign).where(
                    Campaign.id == campaign_id,
                    Campaign.org_id == org_id,
                    Campaign.client_id == client_id,
                )
            )
        ).scalar_one_or_none()
        if campaign is None:
            raise ReviewLinkError(404, "campaign_not_found", "Campaign not found.")
        campaign_name = str(campaign.name)

    token = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    now = datetime.now(UTC)
    link = ClientReviewLink(
        org_id=org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        token_hash=_hash(token),
        created_by=created_by,
        expires_at=now + timedelta(days=ttl_days),
        created_at=now,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    logger.info(
        "client_review_link_created",
        org_id=str(org_id),
        client_id=str(client_id),
        campaign_id=str(campaign_id) if campaign_id else None,
        link_id=str(link.id),
        ttl_days=ttl_days,
    )
    return serialize_link(link, campaign_name=campaign_name), token


async def list_review_links(
    db: AsyncSession, *, org_id: UUID, client_id: UUID
) -> list[dict[str, Any]]:
    """Every link for one client, newest first. 404 when the client is not this org's."""
    owner = (
        await db.execute(
            select(Client.id).where(Client.id == client_id, Client.org_id == org_id)
        )
    ).scalar_one_or_none()
    if owner is None:
        raise ReviewLinkError(404, "client_not_found", "Client not found.")

    rows = (
        await db.execute(
            select(ClientReviewLink, Campaign.name)
            .outerjoin(
                Campaign,
                (Campaign.id == ClientReviewLink.campaign_id)
                & (Campaign.org_id == ClientReviewLink.org_id),
            )
            .where(
                ClientReviewLink.org_id == org_id,
                ClientReviewLink.client_id == client_id,
            )
            .order_by(ClientReviewLink.created_at.desc())
            .limit(50)
        )
    ).all()
    return [serialize_link(link, campaign_name=name) for link, name in rows]


async def revoke_review_link(db: AsyncSession, *, org_id: UUID, link_id: UUID) -> dict[str, Any]:
    """Revoke (idempotent). 404 for another org's link — never a silent no-op."""
    link = (
        await db.execute(
            select(ClientReviewLink).where(
                ClientReviewLink.id == link_id, ClientReviewLink.org_id == org_id
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise ReviewLinkError(404, "link_not_found", "Review link not found.")
    if link.revoked_at is None:
        link.revoked_at = datetime.now(UTC)
        await db.commit()
        logger.info("client_review_link_revoked", org_id=str(org_id), link_id=str(link_id))
    return serialize_link(link)


# ---------------------------------------------------------------------------
# Client side (unauthenticated; the token is the whole credential)
# ---------------------------------------------------------------------------
async def resolve_review_link(db: AsyncSession, token: str) -> ResolvedLink:
    """The link, org, client and campaign behind ``token``, or a 404/410.

    Unknown token → 404. Revoked / expired → 410 with a code saying which. An
    archived client or inactive org → 410 too: the agency stopped the work, and the
    client should be told the link ended rather than shown a broken page.
    """
    if not token.startswith(TOKEN_PREFIX):
        raise ReviewLinkError(404, "link_not_found", "This review link does not exist.")
    link = (
        await db.execute(
            select(ClientReviewLink).where(ClientReviewLink.token_hash == _hash(token))
        )
    ).scalar_one_or_none()
    if link is None:
        raise ReviewLinkError(404, "link_not_found", "This review link does not exist.")

    state = link_state(link)
    if state == "revoked":
        raise ReviewLinkError(
            410, "link_revoked", "This review link was turned off. Ask your agency for a new one."
        )
    if state == "expired":
        raise ReviewLinkError(
            410, "link_expired", "This review link has expired. Ask your agency for a new one."
        )

    org = (
        await db.execute(select(Organization).where(Organization.id == link.org_id))
    ).scalar_one_or_none()
    client = (
        await db.execute(
            select(Client).where(Client.id == link.client_id, Client.org_id == link.org_id)
        )
    ).scalar_one_or_none()
    if org is None or not org.is_active or client is None or not client.is_active:
        raise ReviewLinkError(
            410, "link_inactive", "This review link is no longer active."
        )

    campaign = None
    if link.campaign_id is not None:
        campaign = (
            await db.execute(
                select(Campaign).where(
                    Campaign.id == link.campaign_id,
                    Campaign.org_id == link.org_id,
                    Campaign.client_id == link.client_id,
                )
            )
        ).scalar_one_or_none()
        if campaign is None:
            raise ReviewLinkError(410, "link_inactive", "This review link is no longer active.")

    return ResolvedLink(link=link, org=org, client=client, campaign=campaign)


def _in_scope(resolved: ResolvedLink) -> list[Any]:
    """The WHERE clauses every client-side read and write must carry."""
    link = resolved.link
    clauses = [
        ContentPiece.org_id == link.org_id,
        ContentPiece.client_id == link.client_id,
    ]
    if link.campaign_id is not None:
        clauses.append(ContentPiece.campaign_id == link.campaign_id)
    return clauses


def _client_item(piece: Any) -> dict[str, Any]:
    """What the client sees of a piece — copy and state, nothing internal.

    Moderation issues are deliberately absent: they are notes for the agency, and a
    held approval is explained to the client in plain words instead.
    """
    review = (piece.metadata_ or {}).get("client_review") or None
    return {
        "id": str(piece.id),
        "platform": piece.platform,
        "content_type": piece.content_type,
        "title": piece.title or "",
        "body": piece.body or "",
        "hashtags": list(piece.hashtags or []),
        "media_urls": list(piece.media_urls or []),
        "status": "pending" if piece.status == "draft" else piece.status,
        "scheduled_at": _iso(piece.scheduled_at),
        "client_review": (
            {
                "decision": review.get("decision"),
                "comment": review.get("comment"),
                "name": review.get("name"),
                "at": review.get("at"),
            }
            if isinstance(review, dict)
            else None
        ),
    }


async def review_page(db: AsyncSession, resolved: ResolvedLink) -> dict[str, Any]:
    """Everything the public review page renders for this link.

    Lists the pieces waiting for a decision (Pending, with something in them) plus
    the ones this client already decided on, so a decision visibly sticks after a
    reload. Anything else of the client's — another campaign, an unrelated draft
    the agency is still writing that this link never covered — is not shown.
    """
    pieces: list[Any] = list(
        (
            await db.execute(
                select(ContentPiece)
                .where(
                    *_in_scope(resolved),
                    ContentPiece.status.in_(("draft", "approved", "scheduled", "published")),
                )
                .order_by(ContentPiece.created_at.desc())
                .limit(ITEM_LIMIT * 2)
            )
        )
        .scalars()
        .all()
    )
    pending: list[dict[str, Any]] = []
    decided: list[dict[str, Any]] = []
    for piece in pieces:
        review = (piece.metadata_ or {}).get("client_review")
        if piece.status == "draft" and empty_content_reason(piece) is None:
            pending.append(_client_item(piece))
        elif isinstance(review, dict) and review.get("decision"):
            decided.append(_client_item(piece))
    # "Last opened" for the agency's link list. Best effort — never fails the page.
    resolved.link.last_used_at = datetime.now(UTC)
    await db.commit()

    return {
        "agency": await agency_branding(db, resolved.org),
        "client": {"name": resolved.client.brand_name},
        "campaign": (
            {"id": str(resolved.campaign.id), "name": resolved.campaign.name}
            if resolved.campaign is not None
            else None
        ),
        "expires_at": _iso(resolved.link.expires_at),
        "pending": pending[:ITEM_LIMIT],
        "decided": decided[:ITEM_LIMIT],
    }


def _clean_text(value: Any, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


async def decide(
    db: AsyncSession,
    resolved: ResolvedLink,
    *,
    content_id: UUID,
    decision: str,
    comment: Any = None,
    reviewer_name: Any = None,
) -> dict[str, Any]:
    """Apply a client's decision to one piece. Returns ``{"item", "approved"}``.

    Raises :class:`ReviewLinkError`:

    - 400 ``invalid_decision`` / ``comment_required``.
    - 404 ``content_not_found`` — not in this link's scope (other client, campaign,
      org) or not something a client reviews.
    - 409 ``already_decided`` — no longer Pending (approved, edited back, posted…).
    - 409 ``approval_held`` — the client approved but a gate refused (moderation,
      unscreened media). The piece stays Pending, the agency is told, and the
      client's yes is kept in ``metadata.client_review`` so it is not lost.
    """
    if decision not in DECISIONS:
        raise ReviewLinkError(
            400, "invalid_decision", "decision must be 'approve' or 'request_changes'."
        )
    text = _clean_text(comment, COMMENT_MAX_CHARS)
    name = _clean_text(reviewer_name, NAME_MAX_CHARS) or None
    if decision == DECISION_REQUEST_CHANGES and not text:
        raise ReviewLinkError(
            400, "comment_required", "Say what should change so your agency can fix it."
        )

    piece: Any = (
        await db.execute(
            select(ContentPiece).where(ContentPiece.id == content_id, *_in_scope(resolved))
        )
    ).scalar_one_or_none()
    if piece is None:
        raise ReviewLinkError(404, "content_not_found", "That post is not part of this review.")
    if piece.status != "draft":
        raise ReviewLinkError(
            409, "already_decided", "This post is no longer waiting for review."
        )
    if empty_content_reason(piece) is not None:
        raise ReviewLinkError(404, "content_not_found", "That post is not part of this review.")

    now = datetime.now(UTC).isoformat()
    review: dict[str, Any] = {
        "at": now,
        "link_id": str(resolved.link.id),
        "name": name,
        "comment": text or None,
    }

    approved = False
    if decision == DECISION_APPROVE:
        try:
            await approve_content_piece(
                db,
                piece,
                org_id=resolved.link.org_id,
                override=False,
                user_id=None,
                via=APPROVED_VIA_CLIENT_LINK,
                reviewer_name=name,
            )
            review["decision"] = REVIEW_APPROVED
            approved = True
        except ContentGateError as exc:
            # The gate committed nothing to the piece. Keep the client's yes so the
            # agency sees it beside the flag, and do not tell the client the reason.
            review["decision"] = REVIEW_APPROVAL_HELD
            review["held_by"] = exc.detail.get("code")
    else:
        review["decision"] = REVIEW_CHANGES_REQUESTED

    meta = dict(piece.metadata_ or {})
    meta["client_review"] = review
    piece.metadata_ = meta
    resolved.link.last_used_at = datetime.now(UTC)
    await _notify_agency(db, resolved, piece, review)
    await db.commit()

    logger.info(
        "client_review_decision",
        org_id=str(resolved.link.org_id),
        client_id=str(resolved.link.client_id),
        link_id=str(resolved.link.id),
        content_id=str(piece.id),
        decision=review["decision"],
    )
    if review["decision"] == REVIEW_APPROVAL_HELD:
        raise ReviewLinkError(
            409,
            "approval_held",
            "Thanks — your agency needs to check this post before it can be approved. "
            "They have been told.",
        )
    return {"item": _client_item(piece), "approved": approved}


_NOTIFY_TITLES: Final = {
    REVIEW_APPROVED: "{client} approved a post",
    REVIEW_CHANGES_REQUESTED: "{client} asked for changes",
    REVIEW_APPROVAL_HELD: "{client} approved a post that moderation flagged",
}


async def _notify_agency(
    db: AsyncSession, resolved: ResolvedLink, piece: Any, review: dict[str, Any]
) -> None:
    """Tell the person who made the link. Nobody is told if that user is gone.

    One notification per decision, deliberately not digested: a client typically
    reviews a handful of posts, and a held approval needs acting on individually.
    """
    creator = resolved.link.created_by
    if creator is None:
        return
    active = (
        await db.execute(
            select(User.id).where(
                User.id == creator,
                User.org_id == resolved.link.org_id,
                User.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if active is None:
        logger.warning(
            "client_review_no_recipient",
            link_id=str(resolved.link.id),
            content_id=str(piece.id),
        )
        return
    decision = review["decision"]
    status = "approved" if decision == REVIEW_APPROVED else "draft"
    who = review.get("name") or resolved.client.brand_name
    excerpt = (piece.body or "").strip().replace("\n", " ")
    body = (
        f"“{review['comment']}” — on: {excerpt[:120]}"
        if review.get("comment")
        else excerpt[:160]
    )
    await create_notification(
        db,
        user_id=creator,
        org_id=resolved.link.org_id,
        type="client_review",
        title=_NOTIFY_TITLES[decision].format(client=who),
        body=body,
        data={
            "url": f"/content?client={resolved.link.client_id}&status={status}",
            "content_id": str(piece.id),
            "decision": decision,
        },
    )
