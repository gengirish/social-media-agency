"""Create › Content — blog / comparison / niche scan / video script / AI-SEO,
plus Amplify's saved-asset source.

The LLM and Exa are stubbed; SQL, tenancy filters and quota arithmetic run for
real against the SQLite test database. Every tenancy test asserts on another
org's (or another client's) id, so it fails if that ``org_id``/``client_id``
filter is removed.
"""

import json
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from agency.models.tables import (
    BrandProfile,
    ContentPiece,
    CreativeAsset,
    RepurposePack,
    Subscription,
)
from agency.services.create_content import (
    MalformedGenerationError,
    asset_source_text,
    clean_competitor_names,
    find_similar_scan,
    used_keywords,
    validate_blog,
    validate_niche_scan,
)
from agency.services.repurpose import plan_atoms
from tests.conftest import (
    _persist,
    auth_header_for,
    create_client_row,
    create_org,
    create_subscription,
    create_user_row,
)

API = "/api/v1/create/content"

BODY = (
    "Cold brew at home is simpler than it looks. Grind coarse, steep for sixteen hours, "
    "and filter twice. This guide walks through ratios, containers and storage so the "
    "first batch tastes like the shop version, and explains why coarse grounds matter."
)


def blog_reply(keyword: str = "how to make cold brew at home") -> dict[str, Any]:
    return {
        "keyword": keyword,
        "searchIntent": "informational",
        "title": "How to Make Cold Brew at Home: A Simple Guide",
        "metaDescription": "Learn how to make cold brew at home with a simple ratio.",
        "outline": ["Why cold brew", "The ratio", "Storage"],
        "body": BODY,
    }


COMPARISON = {
    "title": "Sunrise vs Bluebird",
    "metaDescription": "A fair comparison.",
    "introParagraph": "For people choosing a roaster.",
    "comparisonPoints": [
        {"dimension": "Roast style", "us": "Light", "them": "Medium"},
        {"dimension": "Delivery", "us": "Weekly", "them": "Monthly"},
        {"dimension": "Origin", "us": "Single", "them": "Blends"},
    ],
    "honestWhereTheyWin": "Bluebird has more cafe locations.",
    "cta": "Try a bag.",
}

SCAN = {
    "angles": [
        {
            "angle": "Founder story",
            "usedBy": ["Bluebird", "Nobody Inc"],
            "saturation": "High",
            "note": "Everyone does it.",
        },
        {"angle": "Subscription hook", "usedBy": ["redbird"], "saturation": "low", "note": "Rare."},
        {"angle": "Bad angle", "usedBy": [], "saturation": "extreme", "note": "dropped"},
    ],
    "gapRecommendation": "Brewing education for office managers.",
    "sourcesNote": "Limited info on Redbird.",
}

VIDEO = {
    "hook": "Your cold brew is bitter for one reason.",
    "scriptBeats": ["0-2s hook", "2-20s show grind", "20-30s CTA"],
    "onScreenText": ["Bitter cold brew?"],
    "audioStyleNote": "Voiceover only.",
    "caption": "Fix it tonight.",
    "hashtags": ["#coldbrew", "coffee"],
}

AI_SEO = {
    "citableSummary": "Cold brew needs coarse grounds and sixteen hours.",
    "faq": [
        {"question": "How long?", "answer": "Sixteen hours."},
        {"question": "Grind?", "answer": "Coarse."},
    ],
    "entityClarityNotes": "Brand named once; fine.",
    "llmsTxtEntry": "- [Cold brew](/blog/your-slug-here): How to make it.",
}


class StubLLM:
    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[Any] = []

    async def ainvoke(self, messages: Any) -> SimpleNamespace:
        self.calls.append(messages)
        return SimpleNamespace(content=self.replies.pop(0) if self.replies else "")


class FailingLLM:
    calls: list[Any] = []

    async def ainvoke(self, _messages: Any) -> SimpleNamespace:
        raise RuntimeError("provider 503")


@pytest.fixture(autouse=True)
def no_exa(monkeypatch):
    """Web search unconfigured unless a test says otherwise."""
    monkeypatch.setattr("agency.services.exa_client.get_api_key", lambda: "")


