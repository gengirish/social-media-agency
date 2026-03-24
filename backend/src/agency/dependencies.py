import time
from uuid import UUID

import httpx
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select

from agency.config import get_settings
from agency.models.database import get_session_factory
from agency.models.tables import Organization, Subscription, User

logger = structlog.get_logger()
security = HTTPBearer()

_jwks_cache: dict = {"keys": [], "fetched_at": 0.0}
_clerk_user_cache: dict[str, dict] = {}

JWKS_CACHE_TTL = 3600
CLERK_USER_CACHE_TTL = 300


async def get_db():
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def _fetch_jwks(url: str) -> list:
    now = time.time()
    if _jwks_cache["keys"] and (now - _jwks_cache["fetched_at"]) < JWKS_CACHE_TTL:
        return _jwks_cache["keys"]
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        keys = resp.json()["keys"]
        _jwks_cache["keys"] = keys
        _jwks_cache["fetched_at"] = now
        return keys


async def _verify_clerk_jwt(token: str, jwks_url: str) -> dict:
    keys = await _fetch_jwks(jwks_url)
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")

    rsa_key = next((k for k in keys if k.get("kid") == kid), None)
    if not rsa_key:
        _jwks_cache["fetched_at"] = 0.0
        keys = await _fetch_jwks(jwks_url)
        rsa_key = next((k for k in keys if k.get("kid") == kid), None)
        if not rsa_key:
            raise JWTError("No matching signing key")

    return jwt.decode(token, rsa_key, algorithms=["RS256"], options={"verify_aud": False})


async def _get_clerk_user_info(clerk_user_id: str, secret_key: str) -> dict:
    now = time.time()
    cached = _clerk_user_cache.get(clerk_user_id)
    if cached and (now - cached.get("_ts", 0)) < CLERK_USER_CACHE_TTL:
        return cached

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"https://api.clerk.com/v1/users/{clerk_user_id}",
            headers={"Authorization": f"Bearer {secret_key}"},
        )
        resp.raise_for_status()
        data = resp.json()
        data["_ts"] = now
        _clerk_user_cache[clerk_user_id] = data
        return data


async def _resolve_clerk_user(clerk_payload: dict, settings) -> dict:
    clerk_user_id = clerk_payload["sub"]

    clerk_info = await _get_clerk_user_info(clerk_user_id, settings.clerk_secret_key)
    email_list = clerk_info.get("email_addresses", [])
    email = next(
        (e["email_address"] for e in email_list if e.get("id") == clerk_info.get("primary_email_address_id")),
        email_list[0]["email_address"] if email_list else f"{clerk_user_id}@clerk.local",
    )
    full_name = f"{clerk_info.get('first_name') or ''} {clerk_info.get('last_name') or ''}".strip() or "User"

    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            logger.info("clerk_user_auto_provision", email=email, clerk_id=clerk_user_id)
            org = Organization(name=f"{full_name}'s Org")
            db.add(org)
            await db.flush()

            user = User(
                org_id=org.id,
                email=email,
                password_hash="clerk-managed",
                full_name=full_name,
                role="admin",
            )
            db.add(user)

            sub = Subscription(org_id=org.id, plan_tier="free", clients_limit=2, posts_limit=30)
            db.add(sub)
            await db.commit()
            await db.refresh(user)

    return {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "org_id": str(user.org_id),
    }


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    settings = get_settings()
    token = credentials.credentials

    if settings.clerk_jwks_url and settings.clerk_secret_key:
        try:
            clerk_payload = await _verify_clerk_jwt(token, settings.clerk_jwks_url)
            return await _resolve_clerk_user(clerk_payload, settings)
        except JWTError as exc:
            logger.debug("clerk_jwt_error", error=str(exc))
        except Exception as exc:
            logger.warning("clerk_auth_error", error=str(exc), error_type=type(exc).__name__)

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")


async def get_org_id(
    request: Request, user: dict = Depends(get_current_user)
) -> UUID:
    org_id = getattr(request.state, "org_id", None) or user.get("org_id")
    if not org_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Organization context required")
    return UUID(str(org_id))


def require_role(*allowed_roles: str):
    async def checker(user: dict = Depends(get_current_user)):
        if user.get("role") not in allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return checker
