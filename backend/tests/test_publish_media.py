"""Phase 6 — media on connected channels.

Three things are worth asserting here, in descending order of how expensive the
bug would be:

1. **A post with no media publishes exactly as it always did.** Every post in the
   product today is text-only, so this is the regression that matters most; the
   media path is additive and must stay invisible when ``media_urls`` is empty.
2. **A failed upload never produces a success-shaped result.** ``publish()``
   wraps a publisher's normal return as ``{"success": True, ...}`` and the
   callers mark the piece ``published`` and charge a post for it — which is
   exactly how Instagram once burned quota for posts that were never made.
3. ``media_urls`` reaches the publisher from **both** call sites. They build the
   same dict and a divergence means "Publish now" and a scheduled post produce
   different posts from one approved piece.

Every HTTP call is mocked. Nothing here reaches a real platform.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from agency.models.tables import ContentPiece
from agency.services import media_storage, publishing
from agency.services.publishing import (
    MediaUploadError,
    PlatformPublisher,
    _local_storage_key,
    _media_list,
    publisher,
)
from agency.services.scheduler import SchedulerEngine
from tests.conftest import (
    auth_for,
    create_client_row,
    create_content_row,
    create_org,
    create_platform_account,
    create_subscription,
)

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
    b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ---------------------------------------------------------------------------
# Transport doubles
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

    def to(self, substring: str) -> list[httpx.Request]:
        return [c for c in self.calls if substring in str(c.url)]

    def bodies(self, substring: str) -> list[dict[str, Any]]:
        out = []
        for call in self.to(substring):
            try:
                out.append(json.loads(call.content))
            except ValueError:
                out.append({})
        return out


@pytest.fixture
def transport(monkeypatch):
    """Route every ``httpx.AsyncClient`` the publisher opens into a recorder."""
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


def _json(payload: dict[str, Any], status: int = 200, headers: dict | None = None):
    return httpx.Response(status, json=payload, headers=headers or {})


@pytest.fixture
def media_on_disk(monkeypatch, tmp_path):
    """One real asset under the ``local`` driver, and the URL that points at it."""
    monkeypatch.setattr(media_storage, "active_driver", lambda: "local")
    settings = media_storage._settings()
    monkeypatch.setattr(settings, "media_local_dir", str(tmp_path), raising=False)
    key = f"{uuid4()}/{uuid4()}/{uuid4()}/{uuid4()}.png"
    dest = tmp_path / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(PNG)
    return f"/api/v1/media/{key}"


# ---------------------------------------------------------------------------
# The regression that matters most: no media, nothing changes
# ---------------------------------------------------------------------------
async def test_twitter_without_media_posts_exactly_as_before(transport):
    rec = transport(lambda r: _json({"data": {"id": "123"}}))

    out = await PlatformPublisher()._publish_twitter(
        {"body": "hello", "hashtags": ["ai"]}, {"access_token": "tok"}
    )

    assert out["post_id"] == "123"
    # One call, to /2/tweets. No media endpoint was touched at all.
    assert len(rec.calls) == 1
    assert rec.to("/2/media/upload") == []
    assert json.loads(rec.calls[0].content) == {"text": "hello\n\n#ai"}


async def test_linkedin_without_media_keeps_sharemediacategory_none(transport):
    def responder(request: httpx.Request) -> httpx.Response:
        if "userinfo" in str(request.url):
            return _json({"sub": "abc"})
        return _json({"id": "urn:li:share:9"}, headers={"X-RestLi-Id": "urn:li:share:9"})

    rec = transport(responder)

    await PlatformPublisher()._publish_linkedin({"body": "hi"}, {"access_token": "tok"})

    assert rec.to("registerUpload") == []
    share = rec.bodies("ugcPosts")[0]["specificContent"]["com.linkedin.ugc.ShareContent"]
    assert share["shareMediaCategory"] == "NONE"
    assert "media" not in share


async def test_facebook_without_media_still_posts_to_feed(transport):
    rec = transport(lambda r: _json({"id": "page_1"}))

    out = await PlatformPublisher()._publish_facebook(
        {"body": "hi"}, {"access_token": "tok", "page_id": "p1"}
    )

    assert out["post_id"] == "page_1"
    assert rec.to("/photos") == []
    assert rec.to("/p1/feed")
    assert json.loads(rec.calls[0].content) == {"message": "hi"}


async def test_empty_media_urls_is_the_same_as_absent():
    assert _media_list({"body": "x"}, "twitter") == []
    assert _media_list({"body": "x", "media_urls": []}, "twitter") == []
    assert _media_list({"body": "x", "media_urls": None}, "twitter") == []


# ---------------------------------------------------------------------------
# Per-platform upload shape
# ---------------------------------------------------------------------------
async def test_twitter_init_append_finalize_then_media_ids(transport, media_on_disk):
    def responder(request: httpx.Request) -> httpx.Response:
        if "/2/media/upload" in str(request.url):
            return _json({"data": {"id": "m-77"}})
        return _json({"data": {"id": "t-1"}})

    rec = transport(responder)

    await PlatformPublisher()._publish_twitter(
        {"body": "look", "media_urls": [media_on_disk]}, {"access_token": "tok"}
    )

    uploads = rec.to("/2/media/upload")
    assert len(uploads) == 3, "INIT, one APPEND, FINALIZE"
    first = uploads[0].content.decode()
    assert "command=INIT" in first
    assert f"total_bytes={len(PNG)}" in first
    assert "media_category=tweet_image" in first
    assert "image%2Fpng" in first
    # APPEND carries the bytes as a multipart part plus the segment index.
    assert b'name="command"\r\n\r\nAPPEND' in uploads[1].content
    assert b'name="segment_index"\r\n\r\n0' in uploads[1].content
    assert b'name="media"' in uploads[1].content
    assert PNG in uploads[1].content
    assert "command=FINALIZE" in uploads[2].content.decode()
    assert "media_id=m-77" in uploads[2].content.decode()

    tweet = rec.bodies("/2/tweets")[0]
    assert tweet == {"text": "look", "media": {"media_ids": ["m-77"]}}


async def test_linkedin_register_put_then_asset_urn(transport, media_on_disk):
    def responder(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "userinfo" in url:
            return _json({"sub": "abc"})
        if "registerUpload" in url:
            return _json(
                {
                    "value": {
                        "asset": "urn:li:digitalmediaAsset:A1",
                        "uploadMechanism": {
                            "com.linkedin.digitalmedia.uploading."
                            "MediaUploadHttpRequest": {
                                "uploadUrl": "https://upload.linkedin.example/a1"
                            }
                        },
                    }
                }
            )
        if "upload.linkedin.example" in url:
            return httpx.Response(201)
        return _json({"id": "urn:li:share:9"}, headers={"X-RestLi-Id": "urn:li:share:9"})

    rec = transport(responder)

    await PlatformPublisher()._publish_linkedin(
        {"body": "hi", "media_urls": [media_on_disk]}, {"access_token": "tok"}
    )

    register = rec.bodies("registerUpload")[0]["registerUploadRequest"]
    assert register["recipes"] == ["urn:li:digitalmediaRecipe:feedshare-image"]
    assert register["owner"] == "urn:li:person:abc"
    assert register["serviceRelationships"] == [
        {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
    ]

    put = rec.to("upload.linkedin.example")[0]
    assert put.method == "PUT"
    assert put.content == PNG
    assert put.headers["Authorization"] == "Bearer tok"
    # The Restli header belongs to the API host, not the upload host.
    assert "X-Restli-Protocol-Version" not in put.headers

    share = rec.bodies("ugcPosts")[0]["specificContent"]["com.linkedin.ugc.ShareContent"]
    assert share["shareMediaCategory"] == "IMAGE"
    assert share["media"] == [
        {"status": "READY", "media": "urn:li:digitalmediaAsset:A1"}
    ]


async def test_facebook_single_image_posts_to_photos_with_url(transport):
    rec = transport(lambda r: _json({"id": "ph_1", "post_id": "p1_9"}))

    out = await PlatformPublisher()._publish_facebook(
        {"body": "caption", "media_urls": ["https://cdn.example/a.png"]},
        {"access_token": "tok", "page_id": "p1"},
    )

    assert rec.to("/p1/feed") == []
    photo = rec.to("/p1/photos")[0]
    assert dict(photo.url.params) == {
        "access_token": "tok",
        "url": "https://cdn.example/a.png",
        "message": "caption",
    }
    # The feed story, not the photo id — that is what a post URL should open.
    assert out["post_id"] == "p1_9"


async def test_facebook_multi_image_uses_unpublished_photos_then_attached_media(transport):
    def responder(request: httpx.Request) -> httpx.Response:
        if "/photos" in str(request.url):
            return _json({"id": f"ph_{len(rec.to('/photos'))}"})
        return _json({"id": "p1_42"})

    rec = transport(responder)

    out = await PlatformPublisher()._publish_facebook(
        {
            "body": "two",
            "media_urls": ["https://cdn.example/a.png", "https://cdn.example/b.png"],
        },
        {"access_token": "tok", "page_id": "p1"},
    )

    photos = rec.to("/photos")
    assert len(photos) == 2
    assert all(dict(p.url.params)["published"] == "false" for p in photos)

    feed = dict(rec.to("/p1/feed")[0].url.params)
    assert feed["message"] == "two"
    assert json.loads(feed["attached_media[0]"]) == {"media_fbid": "ph_1"}
    assert json.loads(feed["attached_media[1]"]) == {"media_fbid": "ph_2"}
    assert out["post_id"] == "p1_42"


async def test_facebook_refuses_an_app_relative_media_url(transport, media_on_disk):
    """Meta fetches by URL. A local-driver URL has no host, so it cannot work."""
    transport(lambda r: _json({"id": "x"}))

    with pytest.raises(MediaUploadError, match="publicly reachable"):
        await PlatformPublisher()._publish_facebook(
            {"body": "hi", "media_urls": [media_on_disk]},
            {"access_token": "tok", "page_id": "p1"},
        )


# ---------------------------------------------------------------------------
# A failed upload must not look like a success
# ---------------------------------------------------------------------------
async def test_upload_failure_is_an_explicit_failure_not_a_text_only_post(
    transport, media_on_disk
):
    """The piece must not be publishable off the back of this result."""

    def responder(request: httpx.Request) -> httpx.Response:
        if "/2/media/upload" in str(request.url):
            return _json({"errors": ["nope"]}, status=400)
        return _json({"data": {"id": "t-1"}})

    rec = transport(responder)

    result = await publisher.publish(
        "twitter", {"body": "look", "media_urls": [media_on_disk]}, {"access_token": "tok"}
    )

    assert result["success"] is False
    assert result.get("error")
    assert "post_id" not in result
    # Crucially: the tweet was never sent, so there is no live text-only post
    # that the approved copy did not describe.
    assert rec.to("/2/tweets") == []


async def test_missing_local_bytes_fail_rather_than_publish_without_the_image(
    transport, monkeypatch
):
    transport(lambda r: _json({"data": {"id": "t-1"}}))
    monkeypatch.setattr(media_storage, "active_driver", lambda: "local")

    result = await publisher.publish(
        "twitter",
        {"body": "look", "media_urls": [f"/api/v1/media/{uuid4()}/x/y/z.png"]},
        {"access_token": "tok"},
    )

    assert result["success"] is False
    assert "missing from local storage" in result["error"]


async def test_linkedin_register_without_an_upload_target_fails(transport, media_on_disk):
    def responder(request: httpx.Request) -> httpx.Response:
        if "userinfo" in str(request.url):
            return _json({"sub": "abc"})
        if "registerUpload" in str(request.url):
            return _json({"value": {}})
        return _json({"id": "urn:li:share:9"})

    rec = transport(responder)

    result = await publisher.publish(
        "linkedin", {"body": "hi", "media_urls": [media_on_disk]}, {"access_token": "tok"}
    )

    assert result["success"] is False
    assert rec.to("ugcPosts") == []


async def test_instagram_stays_unavailable():
    """§1H: removing this needs a reviewed Meta app, and it moves with the frontend."""
    assert "instagram" in publishing.UNAVAILABLE_PUBLISH_PLATFORMS
    assert "tiktok" in publishing.UNAVAILABLE_PUBLISH_PLATFORMS

    result = await publisher.publish(
        "instagram", {"body": "hi", "media_urls": ["https://cdn.example/a.png"]}, {}
    )
    assert result == {
        "success": False,
        "error": publishing.UNAVAILABLE_PUBLISH_PLATFORMS["instagram"],
    }


# ---------------------------------------------------------------------------
# Instagram — container → publish (Phase 7)
#
# Every test here calls ``_publish_instagram`` directly, because ``instagram`` is
# still in ``UNAVAILABLE_PUBLISH_PLATFORMS`` until Meta app review lands and
# ``publish()`` short-circuits before the publisher runs. Testing behind the flag
# is the point: the real publisher has to be in place *before* the flag moves, or
# the flag move re-creates the stub incident.
# ---------------------------------------------------------------------------
IG_QUOTA_OK = {"data": [{"config": {"quota_total": 50, "quota_duration": 86400}, "quota_usage": 3}]}


def _ig_responder(
    *,
    quota: dict[str, Any] | None = None,
    statuses: list[str] | None = None,
):
    """Answers the whole Instagram flow: quota, containers, status, publish."""
    created = {"n": 0}
    polls = {"n": 0}

    def responder(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "content_publishing_limit" in url:
            return _json(quota if quota is not None else IG_QUOTA_OK)
        if url.endswith("/media_publish") or "/media_publish?" in url:
            return _json({"id": "ig_media_1"})
        if "/media?" in url or url.endswith("/media"):
            created["n"] += 1
            return _json({"id": f"c{created['n']}"})
        if "fields=status_code" in url or "status_code" in url:
            seq = statuses or ["FINISHED"]
            idx = min(polls["n"], len(seq) - 1)
            polls["n"] += 1
            return _json({"status_code": seq[idx]})
        if "permalink" in url:
            return _json({"permalink": "https://www.instagram.com/p/ABC/"})
        return _json({"id": "ig_media_1"})

    return responder


async def test_instagram_single_image_creates_a_container_then_publishes(transport):
    rec = transport(_ig_responder())

    out = await PlatformPublisher()._publish_instagram(
        {"body": "caption", "hashtags": ["ai"], "media_urls": ["https://cdn.example/a.png"]},
        {"access_token": "tok", "page_id": "ig_17841400000000000"},
    )

    containers = [
        c
        for c in rec.calls
        if "/media" in str(c.url) and "media_publish" not in str(c.url)
    ]
    publishes = rec.to("/media_publish")
    assert len(containers) == 1
    assert len(publishes) == 1
    # Order matters: the container has to exist before it can be published.
    assert rec.calls.index(containers[0]) < rec.calls.index(publishes[0])

    params = dict(containers[0].url.params)
    assert params["image_url"] == "https://cdn.example/a.png"
    assert params["caption"] == "caption\n\n#ai"
    assert params["access_token"] == "tok"
    # Addressed at the IG Business Account id carried in ``page_id``.
    assert "/ig_17841400000000000/media" in str(containers[0].url)
    assert dict(publishes[0].url.params)["creation_id"] == "c1"

    assert out["post_id"] == "ig_media_1"
    assert out["url"] == "https://www.instagram.com/p/ABC/"


async def test_instagram_carousel_posts_children_then_one_parent(transport):
    rec = transport(_ig_responder())

    urls = [f"https://cdn.example/{i}.png" for i in range(3)]
    await PlatformPublisher()._publish_instagram(
        {"body": "three", "media_urls": urls},
        {"access_token": "tok", "page_id": "ig_1"},
    )

    containers = [
        dict(c.url.params)
        for c in rec.calls
        if "/media" in str(c.url) and "media_publish" not in str(c.url)
    ]
    children = [c for c in containers if c.get("is_carousel_item") == "true"]
    parents = [c for c in containers if c.get("media_type") == "CAROUSEL"]
    assert len(children) == 3
    assert [c["image_url"] for c in children] == urls
    assert all("caption" not in c for c in children), "the caption belongs to the parent"
    assert len(parents) == 1
    assert parents[0]["children"] == "c1,c2,c3"
    assert parents[0]["caption"] == "three"
    assert len(rec.to("/media_publish")) == 1
    assert dict(rec.to("/media_publish")[0].url.params)["creation_id"] == "c4"


async def test_instagram_carousel_is_capped_at_ten(transport):
    """Without ``MAX_MEDIA_PER_POST["instagram"]`` the lookup default of 1 made a
    carousel silently become a single image."""
    assert publishing.MAX_MEDIA_PER_POST["instagram"] == 10
    urls = [f"https://cdn.example/{i}.png" for i in range(14)]
    assert len(_media_list({"media_urls": urls}, "instagram")) == 10

    rec = transport(_ig_responder())
    await PlatformPublisher()._publish_instagram(
        {"body": "many", "media_urls": urls}, {"access_token": "tok", "page_id": "ig_1"}
    )

    containers = [
        dict(c.url.params)
        for c in rec.calls
        if "/media" in str(c.url) and "media_publish" not in str(c.url)
    ]
    assert len([c for c in containers if c.get("is_carousel_item") == "true"]) == 10
    assert dict(rec.to("/media_publish")[0].url.params)["creation_id"] == "c11"


async def test_instagram_reel_waits_for_the_container_to_finish(transport, monkeypatch):
    monkeypatch.setattr(publishing, "IG_CONTAINER_POLL_SECONDS", 0.0)
    rec = transport(_ig_responder(statuses=["IN_PROGRESS", "IN_PROGRESS", "FINISHED"]))

    out = await PlatformPublisher()._publish_instagram(
        {"body": "reel", "media_urls": ["https://cdn.example/v.mp4"]},
        {"access_token": "tok", "page_id": "ig_1"},
    )

    container = dict(
        [c for c in rec.calls if "/media" in str(c.url) and "media_publish" not in str(c.url)][
            0
        ].url.params
    )
    assert container["media_type"] == "REELS"
    assert container["video_url"] == "https://cdn.example/v.mp4"
    assert len(rec.to("status_code")) == 3
    # Published only after FINISHED.
    assert rec.calls.index(rec.to("/media_publish")[0]) > rec.calls.index(
        rec.to("status_code")[-1]
    )
    assert out["post_id"] == "ig_media_1"


async def test_instagram_refuses_a_container_stuck_pending(transport, monkeypatch):
    monkeypatch.setattr(publishing, "IG_CONTAINER_POLL_SECONDS", 0.0)
    rec = transport(_ig_responder(statuses=["IN_PROGRESS"]))

    with pytest.raises(MediaUploadError, match="still processing"):
        await PlatformPublisher()._publish_instagram(
            {"body": "reel", "media_urls": ["https://cdn.example/v.mp4"]},
            {"access_token": "tok", "page_id": "ig_1"},
        )

    assert len(rec.to("status_code")) == publishing.IG_CONTAINER_POLL_ATTEMPTS
    # The whole point: an unfinished container is never published.
    assert rec.to("/media_publish") == []


async def test_instagram_refuses_a_text_only_post(transport):
    """Not "unsupported" — Instagram's API has no text-only post at all."""
    rec = transport(_ig_responder())

    with pytest.raises(MediaUploadError, match="text-only"):
        await PlatformPublisher()._publish_instagram(
            {"body": "words only"}, {"access_token": "tok", "page_id": "ig_1"}
        )

    assert rec.calls == []


