"""Phase 7 Part B — resolving a Meta connection into something publishable.

Four things are asserted here, in descending order of how expensive the bug would be:

1. **``account_handle`` holds a real id, never a placeholder.** The callback used to
   store ``f"{platform}_user"`` for every OAuth connection because nothing resolved
   it server-side and the frontend's OAuth path sends no handle — so Facebook
   publishing was POSTing to ``/v19.0/facebook_user/feed`` in production. Instagram
   would have inherited it.
2. **The stored token is the Page token, not the user token.** A user token cannot
   publish and Graph's error does not say so, which makes this the most expensive
   kind of silent mistake: everything looks connected.
3. **Several Pages is a refusal, not a default.** Silently picking the first Page is
   how one client's posts end up on another client's account.
4. **Cross-org tenancy still 404s before any of it runs.** There is no RLS; the
   ``client_id`` resolution in the callback is the only thing stopping a connected
   account being attached to another tenant's client.

Every HTTP call is mocked through ``httpx.MockTransport``. Nothing here reaches Meta.
"""

from __future__ import annotations

import urllib.parse
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from agency.models.tables import PlatformAccount
from agency.services.meta_accounts import (
    GRAPH_VERSION,
    MetaAccountChoiceRequired,
    MetaAccountError,
    resolve_meta_account,
)
from agency.services.oauth_state import sign_state
from agency.utils.encryption import decrypt_token
from tests.conftest import auth_for, create_client_row, create_org

API = "/api/v1"

USER_TOKEN = "user-token-cannot-publish"
PAGE_TOKEN = "page-token-can-publish"
OTHER_PAGE_TOKEN = "other-page-token"


# ---------------------------------------------------------------------------
# Transport double
# ---------------------------------------------------------------------------
class Recorder:
    """Collects every request an httpx client makes, and answers from a script."""

    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []

    def handler(self, responder):
        def _handle(request: httpx.Request) -> httpx.Response:
            self.calls.append(request)
            return responder(request)

        return httpx.MockTransport(_handle)

    @property
    def paths(self) -> list[str]:
        """Request paths in order, with the Graph version prefix stripped."""
        return [c.url.path.replace(f"/{GRAPH_VERSION}", "", 1) for c in self.calls]

    def token_for(self, path_fragment: str) -> str | None:
        for call in self.calls:
            if path_fragment in str(call.url):
                return call.url.params.get("access_token")
        return None


@pytest.fixture
def transport(monkeypatch):
    """Route every ``httpx.AsyncClient`` opened under test into a recorder."""
    rec = Recorder()
    state: dict[str, Any] = {"responder": None}

    real_init = httpx.AsyncClient.__init__

    def _init(self, *args, **kwargs):
        kwargs["transport"] = rec.handler(lambda r: state["responder"](r))
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _init)

    def install(responder):
        state["responder"] = responder
        return rec

    return install


