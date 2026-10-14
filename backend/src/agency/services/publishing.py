"""Platform publishing service — posts approved content to X, LinkedIn, Meta."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from urllib.parse import urlsplit

import httpx
import structlog

from agency.config import get_settings
from agency.services import media_storage
from agency.utils.encryption import decrypt_token

logger = structlog.get_logger()

T = TypeVar("T")

#: Platforms the UI can offer but this service cannot actually post to.
#:
#: A publisher listed here is short-circuited in :meth:`PlatformPublisher.publish`
#: so it returns an explicit failure instead of a success-shaped body. Without this
#: guard ``_publish_instagram`` returned normally, ``publish()`` wrapped it as
#: ``{"success": True, ...}`` and callers marked the piece ``published`` (and burned
#: post quota) for a post that was never made.
#:
#: T2.1 (Instagram publishing) removes ``"instagram"`` from this set once the Graph
#: API container→publish flow lands. ``tiktok`` has no publisher at all.
UNAVAILABLE_PUBLISH_PLATFORMS: dict[str, str] = {
    "instagram": (
        "Instagram publishing is not available yet. It requires uploading media "
        "through the Meta Graph API (container + publish flow), which is not "
        "implemented. Export the post and publish it manually for now."
    ),
    "tiktok": (
        "TikTok publishing is not available yet. TikTok content can be generated "
        "and scheduled as a draft, but there is no TikTok publisher or OAuth "
        "connection. Export the post and publish it manually for now."
    ),
}


#: How many assets each platform will take on one post. A post carrying more is
#: truncated rather than refused — the copy is approved and the extra images are
#: not worth failing a publish over — but the truncation is logged.
#:
#: X allows four images *or* one video, never a mix; :func:`_limit_for_twitter`
#: applies that rule. LinkedIn's multi-image share caps at nine. Facebook's
#: ``attached_media`` caps at ten.
MAX_MEDIA_PER_POST: dict[str, int] = {"twitter": 4, "linkedin": 9, "facebook": 10}

#: What :func:`media_storage.public_url` emits under the ``local`` driver. Those
#: URLs are app-relative, so the publisher reads the file off disk instead of
#: trying to HTTP-fetch a path with no host.
LOCAL_MEDIA_URL_PREFIX = "/api/v1/media/"

#: X's chunked upload wants ≤5MB per APPEND. 4MB leaves headroom for the
#: multipart envelope.
X_UPLOAD_CHUNK_BYTES = 4 * 1024 * 1024


class MediaUploadError(RuntimeError):
    """A post's media could not be uploaded, so the post must not go out.

    Raised, never returned: :meth:`PlatformPublisher.publish` turns a publisher's
    normal return into ``{"success": True, ...}``, and callers mark the piece
    ``published`` and charge a post against the plan on the strength of that. A
    media failure swallowed into a text-only post would publish copy that was
    approved *with* an image; a media failure swallowed into a success body is
    how Instagram once marked pieces published for posts that were never made.
    """


def _local_storage_key(url: str) -> str | None:
    """The storage key inside a ``local``-driver media URL, else ``None``.

    Accepts both the app-relative form ``public_url`` writes and an absolute URL
    that happens to point at the same route, because ``media_urls`` rows written
    under one driver survive a driver change.
    """
    path = urlsplit(url).path or url
    idx = path.find(LOCAL_MEDIA_URL_PREFIX)
    if idx == -1:
        return None
    key = path[idx + len(LOCAL_MEDIA_URL_PREFIX) :]
    return key or None


async def _media_bytes(url: str) -> tuple[bytes, str]:
    """Read one asset server-side. Returns ``(payload, mime)``.

    The platform APIs want the bytes, not our URL — X and LinkedIn both upload
    them — so this is the one place that resolves a ``media_urls`` entry into a
    payload. Under the ``local`` driver the URL has no host, so it is read off
    disk; under ``r2`` it is a real public URL and is fetched.
    """
    if media_storage.active_driver() == "local":
        key = _local_storage_key(url)
        if key is not None:
            found = await media_storage.read_local(key)
            if found is None:
                raise MediaUploadError(f"Media is missing from local storage: {url}")
            return found
    try:
        return await media_storage.fetch_bytes(url)
    except media_storage.MediaStorageError as exc:
        raise MediaUploadError(str(exc)) from exc


def _media_list(content: dict, platform: str) -> list[str]:
    """The post's media URLs, de-duplicated and capped for the platform."""
    raw = content.get("media_urls") or []
    urls = [str(u) for u in raw if isinstance(u, str) and u.strip()]
    # Dedupe while keeping order: the same asset appended twice would otherwise
    # be uploaded twice and appear twice in the post.
    seen: set[str] = set()
    unique = [u for u in urls if not (u in seen or seen.add(u))]
    cap = MAX_MEDIA_PER_POST.get(platform, 1)
    if len(unique) > cap:
        logger.warning(
            "publish_media_truncated", platform=platform, had=len(unique), cap=cap
        )
    return unique[:cap]