async def test_instagram_text_only_does_not_look_like_a_success(transport, monkeypatch):
    """Through ``publish()`` with the availability guard lifted, a text-only post
    is an explicit failure — never the success-shaped body the old stub returned.
    """
    transport(_ig_responder())
    monkeypatch.setattr(publishing, "UNAVAILABLE_PUBLISH_PLATFORMS", {"tiktok": "no"})

    result = await publisher.publish(
        "instagram", {"body": "hi"}, {"access_token": "tok", "page_id": "ig_1"}
    )

    assert result["success"] is False
    assert "text-only" in result["error"]
    assert "post_id" not in result


async def test_instagram_refuses_an_app_relative_media_url(transport, media_on_disk):
    """Graph fetches the bytes, so the ``local`` driver can never work here."""
    rec = transport(_ig_responder())

    with pytest.raises(MediaUploadError, match="S3_ENDPOINT_URL"):
        await PlatformPublisher()._publish_instagram(
            {"body": "hi", "media_urls": [media_on_disk]},
            {"access_token": "tok", "page_id": "ig_1"},
        )

    assert rec.calls == []


async def test_instagram_refuses_when_the_publish_quota_is_spent(transport):
    """The limit is read from the account, never hardcoded at 25 or 50."""
    spent = {"data": [{"config": {"quota_total": 25, "quota_duration": 86400}, "quota_usage": 25}]}
    rec = transport(_ig_responder(quota=spent))

    with pytest.raises(MediaUploadError, match="24 hours"):
        await PlatformPublisher()._publish_instagram(
            {"body": "hi", "media_urls": ["https://cdn.example/a.png"]},
            {"access_token": "tok", "page_id": "ig_1"},
        )

    assert rec.to("content_publishing_limit")
    assert rec.to("/media_publish") == []
    assert [c for c in rec.calls if "/media?" in str(c.url)] == []


