"""Platform publishing service — posts approved content to X, LinkedIn, Meta."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx
import structlog

from agency.config import get_settings

logger = structlog.get_logger()

T = TypeVar("T")


class PlatformPublisher:
    """Handles publishing content to social media platforms."""

    def __init__(self):
        self.settings = get_settings()

    def _decrypt_token(self, encrypted: str) -> str:
        """Decrypt platform token. Currently passthrough — add Fernet in production."""
        return encrypted

    async def _with_http_retries(
        self,
        op: Callable[[], Awaitable[T]],
        *,
        max_retries: int = 2,
    ) -> T:
        """Run an async HTTP operation with retries on transient failures."""
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return await op()
            except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as e:
                last_error = e
                logger.warning(
                    "publish_http_retry",
                    attempt=attempt,
                    max_retries=max_retries,
                    error=str(e),
                )
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(0.5 * (2**attempt))
        raise last_error  # pragma: no cover

    async def publish(self, platform: str, content: dict, credentials: dict) -> dict:
        """Route to platform-specific publisher."""
        publishers = {
            "twitter": self._publish_twitter,
            "linkedin": self._publish_linkedin,
            "facebook": self._publish_facebook,
            "instagram": self._publish_instagram,
        }
        publisher = publishers.get(platform)
        if not publisher:
            return {"success": False, "error": f"Unsupported platform: {platform}"}

        creds = dict(credentials)
        if "access_token" in creds and creds["access_token"] is not None:
            creds["access_token"] = self._decrypt_token(str(creds["access_token"]))

        try:
            result = await publisher(content, creds)
            logger.info("content_published", platform=platform, post_id=result.get("post_id"))
            return {"success": True, **result}
        except Exception as e:
            logger.error("publish_failed", platform=platform, error=str(e))
            return {"success": False, "error": str(e)}

    async def _publish_twitter(self, content: dict, credentials: dict) -> dict:
        """Post to X/Twitter using v2 API."""
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {credentials['access_token']}"}
            body = content.get("body", "")
            hashtags = content.get("hashtags", [])
            if hashtags:
                body += "\n\n" + " ".join(f"#{tag}" for tag in hashtags[:5])

            # Truncate to 280 chars
            if len(body) > 280:
                body = body[:277] + "..."

            async def do_post():
                resp = await client.post(
                    "https://api.x.com/2/tweets",
                    headers=headers,
                    json={"text": body},
                )
                resp.raise_for_status()
                return resp.json()

            data = await self._with_http_retries(do_post)
            return {
                "post_id": data["data"]["id"],
                "url": f"https://x.com/i/status/{data['data']['id']}",
            }

    async def _publish_linkedin(self, content: dict, credentials: dict) -> dict:
        """Post to LinkedIn using v2 API."""
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"Bearer {credentials['access_token']}",
                "X-Restli-Protocol-Version": "2.0.0",
            }

            async def do_me():
                me_resp = await client.get("https://api.linkedin.com/v2/userinfo", headers=headers)
                me_resp.raise_for_status()
                return me_resp.json()

            me_data = await self._with_http_retries(do_me)
            user_sub = me_data["sub"]
            author_urn = f"urn:li:person:{user_sub}"

            body = content.get("body", "")
            hashtags = content.get("hashtags", [])
            if hashtags:
                body += "\n\n" + " ".join(f"#{tag}" for tag in hashtags[:10])

            post_data = {
                "author": author_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": body},
                        "shareMediaCategory": "NONE",
                    }
                },
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
            }

            async def do_post():
                resp = await client.post(
                    "https://api.linkedin.com/v2/ugcPosts", headers=headers, json=post_data
                )
                resp.raise_for_status()
                return resp

            resp = await self._with_http_retries(do_post)
            post_id = resp.headers.get("X-RestLi-Id", resp.json().get("id", ""))
            return {"post_id": post_id, "url": f"https://linkedin.com/feed/update/{post_id}"}

    async def _publish_facebook(self, content: dict, credentials: dict) -> dict:
        """Post to Facebook Page."""
        async with httpx.AsyncClient() as client:
            page_id = credentials.get("page_id", "me")
            body = content.get("body", "")

            async def do_post():
                resp = await client.post(
                    f"https://graph.facebook.com/v19.0/{page_id}/feed",
                    params={"access_token": credentials["access_token"]},
                    json={"message": body},
                )
                resp.raise_for_status()
                return resp.json()

            data = await self._with_http_retries(do_post)
            return {"post_id": data["id"], "url": f"https://facebook.com/{data['id']}"}

    async def _publish_instagram(self, content: dict, credentials: dict) -> dict:
        """Post to Instagram (requires media URL — not implemented)."""
        return {
            "post_id": "",
            "url": "",
            "message": (
                "Instagram publishing is not available yet. "
                "Text-only posts are not supported; implementation requires uploading media "
                "through the Meta Graph API (container + publish flow)."
            ),
        }


publisher = PlatformPublisher()
