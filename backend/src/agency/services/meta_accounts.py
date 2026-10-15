"""Resolving a Meta (Facebook / Instagram) connection into something publishable.

Every other platform's OAuth callback finishes at the token exchange: the token
*is* the identity. Meta is different. A user token identifies a *person*, and a
person administers zero or more **Pages**; publishing is addressed to a Page
(Facebook) or to the **Instagram Business Account linked to a Page** (Instagram),
and each Page carries its **own** access token. A user token cannot publish, and
the error Graph returns when you try does not say so — it reads like a missing
permission.

So the callback has to make Graph calls of its own before it can write a
``platform_account`` row. That is what this module does.

Before this existed, ``routers/oauth.py`` stored
``body.get("account_handle", f"{platform}_user")`` and the frontend's OAuth path
sends no handle, so every OAuth-connected Facebook account stored the literal
string ``"facebook_user"`` — which ``routers/publishing.py`` then passed as
``page_id``, producing a POST to ``/v19.0/facebook_user/feed``. Instagram would
have inherited the same bug. Resolution is server-side for that reason: the
handle is a fact about the token, not an input.

``GRAPH_VERSION`` is the single source of truth for the Graph version across
OAuth, publishing and metrics. Meta retires versions on a schedule; one constant
means one edit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

#: The one Graph API version in the codebase. Bump here, nowhere else.
GRAPH_VERSION = "v19.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

#: Platforms reached through Facebook Login and a Page. Instagram has no OAuth of
#: its own: you authorize through Facebook and address Instagram via the Page.
META_PLATFORMS = frozenset({"facebook", "instagram"})

_TIMEOUT = 20.0


class MetaAccountError(RuntimeError):
    """Resolution failed in a way the operator has to act on.

    The message is written to be shown to a person: it names the fix, because
    Graph's own errors here are famously uninterpretable (a personal Instagram
    account reports a permissions problem, not "this account cannot publish").
    """


class MetaAccountChoiceRequired(MetaAccountError):  # noqa: N818 - reads as the outcome
    """Several Pages; the user must pick.

    Silently taking the first Page is how one client's posts end up on another
    client's account, so this is a refusal, not a default. ``candidates`` is what
    the UI renders; the caller re-submits the callback with ``page_id``.
    """

    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        super().__init__(
            "This Facebook login administers several Pages. Choose which Page to connect."
        )
        self.candidates = candidates


@dataclass(frozen=True)
class ResolvedMetaAccount:
    """What the callback writes to ``platform_account``.

    ``account_handle`` is the id the publisher addresses — the Page id for
    Facebook, the Instagram Business Account id for Instagram (mirroring how
    ``routers/publishing.py`` passes ``page_id=account.account_handle``).
    """

    #: Page id (facebook) or IG Business Account id (instagram).
    account_handle: str
    display_name: str
    #: The **Page** access token. Never the user token — a user token cannot publish.
    access_token: str
    #: The owning Page, for both platforms.
    page_id: str


async def _graph_get(
    http: httpx.AsyncClient, path: str, *, token: str, params: dict[str, str] | None = None
) -> dict[str, Any]:
    query = {"access_token": token, **(params or {})}
    resp = await http.get(f"{GRAPH_BASE}/{path.lstrip('/')}", params=query)
    if resp.status_code != 200:
        # The token is in ``params``, never in the message.
        logger.warning("meta_graph_call_failed", path=path, status=resp.status_code)
        raise MetaAccountError(
            f"Facebook rejected the request for {path} ({resp.status_code}). "
            "Reconnect the account, or check that the app still holds the "
            "requested permissions."
        )
    body = resp.json()
    if not isinstance(body, dict):
        raise MetaAccountError(f"Facebook returned an unexpected response for {path}.")
    return body


async def _list_pages(http: httpx.AsyncClient, user_access_token: str) -> list[dict[str, Any]]:
    body = await _graph_get(
        http, "me/accounts", token=user_access_token, params={"fields": "id,name,access_token"}
    )
    pages = [p for p in body.get("data") or [] if isinstance(p, dict) and p.get("id")]
    if not pages:
        raise MetaAccountError(
            "This Facebook login does not administer any Pages. Publishing is "
            "addressed to a Page, so create one (or ask to be made an admin of "
            "the client's Page) and connect again."
        )
    return pages


async def _instagram_account_id(
    http: httpx.AsyncClient, page_id: str, page_token: str
) -> str | None:
    body = await _graph_get(
        http, page_id, token=page_token, params={"fields": "instagram_business_account"}
    )
    linked = body.get("instagram_business_account")
    if isinstance(linked, dict) and linked.get("id"):
        return str(linked["id"])
    return None


async def _instagram_username(http: httpx.AsyncClient, ig_user_id: str, page_token: str) -> str:
    body = await _graph_get(http, ig_user_id, token=page_token, params={"fields": "username"})
    username = body.get("username")
    return str(username) if username else ""


async def _candidates(
    http: httpx.AsyncClient, platform: str, pages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The choice list. For Instagram each entry says whether a linked IG account exists.

    A Page with no linked account is still listed — showing it greyed out with the
    reason is how the user learns which Page to fix, and hiding it looks like the
    Page vanished.
    """
    out: list[dict[str, Any]] = []
    for page in pages:
        page_id = str(page["id"])
        entry: dict[str, Any] = {
            "page_id": page_id,
            "name": str(page.get("name") or page_id),
            "instagram_business_account": None,
        }
        if platform == "instagram":
            token = str(page.get("access_token") or "")
            if token:
                try:
                    entry["instagram_business_account"] = await _instagram_account_id(
                        http, page_id, token
                    )
                except MetaAccountError:
                    # One unreadable Page must not sink the whole choice list.
                    logger.warning("meta_candidate_ig_lookup_failed", page_id=page_id)
        out.append(entry)
    return out