async def test_instagram_quota_message_names_the_window_and_the_numbers(transport):
    spent = {"data": [{"config": {"quota_total": 50, "quota_duration": 86400}, "quota_usage": 60}]}
    transport(_ig_responder(quota=spent))

    with pytest.raises(MediaUploadError) as exc:
        await PlatformPublisher()._publish_instagram(
            {"body": "hi", "media_urls": ["https://cdn.example/a.png"]},
            {"access_token": "tok", "page_id": "ig_1"},
        )

    assert "60 of 50" in str(exc.value)
    assert "24 hours" in str(exc.value)


async def test_instagram_unreadable_quota_does_not_block_the_post(transport):
    """A Graph field rename must not become an outage."""
    rec = transport(_ig_responder(quota={"data": []}))

    out = await PlatformPublisher()._publish_instagram(
        {"body": "hi", "media_urls": ["https://cdn.example/a.png"]},
        {"access_token": "tok", "page_id": "ig_1"},
    )

    assert out["post_id"] == "ig_media_1"
    assert len(rec.to("/media_publish")) == 1


async def test_instagram_without_an_account_id_refuses(transport):
    rec = transport(_ig_responder())

    with pytest.raises(MediaUploadError, match="Instagram Business Account"):
        await PlatformPublisher()._publish_instagram(
            {"body": "hi", "media_urls": ["https://cdn.example/a.png"]},
            {"access_token": "tok"},
        )

    assert rec.calls == []