def _guess_mime(url: str) -> str:
    import mimetypes

    return mimetypes.guess_type(urlsplit(url).path or url)[0] or "application/octet-stream"


def _limit_for_twitter(urls: list[str]) -> list[str]:
    """X takes up to four images **or** exactly one video, never a mix.

    Guessed from the key's extension rather than fetched first: the whole point
    is to decide how many bytes to pull. A video with no recognisable extension
    reads as an image and X rejects the upload with its own error, which is the
    right place for that to surface.
    """
    for idx, url in enumerate(urls):
        if _guess_mime(url).startswith("video/"):
            # A video must be the only attachment. If it is not first, it is
            # still the one the operator cared about.
            if len(urls) > 1:
                logger.warning("publish_media_video_only", platform="twitter", had=len(urls))
            return [urls[idx]]
    return urls


def _x_media_id(data: dict[str, Any]) -> str:
    """X's media id, from either the v2 or the v1.1 response shape.

    ``POST /2/media/upload`` answers ``{"data": {"id": ...}}``; the long-lived
    v1.1 endpoint answered ``{"media_id_string": ...}``. Accepting both costs two
    lines and means a response-shape change does not take publishing down.
    """
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    media_id = (
        (inner or {}).get("id")
        or (inner or {}).get("media_id_string")
        or data.get("media_id_string")
        or data.get("id")
    )
    if not media_id:
        raise MediaUploadError(f"X media upload returned no media id: {data!r}")
    return str(media_id)


