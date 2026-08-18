"""`get_current_user` must not report every failure as `401 Invalid token`.

The router previously tried Clerk first and, on *any* Clerk exception, fell
through to the local HS256 branch whose only error is a flat 401. An expired
session, an unset CLERK_SECRET_KEY, an unreachable JWKS endpoint and a database
failure during auto-provisioning all produced the same response, and the real
cause was logged at debug level. These tests pin each mode to a distinct answer.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt

from agency import dependencies as deps

JWT_SECRET = "test-secret"

# Throwaway RS256 keypair. Generated per-run so no key material lives in the repo.
_RSA = None


def _rsa() -> Any:
    global _RSA
    if _RSA is None:
        from cryptography.hazmat.primitives.asymmetric import rsa

        _RSA = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return _RSA


def _rs256_token(exp_offset: int = 300) -> str:
    from cryptography.hazmat.primitives import serialization

    pem = (
        _rsa()
        .private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        .decode()
    )
    now = int(time.time())
    return jwt.encode(
        {"sub": "user_clerk_123", "iat": now, "exp": now + exp_offset},
        pem,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _configure_clerk(monkeypatch: pytest.MonkeyPatch, on: bool) -> None:
    settings = deps.get_settings()
    monkeypatch.setattr(
        settings, "clerk_jwks_url", "https://example.test/jwks.json" if on else "", raising=False
    )
    monkeypatch.setattr(settings, "clerk_secret_key", "sk_test" if on else "", raising=False)
    monkeypatch.setattr(settings, "jwt_secret", JWT_SECRET, raising=False)
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256", raising=False)


async def test_local_hs256_token_still_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dual-mode fallback is deliberate — an HS256 token must keep working."""
    _configure_clerk(monkeypatch, on=True)
    token = jwt.encode({"sub": "abc", "org_id": "def"}, JWT_SECRET, algorithm="HS256")

    payload = await deps.get_current_user(_creds(token))

    assert payload["sub"] == "abc"


async def test_expired_local_token_says_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_clerk(monkeypatch, on=False)
    now = int(time.time())
    token = jwt.encode({"sub": "abc", "exp": now - 60}, JWT_SECRET, algorithm="HS256")

    with pytest.raises(HTTPException) as err:
        await deps.get_current_user(_creds(token))

    assert err.value.status_code == 401
    assert err.value.detail == "Token expired"


async def test_expired_clerk_token_says_expired_not_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reported symptom: a replayed 60-second Clerk token."""
    _configure_clerk(monkeypatch, on=True)

    async def _fake_jwks(url: str) -> list:
        from jose import jwk

        pub = jwk.construct(_rsa().public_key(), algorithm="RS256").to_dict()
        pub["kid"] = "test-kid"
        return [pub]

    monkeypatch.setattr(deps, "_fetch_jwks", _fake_jwks)

    with pytest.raises(HTTPException) as err:
        await deps.get_current_user(_creds(_rs256_token(exp_offset=-60)))

    assert err.value.status_code == 401
    assert err.value.detail == "Token expired"


async def test_clerk_token_without_clerk_configured_is_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A server misconfiguration must not masquerade as a bad credential."""
    _configure_clerk(monkeypatch, on=False)

    with pytest.raises(HTTPException) as err:
        await deps.get_current_user(_creds(_rs256_token()))

    assert err.value.status_code == 503


async def test_jwks_outage_is_503_not_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unreachable Clerk is an upstream outage, not an invalid token."""
    _configure_clerk(monkeypatch, on=True)

    async def _boom(url: str) -> list:
        raise httpx.ConnectError("clerk unreachable")

    monkeypatch.setattr(deps, "_fetch_jwks", _boom)

    with pytest.raises(HTTPException) as err:
        await deps.get_current_user(_creds(_rs256_token()))

    assert err.value.status_code == 503


async def test_user_resolution_failure_is_503_not_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """Signature already proved the credential; a DB/Clerk-API fault is not a 401."""
    _configure_clerk(monkeypatch, on=True)

    async def _fake_jwks(url: str) -> list:
        from jose import jwk

        pub = jwk.construct(_rsa().public_key(), algorithm="RS256").to_dict()
        pub["kid"] = "test-kid"
        return [pub]

    async def _boom(payload: dict, settings: Any) -> dict:
        raise RuntimeError("database is down")

    monkeypatch.setattr(deps, "_fetch_jwks", _fake_jwks)
    monkeypatch.setattr(deps, "_resolve_clerk_user", _boom)

    with pytest.raises(HTTPException) as err:
        await deps.get_current_user(_creds(_rs256_token()))

    assert err.value.status_code == 503


async def test_garbage_token_is_401_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_clerk(monkeypatch, on=True)

    with pytest.raises(HTTPException) as err:
        await deps.get_current_user(_creds("not-a-jwt"))

    assert err.value.status_code == 401
    assert err.value.detail == "Invalid token"