def _select_page(
    pages: list[dict[str, Any]], page_id: str | None
) -> dict[str, Any] | None:
    if page_id:
        for page in pages:
            if str(page["id"]) == str(page_id):
                return page
        raise MetaAccountError(
            "That Page is not one this Facebook login administers. Pick one of the "
            "Pages offered, or reconnect with an account that admins it."
        )
    if len(pages) == 1:
        return pages[0]
    return None


async def resolve_meta_account(
    platform: str, user_access_token: str, *, page_id: str | None = None
) -> ResolvedMetaAccount:
    """Turn a Facebook **user** token into a publishable Page/Instagram identity.

    Graph calls, in order:

    1. ``GET /me/accounts?fields=id,name,access_token`` — the Pages this user
       administers, each with its own Page token.
    2. Instagram only: ``GET /{page-id}?fields=instagram_business_account``.
    3. Instagram only: ``GET /{ig-user-id}?fields=username`` — the handle to show.

    Exactly one Page auto-selects. Several Pages with no explicit ``page_id``
    raises :class:`MetaAccountChoiceRequired`. Anything else that cannot produce a
    publishable identity raises :class:`MetaAccountError` with the fix named.
    """
    if platform not in META_PLATFORMS:
        raise MetaAccountError(f"{platform} is not resolved through a Facebook Page.")
    if not user_access_token:
        raise MetaAccountError("Facebook returned no access token; start the connection again.")

    async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
        pages = await _list_pages(http, user_access_token)
        page = _select_page(pages, page_id)
        if page is None:
            raise MetaAccountChoiceRequired(await _candidates(http, platform, pages))

        resolved_page_id = str(page["id"])
        page_name = str(page.get("name") or resolved_page_id)
        # The Page token, not the user token. ``/me/accounts`` is the only place it
        # is handed out, which is why it is read here and not re-fetched later.
        page_token = str(page.get("access_token") or "")
        if not page_token:
            raise MetaAccountError(
                f"Facebook did not return a Page access token for “{page_name}”. "
                "Reconnect and grant the Pages permissions — a user token cannot publish."
            )

        if platform == "facebook":
            return ResolvedMetaAccount(
                account_handle=resolved_page_id,
                display_name=page_name,
                access_token=page_token,
                page_id=resolved_page_id,
            )

        ig_user_id = await _instagram_account_id(http, resolved_page_id, page_token)
        if not ig_user_id:
            raise MetaAccountError(
                f"The Facebook Page “{page_name}” has no Instagram account linked to "
                "it. Convert the Instagram account to a Business or Creator account "
                "and link it to this Page in Instagram's settings, then connect "
                "again. A personal Instagram account can never publish via the API."
            )
        username = await _instagram_username(http, ig_user_id, page_token)

    return ResolvedMetaAccount(
        account_handle=ig_user_id,
        display_name=username or page_name,
        access_token=page_token,
        page_id=resolved_page_id,
    )
