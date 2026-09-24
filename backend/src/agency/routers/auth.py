from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.config import get_settings
from agency.dependencies import get_current_user_id, get_db, get_org_id
from agency.models.schemas import LoginRequest, SignupRequest, TokenResponse
from agency.models.tables import Client, Organization, Subscription, User
from agency.permissions import capabilities_for, normalize_role
from agency.services.billing import PLAN_CONFIG
from agency.utils.slug import unique_org_slug

router = APIRouter(prefix="/auth", tags=["Auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class MeResponse(BaseModel):
    """What the frontend needs to decide what to render.

    ``role`` and ``account_type`` come from the database, never from the token —
    a demotion has to take effect before the token expires. ``capabilities`` is
    the already-resolved set, so the client never reimplements the matrix.
    """

    user_id: str
    email: str
    role: str
    org_id: str
    account_type: str
    capabilities: list[str]


def _create_token(user_id: str, email: str, role: str, org_id: str) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
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

    # A brand-new org: its first user owns it, and it starts as a personal
    # account. ``account_type`` flips to 'business' one-way on the first team
    # invite or growth-tier purchase — it is never asked at sign-up.
    org = Organization(
        name=request.org_name,
        slug=await unique_org_slug(db, request.org_name),
        account_type="personal",
    )
    db.add(org)
    await db.flush()

    user = User(
        org_id=org.id,
        email=request.email,
        password_hash=pwd_context.hash(request.password),
        full_name=request.full_name,
        role="owner",
    )
    db.add(user)

    # ``Campaign.client_id`` is NOT NULL, so every org needs at least one client
    # from the moment it exists. A personal account keeps exactly this one and
    # the UI hides the picker; flipping to business just reveals it.
    db.add(Client(org_id=org.id, brand_name=request.org_name))

    free = PLAN_CONFIG["free"]
    subscription = Subscription(
        org_id=org.id,
        plan_tier="free",
        clients_limit=free["clients_limit"],
        posts_limit=free["posts_limit"],
        generations_limit=free["generations_limit"],
    )
    db.add(subscription)

    await db.commit()

    token = _create_token(str(user.id), user.email, user.role, str(org.id))
    return TokenResponse(access_token=token, role=user.role, org_id=str(org.id))


@router.get("/me", response_model=MeResponse)
async def me(
    user_id: UUID = Depends(get_current_user_id),
    org_id: UUID = Depends(get_org_id),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    """The caller's seat, resolved fresh from the database.

    Reachable by every authenticated caller including ``viewer`` — it carries no
    capability gate of its own, because a client that cannot read its own
    permissions cannot render anything.

    The row must match **both** the token subject and the request's org: there is
    no row-level security here, so an id alone could resolve another tenant's
    user. No match is a 404, not a degraded payload — a caller with no row has no
    capabilities and the frontend should treat that as broken, not as a viewer.
    """
    result = await db.execute(
        select(User.email, User.role, Organization.account_type)
        .join(Organization, Organization.id == User.org_id)
        .where(
            User.id == user_id,
            User.org_id == org_id,
            User.is_active.is_(True),
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "user_not_found"},
        )

    email, role, account_type = row
    return MeResponse(
        user_id=str(user_id),
        email=email,
        role=normalize_role(role) or role,
        org_id=str(org_id),
        account_type=account_type,
        capabilities=sorted(str(c) for c in capabilities_for(role, account_type)),
    )
