"""Inbox — real X mentions and LinkedIn comments for a client's connected accounts.

Nothing here is seeded or simulated (Cadence's prototype inbox was). Every item
comes from the platform's API with the account's stored OAuth token, and every
account gets an explicit status so the UI can say *why* it has nothing:

- ``ok`` — fetched; ``items`` may legitimately be empty.
- ``not_connected`` — no connected account for an inbox platform.
- ``needs_reconnect`` — no usable token (missing, revoked, expired and refresh failed).
- ``api_access_denied`` — the platform refused on access grounds (X API plan /
  credits, a LinkedIn permission this app does not hold). ``message`` carries the
  platform's own text where there is one.
- ``rate_limited`` — HTTP 429; ``retry_after`` in seconds when the platform said.
- ``unsupported`` — connected platform the inbox does not read (Facebook, ...).
- ``error`` — anything else (5xx, network, malformed response).

What each platform can actually give us with the scopes ``routers/oauth.py`` requests:

**X** (``tweet.read tweet.write users.read offline.access``): the mentions timeline
``GET /2/users/:id/mentions`` needs ``tweet.read`` + ``users.read`` — held. Whether it
is *allowed* is an API-plan question: since Feb 2026 X bills reads per post
(pay-per-use; the legacy Free plan could not read mentions at all). A 402/403 from X
is surfaced verbatim as ``api_access_denied``. Replying (``POST /2/tweets`` with
``reply.in_reply_to_tweet_id``) needs ``tweet.write`` — held; X only allows an API
reply when the original author @mentioned or quoted the replier, which a mention does.

**LinkedIn** (``openid profile w_member_social``): *reading* comments needs
``r_member_social`` (restricted to approved developers) or ``r_organization_social``
(Community Management API). Neither is requested by default because LinkedIn rejects
the whole authorization for a scope the app lacks — that would break connecting
LinkedIn for publishing. ``LINKEDIN_INBOX_SCOPE`` turns it on once the app is approved.
Without it LinkedIn reports ``api_access_denied`` and no call is made. With it, comments
are read from the posts CampaignForge itself published (their URNs are in
``content_piece.metadata.post_id``). Commenter names are not resolvable with these
scopes, so authors show as "LinkedIn member" plus their URN.

**DMs** are not read on any platform: X needs ``dm.read`` (not requested) and LinkedIn
has no messaging API for this kind of app.

Results are cached per account in memory for a short TTL — reads cost money on X and
count against rate limits on both.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Literal
from urllib.parse import quote

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.config import get_settings
from agency.models.tables import ContentPiece, InboxItemState, PlatformAccount
from agency.utils.encryption import decrypt_token, encrypt_token

logger = structlog.get_logger()

InboxStatus = Literal[
    "ok",
    "not_connected",
    "needs_reconnect",
    "api_access_denied",
    "rate_limited",
    "unsupported",
    "error",
]

#: Platforms the inbox reads, in display order.
INBOX_PLATFORMS: Final = ("twitter", "linkedin")
PLATFORM_LABELS: Final = {
    "twitter": "X",
    "linkedin": "LinkedIn",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "tiktok": "TikTok",
}

X_API: Final = "https://api.x.com/2"
X_TOKEN_URL: Final = "https://api.x.com/2/oauth2/token"
LI_API: Final = "https://api.linkedin.com"

X_MENTIONS_MAX: Final = 20
LI_POSTS_MAX: Final = 10
LI_COMMENTS_PER_POST: Final = 20

CACHE_TTL_OK: Final = 120.0
CACHE_TTL_ERROR: Final = 30.0
#: ``?refresh=1`` never re-fetches more often than this — reads are billed on X.
MIN_REFRESH_INTERVAL: Final = 20.0
MAX_RETRY_AFTER: Final = 900

DM_UNAVAILABLE: Final = (
    "Direct messages aren't read. X DMs need the dm.read permission, which "
    "CampaignForge doesn't request, and LinkedIn offers no messaging API to this "
    "kind of app."
)
LI_NOT_GRANTED: Final = (
    "Reading LinkedIn comments needs LinkedIn's r_member_social permission (granted "
    "only to approved developers) or the Community Management API for company pages. "
    "This workspace's LinkedIn app requests only openid, profile and w_member_social, "
    "so CampaignForge can publish to LinkedIn but can't read comments."
)
LI_NO_POSTS: Final = (
    "No LinkedIn posts published through CampaignForge yet. Comments are read from "
    "the posts CampaignForge published for this client."
)


def _default_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=15.0)


#: Swapped for an ``httpx.MockTransport`` client in tests. No live calls in the suite.
client_factory: Callable[[], httpx.AsyncClient] = _default_client


class PlatformCallError(Exception):
    """A platform call that ended in a non-ok inbox status."""

    def __init__(self, status: InboxStatus, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.status: InboxStatus = status
        self.message = message
        self.retry_after = retry_after


@dataclass
class AccountInbox:
    account_id: str | None
    platform: str
    handle: str
    status: InboxStatus
    message: str = ""
    retry_after: int | None = None
    reply_supported: bool = False
    items: list[dict[str, Any]] = field(default_factory=list)
    fetched_at: str | None = None
    cached: bool = False

    def summary(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "platform": self.platform,
            "handle": self.handle,
            "status": self.status,
            "message": self.message,
            "retry_after": self.retry_after,
            "reply_supported": self.reply_supported,
            "item_count": len(self.items),
            "fetched_at": self.fetched_at,
            "cached": self.cached,
        }


# (expires_at, fetched_at, result) keyed by platform_account.id. Per process.
_cache: dict[str, tuple[float, float, AccountInbox]] = {}
_x_user_ids: dict[str, str] = {}
_li_person_urns: dict[str, str] = {}


def clear_cache() -> None:
    _cache.clear()
    _x_user_ids.clear()
    _li_person_urns.clear()


def _label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform)


def linkedin_inbox_enabled() -> bool:
    return bool((get_settings().linkedin_inbox_scope or "").strip())


def reply_supported(platform: str) -> bool:
    if platform == "twitter":
        return True
    if platform == "linkedin":
        # Creating comments needs only w_member_social (held); replying is offered
        # only where reading is, since a reply targets an item we read.
        return linkedin_inbox_enabled()
    return False


# --------------------------------------------------------------------------- errors


def platform_message(resp: httpx.Response) -> str:
    """The platform's own explanation, from whichever field it uses."""
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        for key in ("detail", "message", "error_description", "title", "error"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:300]
        errors = body.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            msg = errors[0].get("message") or errors[0].get("detail")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()[:300]
    text = (resp.text or "").strip()
    return text[:200] if text else (resp.reason_phrase or f"HTTP {resp.status_code}")