async def test_instagram_missing_permalink_is_empty_not_invented(transport):
    def responder(request: httpx.Request) -> httpx.Response:
        if "permalink" in str(request.url):
            return _json({"error": {"message": "nope"}}, status=400)
        return _ig_responder()(request)

    transport(responder)

    out = await PlatformPublisher()._publish_instagram(
        {"body": "hi", "media_urls": ["https://cdn.example/a.png"]},
        {"access_token": "tok", "page_id": "ig_1"},
    )

    assert out["post_id"] == "ig_media_1"
    assert out["url"] == ""


# ---------------------------------------------------------------------------
# Both call sites carry media_urls — they must not diverge
# ---------------------------------------------------------------------------
@pytest.fixture
def captured(monkeypatch) -> list[dict[str, Any]]:
    """What reached the publisher, per call."""
    calls: list[dict[str, Any]] = []

    async def _record(platform: str, content: dict, credentials: dict) -> dict:
        calls.append({"platform": platform, "content": content})
        return {"success": True, "post_id": "p1", "url": "https://example.com/p1"}

    monkeypatch.setattr(publisher, "publish", _record)
    return calls


async def test_scheduler_carries_media_urls_to_the_publisher(session_factory, captured):
    org = await create_org(session_factory, "Org")
    await create_subscription(session_factory, org, plan_tier="growth", posts_limit=1000)
    client_id = await create_client_row(session_factory, org, "Brand")
    await create_platform_account(session_factory, org, client_id, platform="twitter")
    content_id = await create_content_row(
        session_factory,
        org,
        client_id,
        platform="twitter",
        status="scheduled",
        media_urls=["https://cdn.example/a.png"],
    )

    async with session_factory() as db:
        piece = (
            await db.execute(select(ContentPiece).where(ContentPiece.id == content_id))
        ).scalar_one()
        await SchedulerEngine()._publish_piece(db, piece)

    assert captured[0]["content"]["media_urls"] == ["https://cdn.example/a.png"]