def _json(payload: dict[str, Any], status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def _graph_responder(
    *,
    pages: list[dict[str, Any]],
    ig_by_page: dict[str, str | None] | None = None,
    usernames: dict[str, str] | None = None,
    token_exchange: dict[str, Any] | None = None,
):
    """A scripted Meta Graph, addressed the way ``meta_accounts`` addresses it."""
    ig_by_page = ig_by_page or {}
    usernames = usernames or {}

    def responder(request: httpx.Request) -> httpx.Response:
        path = request.url.path.replace(f"/{GRAPH_VERSION}", "", 1).strip("/")
        if path == "oauth/access_token":
            return _json(token_exchange or {"access_token": USER_TOKEN})
        if path == "me/accounts":
            return _json({"data": pages})
        fields = request.url.params.get("fields", "")
        if fields == "instagram_business_account":
            linked = ig_by_page.get(path)
            return _json({"id": path, "instagram_business_account": {"id": linked}} if linked
                         else {"id": path})
        if fields == "username":
            return _json({"id": path, "username": usernames.get(path, "")})
        return _json({"error": {"message": f"unscripted path {path}"}}, 400)

    return responder


ONE_PAGE = [{"id": "page-111", "name": "Acme Coffee", "access_token": PAGE_TOKEN}]
TWO_PAGES = [
    {"id": "page-111", "name": "Acme Coffee", "access_token": PAGE_TOKEN},
    {"id": "page-222", "name": "Acme Tea", "access_token": OTHER_PAGE_TOKEN},
]


# ---------------------------------------------------------------------------
# 1. The placeholder bug: resolution produces a real id
# ---------------------------------------------------------------------------
async def test_facebook_resolution_picks_the_page_id_not_a_placeholder(transport):
    rec = transport(_graph_responder(pages=ONE_PAGE))

    resolved = await resolve_meta_account("facebook", USER_TOKEN)

    assert resolved.account_handle == "page-111"
    assert resolved.account_handle != "facebook_user"
    assert resolved.page_id == "page-111"
    assert resolved.display_name == "Acme Coffee"
    # One call only: Facebook needs no Instagram lookup.
    assert rec.paths == ["/me/accounts"]


async def test_instagram_resolution_stores_the_ig_id_as_account_handle(transport):
    rec = transport(
        _graph_responder(
            pages=ONE_PAGE,
            ig_by_page={"page-111": "ig-999"},
            usernames={"ig-999": "acmecoffee"},
        )
    )

    resolved = await resolve_meta_account("instagram", USER_TOKEN)

    # The publisher addresses ``/{ig-user-id}/media``, so the handle is the IG id —
    # not the Page id, and not the username.
    assert resolved.account_handle == "ig-999"
    assert resolved.page_id == "page-111"
    assert resolved.display_name == "acmecoffee"
    # The three calls of section B2, in order.
    assert rec.paths == ["/me/accounts", "/page-111", "/ig-999"]


# ---------------------------------------------------------------------------
# 2. The Page token, never the user token
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("platform", ["facebook", "instagram"])
async def test_resolution_returns_the_page_access_token(transport, platform):
    transport(
        _graph_responder(
            pages=ONE_PAGE, ig_by_page={"page-111": "ig-999"}, usernames={"ig-999": "acme"}
        )
    )

    resolved = await resolve_meta_account(platform, USER_TOKEN)

    assert resolved.access_token == PAGE_TOKEN
    assert resolved.access_token != USER_TOKEN


async def test_instagram_lookups_use_the_page_token(transport):
    """The IG lookups authenticate as the Page, which is also what will publish."""
    rec = transport(
        _graph_responder(
            pages=ONE_PAGE, ig_by_page={"page-111": "ig-999"}, usernames={"ig-999": "acme"}
        )
    )

    await resolve_meta_account("instagram", USER_TOKEN)

    assert rec.token_for("/me/accounts") == USER_TOKEN
    assert rec.token_for("/page-111") == PAGE_TOKEN
    assert rec.token_for("/ig-999") == PAGE_TOKEN


async def test_a_page_without_its_own_token_is_refused(transport):
    transport(_graph_responder(pages=[{"id": "page-111", "name": "Acme"}]))

    with pytest.raises(MetaAccountError) as exc:
        await resolve_meta_account("facebook", USER_TOKEN)

    assert "cannot publish" in str(exc.value)


# ---------------------------------------------------------------------------
# 3. Multi-Page: refuse and offer the choice
# ---------------------------------------------------------------------------
async def test_a_single_page_auto_selects(transport):
    transport(_graph_responder(pages=ONE_PAGE))

    resolved = await resolve_meta_account("facebook", USER_TOKEN)

    assert resolved.page_id == "page-111"


async def test_several_pages_raise_a_choice_with_candidates(transport):
    transport(_graph_responder(pages=TWO_PAGES))

    with pytest.raises(MetaAccountChoiceRequired) as exc:
        await resolve_meta_account("facebook", USER_TOKEN)

    assert exc.value.candidates == [
        {"page_id": "page-111", "name": "Acme Coffee", "instagram_business_account": None},
        {"page_id": "page-222", "name": "Acme Tea", "instagram_business_account": None},
    ]


async def test_instagram_candidates_say_which_pages_have_a_linked_account(transport):
    """A Page with no linked IG account is still listed — with ``None``, so the UI
    can say which one needs fixing rather than appearing to lose a Page."""
    transport(_graph_responder(pages=TWO_PAGES, ig_by_page={"page-111": "ig-999"}))

    with pytest.raises(MetaAccountChoiceRequired) as exc:
        await resolve_meta_account("instagram", USER_TOKEN)

    assert exc.value.candidates == [
        {"page_id": "page-111", "name": "Acme Coffee", "instagram_business_account": "ig-999"},
        {"page_id": "page-222", "name": "Acme Tea", "instagram_business_account": None},
    ]


async def test_an_explicit_page_id_disambiguates(transport):
    transport(_graph_responder(pages=TWO_PAGES))

    resolved = await resolve_meta_account("facebook", USER_TOKEN, page_id="page-222")

    assert resolved.account_handle == "page-222"
    assert resolved.display_name == "Acme Tea"
    assert resolved.access_token == OTHER_PAGE_TOKEN


async def test_a_page_id_the_user_does_not_administer_is_refused(transport):
    transport(_graph_responder(pages=TWO_PAGES))

    with pytest.raises(MetaAccountError) as exc:
        await resolve_meta_account("facebook", USER_TOKEN, page_id="page-someone-elses")

    assert not isinstance(exc.value, MetaAccountChoiceRequired)
    assert "not one this Facebook login administers" in str(exc.value)


async def test_no_pages_at_all_names_the_fix(transport):
    transport(_graph_responder(pages=[]))

    with pytest.raises(MetaAccountError) as exc:
        await resolve_meta_account("facebook", USER_TOKEN)

    assert "does not administer any Pages" in str(exc.value)


# ---------------------------------------------------------------------------
# A Page with no Instagram account: the error that has to be readable
# ---------------------------------------------------------------------------
async def test_a_page_with_no_instagram_account_errors_clearly(transport):
    transport(_graph_responder(pages=ONE_PAGE, ig_by_page={}))

    with pytest.raises(MetaAccountError) as exc:
        await resolve_meta_account("instagram", USER_TOKEN)

    message = str(exc.value)
    assert "Acme Coffee" in message
    # The fix, named: this is the most common reason the project dies at the demo.
    assert "Business or Creator" in message
    assert "link it to this Page" in message
    assert "personal Instagram account can never publish" in message


async def test_instagram_falls_back_to_the_page_name_when_username_is_empty(transport):
    transport(_graph_responder(pages=ONE_PAGE, ig_by_page={"page-111": "ig-999"}))

    resolved = await resolve_meta_account("instagram", USER_TOKEN)

    assert resolved.account_handle == "ig-999"
    assert resolved.display_name == "Acme Coffee"


async def test_a_graph_failure_does_not_leak_the_token(transport):
    transport(lambda r: _json({"error": {"message": "bad"}}, 400))

    with pytest.raises(MetaAccountError) as exc:
        await resolve_meta_account("facebook", USER_TOKEN)

    assert USER_TOKEN not in str(exc.value)


async def test_a_non_meta_platform_is_rejected(transport):
    with pytest.raises(MetaAccountError):
        await resolve_meta_account("twitter", USER_TOKEN)


# ---------------------------------------------------------------------------
# One Graph version in the codebase
# ---------------------------------------------------------------------------
def test_oauth_configs_use_the_shared_graph_version():
    from agency.routers.oauth import OAUTH_CONFIGS

    for platform in ("facebook", "instagram"):
        config = OAUTH_CONFIGS[platform]
        assert GRAPH_VERSION in config["authorize_url"]
        assert GRAPH_VERSION in config["token_url"]
        assert "v18.0" not in config["authorize_url"]
        assert "v18.0" not in config["token_url"]


def test_instagram_is_configured_as_a_meta_platform_without_pkce():
    from agency.routers.oauth import OAUTH_CONFIGS, PKCE_PLATFORMS, PLATFORM_CLIENT_KEYS

    assert PLATFORM_CLIENT_KEYS["instagram"] == ("meta_app_id", "meta_app_secret")
    assert "instagram" not in PKCE_PLATFORMS
    scopes = OAUTH_CONFIGS["instagram"]["scopes"].split(",")
    assert scopes == [
        "instagram_basic",
        "instagram_content_publish",
        "pages_show_list",
        "pages_read_engagement",
    ]


def test_instagram_stays_out_of_the_reported_providers_while_publishing_is_off():
    """Product rule 1. The connect code is ready; the capability is still switched off.

    Derived from ``UNAVAILABLE_PUBLISH_PLATFORMS`` so the go-live commit flips it on.
    """
    from agency.routers.oauth import oauth_platform_status
    from agency.services.publishing import UNAVAILABLE_PUBLISH_PLATFORMS

    assert "instagram" in UNAVAILABLE_PUBLISH_PLATFORMS, "go-live is a separate commit"
    assert set(oauth_platform_status()) == {"twitter", "linkedin", "facebook"}


# ---------------------------------------------------------------------------
# 4. The callback: real handle stored, choice surfaced, tenancy still holds
# ---------------------------------------------------------------------------
@pytest.fixture
def meta_configured(monkeypatch):
    from agency.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "meta_app_id", "meta-id", raising=False)
    monkeypatch.setattr(settings, "meta_app_secret", "meta-secret", raising=False)
    return settings