def _retry_after(resp: httpx.Response) -> int | None:
    raw = resp.headers.get("retry-after")
    if raw and raw.strip().isdigit():
        return min(int(raw), MAX_RETRY_AFTER)
    reset = resp.headers.get("x-rate-limit-reset")
    if reset and reset.strip().isdigit():
        return max(0, min(int(reset) - int(time.time()), MAX_RETRY_AFTER))
    return None


def error_for_response(platform: str, resp: httpx.Response) -> PlatformCallError:
    """Map a non-2xx platform response to an inbox status. Never raises."""
    label = _label(platform)
    detail = platform_message(resp)
    code = resp.status_code
    if code == 401:
        return PlatformCallError(
            "needs_reconnect",
            f"{label} rejected the stored access token (expired or revoked). "
            f"Reconnect the account. {label} said: {detail}",
        )
    if code in (402, 403):
        return PlatformCallError("api_access_denied", f"{label} denied access: {detail}")
    if code == 429:
        return PlatformCallError(
            "rate_limited",
            f"{label} rate limit reached. {detail}".strip(),
            retry_after=_retry_after(resp),
        )
    return PlatformCallError("error", f"{label} returned HTTP {code}: {detail}")


# --------------------------------------------------------------------------- X


async def _refresh_x_token(
    http: httpx.AsyncClient, account: PlatformAccount, db: AsyncSession
) -> bool:
    """Swap the refresh token for a new access token (X tokens live ~2h). Persists both."""
    settings = get_settings()
    refresh = decrypt_token(str(account.refresh_token_enc or ""))
    if not refresh or not settings.twitter_client_id:
        return False
    # Confidential clients authenticate with Basic; public clients send client_id only.
    auth: httpx.BasicAuth | httpx._client.UseClientDefault = (
        httpx.BasicAuth(settings.twitter_client_id, settings.twitter_client_secret)
        if settings.twitter_client_secret
        else httpx.USE_CLIENT_DEFAULT
    )
    try:
        resp = await http.post(
            X_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": settings.twitter_client_id,
            },
            auth=auth,
        )
    except httpx.HTTPError as exc:
        logger.warning("inbox_x_refresh_failed", account_id=str(account.id), error=str(exc))
        return False
    if resp.status_code != 200:
        logger.warning(
            "inbox_x_refresh_failed", account_id=str(account.id), status=resp.status_code
        )
        return False
    data = resp.json()
    access = data.get("access_token")
    if not access:
        return False
    account.access_token_enc = encrypt_token(access)  # type: ignore[assignment]
    if data.get("refresh_token"):  # X rotates refresh tokens
        account.refresh_token_enc = encrypt_token(data["refresh_token"])  # type: ignore[assignment]
    if isinstance(data.get("expires_in"), int):
        account.token_expires_at = datetime.now(UTC) + timedelta(  # type: ignore[assignment]
            seconds=data["expires_in"]
        )
    await db.flush()
    logger.info("inbox_x_token_refreshed", account_id=str(account.id))
    return True


