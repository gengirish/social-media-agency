from fastapi import APIRouter, Depends
from sqlalchemy import text

from agency.config import get_settings
from agency.dependencies import get_current_user, get_db

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health():
    return {"status": "healthy", "service": "campaignforge-api"}


@router.get("/db")
async def health_db(db=Depends(get_db)):
    # SQLAlchemy 2.x rejects a bare string here; it must be wrapped in text().
    await db.execute(text("SELECT 1"))
    return {"status": "healthy", "database": "connected"}


@router.get("/llm")
async def health_llm(user=Depends(get_current_user)):
    """Which provider and model serves each tier. Never returns key material.

    Authenticated because it exposes provider/model configuration.
    """
    from agency.services.llm_provider import describe_providers

    return describe_providers()


@router.get("/email")
async def health_email(user=Depends(get_current_user)):
    """Whether transactional email can actually send. Never returns key material.

    ``configured`` only means a key is present — that is *not* enough to send.
    ``sender_inbox`` is the live check: it resolves to None when the key is
    rejected or the sending domain is unverified in AgentMail, which is the exact
    state in which every team invite creates an account and silently mails
    nothing. Read ``can_send``, not ``configured``.

    Authenticated because it exposes sender configuration.
    """
    from agency.services.email_service import ensure_sender_inbox, is_configured

    configured = is_configured()
    inbox = await ensure_sender_inbox() if configured else None
    return {
        "configured": configured,
        "from_email": get_settings().agentmail_from_email,
        "sender_inbox": inbox,
        "can_send": bool(inbox),
    }
