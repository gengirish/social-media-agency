"""OAuth router — platform connection flows for X, LinkedIn, Meta."""

import json
import urllib.parse
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from agency.config import get_settings
from agency.dependencies import get_current_user, get_db, get_org_id
from agency.models.tables import PlatformAccount

router = APIRouter(prefix="/oauth", tags=["OAuth"])


def _first_cors_origin(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("["):
        return json.loads(raw)[0]
    return raw.split(",")[0].strip()


OAUTH_CONFIGS = {
    "twitter": {
        "authorize_url": "https://twitter.com/i/oauth2/authorize",
        "token_url": "https://api.twitter.com/2/oauth2/token",
        "scopes": "tweet.read tweet.write users.read offline.access",
    },
    "linkedin": {
        "authorize_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "scopes": "openid profile w_member_social",
    },
    "facebook": {
        "authorize_url": "https://www.facebook.com/v18.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v18.0/oauth/access_token",
        "scopes": "pages_manage_posts,pages_read_engagement",
    },
}

PLATFORM_CLIENT_KEYS = {
    "twitter": ("twitter_client_id", "twitter_client_secret"),
    "linkedin": ("linkedin_client_id", "linkedin_client_secret"),
    "facebook": ("meta_app_id", "meta_app_secret"),
}


@router.get("/{platform}/authorize")
async def get_oauth_url(
    platform: str,
    user=Depends(get_current_user),
    org_id: UUID = Depends(get_org_id),
):
    """Return the OAuth authorization URL for a given platform."""
    if platform not in OAUTH_CONFIGS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unsupported platform: {platform}")

    settings = get_settings()
    key_attr, _ = PLATFORM_CLIENT_KEYS[platform]
    client_id = getattr(settings, key_attr, "")
    if not client_id:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            f"{platform} OAuth not configured. Set {key_attr.upper()} env var.",
        )

    config = OAUTH_CONFIGS[platform]
    callback_url = f"{_first_cors_origin(settings.cors_origins)}/api/oauth/{platform}/callback"

    params = {
        "client_id": client_id,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": config["scopes"],
        "state": str(org_id),
    }
    auth_url = f"{config['authorize_url']}?{urllib.parse.urlencode(params)}"
    return {"authorize_url": auth_url, "platform": platform}


@router.post("/{platform}/callback")
async def oauth_callback(
    platform: str,
    body: dict,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Exchange OAuth code for tokens and store platform account."""
    if platform not in OAUTH_CONFIGS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unsupported platform: {platform}")

    code = body.get("code")
    if not code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Authorization code required")

    settings = get_settings()
    key_attr, secret_attr = PLATFORM_CLIENT_KEYS[platform]
    client_id = getattr(settings, key_attr, "")
    client_secret = getattr(settings, secret_attr, "")

    config = OAUTH_CONFIGS[platform]
    callback_url = f"{_first_cors_origin(settings.cors_origins)}/api/oauth/{platform}/callback"

    async with httpx.AsyncClient() as client_http:
        token_resp = await client_http.post(
            config["token_url"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": callback_url,
            },
            headers={"Accept": "application/json"},
        )

    if token_resp.status_code != 200:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Token exchange failed: {token_resp.text}")

    token_data = token_resp.json()
    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")

    account_handle = body.get("account_handle", f"{platform}_user")
    display_name = body.get("display_name", account_handle)
    client_id_fk = body.get("client_id")

    if not client_id_fk:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "client_id required")

    account = PlatformAccount(
        client_id=UUID(client_id_fk),
        org_id=org_id,
        platform=platform,
        account_handle=account_handle,
        display_name=display_name,
        access_token_enc=access_token,
        refresh_token_enc=refresh_token,
        status="connected",
    )
    db.add(account)
    await db.commit()
    return {"status": "connected", "platform": platform, "account_handle": account_handle}


@router.delete("/{platform}/{account_id}")
async def disconnect_platform(
    platform: str,
    account_id: UUID,
    user=Depends(get_current_user),
    db=Depends(get_db),
    org_id: UUID = Depends(get_org_id),
):
    """Disconnect a platform account."""
    result = await db.execute(
        select(PlatformAccount).where(
            PlatformAccount.id == account_id,
            PlatformAccount.org_id == org_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")

    account.status = "disconnected"
    account.access_token_enc = None
    account.refresh_token_enc = None
    await db.commit()
    return {"status": "disconnected", "platform": platform}