async def _x_request(
    http: httpx.AsyncClient,
    method: str,
    url: str,
    account: PlatformAccount,
    db: AsyncSession,
    **kwargs: Any,
) -> httpx.Response:
    """Authenticated X call; on 401 refreshes the token once and retries."""

    async def call() -> httpx.Response:
        token = decrypt_token(str(account.access_token_enc or ""))
        return await http.request(
            method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs
        )

    resp = await call()
    if resp.status_code == 401 and await _refresh_x_token(http, account, db):
        resp = await call()
    return resp


def normalize_x_mentions(
    payload: dict[str, Any], *, own_user_id: str | None = None
) -> list[dict[str, Any]]:
    """``GET /2/users/:id/mentions`` (with ``expansions=author_id``) → inbox items."""
    users: dict[str, dict[str, Any]] = {}
    for user in (payload.get("includes") or {}).get("users") or []:
        if isinstance(user, dict) and user.get("id"):
            users[str(user["id"])] = user
    items: list[dict[str, Any]] = []
    for tweet in payload.get("data") or []:
        if not isinstance(tweet, dict) or not tweet.get("id"):
            continue
        tweet_id = str(tweet["id"])
        author_id = str(tweet.get("author_id") or "")
        if own_user_id and author_id == own_user_id:
            continue  # the account mentioning itself is not inbound
        author = users.get(author_id, {})
        username = author.get("username")
        replied_to = next(
            (
                str(ref.get("id"))
                for ref in tweet.get("referenced_tweets") or []
                if isinstance(ref, dict) and ref.get("type") == "replied_to" and ref.get("id")
            ),
            None,
        )
        items.append(
            {
                "id": f"twitter:{tweet_id}",
                "native_id": tweet_id,
                "platform": "twitter",
                "type": "mention",
                "author": {
                    "name": author.get("name") or (f"@{username}" if username else "X user"),
                    "handle": f"@{username}" if username else author_id,
                    "avatar": author.get("profile_image_url"),
                },
                "text": str(tweet.get("text") or ""),
                "url": (
                    f"https://x.com/{username}/status/{tweet_id}"
                    if username
                    else f"https://x.com/i/status/{tweet_id}"
                ),
                "created_at": tweet.get("created_at"),
                "in_reply_to": (
                    {"id": replied_to, "url": f"https://x.com/i/status/{replied_to}"}
                    if replied_to
                    else None
                ),
                "reply_target": {"tweet_id": tweet_id},
            }
        )
    return items


async def _fetch_x(
    http: httpx.AsyncClient, account: PlatformAccount, db: AsyncSession
) -> tuple[list[dict[str, Any]], str]:
    key = str(account.id)
    user_id = _x_user_ids.get(key)
    if not user_id:
        resp = await _x_request(http, "GET", f"{X_API}/users/me", account, db)
        if resp.status_code != 200:
            raise error_for_response("twitter", resp)
        user_id = str(((resp.json() or {}).get("data") or {}).get("id") or "")
        if not user_id:
            raise PlatformCallError("error", "X returned no user id for this account.")
        _x_user_ids[key] = user_id

    resp = await _x_request(
        http,
        "GET",
        f"{X_API}/users/{user_id}/mentions",
        account,
        db,
        params={
            "max_results": X_MENTIONS_MAX,
            "expansions": "author_id",
            "user.fields": "name,username,profile_image_url",
            "tweet.fields": "created_at,author_id,conversation_id,referenced_tweets",
        },
    )
    if resp.status_code != 200:
        raise error_for_response("twitter", resp)
    return normalize_x_mentions(resp.json() or {}, own_user_id=user_id), ""


