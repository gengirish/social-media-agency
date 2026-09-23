"""Signed OAuth ``state`` — carries the org and client through the provider redirect.

The provider echoes ``state`` back to our callback page unchanged. Signing it
(HS256 with ``JWT_SECRET``, 15-minute expiry) means the callback can trust
which client the connection was started for, and that the flow was started by
this org — the previous ``state`` was the bare org id, which neither
identified the client nor protected against a forged callback.
"""

from __future__ import annotations

import secrets
import time
from typing import Any
from uuid import UUID

from jose import JWTError, jwt

from agency.config import get_settings

STATE_TTL_SECONDS = 15 * 60
_TYP = "oauth_state"


class InvalidOAuthStateError(ValueError):
    pass


def _state_key() -> str:
    # A key derived from, not equal to, JWT_SECRET: the state travels through the
    # provider's URL, and must never verify as a login token (or vice versa).
    return f"{get_settings().jwt_secret}:oauth_state"


def sign_state(*, org_id: UUID, client_id: UUID | None, platform: str) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "typ": _TYP,
        "org": str(org_id),
        "plt": platform,
        "nonce": secrets.token_urlsafe(12),
        "iat": now,
        "exp": now + STATE_TTL_SECONDS,
    }
    if client_id is not None:
        claims["cid"] = str(client_id)
    token: str = jwt.encode(claims, _state_key(), algorithm="HS256")
    return token


def verify_state(state: str, *, org_id: UUID, platform: str) -> UUID | None:
    """The client id the flow was started for (``None`` if none). Raises on any mismatch."""
    try:
        claims = jwt.decode(state, _state_key(), algorithms=["HS256"])
    except JWTError as exc:
        raise InvalidOAuthStateError("OAuth state is invalid or expired") from exc
    if claims.get("typ") != _TYP or claims.get("plt") != platform:
        raise InvalidOAuthStateError("OAuth state does not match this platform")
    if claims.get("org") != str(org_id):
        raise InvalidOAuthStateError("OAuth state was issued to another workspace")
    cid = claims.get("cid")
    try:
        return UUID(str(cid)) if cid else None
    except ValueError as exc:
        raise InvalidOAuthStateError("OAuth state is malformed") from exc
