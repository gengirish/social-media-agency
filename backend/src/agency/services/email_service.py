"""Transactional email via AgentMail.

Mail leaves from one shared sender inbox — ``AGENTMAIL_FROM_EMAIL``, default
``alerts@intelliforge.tech`` — unless the org carries its own
``agentmail_inbox_id``, which wins. Nothing provisions per-org inboxes yet, so
in practice every message sends from the shared address.

Best-effort by contract: a missing API key, an unverified sending domain, or an
AgentMail outage yields ``SendResult(sent=False, reason=...)``. Callers always
get a value back, never an exception — a failed notification must not fail the
request that triggered it. Callers are expected to surface ``sent`` honestly
rather than claiming an email went out.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.config import get_settings
from agency.models.tables import Organization

logger = structlog.get_logger()

# Shown as the friendly From: name on the shared sender inbox.
SENDER_DISPLAY_NAME = "CampaignForge"

_client: Any | None = None
_sender_inbox_id: str | None = None
_sender_lock = asyncio.Lock()


@dataclass(frozen=True)
class SendResult:
    """Outcome of one send. ``reason`` is empty when ``sent`` is True."""

    sent: bool
    reason: str = ""
    inbox_id: str | None = None


def reset_cache() -> None:
    """Drop the memoized client and sender inbox. For tests and key rotation."""
    global _client, _sender_inbox_id
    _client = None
    _sender_inbox_id = None


def is_configured() -> bool:
    """True when an API key is present. Says nothing about the domain."""
    return bool(get_settings().agentmail_api_key)


def _get_client() -> Any | None:
    """Memoized AsyncAgentMail client, or None when no API key is set."""
    global _client
    if _client is not None:
        return _client
    settings = get_settings()
    if not settings.agentmail_api_key:
        return None
    from agentmail import AsyncAgentMail

    _client = AsyncAgentMail(api_key=settings.agentmail_api_key)
    return _client


def _split_address(address: str) -> tuple[str, str]:
    """Split ``alerts@intelliforge.tech`` into username and domain.

    A bare username falls back to ``AGENTMAIL_DEFAULT_DOMAIN``, and an empty
    domain means AgentMail's own ``agentmail.to`` — which is what you get on a
    fresh account before a custom domain is verified.
    """
    if "@" in address:
        username, _, domain = address.partition("@")
        return username, domain
    return address, get_settings().agentmail_default_domain


async def ensure_sender_inbox() -> str | None:
    """Return the shared sender inbox id, creating it on first use.

    The id *is* the email address. Returns None when AgentMail is unconfigured
    or the inbox cannot be created — most often because the sending domain is
    not verified in AgentMail yet.
    """
    global _sender_inbox_id
    if _sender_inbox_id is not None:
        return _sender_inbox_id

    client = _get_client()
    if client is None:
        return None

    address = get_settings().agentmail_from_email
    if not address:
        return None

    async with _sender_lock:
        # Another coroutine may have won the race while we waited on the lock.
        if _sender_inbox_id is not None:
            return _sender_inbox_id

        from agentmail.errors import IsTakenError, NotFoundError

        try:
            inbox = await client.inboxes.get(address)
            _sender_inbox_id = str(inbox.inbox_id)
            return _sender_inbox_id
        except NotFoundError:
            pass
        except Exception as e:  # noqa: BLE001 — network/auth failures degrade to "no sender"
            logger.warning("agentmail_sender_lookup_failed", address=address, error=str(e))
            return None

        from agentmail.inboxes import CreateInboxRequest

        username, domain = _split_address(address)
        request = CreateInboxRequest(
            username=username,
            domain=domain or None,
            display_name=SENDER_DISPLAY_NAME,
            client_id=f"campaignforge-sender-{username}",
        )
        try:
            inbox = await client.inboxes.create(request=request)
            _sender_inbox_id = str(inbox.inbox_id)
            logger.info("agentmail_sender_inbox_created", inbox_id=_sender_inbox_id)
            return _sender_inbox_id
        except IsTakenError:
            # Someone else's account holds the address, or it was created between
            # our get and our create. Either way the address is not ours to use
            # blindly, so trust the get above and treat this as unavailable.
            logger.warning("agentmail_sender_inbox_taken", address=address)
            return None
        except Exception as e:  # noqa: BLE001 — unverified domain lands here
            logger.warning(
                "agentmail_sender_inbox_create_failed",
                address=address,
                domain=domain,
                error=str(e),
            )
            return None


async def resolve_sender(db: AsyncSession | None = None, org_id: UUID | None = None) -> str | None:
    """Pick the inbox a message for ``org_id`` should send from.

    The org's own ``agentmail_inbox_id`` wins when set; otherwise the shared
    sender inbox. Returns None when neither is available.
    """
    if db is not None and org_id is not None:
        row = await db.execute(select(Organization).where(Organization.id == org_id))
        org = row.scalar_one_or_none()
        if org is not None and org.agentmail_inbox_id:
            return str(org.agentmail_inbox_id)
    return await ensure_sender_inbox()


async def send_email(
    *,
    to: str | list[str],
    subject: str,
    text: str,
    html: str | None = None,
    db: AsyncSession | None = None,
    org_id: UUID | None = None,
    labels: list[str] | None = None,
    reply_to: str | None = None,
) -> SendResult:
    """Send one transactional email. Never raises.

    Pass ``db`` + ``org_id`` to let an org-owned inbox override the shared
    sender. Always send ``text``; ``html`` is optional but improves rendering.
    """
    client = _get_client()
    if client is None:
        return SendResult(False, "AgentMail is not configured (AGENTMAIL_API_KEY is unset).")

    inbox_id = await resolve_sender(db, org_id)
    if not inbox_id:
        return SendResult(
            False,
            "AgentMail has no usable sender inbox — check that the sending domain is "
            "verified in AgentMail.",
        )

    payload: dict[str, Any] = {"to": to, "subject": subject, "text": text}
    if html is not None:
        payload["html"] = html
    if labels:
        payload["labels"] = labels
    if reply_to is not None:
        payload["reply_to"] = reply_to

    try:
        await client.inboxes.messages.send(inbox_id, **payload)
    except Exception as e:  # noqa: BLE001 — the caller's request must still succeed
        logger.warning(
            "agentmail_send_failed", inbox_id=inbox_id, subject=subject, error=str(e)
        )
        return SendResult(False, f"AgentMail send failed: {e}", inbox_id)

    logger.info("agentmail_send_ok", inbox_id=inbox_id, subject=subject, labels=labels or [])
    return SendResult(True, "", inbox_id)