# --------------------------------------------------------------------------- LinkedIn


def _li_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Linkedin-Version": get_settings().linkedin_api_version,
        "X-Restli-Protocol-Version": "2.0.0",
    }


def _li_post_url(urn: str) -> str:
    return f"https://www.linkedin.com/feed/update/{urn}/"


def normalize_linkedin_comments(
    payload: dict[str, Any], *, post_urn: str, own_actor: str | None = None
) -> list[dict[str, Any]]:
    """``GET /rest/socialActions/{urn}/comments`` → inbox items."""
    items: list[dict[str, Any]] = []
    for c in payload.get("elements") or []:
        if not isinstance(c, dict):
            continue
        comment_urn = str(c.get("commentUrn") or "")
        if not comment_urn:
            continue
        actor = str(c.get("actor") or "")
        if own_actor and actor == own_actor:
            continue  # our own replies are not inbound
        created_ms = (c.get("created") or {}).get("time")
        created_at = (
            datetime.fromtimestamp(created_ms / 1000, UTC).isoformat()
            if isinstance(created_ms, int | float)
            else None
        )
        parent = c.get("parentComment")
        is_org = actor.startswith(("urn:li:organization", "urn:li:organizationBrand"))
        items.append(
            {
                "id": f"linkedin:{comment_urn}",
                "native_id": comment_urn,
                "platform": "linkedin",
                "type": "comment",
                "author": {
                    # Names need a profile permission these scopes don't include.
                    "name": "LinkedIn organization" if is_org else "LinkedIn member",
                    "handle": actor,
                    "avatar": None,
                },
                "text": str((c.get("message") or {}).get("text") or ""),
                "url": f"{_li_post_url(post_urn)}?commentUrn={quote(comment_urn, safe='')}",
                "created_at": created_at,
                "in_reply_to": {
                    "id": str(parent) if parent else post_urn,
                    "url": _li_post_url(post_urn),
                },
                "reply_target": {
                    "post_urn": post_urn,
                    "comment_urn": comment_urn,
                    # LinkedIn nests one level: a reply to a reply joins its parent thread.
                    "parent_comment": str(parent) if parent else comment_urn,
                },
            }
        )
    return items