@pytest.fixture
def stub_llm(monkeypatch):
    def _install(*replies: Any, fail: bool = False):
        stub: Any = (
            FailingLLM()
            if fail
            else StubLLM([r if isinstance(r, str) else json.dumps(r) for r in replies])
        )
        monkeypatch.setattr(
            "agency.agents.create_content.get_worker_llm", lambda temperature=0.7: stub
        )
        return stub

    return _install


async def _brand_profile(session_factory, org_id, client_id):
    await _persist(
        session_factory,
        BrandProfile(
            client_id=client_id,
            org_id=org_id,
            voice_description="warm and neighbourly",
            tone_attributes={},
            vocabulary_include=[],
            vocabulary_exclude=[],
            example_posts=[],
            style_rules=[],
        ),
    )


@pytest.fixture
async def org(session_factory):
    org_id = await create_org(session_factory, "Content Org")
    await create_subscription(session_factory, org_id, plan_tier="starter")
    user_id = await create_user_row(session_factory, org_id)
    client_id = await create_client_row(session_factory, org_id, "Sunrise Coffee")
    await _brand_profile(session_factory, org_id, client_id)
    return SimpleNamespace(
        org_id=org_id,
        client_id=client_id,
        headers=auth_header_for(org_id, user_id=user_id),
    )


@pytest.fixture
async def other(session_factory):
    """A second org with a profiled client — the cross-tenant target."""
    org_id = await create_org(session_factory, "Other Org")
    await create_subscription(session_factory, org_id, plan_tier="starter")
    client_id = await create_client_row(session_factory, org_id, "Other Brand")
    await _brand_profile(session_factory, org_id, client_id)
    return SimpleNamespace(org_id=org_id, client_id=client_id)