@pytest.fixture
async def org(session_factory):
    org_id = await create_org(session_factory, "Meta Org", slug=f"meta-{uuid4().hex[:6]}")
    client_id = await create_client_row(session_factory, org_id, "Acme")
    headers = await auth_for(session_factory, org_id, "owner")
    return {"org_id": org_id, "client_id": client_id, "headers": headers}


def _callback_body(org: dict[str, Any], platform: str, **extra: Any) -> dict[str, Any]:
    return {
        "code": "auth-code",
        "client_id": str(org["client_id"]),
        "state": sign_state(
            org_id=org["org_id"], client_id=org["client_id"], platform=platform
        ),
        **extra,
    }


async def _stored(session_factory, org_id: UUID) -> PlatformAccount | None:
    async with session_factory() as session:
        rows = await session.execute(
            select(PlatformAccount).where(PlatformAccount.org_id == org_id)
        )
        return rows.scalars().first()


@pytest.mark.parametrize(
    ("platform", "expected_handle", "expected_name"),
    [("facebook", "page-111", "Acme Coffee"), ("instagram", "ig-999", "acmecoffee")],
)
async def test_callback_stores_the_resolved_handle_and_page_token(
    client,
    session_factory,
    org,
    meta_configured,
    transport,
    platform,
    expected_handle,
    expected_name,
):
    transport(
        _graph_responder(
            pages=ONE_PAGE,
            ig_by_page={"page-111": "ig-999"},
            usernames={"ig-999": "acmecoffee"},
        )
    )

    resp = await client.post(
        f"{API}/oauth/{platform}/callback",
        json=_callback_body(org, platform),
        headers=org["headers"],
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["account_handle"] == expected_handle

    row = await _stored(session_factory, org["org_id"])
    assert row is not None
    # The bug this phase fixes: never the placeholder again.
    assert row.account_handle == expected_handle
    assert row.account_handle != f"{platform}_user"
    assert row.display_name == expected_name
    assert row.status == "connected"
    # The Page token is what was stored, so the publisher can actually post.
    assert decrypt_token(row.access_token_enc) == PAGE_TOKEN


async def test_callback_ignores_an_account_handle_sent_by_the_client(
    client, session_factory, org, meta_configured, transport
):
    """The handle is a fact about the token, not an input — a spoofed Page id in the
    body must not become the id the publisher addresses."""
    transport(_graph_responder(pages=ONE_PAGE))

    resp = await client.post(
        f"{API}/oauth/facebook/callback",
        json=_callback_body(
            org, "facebook", account_handle="page-victim", display_name="Not Acme"
        ),
        headers=org["headers"],
    )

    assert resp.status_code == 200, resp.text
    row = await _stored(session_factory, org["org_id"])
    assert row is not None
    assert row.account_handle == "page-111"
    assert row.display_name == "Acme Coffee"


async def test_callback_409s_with_candidates_when_several_pages_exist(
    client, session_factory, org, meta_configured, transport
):
    transport(_graph_responder(pages=TWO_PAGES, ig_by_page={"page-111": "ig-999"}))

    resp = await client.post(
        f"{API}/oauth/instagram/callback",
        json=_callback_body(org, "instagram"),
        headers=org["headers"],
    )

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "meta_page_choice_required"
    assert [c["page_id"] for c in detail["candidates"]] == ["page-111", "page-222"]
    assert detail["candidates"][0]["instagram_business_account"] == "ig-999"
    assert detail["candidates"][1]["instagram_business_account"] is None

    # Nothing was written. A 409 that still connected an arbitrary Page would be
    # the exact failure the refusal exists to prevent.
    assert await _stored(session_factory, org["org_id"]) is None


async def test_callback_accepts_page_id_to_disambiguate(
    client, session_factory, org, meta_configured, transport
):
    transport(_graph_responder(pages=TWO_PAGES))

    resp = await client.post(
        f"{API}/oauth/facebook/callback",
        json=_callback_body(org, "facebook", page_id="page-222"),
        headers=org["headers"],
    )

    assert resp.status_code == 200, resp.text
    row = await _stored(session_factory, org["org_id"])
    assert row is not None
    assert row.account_handle == "page-222"
    assert decrypt_token(row.access_token_enc) == OTHER_PAGE_TOKEN


async def test_callback_502s_when_the_page_has_no_instagram_account(
    client, session_factory, org, meta_configured, transport
):
    transport(_graph_responder(pages=ONE_PAGE, ig_by_page={}))

    resp = await client.post(
        f"{API}/oauth/instagram/callback",
        json=_callback_body(org, "instagram"),
        headers=org["headers"],
    )

    assert resp.status_code == 502, resp.text
    assert "Business or Creator" in resp.json()["detail"]
    assert await _stored(session_factory, org["org_id"]) is None


async def test_callback_rejects_another_orgs_client_before_resolving(
    client, session_factory, org, meta_configured, transport
):
    """TENANCY. There is no RLS: the ``client_id`` resolution in the callback is the
    only thing stopping a connected account landing on another tenant's client.

    Delete the ``Client.org_id == org_id`` filter in ``oauth_callback`` and this fails.
    """
    other_org = await create_org(
        session_factory, "Other Org", slug=f"other-{uuid4().hex[:6]}"
    )
    other_client = await create_client_row(session_factory, other_org, "Theirs")
    rec = transport(_graph_responder(pages=ONE_PAGE))

    resp = await client.post(
        f"{API}/oauth/facebook/callback",
        json={
            "code": "auth-code",
            "client_id": str(other_client),
            "state": sign_state(
                org_id=org["org_id"], client_id=other_client, platform="facebook"
            ),
        },
        headers=org["headers"],
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Client not found"
    # It refused before the token exchange, so no Graph call was made at all.
    assert rec.calls == []
    assert await _stored(session_factory, other_org) is None
    assert await _stored(session_factory, org["org_id"]) is None


async def test_instagram_authorize_url_carries_the_publish_scope(
    client, org, meta_configured
):
    resp = await client.get(
        f"{API}/oauth/instagram/authorize",
        params={"client_id": str(org["client_id"])},
        headers=org["headers"],
    )

    assert resp.status_code == 200, resp.text
    url = resp.json()["authorize_url"]
    assert url.startswith(f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth?")
    params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert "instagram_content_publish" in params["scope"][0]
    # No PKCE on the Meta flow.
    assert "code_challenge" not in params
    assert params["redirect_uri"][0].endswith("/api/oauth/instagram/callback")
