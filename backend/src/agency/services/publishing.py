"""Platform publishing service — posts approved content to X, LinkedIn, Meta."""

import httpx
import structlog

from agency.config import get_settings

logger = structlog.get_logger()


class PlatformPublisher:
    """Handles publishing content to social media platforms."""

    def __init__(self):
        self.settings = get_settings()

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

        try:
            result = await publisher(content, credentials)
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

            resp = await client.post(
                "https://api.x.com/2/tweets",
                headers=headers,
                json={"text": body},
            )
            resp.raise_for_status()
            data = resp.json()
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

            # Get user URN
            me_resp = await client.get("https://api.linkedin.com/v2/userinfo", headers=headers)
            me_resp.raise_for_status()
            user_sub = me_resp.json()["sub"]
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

            resp = await client.post(
                "https://api.linkedin.com/v2/ugcPosts", headers=headers, json=post_data
            )
            resp.raise_for_status()
            post_id = resp.headers.get("X-RestLi-Id", resp.json().get("id", ""))
            return {"post_id": post_id, "url": f"https://linkedin.com/feed/update/{post_id}"}

    async def _publish_facebook(self, content: dict, credentials: dict) -> dict:
        """Post to Facebook Page."""
        async with httpx.AsyncClient() as client:
            page_id = credentials.get("page_id", "me")
            body = content.get("body", "")

            resp = await client.post(
                f"https://graph.facebook.com/v19.0/{page_id}/feed",
                params={"access_token": credentials["access_token"]},
                json={"message": body},
            )
            resp.raise_for_status()
            data = resp.json()
            return {"post_id": data["id"], "url": f"https://facebook.com/{data['id']}"}

    async def _publish_instagram(self, content: dict, credentials: dict) -> dict:
        """Post to Instagram (requires media URL — placeholder for now)."""
        return {
            "post_id": "ig_pending",
            "url": "",
            "note": "Instagram requires media upload via Meta Graph API",
        }


publisher = PlatformPublisher()