class PlatformPublisher:
    """Handles publishing content to social media platforms."""

    def __init__(self):
        self.settings = get_settings()

    def _decrypt_token(self, encrypted: str) -> str:
        """Decrypt platform token; legacy plaintext rows fall back with a warning."""
        return decrypt_token(encrypted)

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
        """Route to platform-specific publisher.

        ``content["media_urls"]`` is optional; a post without it takes exactly
        the same path it always did. With it, the platform publisher uploads the
        assets first and raises :class:`MediaUploadError` if that fails, which
        the ``except`` below turns into an explicit failure — never a
        success-shaped body, because the caller marks the piece ``published`` and
        charges a post against the plan on the strength of one.
        """
        unavailable = UNAVAILABLE_PUBLISH_PLATFORMS.get(platform)
        if unavailable:
            logger.info("publish_platform_unavailable", platform=platform)
            return {"success": False, "error": unavailable}

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

            media_ids: list[str] = []
            for url in _limit_for_twitter(_media_list(content, "twitter")):
                media_ids.append(await self._upload_twitter_media(client, headers, url))

            payload: dict[str, Any] = {"text": body}
            if media_ids:
                payload["media"] = {"media_ids": media_ids}

            async def do_post():
                resp = await client.post(
                    "https://api.x.com/2/tweets",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()

            data = await self._with_http_retries(do_post)
            return {
                "post_id": data["data"]["id"],
                "url": f"https://x.com/i/status/{data['data']['id']}",
            }

    async def _upload_twitter_media(
        self, client: httpx.AsyncClient, headers: dict, url: str
    ) -> str:
        """INIT → APPEND* → FINALIZE against ``POST /2/media/upload``.

        Returns the media id for ``media.media_ids``. Raises
        :class:`MediaUploadError` rather than returning a sentinel, so a failed
        upload cannot become a text-only post that reads as a success.
        """
        payload, mime = await _media_bytes(url)
        category = (
            "tweet_video"
            if mime.startswith("video/")
            else "tweet_gif"
            if mime == "image/gif"
            else "tweet_image"
        )
        endpoint = "https://api.x.com/2/media/upload"

        async def do_init():
            resp = await client.post(
                endpoint,
                headers=headers,
                data={
                    "command": "INIT",
                    "total_bytes": str(len(payload)),
                    "media_type": mime,
                    "media_category": category,
                },
            )
            resp.raise_for_status()
            return resp.json()

        media_id = _x_media_id(await self._with_http_retries(do_init))

        for index in range(0, max(1, -(-len(payload) // X_UPLOAD_CHUNK_BYTES))):
            start = index * X_UPLOAD_CHUNK_BYTES
            chunk = payload[start : start + X_UPLOAD_CHUNK_BYTES]

            async def do_append(segment: int = index, part: bytes = chunk):
                resp = await client.post(
                    endpoint,
                    headers=headers,
                    data={
                        "command": "APPEND",
                        "media_id": media_id,
                        "segment_index": str(segment),
                    },
                    files={"media": ("blob", part, mime)},
                )
                resp.raise_for_status()
                return resp

            await self._with_http_retries(do_append)

        async def do_finalize():
            resp = await client.post(
                endpoint,
                headers=headers,
                data={"command": "FINALIZE", "media_id": media_id},
            )
            resp.raise_for_status()
            return resp

        await self._with_http_retries(do_finalize)
        logger.info("publish_media_uploaded", platform="twitter", media_id=media_id, mime=mime)
        return media_id

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

            share_content: dict[str, Any] = {
                "shareCommentary": {"text": body},
                "shareMediaCategory": "NONE",
            }

            media_urls = _media_list(content, "linkedin")
            if media_urls:
                # One category per share: LinkedIn has no mixed image+video post.
                # A video wins if one is present, and it is the only attachment.
                videos = [u for u in media_urls if _guess_mime(u).startswith("video/")]
                if videos:
                    chosen, category = videos[:1], "VIDEO"
                else:
                    chosen, category = media_urls, "IMAGE"
                assets = [
                    await self._upload_linkedin_asset(client, headers, author_urn, url)
                    for url in chosen
                ]
                share_content["shareMediaCategory"] = category
                share_content["media"] = [
                    {"status": "READY", "media": urn} for urn in assets
                ]

            post_data = {
                "author": author_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {"com.linkedin.ugc.ShareContent": share_content},
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

    async def _upload_linkedin_asset(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        author_urn: str,
        url: str,
    ) -> str:
        """``registerUpload`` → PUT the bytes → the asset URN for ``ShareContent``.

        The recipe and the share category have to agree: a ``feedshare-image``
        asset in a ``VIDEO`` share is rejected, and the error does not say why.
        """
        payload, mime = await _media_bytes(url)
        is_video = mime.startswith("video/")
        recipe = (
            "urn:li:digitalmediaRecipe:feedshare-video"
            if is_video
            else "urn:li:digitalmediaRecipe:feedshare-image"
        )

        async def do_register():
            resp = await client.post(
                "https://api.linkedin.com/v2/assets?action=registerUpload",
                headers=headers,
                json={
                    "registerUploadRequest": {
                        "recipes": [recipe],
                        "owner": author_urn,
                        "serviceRelationships": [
                            {
                                "relationshipType": "OWNER",
                                "identifier": "urn:li:userGeneratedContent",
                            }
                        ],
                    }
                },
            )
            resp.raise_for_status()
            return resp.json()

        registered = await self._with_http_retries(do_register)
        value = registered.get("value") or {}
        asset_urn = value.get("asset")
        upload_url = (
            (value.get("uploadMechanism") or {})
            .get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {})
            .get("uploadUrl")
        )
        if not asset_urn or not upload_url:
            raise MediaUploadError(f"LinkedIn registerUpload returned no upload target: {value!r}")

        async def do_put():
            # Only the bearer token travels here; the Restli header belongs to
            # the API host, not to the media upload host.
            resp = await client.put(
                upload_url,
                headers={"Authorization": headers["Authorization"]},
                content=payload,
            )
            resp.raise_for_status()
            return resp

        await self._with_http_retries(do_put)
        logger.info("publish_media_uploaded", platform="linkedin", asset=asset_urn, mime=mime)
        return str(asset_urn)

    async def _publish_facebook(self, content: dict, credentials: dict) -> dict:
        """Post to Facebook Page.

        Meta fetches media by URL rather than taking an upload, so this is the
        one publisher that never reads the bytes — and the one that needs the URL
        to be publicly reachable. Under the ``local`` storage driver it is not,
        which is why that case raises instead of handing Graph a path with no
        host and reporting whatever it says about it.
        """
        async with httpx.AsyncClient() as client:
            page_id = credentials.get("page_id", "me")
            body = content.get("body", "")
            media_urls = _media_list(content, "facebook")

            if media_urls:
                return await self._publish_facebook_photos(
                    client, page_id, credentials["access_token"], body, media_urls
                )

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

    async def _publish_facebook_photos(
        self,
        client: httpx.AsyncClient,
        page_id: str,
        access_token: str,
        body: str,
        media_urls: list[str],
    ) -> dict:
        """One photo → ``/photos`` with the message on it. Several → unpublished
        photos then a ``/feed`` post carrying ``attached_media``.

        The single-photo case is not an optimisation: a one-image ``/feed`` post
        with ``attached_media`` renders differently from a photo post, and the
        photo post is what an operator expects from "post this image".
        """
        for url in media_urls:
            if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).netloc:
                raise MediaUploadError(
                    "Facebook fetches media by URL, so it must be publicly reachable. "
                    f"{url!r} is not an absolute URL — configure durable media storage "
                    "(S3_ENDPOINT_URL and keys) before publishing media to Facebook."
                )

        photos_endpoint = f"https://graph.facebook.com/v19.0/{page_id}/photos"

        if len(media_urls) == 1:

            async def do_photo():
                resp = await client.post(
                    photos_endpoint,
                    params={
                        "access_token": access_token,
                        "url": media_urls[0],
                        "message": body,
                    },
                )
                resp.raise_for_status()
                return resp.json()

            data = await self._with_http_retries(do_photo)
            # ``post_id`` is the feed story; ``id`` is the photo. The story is
            # what a link should point at, and what Insights can later read.
            post_id = str(data.get("post_id") or data["id"])
            logger.info("publish_media_uploaded", platform="facebook", count=1)
            return {"post_id": post_id, "url": f"https://facebook.com/{post_id}"}

        fbids: list[str] = []
        for url in media_urls:

            async def do_unpublished(target: str = url):
                resp = await client.post(
                    photos_endpoint,
                    params={
                        "access_token": access_token,
                        "url": target,
                        "published": "false",
                    },
                )
                resp.raise_for_status()
                return resp.json()

            fbids.append(str((await self._with_http_retries(do_unpublished))["id"]))

        params: dict[str, str] = {"access_token": access_token, "message": body}
        for idx, fbid in enumerate(fbids):
            # Graph wants each entry as its own JSON-encoded indexed param.
            params[f"attached_media[{idx}]"] = json.dumps({"media_fbid": fbid})

        async def do_feed():
            resp = await client.post(
                f"https://graph.facebook.com/v19.0/{page_id}/feed", params=params
            )
            resp.raise_for_status()
            return resp.json()

        data = await self._with_http_retries(do_feed)
        logger.info("publish_media_uploaded", platform="facebook", count=len(fbids))
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
