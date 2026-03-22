from fastapi import APIRouter, Depends

from agency.dependencies import get_db

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health():
    return {"status": "healthy", "service": "campaignforge-api"}


@router.get("/db")
async def health_db(db=Depends(get_db)):
    result = await db.execute("SELECT 1")
    return {"status": "healthy", "database": "connected"}
