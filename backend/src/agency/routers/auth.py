import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select

from agency.config import get_settings
from agency.dependencies import get_db
from agency.models.schemas import LoginRequest, SignupRequest, TokenResponse
from agency.models.tables import Organization, Subscription, User

router = APIRouter(prefix="/auth", tags=["Auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _create_token(user_id: str, email: str, role: str, org_id: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "org_id": org_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db=Depends(get_db)):
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if not user or not pwd_context.verify(request.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account deactivated")

    token = _create_token(str(user.id), user.email, user.role, str(user.org_id))
    return TokenResponse(access_token=token, role=user.role, org_id=str(user.org_id))


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(request: SignupRequest, db=Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == request.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    org = Organization(name=request.org_name)
    db.add(org)
    await db.flush()

    user = User(
        org_id=org.id,
        email=request.email,
        password_hash=pwd_context.hash(request.password),
        full_name=request.full_name,
        role="admin",
    )
    db.add(user)

    subscription = Subscription(
        org_id=org.id,
        plan_tier="free",
        clients_limit=2,
        posts_limit=30,
    )
    db.add(subscription)

    await db.commit()

    token = _create_token(str(user.id), user.email, user.role, str(org.id))
    return TokenResponse(access_token=token, role=user.role, org_id=str(org.id))