async def test_publish_now_carries_media_urls_to_the_publisher(
    client, session_factory, captured
):
    org = await create_org(session_factory, "Org")
    headers = await auth_for(session_factory, org, role="owner")
    await create_subscription(session_factory, org, plan_tier="growth", posts_limit=1000)
    client_id = await create_client_row(session_factory, org, "Brand")
    await create_platform_account(session_factory, org, client_id, platform="twitter")
    content_id = await create_content_row(
        session_factory,
        org,
        client_id,
        platform="twitter",
        status="approved",
        media_urls=["https://cdn.example/a.png"],
    )

    resp = await client.post(f"/api/v1/publishing/{content_id}/publish", headers=headers)

    assert resp.status_code == 200, resp.text
    assert captured[0]["content"]["media_urls"] == ["https://cdn.example/a.png"]


async def test_both_call_sites_send_the_same_keys(session_factory, captured, client):
    """A key in one dict and not the other is the bug this pair exists to catch."""
    org = await create_org(session_factory, "Org")
    headers = await auth_for(session_factory, org, role="owner")
    await create_subscription(session_factory, org, plan_tier="growth", posts_limit=1000)
    client_id = await create_client_row(session_factory, org, "Brand")
    await create_platform_account(session_factory, org, client_id, platform="twitter")

    scheduled = await create_content_row(
        session_factory, org, client_id, platform="twitter", status="scheduled",
        media_urls=["https://cdn.example/a.png"],
    )
    approved = await create_content_row(
        session_factory, org, client_id, platform="twitter", status="approved",
        media_urls=["https://cdn.example/a.png"],
    )

    async with session_factory() as db:
        piece = (
            await db.execute(select(ContentPiece).where(ContentPiece.id == scheduled))
        ).scalar_one()
        await SchedulerEngine()._publish_piece(db, piece)
    await client.post(f"/api/v1/publishing/{approved}/publish", headers=headers)

    assert len(captured) == 2
    assert set(captured[0]["content"]) == set(captured[1]["content"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def test_local_storage_key_handles_relative_and_absolute_urls():
    assert _local_storage_key("/api/v1/media/org/client/content/a.png") == (
        "org/client/content/a.png"
    )
    assert _local_storage_key("https://api.example/api/v1/media/o/c/x/a.png") == (
        "o/c/x/a.png"
    )
    assert _local_storage_key("https://cdn.example/o/c/x/a.png") is None


def test_media_list_dedupes_and_caps_per_platform():
    urls = [f"https://cdn.example/{i}.png" for i in range(12)]
    assert len(_media_list({"media_urls": urls}, "twitter")) == 4
    assert len(_media_list({"media_urls": urls}, "linkedin")) == 9
    assert len(_media_list({"media_urls": urls}, "facebook")) == 10
    dupes = ["https://cdn.example/a.png"] * 3
    assert _media_list({"media_urls": dupes}, "twitter") == ["https://cdn.example/a.png"]


def test_a_video_is_the_only_attachment_on_x():
    out = _media_list(
        {"media_urls": ["https://cdn.example/a.png", "https://cdn.example/v.mp4"]},
        "twitter",
    )
    assert publishing._limit_for_twitter(out) == ["https://cdn.example/v.mp4"]
