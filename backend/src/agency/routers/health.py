from fastapi import APIRouter, Depends
from sqlalchemy import text

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