async def _li_person_urn(http: httpx.AsyncClient, account: PlatformAccount, token: str) -> str:
    key = str(account.id)
    if key in _li_person_urns:
        return _li_person_urns[key]
    resp = await http.get(f"{LI_API}/v2/userinfo", headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        raise error_for_response("linkedin", resp)
    sub = (resp.json() or {}).get("sub")
    if not sub:
        raise PlatformCallError("error", "LinkedIn returned no member id for this account.")
    _li_person_urns[key] = f"urn:li:person:{sub}"
    return _li_person_urns[key]


async def _published_linkedin_urns(db: AsyncSession, account: PlatformAccount) -> list[str]:
    rows = (
        await db.execute(
            select(ContentPiece)
            .where(
                ContentPiece.org_id == account.org_id,
                ContentPiece.client_id == account.client_id,
                ContentPiece.platform == "linkedin",
                ContentPiece.status == "published",
            )
            .order_by(ContentPiece.published_at.desc())
            .limit(LI_POSTS_MAX * 3)
        )
    ).scalars()
    urns: list[str] = []
    for piece in rows:
        meta: Any = piece.metadata_
        post_id = meta.get("post_id") if isinstance(meta, dict) else None
        if isinstance(post_id, str) and post_id.startswith("urn:li:") and post_id not in urns:
            urns.append(post_id)
        if len(urns) >= LI_POSTS_MAX:
            break
    return urns


async def _fetch_linkedin(
    http: httpx.AsyncClient, account: PlatformAccount, db: AsyncSession
) -> tuple[list[dict[str, Any]], str]:
    if not linkedin_inbox_enabled():
        raise PlatformCallError("api_access_denied", LI_NOT_GRANTED)
    urns = await _published_linkedin_urns(db, account)
    if not urns:
        return [], LI_NO_POSTS
    token = decrypt_token(str(account.access_token_enc or ""))
    own = await _li_person_urn(http, account, token)
    items: list[dict[str, Any]] = []
    for urn in urns:
        resp = await http.get(
            f"{LI_API}/rest/socialActions/{quote(urn, safe='')}/comments",
            params={"count": LI_COMMENTS_PER_POST},
            headers=_li_headers(token),
        )
        if resp.status_code == 404:
            continue  # post deleted on LinkedIn since we published it
        if resp.status_code != 200:
            raise error_for_response("linkedin", resp)
        items.extend(normalize_linkedin_comments(resp.json() or {}, post_urn=urn, own_actor=own))
    return items, ""


# --------------------------------------------------------------------------- per account


async def fetch_account_inbox(
    db: AsyncSession, account: PlatformAccount, *, refresh: bool = False
) -> AccountInbox:
    """One account's items + status. ``account`` must already be org-scoped by the caller."""
    platform = str(account.platform)
    key = str(account.id)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None:
        expires, fetched, cached = hit
        forced = (
            refresh and cached.status != "rate_limited" and now - fetched >= MIN_REFRESH_INTERVAL
        )
        if now < expires and not forced:
            return replace(cached, cached=True)

    base = AccountInbox(
        account_id=key,
        platform=platform,
        handle=str(account.display_name or account.account_handle or ""),
        status="ok",
        reply_supported=reply_supported(platform),
    )
    if account.status != "connected" or not account.access_token_enc:
        result = replace(
            base,
            status="needs_reconnect",
            message=(
                f"This {_label(platform)} connection has no usable token "
                f"(status: {account.status}). Reconnect it to read the inbox."
            ),
        )
        return result  # nothing was called; not worth caching

    fetchers = {"twitter": _fetch_x, "linkedin": _fetch_linkedin}
    try:
        async with client_factory() as http:
            items, note = await fetchers[platform](http, account, db)
        result = replace(base, items=items, message=note)
    except PlatformCallError as exc:
        result = replace(base, status=exc.status, message=exc.message, retry_after=exc.retry_after)
    except (httpx.HTTPError, ValueError) as exc:
        result = replace(base, status="error", message=f"Couldn't reach {_label(platform)}: {exc}")
    result.fetched_at = datetime.now(UTC).isoformat()

    if result.status != "ok":
        logger.info(
            "inbox_account_status",
            account_id=key,
            platform=platform,
            status=result.status,
        )
    if result.status == "ok":
        ttl = CACHE_TTL_OK
    elif result.status == "rate_limited":
        ttl = float(result.retry_after or 60)
    else:
        ttl = CACHE_TTL_ERROR
    _cache[key] = (now + ttl, now, result)
    return result


def invalidate(account_id: str) -> None:
    _cache.pop(account_id, None)


# --------------------------------------------------------------------------- client


async def load_client_inbox(
    db: AsyncSession, *, org_id: Any, client_id: Any, refresh: bool = False
) -> dict[str, Any]:
    """Every account of one client, org-scoped. Caller has already resolved the client."""
    accounts = list(
        (
            await db.execute(
                select(PlatformAccount)
                .where(PlatformAccount.org_id == org_id, PlatformAccount.client_id == client_id)
                .order_by(PlatformAccount.created_at.desc())
            )
        ).scalars()
    )
    results: list[AccountInbox] = []
    seen: set[str] = set()
    for acc in accounts:
        if acc.status == "disconnected":
            continue
        platform = str(acc.platform)
        if platform not in INBOX_PLATFORMS:
            results.append(
                AccountInbox(
                    account_id=str(acc.id),
                    platform=platform,
                    handle=str(acc.display_name or acc.account_handle or ""),
                    status="unsupported",
                    message=(
                        f"The inbox reads X mentions and LinkedIn comments only; "
                        f"{_label(platform)} isn't wired up."
                    ),
                )
            )
            continue
        seen.add(platform)
        results.append(await fetch_account_inbox(db, acc, refresh=refresh))
    for platform in INBOX_PLATFORMS:
        if platform not in seen:
            results.append(
                AccountInbox(
                    account_id=None,
                    platform=platform,
                    handle="",
                    status="not_connected",
                    message=f"No {_label(platform)} account connected for this client.",
                )
            )

    items: list[dict[str, Any]] = []
    for res in results:
        for item in res.items:
            items.append({**item, "account_id": res.account_id})
    items.sort(key=lambda i: i.get("created_at") or "", reverse=True)

    states: dict[str, InboxItemState] = {}
    if items:
        rows = await db.execute(
            select(InboxItemState).where(
                InboxItemState.org_id == org_id,
                InboxItemState.client_id == client_id,
                InboxItemState.item_key.in_([i["id"] for i in items]),
            )
        )
        states = {str(s.item_key): s for s in rows.scalars()}
    for item in items:
        st = states.get(item["id"])
        item["read"] = bool(st.is_read) if st else False
        item["handled"] = bool(st.handled) if st else False
        item["reply_url"] = st.reply_url if st else None

    return {
        "client_id": str(client_id),
        "accounts": [r.summary() for r in results],
        "items": items,
        "dms": {"available": False, "reason": DM_UNAVAILABLE},
    }


async def find_item(
    db: AsyncSession, account: PlatformAccount, item_id: str
) -> dict[str, Any] | None:
    """The item, only if it is really in this account's inbox (never a client-supplied target)."""
    result = await fetch_account_inbox(db, account)
    return next((i for i in result.items if i["id"] == item_id), None)


async def set_item_state(
    db: AsyncSession,
    *,
    org_id: Any,
    client_id: Any,
    item_key: str,
    user_id: Any = None,
    read: bool | None = None,
    handled: bool | None = None,
    reply_id: str | None = None,
    reply_url: str | None = None,
) -> InboxItemState:
    """Upsert triage state. Caller commits."""
    row = (
        await db.execute(
            select(InboxItemState).where(
                InboxItemState.org_id == org_id,
                InboxItemState.client_id == client_id,
                InboxItemState.item_key == item_key,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = InboxItemState(
            org_id=org_id, client_id=client_id, item_key=item_key, is_read=False, handled=False
        )
        db.add(row)
    if read is not None:
        row.is_read = read  # type: ignore[assignment]
    if handled is not None:
        row.handled = handled  # type: ignore[assignment]
    if reply_id is not None:
        row.reply_id = reply_id  # type: ignore[assignment]
        row.reply_url = reply_url  # type: ignore[assignment]
    row.updated_by = user_id
    row.updated_at = datetime.now(UTC)  # type: ignore[assignment]
    await db.flush()
    return row


# --------------------------------------------------------------------------- reply


async def post_reply(
    db: AsyncSession, account: PlatformAccount, item: dict[str, Any], text: str
) -> dict[str, str]:
    """Post ``text`` as a reply to ``item``. Raises :class:`PlatformCallError` on refusal.

    Only ever called from ``POST /inbox/reply`` — an explicit human click, after
    moderation. Never retried automatically: a retried POST can double-post.
    """
    platform = str(account.platform)
    target = item.get("reply_target") or {}
    async with client_factory() as http:
        if platform == "twitter":
            resp = await _x_request(
                http,
                "POST",
                f"{X_API}/tweets",
                account,
                db,
                json={"text": text, "reply": {"in_reply_to_tweet_id": target["tweet_id"]}},
            )
            if resp.status_code not in (200, 201):
                raise error_for_response("twitter", resp)
            reply_id = str(((resp.json() or {}).get("data") or {}).get("id") or "")
            return {"reply_id": reply_id, "url": f"https://x.com/i/status/{reply_id}"}

        if platform == "linkedin" and linkedin_inbox_enabled():
            token = decrypt_token(str(account.access_token_enc or ""))
            actor = await _li_person_urn(http, account, token)
            parent = str(target["parent_comment"])
            resp = await http.post(
                f"{LI_API}/rest/socialActions/{quote(parent, safe='')}/comments",
                headers={**_li_headers(token), "Content-Type": "application/json"},
                json={
                    "actor": actor,
                    "object": target["post_urn"],
                    "message": {"text": text},
                    "parentComment": parent,
                },
            )
            if resp.status_code not in (200, 201):
                raise error_for_response("linkedin", resp)
            reply_id = resp.headers.get("x-restli-id") or ""
            if not reply_id:
                try:
                    reply_id = str((resp.json() or {}).get("id") or "")
                except ValueError:
                    reply_id = ""
            return {"reply_id": reply_id, "url": _li_post_url(str(target["post_urn"]))}

    raise PlatformCallError(
        "api_access_denied", f"Replying on {_label(platform)} isn't available from CampaignForge."
    )