async def _used(session_factory, org_id) -> int:
    async with session_factory() as s:
        sub = (
            await s.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one()
        return int(sub.generations_used or 0)


async def _assets(session_factory, org_id) -> list[CreativeAsset]:
    async with session_factory() as s:
        rows = await s.execute(select(CreativeAsset).where(CreativeAsset.org_id == org_id))
        return list(rows.scalars().all())


async def _save(session_factory, org_id, client_id, kind, payload, title="t") -> UUID:
    asset = CreativeAsset(
        id=uuid4(), org_id=org_id, client_id=client_id, kind=kind, title=title, payload=payload
    )
    await _persist(session_factory, asset)
    return asset.id


# ---------------------------------------------------------------------------
# blog
# ---------------------------------------------------------------------------
async def test_blog_saves_asset_and_charges_one(client, org, session_factory, stub_llm):
    stub = stub_llm(blog_reply())
    resp = await client.post(
        f"{API}/blog", json={"client_id": str(org.client_id)}, headers=org.headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["kind"] == "blog_post"
    assert data["payload"]["keyword"] == "how to make cold brew at home"
    assert data["title"] == blog_reply()["title"]
    assert await _used(session_factory, org.org_id) == 1
    assert "warm and neighbourly" in stub.calls[0][1].content


async def test_blog_passes_used_keywords_and_rejects_a_repeat(
    client, org, session_factory, stub_llm
):
    await _save(
        session_factory, org.org_id, org.client_id, "blog_post", {"keyword": "best grinder"}
    )
    stub = stub_llm(blog_reply("Best  Grinder"))
    resp = await client.post(
        f"{API}/blog", json={"client_id": str(org.client_id)}, headers=org.headers
    )
    assert resp.status_code == 502
    assert "no quota was used" in resp.json()["detail"]
    assert "best grinder" in stub.calls[0][1].content
    assert await _used(session_factory, org.org_id) == 0
    assert len(await _assets(session_factory, org.org_id)) == 1


async def test_blog_malformed_or_failed_charges_nothing(client, org, session_factory, stub_llm):
    stub_llm({"keyword": "x", "title": "missing the rest"})
    bad = await client.post(
        f"{API}/blog", json={"client_id": str(org.client_id)}, headers=org.headers
    )
    assert bad.status_code == 502
    stub_llm(fail=True)
    failed = await client.post(
        f"{API}/blog", json={"client_id": str(org.client_id)}, headers=org.headers
    )
    assert failed.status_code == 502
    assert await _used(session_factory, org.org_id) == 0
    assert await _assets(session_factory, org.org_id) == []


async def test_quota_exhausted_never_reaches_model(client, session_factory, stub_llm):
    org_id = await create_org(session_factory)
    await create_subscription(session_factory, org_id, generations_used=10, generations_limit=10)
    client_id = await create_client_row(session_factory, org_id)
    await _brand_profile(session_factory, org_id, client_id)
    stub = stub_llm(blog_reply())
    resp = await client.post(
        f"{API}/blog", json={"client_id": str(client_id)}, headers=auth_header_for(org_id)
    )
    assert resp.status_code == 402
    assert resp.json()["detail"]["code"] == "generation_quota_exceeded"
    assert stub.calls == []


async def test_brand_profile_required(client, session_factory, stub_llm):
    org_id = await create_org(session_factory)
    await create_subscription(session_factory, org_id, plan_tier="starter")
    client_id = await create_client_row(session_factory, org_id)
    stub = stub_llm(blog_reply())
    resp = await client.post(
        f"{API}/video-script", json={"client_id": str(client_id)}, headers=auth_header_for(org_id)
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "brand_profile_required"
    assert stub.calls == []


# ---------------------------------------------------------------------------
# comparison + niche scan
# ---------------------------------------------------------------------------
async def test_comparison_without_web_data_says_so(client, org, session_factory, stub_llm):
    stub = stub_llm(COMPARISON)
    resp = await client.post(
        f"{API}/comparison",
        json={"client_id": str(org.client_id), "competitor_name": "  Bluebird "},
        headers=org.headers,
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()["payload"]
    assert payload["competitorName"] == "Bluebird"
    assert payload["webResearch"]["status"] == "unavailable"
    assert payload["sourcesNote"].startswith("No live web data")
    assert "NO web access" in stub.calls[0][1].content
    assert await _used(session_factory, org.org_id) == 1


async def test_comparison_requires_honest_paragraph(client, org, session_factory, stub_llm):
    stub_llm({**COMPARISON, "honestWhereTheyWin": ""})
    resp = await client.post(
        f"{API}/comparison",
        json={"client_id": str(org.client_id), "competitor_name": "Bluebird"},
        headers=org.headers,
    )
    assert resp.status_code == 502
    assert await _used(session_factory, org.org_id) == 0


async def test_niche_scan_validates_names(client, org, stub_llm):
    stub = stub_llm(SCAN)
    one = await client.post(
        f"{API}/niche-scan",
        json={"client_id": str(org.client_id), "competitor_names": ["A", " a "]},
        headers=org.headers,
    )
    assert one.status_code == 422
    six = await client.post(
        f"{API}/niche-scan",
        json={"client_id": str(org.client_id), "competitor_names": list("ABCDEF")},
        headers=org.headers,
    )
    assert six.status_code == 422
    assert stub.calls == []


async def test_niche_scan_with_live_sources(client, org, session_factory, stub_llm, monkeypatch):
    monkeypatch.setattr("agency.services.exa_client.get_api_key", lambda: "k")

    async def fake_gather(_key, names, _industry):
        return (
            [
                {
                    "id": "S1",
                    "competitor": "Bluebird",
                    "title": "Bluebird launches subscriptions",
                    "url": "https://bluebird.example/news",
                    "domain": "bluebird.example",
                    "published_date": None,
                    "excerpt": "Bluebird now ships monthly.",
                }
            ],
            {},
            [],
            None,
        )

    monkeypatch.setattr("agency.agents.competitive_intel.gather_sources", fake_gather)
    stub = stub_llm(SCAN)
    resp = await client.post(
        f"{API}/niche-scan",
        json={"client_id": str(org.client_id), "competitor_names": ["Bluebird", "Redbird"]},
        headers=org.headers,
    )
    assert resp.status_code == 200, resp.text
    p = resp.json()["payload"]
    assert p["competitorNames"] == ["Bluebird", "Redbird"]
    # Unknown names dropped from usedBy, casing normalised, bad saturation dropped.
    assert [a["usedBy"] for a in p["angles"]] == [["Bluebird"], ["Redbird"]]
    assert [a["saturation"] for a in p["angles"]] == ["high", "low"]
    assert p["webResearch"]["status"] == "ok"
    assert p["webResearch"]["sources"][0]["url"] == "https://bluebird.example/news"
    assert "excerpt" not in p["webResearch"]["sources"][0]
    assert p["sourcesNote"].startswith("Based on 1 document retrieved by live web search.")
    assert "No documents found for: Redbird" in p["sourcesNote"]
    assert "Bluebird now ships monthly." in stub.calls[0][1].content


async def test_generate_blog_from_gap(client, org, session_factory, stub_llm):
    scan_id = await _save(session_factory, org.org_id, org.client_id, "niche_scan", SCAN)
    stub = stub_llm(blog_reply())
    resp = await client.post(f"{API}/niche-scan/{scan_id}/blog", headers=org.headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["kind"] == "blog_post"
    assert data["source_asset_id"] == str(scan_id)
    assert data["payload"]["fromGap"] == SCAN["gapRecommendation"]
    assert SCAN["gapRecommendation"] in stub.calls[0][1].content
    assert await _used(session_factory, org.org_id) == 1


async def test_video_script_is_a_script(client, org, stub_llm):
    stub = stub_llm(VIDEO)
    resp = await client.post(
        f"{API}/video-script", json={"client_id": str(org.client_id)}, headers=org.headers
    )
    assert resp.status_code == 200, resp.text
    p = resp.json()["payload"]
    assert p["hashtags"] == ["coldbrew", "coffee"]
    assert "not making a video" in stub.calls[0][1].content


# ---------------------------------------------------------------------------
# AI-SEO (PATCH semantics on the blog asset)
# ---------------------------------------------------------------------------
async def test_ai_seo_merges_into_blog_payload(client, org, session_factory, stub_llm):
    blog_id = await _save(session_factory, org.org_id, org.client_id, "blog_post", blog_reply())
    stub_llm(AI_SEO)
    resp = await client.post(f"{API}/blog/{blog_id}/ai-seo", headers=org.headers)
    assert resp.status_code == 200, resp.text
    p = resp.json()["payload"]
    assert p["body"] == BODY  # draft untouched
    assert p["aiSeoPack"]["faq"][0]["question"] == "How long?"
    assert await _used(session_factory, org.org_id) == 1

    stub = stub_llm(AI_SEO)
    again = await client.post(f"{API}/blog/{blog_id}/ai-seo", headers=org.headers)
    assert again.status_code == 409
    assert stub.calls == []
    assert await _used(session_factory, org.org_id) == 1


async def test_ai_seo_malformed_leaves_blog_alone(client, org, session_factory, stub_llm):
    blog_id = await _save(session_factory, org.org_id, org.client_id, "blog_post", blog_reply())
    stub_llm({"citableSummary": "x", "faq": []})
    resp = await client.post(f"{API}/blog/{blog_id}/ai-seo", headers=org.headers)
    assert resp.status_code == 502
    async with session_factory() as s:
        assert "aiSeoPack" not in (await s.get(CreativeAsset, blog_id)).payload
    assert await _used(session_factory, org.org_id) == 0


async def test_ai_seo_only_on_blog_posts(client, org, session_factory, stub_llm):
    video_id = await _save(session_factory, org.org_id, org.client_id, "video_script", VIDEO)
    stub_llm(AI_SEO)
    resp = await client.post(f"{API}/blog/{video_id}/ai-seo", headers=org.headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# tenancy — every endpoint, cross-org ids
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "path,extra",
    [
        ("blog", {}),
        ("comparison", {"competitor_name": "Bluebird"}),
        ("niche-scan", {"competitor_names": ["Bluebird", "Redbird"]}),
        ("video-script", {}),
    ],
)
async def test_generate_rejects_other_orgs_client(
    client, org, other, session_factory, stub_llm, path, extra
):
    stub = stub_llm(blog_reply(), COMPARISON, SCAN, VIDEO)
    resp = await client.post(
        f"{API}/{path}", json={"client_id": str(other.client_id), **extra}, headers=org.headers
    )
    assert resp.status_code == 404
    assert stub.calls == []
    assert await _assets(session_factory, other.org_id) == []
    assert await _used(session_factory, org.org_id) == 0


async def test_gap_blog_rejects_other_orgs_scan(client, org, other, session_factory, stub_llm):
    scan_id = await _save(session_factory, other.org_id, other.client_id, "niche_scan", SCAN)
    stub = stub_llm(blog_reply())
    resp = await client.post(f"{API}/niche-scan/{scan_id}/blog", headers=org.headers)
    assert resp.status_code == 404
    assert stub.calls == []


async def test_ai_seo_rejects_other_orgs_blog(client, org, other, session_factory, stub_llm):
    blog_id = await _save(session_factory, other.org_id, other.client_id, "blog_post", blog_reply())
    stub = stub_llm(AI_SEO)
    resp = await client.post(f"{API}/blog/{blog_id}/ai-seo", headers=org.headers)
    assert resp.status_code == 404
    assert stub.calls == []
    async with session_factory() as s:
        assert "aiSeoPack" not in (await s.get(CreativeAsset, blog_id)).payload


async def test_keyword_memory_is_scoped_to_the_client(
    client, org, other, session_factory, stub_llm
):
    # Same keyword in another org and in another client of this org: neither blocks.
    await _save(session_factory, other.org_id, other.client_id, "blog_post", blog_reply())
    sibling = await create_client_row(session_factory, org.org_id, "Sibling")
    await _save(session_factory, org.org_id, sibling, "blog_post", blog_reply())
    stub = stub_llm(blog_reply())
    resp = await client.post(
        f"{API}/blog", json={"client_id": str(org.client_id)}, headers=org.headers
    )
    assert resp.status_code == 200, resp.text
    assert "Keywords already targeted" not in stub.calls[0][1].content


# ---------------------------------------------------------------------------
# Amplify — a saved asset as the source
# ---------------------------------------------------------------------------
@pytest.fixture
def amplify_llm(monkeypatch):
    def _install(platforms: list[str], n: int):
        reply = json.dumps(
            {
                "atoms": [
                    {
                        "platform": r["platform"],
                        "angle": r["angle"],
                        "title": r["angle"],
                        "body": f"Distinct body number {i} about {r['angle']} and grinders.",
                        "hashtags": [],
                    }
                    for i, r in enumerate(plan_atoms(platforms, n))
                ]
            }
        )
        stub = StubLLM([reply])
        monkeypatch.setattr("agency.agents.amplify.get_worker_llm", lambda temperature=0.8: stub)
        return stub

    return _install


async def test_amplify_from_asset_records_source(client, org, session_factory, amplify_llm):
    blog_id = await _save(
        session_factory, org.org_id, org.client_id, "blog_post", blog_reply(), title="Cold brew"
    )
    stub = amplify_llm(["twitter"], 2)
    resp = await client.post(
        "/api/v1/amplify/preview",
        json={
            "client_id": str(org.client_id),
            "source_asset_id": str(blog_id),
            "platforms": ["twitter"],
            "max_atoms": 2,
        },
        headers=org.headers,
    )
    assert resp.status_code == 200, resp.text
    pack = resp.json()
    assert BODY in stub.calls[0][1].content
    async with session_factory() as s:
        row = await s.get(RepurposePack, UUID(pack["pack_id"]))
        assert row.source_asset_id == blog_id
        assert row.source_content_id is None and row.source_text is None

    commit = await client.post(
        f"/api/v1/amplify/{pack['pack_id']}/commit",
        json={"atoms": pack["atoms"]},
        headers=org.headers,
    )
    assert commit.status_code == 200, commit.text
    async with session_factory() as s:
        pieces = (
            (await s.execute(select(ContentPiece).where(ContentPiece.org_id == org.org_id)))
            .scalars()
            .all()
        )
    assert pieces and all(p.metadata_["source_asset_id"] == str(blog_id) for p in pieces)
    assert all(p.status == "draft" for p in pieces)

    history = await client.get("/api/v1/amplify/packs", headers=org.headers)
    item = history.json()["items"][0]
    assert item["source_asset_id"] == str(blog_id)
    assert item["source_title"] == "Cold brew"


async def test_amplify_asset_source_tenancy(client, org, other, session_factory, amplify_llm):
    stub = amplify_llm(["twitter"], 1)
    foreign = await _save(session_factory, other.org_id, other.client_id, "blog_post", blog_reply())
    sibling = await create_client_row(session_factory, org.org_id, "Sibling")
    wrong_client = await _save(session_factory, org.org_id, sibling, "blog_post", blog_reply())
    for asset_id in (foreign, wrong_client):
        resp = await client.post(
            "/api/v1/amplify/preview",
            json={
                "client_id": str(org.client_id),
                "source_asset_id": str(asset_id),
                "platforms": ["twitter"],
            },
            headers=org.headers,
        )
        assert resp.status_code == 404, resp.text
    assert stub.calls == []
    assert await _used(session_factory, org.org_id) == 0


async def test_amplify_asset_source_rejects_unrepurposable_kind_and_two_sources(
    client, org, session_factory, amplify_llm
):
    amplify_llm(["twitter"], 1)
    email_id = await _save(session_factory, org.org_id, org.client_id, "email_campaign", {"x": 1})
    resp = await client.post(
        "/api/v1/amplify/preview",
        json={
            "client_id": str(org.client_id),
            "source_asset_id": str(email_id),
            "platforms": ["twitter"],
        },
        headers=org.headers,
    )
    assert resp.status_code == 422
    both = await client.post(
        "/api/v1/amplify/preview",
        json={
            "client_id": str(org.client_id),
            "source_asset_id": str(email_id),
            "source_text": "also",
            "platforms": ["twitter"],
        },
        headers=org.headers,
    )
    assert both.status_code == 422


# ---------------------------------------------------------------------------
# pure logic (ports of Cadence's logic.test.js)
# ---------------------------------------------------------------------------
EXISTING = [{"id": 1, "competitorNames": ["Buffer", "Later", "Publer"]}]


def test_find_similar_scan_none_without_history():
    assert find_similar_scan(["Buffer", "Later"], []) is None


def test_find_similar_scan_exact_ignores_case_and_space():
    match = find_similar_scan(["  buffer", "LATER ", "publer"], EXISTING)
    assert match["scan"] is EXISTING[0] and match["isExact"] is True


def test_find_similar_scan_sixty_percent_overlap():
    match = find_similar_scan(["Buffer", "Later", "SomeNewTool"], EXISTING)
    assert match["isExact"] is False and match["shared"] == ["buffer", "later"]


def test_find_similar_scan_different_set():
    assert find_similar_scan(["Zapier", "Make", "n8n"], EXISTING) is None


def test_asset_source_text_per_kind():
    assert asset_source_text("blog_post", "T", {"title": "Why", "body": "Body."}) == "Why\n\nBody."
    comp = asset_source_text("comparison_page", "", COMPARISON)
    assert "Roast style: us: Light | them: Medium" in comp
    assert "Where they win: Bluebird" in comp
    assert asset_source_text("niche_scan", "", SCAN).startswith("Gap none of them cover")
    assert asset_source_text("video_script", "", VIDEO).startswith(VIDEO["hook"])
    assert asset_source_text("launch_kit", "", {"announcementPost": "Live!", "summary": "s"}) == (
        "Live!"
    )
    # Anything without real text is empty, never a padded placeholder.
    assert asset_source_text("blog_post", "", {}) == ""
    assert asset_source_text("launch_kit", "", {}) == ""


def test_validators_and_helpers():
    assert clean_competitor_names([" Buffer ", "buffer", "", "Later"]) == ["Buffer", "Later"]
    assert used_keywords([{"keyword": "a"}, {"keyword": "a"}, {}, {"keyword": " b "}]) == ["a", "b"]
    with pytest.raises(MalformedGenerationError):
        validate_blog({**blog_reply(), "body": "too short"})
    with pytest.raises(MalformedGenerationError):
        validate_blog(["not", "an", "object"])
    with pytest.raises(MalformedGenerationError):
        validate_niche_scan({**SCAN, "angles": SCAN["angles"][:1]}, ["Bluebird"])
