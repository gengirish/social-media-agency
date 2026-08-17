"""Real engagement-metric fetching from social platform APIs.

Each ``fetch_*_metrics`` coroutine calls the live platform API for a single
published post and maps the response onto a normalized metrics dict:

    {
        "status": "ok",
        "impressions": int,   # only when the API actually returns it
        "reach": int,
        "engagement": int,
        "clicks": int,
        "shares": int,
        "likes": int,
        "extra": {...provenance / raw fields / fields the API does not expose...},
    }

DATA RELIABILITY: these functions NEVER fabricate numbers. When a platform
does not expose a metric (or a call fails / is unauthorized), the metric is
either omitted or the whole result is returned as
``{"status": "unavailable", "reason": ...}``. Callers must not persist
snapshots from an ``unavailable`` result.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from urllib.parse import quote

import httpx
import structlog

from agency.utils.encryption import decrypt_token

logger = structlog.get_logger()

T = TypeVar("T")

DEFAULT_TIMEOUT = 15.0
_MAX_RETRIES = 2


def _unavailable(reason: str, **extra) -> dict:
    """Build an explicit unavailable result (never fake zeros)."""
    return {"status": "unavailable", "reason": reason, **extra}


async def _with_retries(
    op: Callable[[], Awaitable[T]],
    *,
    label: str,
    max_retries: int = _MAX_RETRIES,
) -> T:
    """Run an async HTTP op with backoff on transient errors.

    4xx responses (other than 429) are treated as permanent and not retried,
    since they indicate auth/permission/not-found problems that won't recover.
    """
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await op()
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if 400 <= code < 500 and code != 429:
                raise
            last_error = e
            logger.warning(
                "metrics_http_retry", label=label, attempt=attempt, status=code, error=str(e)
            )
            if attempt >= max_retries:
                raise
            await asyncio.sleep(0.5 * (2**attempt))
        except (httpx.RequestError, httpx.TimeoutException) as e:
            last_error = e
            logger.warning("metrics_http_retry", label=label, attempt=attempt, error=str(e))
            if attempt >= max_retries:
                raise
            await asyncio.sleep(0.5 * (2**attempt))
    raise last_error  # pragma: no cover


def _to_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


async def fetch_twitter_metrics(post_id: str, access_token: str) -> dict:
    """X/Twitter v2: public_metrics (+ non_public_metrics when the token owns the tweet)."""
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"tweet.fields": "public_metrics,non_public_metrics"}

        async def do_get():
            resp = await client.get(
                f"https://api.x.com/2/tweets/{post_id}", headers=headers, params=params
            )
            resp.raise_for_status()
            return resp.json()

        data = await _with_retries(do_get, label="twitter")

    tweet = data.get("data") or {}
    public = tweet.get("public_metrics") or {}
    non_public = tweet.get("non_public_metrics") or {}

    likes = _to_int(public.get("like_count"))
    shares = _to_int(public.get("retweet_count"))
    replies = _to_int(public.get("reply_count"))
    quotes = _to_int(public.get("quote_count"))
    engagement = likes + shares + replies + quotes

    metrics: dict = {
        "status": "ok",
        "likes": likes,
        "shares": shares,
        "engagement": engagement,
        "extra": {
            "source": "x_api_v2",
            "replies": replies,
            "quotes": quotes,
        },
    }

    # non_public_metrics are only returned for tweets owned by the authed user.
    fields_not_provided = []
    if "impression_count" in non_public:
        metrics["impressions"] = _to_int(non_public.get("impression_count"))
    elif "impression_count" in public:
        metrics["impressions"] = _to_int(public.get("impression_count"))
    else:
        fields_not_provided.append("impressions")

    if "url_link_clicks" in non_public:
        metrics["clicks"] = _to_int(non_public.get("url_link_clicks"))
    else:
        fields_not_provided.append("clicks")

    # X v2 does not expose per-tweet reach.
    fields_not_provided.append("reach")
    if fields_not_provided:
        metrics["extra"]["fields_not_provided"] = fields_not_provided
    return metrics


async def fetch_linkedin_metrics(
    post_id: str, access_token: str, org_urn: str | None = None
) -> dict:
    """LinkedIn: socialActions for likes/comments (+ org share statistics when available)."""
    urn = post_id if str(post_id).startswith("urn:") else f"urn:li:ugcPost:{post_id}"

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        async def do_social():
            resp = await client.get(
                f"https://api.linkedin.com/v2/socialActions/{quote(urn, safe='')}",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

        social = await _with_retries(do_social, label="linkedin_social")

        likes = _to_int((social.get("likesSummary") or {}).get("totalLikes"))
        comments = _to_int(
            (social.get("commentsSummary") or {}).get("aggregatedTotalComments")
        )
        engagement = likes + comments
        extra: dict = {"source": "linkedin_socialActions", "comments": comments}
        metrics: dict = {
            "status": "ok",
            "likes": likes,
            "engagement": engagement,
            "extra": extra,
        }
        # LinkedIn socialActions only exposes likes/comments. Impressions, clicks,
        # shares and reach require organizationalEntityShareStatistics (org pages).
        not_provided = {"impressions", "clicks", "shares", "reach"}

        if org_urn and str(org_urn).startswith("urn:li:organization"):
            try:

                async def do_stats():
                    resp = await client.get(
                        "https://api.linkedin.com/v2/organizationalEntityShareStatistics",
                        headers=headers,
                        params={
                            "q": "organizationalEntity",
                            "organizationalEntity": org_urn,
                            "shares[0]": urn,
                        },
                    )
                    resp.raise_for_status()
                    return resp.json()

                stats = await _with_retries(do_stats, label="linkedin_stats")
                elements = stats.get("elements") or []
                totals = (elements[0].get("totalShareStatistics") if elements else {}) or {}
                if "impressionCount" in totals:
                    metrics["impressions"] = _to_int(totals.get("impressionCount"))
                    not_provided.discard("impressions")
                if "clickCount" in totals:
                    metrics["clicks"] = _to_int(totals.get("clickCount"))
                    not_provided.discard("clicks")
                if "shareCount" in totals:
                    shares = _to_int(totals.get("shareCount"))
                    metrics["shares"] = shares
                    metrics["engagement"] = engagement + shares
                    not_provided.discard("shares")
                extra["source"] = "linkedin_socialActions+shareStatistics"
            except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as e:
                logger.info("linkedin_share_stats_unavailable", error=str(e))

        if not_provided:
            extra["fields_not_provided"] = sorted(not_provided)
        return metrics


async def fetch_facebook_metrics(post_id: str, access_token: str) -> dict:
    """Facebook Page post: engagement fields + /insights (impressions, reach, clicks)."""
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:

        async def do_fields():
            resp = await client.get(
                f"https://graph.facebook.com/v19.0/{post_id}",
                params={
                    "fields": "likes.summary(true),comments.summary(true),shares",
                    "access_token": access_token,
                },
            )
            resp.raise_for_status()
            return resp.json()

        fields = await _with_retries(do_fields, label="facebook_fields")

        likes = _to_int(((fields.get("likes") or {}).get("summary") or {}).get("total_count"))
        comments = _to_int(
            ((fields.get("comments") or {}).get("summary") or {}).get("total_count")
        )
        shares = _to_int((fields.get("shares") or {}).get("count"))
        extra: dict = {"source": "facebook_graph_v19", "comments": comments}

        metrics: dict = {
            "status": "ok",
            "likes": likes,
            "shares": shares,
            "extra": extra,
        }
        fields_not_provided: list[str] = []

        # Insights require a Page access token with read_insights; degrade gracefully.
        insight_map: dict = {}
        try:

            async def do_insights():
                resp = await client.get(
                    f"https://graph.facebook.com/v19.0/{post_id}/insights",
                    params={
                        "metric": "post_impressions,post_impressions_unique,"
                        "post_clicks,post_engaged_users",
                        "access_token": access_token,
                    },
                )
                resp.raise_for_status()
                return resp.json()

            insights = await _with_retries(do_insights, label="facebook_insights")
            for item in insights.get("data") or []:
                values = item.get("values") or []
                if values:
                    insight_map[item.get("name")] = _to_int(values[0].get("value"))
        except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as e:
            logger.info("facebook_insights_unavailable", error=str(e))

        if "post_impressions" in insight_map:
            metrics["impressions"] = insight_map["post_impressions"]
        else:
            fields_not_provided.append("impressions")
        if "post_impressions_unique" in insight_map:
            metrics["reach"] = insight_map["post_impressions_unique"]
        else:
            fields_not_provided.append("reach")
        if "post_clicks" in insight_map:
            metrics["clicks"] = insight_map["post_clicks"]
        else:
            fields_not_provided.append("clicks")

        if "post_engaged_users" in insight_map:
            metrics["engagement"] = insight_map["post_engaged_users"]
        else:
            metrics["engagement"] = likes + comments + shares

        if fields_not_provided:
            extra["fields_not_provided"] = fields_not_provided
        return metrics


async def fetch_instagram_metrics(post_id: str, access_token: str) -> dict:
    """Instagram metrics are not implemented yet."""
    return _unavailable("Instagram metrics not implemented")


async def fetch_post_metrics(
    platform: str,
    post_id: str,
    access_token: str,
    *,
    page_id: str | None = None,
    token_is_encrypted: bool = False,
) -> dict:
    """Dispatch to the platform-specific fetcher and normalize errors.

    ``access_token`` is expected already-decrypted. Pass
    ``token_is_encrypted=True`` to have the encrypted ciphertext decrypted here.
    Any failure is converted into an explicit ``unavailable`` result rather
    than raising, so callers never persist fabricated data.
    """
    if not post_id:
        return _unavailable("Missing platform post_id")
    if not access_token:
        return _unavailable("Missing access token")

    if token_is_encrypted:
        access_token = decrypt_token(access_token)

    try:
        if platform == "twitter":
            return await fetch_twitter_metrics(post_id, access_token)
        if platform == "linkedin":
            return await fetch_linkedin_metrics(post_id, access_token, org_urn=page_id)
        if platform == "facebook":
            return await fetch_facebook_metrics(post_id, access_token)
        if platform == "instagram":
            return await fetch_instagram_metrics(post_id, access_token)
        return _unavailable(f"Unsupported platform: {platform}")
    except httpx.HTTPStatusError as e:
        logger.warning(
            "platform_metrics_http_error",
            platform=platform,
            post_id=post_id,
            status=e.response.status_code,
        )
        return _unavailable(
            f"{platform} API returned HTTP {e.response.status_code}",
            http_status=e.response.status_code,
        )
    except (httpx.RequestError, httpx.TimeoutException) as e:
        logger.warning("platform_metrics_request_error", platform=platform, error=str(e))
        return _unavailable(f"{platform} API request failed: {e}")
    except Exception as e:  # noqa: BLE001 — defensive: never fabricate on unexpected errors
        logger.error("platform_metrics_unexpected_error", platform=platform, error=str(e))
        return _unavailable(f"{platform} metrics fetch error: {e}")
