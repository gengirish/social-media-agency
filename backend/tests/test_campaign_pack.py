"""The campaign pack — what it states, what it refuses to state, and who may read it.

The pack goes in front of an agency's client, so the tests are mostly about honesty:
no QA score, no keyword volume, no approver name that was never recorded, and every
model-written string escaped before it reaches HTML.
"""

import json
from uuid import UUID, uuid4

import pytest

from agency.models.tables import AgentRun
from tests.conftest import (
    _persist,
    auth_for,
    create_campaign_row,
    create_client_row,
    create_content_row,
    create_org,
    create_user_row,
    create_white_label,
)

API = "/api/v1"

STRATEGY = {
    "strategy": {
        "campaign_theme": "Cold brew, warm mornings",
        "target_audience": {
            "primary": "Commuters 25-40",
            "secondary": "Remote workers",
            "pain_points": ["No time for breakfast"],
            "motivations": ["A treat that feels earned"],
        },
        "channel_strategy": {
            "linkedin": {"role": "awareness", "posting_frequency": "3 times per week"}
        },
        "content_pillars": ["Ritual", "Craft"],
        "campaign_timeline": [{"week": 1, "theme": "Launch", "focus": "Reach"}],
        "kpis": [{"metric": "Engagement rate", "target": "4%", "measurement": "Native"}],
        "competitive_angle": "Small-batch, local",
    },
    "current_agent": "strategy",
}
SEO = {
    "seo_keywords": [
        {
            "keyword": "cold brew near me",
            "intent": "transactional",
            "search_volume": "high",
            "difficulty": "low",
            "metrics_source": "llm_estimate",
        }
    ]
}
QA = {
    "qa_feedback": {
        "overall_score": 8.5,
        "brand_voice_score": 9,
        "pass": True,
        "summary": "On-voice and compliant.",
        "issues": [
            {"severity": "suggestion", "issue": "Hashtag set repeats", "fix_suggestion": "Vary"}
        ],
        "strengths": ["Clear hook"],
        "coverage": {
            "content_reviewed": 2,
            "content_total": 3,
            "ads_reviewed": 0,
            "ads_total": 0,
            "complete": False,
        },
    }
}


async def _run(session_factory, org_id: UUID, campaign_id: UUID, node: str, output: dict):
    await _persist(
        session_factory,
        AgentRun(
            id=uuid4(),
            campaign_id=campaign_id,
            org_id=org_id,
            agent_name=node,
            status="completed",
            output=json.dumps(output),
        ),
    )


@pytest.fixture
async def campaign(session_factory):
    org_id = await create_org(session_factory, "Pack Agency")
    client_id = await create_client_row(session_factory, org_id, "Sunrise Coffee")
    campaign_id = await create_campaign_row(
        session_factory, org_id, client_id, "Cold Brew Launch", channels=["linkedin", "twitter"]
    )
    approver = await create_user_row(session_factory, org_id, full_name="Priya Shah")
    for node, output in (("strategise", STRATEGY), ("seo_research", SEO), ("qa_check", QA)):
        await _run(session_factory, org_id, campaign_id, node, output)
    return org_id, client_id, campaign_id, approver


async def _pack(client, session_factory, org_id, campaign_id) -> dict:
    headers = await auth_for(session_factory, org_id, role="viewer")
    resp = await client.get(f"{API}/campaigns/{campaign_id}/pack", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_pack_reads_strategy_seo_and_qa(client, session_factory, campaign):
    org_id, _, campaign_id, _ = campaign
    pack = await _pack(client, session_factory, org_id, campaign_id)

    assert pack["agency"]["name"] == "Pack Agency"
    assert pack["client"]["name"] == "Sunrise Coffee"
    assert pack["campaign"]["name"] == "Cold Brew Launch"
    assert pack["strategy"]["theme"] == "Cold brew, warm mornings"
    assert pack["strategy"]["proposed_kpis"][0]["target"] == "4%"
    assert pack["seo"]["keywords"] == [{"keyword": "cold brew near me", "intent": "transactional"}]
    assert pack["qa"]["passed"] is True
    assert pack["qa"]["coverage"]["complete"] is False


async def test_pack_states_no_invented_numbers(client, session_factory, campaign):
    """No QA score and no keyword volume/difficulty — neither is a measurement."""
    org_id, _, campaign_id, _ = campaign
    pack = await _pack(client, session_factory, org_id, campaign_id)
    text = json.dumps(pack)
    for banned in ("overall_score", "brand_voice_score", "8.5", "search_volume", "difficulty"):
        assert banned not in text, banned

    headers = await auth_for(session_factory, org_id)
    html = (await client.get(f"{API}/campaigns/{campaign_id}/pack.html", headers=headers)).text
    assert "8.5" not in html
    assert "not results" in html  # KPIs are labelled as proposals


async def test_unparsed_qa_says_not_checked(client, session_factory, campaign):
    org_id, _, campaign_id, _ = campaign
    await _run(
        session_factory,
        org_id,
        campaign_id,
        "qa_check",
        {"qa_feedback": {"pass": None, "error": "QA response could not be parsed", "issues": []}},
    )
    pack = await _pack(client, session_factory, org_id, campaign_id)
    assert pack["qa"]["checked"] is False
    assert pack["qa"]["passed"] is None


async def test_approval_record(client, session_factory, campaign):
    org_id, client_id, campaign_id, approver = campaign
    by_seat = await create_content_row(
        session_factory,
        org_id,
        client_id,
        campaign_id,
        status="approved",
        metadata={
            "moderation": {"status": "passed", "issues": []},
            "approval": {
                "at": "2026-10-30T10:00:00+00:00",
                "via": "dashboard",
                "by": str(approver),
            },
        },
    )
    by_client = await create_content_row(
        session_factory,
        org_id,
        client_id,
        campaign_id,
        status="scheduled",
        metadata={
            "moderation": {"status": "passed", "issues": []},
            "approval": {"at": "2026-10-30T11:00:00+00:00", "via": "client_link", "name": "Dana"},
            "client_review": {"decision": "approved", "name": "Dana"},
        },
    )
    legacy = await create_content_row(
        session_factory,
        org_id,
        client_id,
        campaign_id,
        status="approved",
        metadata={
            "moderation": {"status": "overridden", "issues": [{}], "override_by": str(approver)}
        },
    )
    pending = await create_content_row(session_factory, org_id, client_id, campaign_id)
    await create_content_row(session_factory, org_id, client_id, campaign_id, status="failed")

    pack = await _pack(client, session_factory, org_id, campaign_id)
    rec = {p["id"]: p["record"] for p in pack["posts"]}

    assert rec[str(by_seat)]["approved_by"] == "Priya Shah"
    assert rec[str(by_client)]["approved_by"] == "Client (Dana)"
    # Approved before approvals were logged: no name is invented.
    assert rec[str(legacy)]["approver_recorded"] is False
    assert rec[str(legacy)]["approved_by"] is None
    assert rec[str(legacy)]["moderation"]["override_by"] == "Priya Shah"
    assert rec[str(pending)]["approved"] is False
    # A failed generation is not something to show a client.
    assert len(pack["posts"]) == 4
    assert pack["summary"]["approved"] == 3
    assert pack["summary"]["pending"] == 1
    assert pack["summary"]["client_approved"] == 1
    assert "1 item in this pack is still pending" in pack["disclosure"]


async def test_html_escapes_model_output(client, session_factory, campaign):
    org_id, client_id, campaign_id, _ = campaign
    await create_content_row(
        session_factory,
        org_id,
        client_id,
        campaign_id,
        body='<script>alert("x")</script>',
        metadata={"post_url": "javascript:alert(1)"},
    )
    headers = await auth_for(session_factory, org_id)
    resp = await client.get(f"{API}/campaigns/{campaign_id}/pack.html", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "attachment" in resp.headers["content-disposition"]
    assert "cold-brew-launch-campaign-pack.html" in resp.headers["content-disposition"]
    assert '<script>alert("x")</script>' not in resp.text
    assert "&lt;script&gt;" in resp.text
    assert "javascript:alert(1)" not in resp.text


async def test_white_label_brands_the_pack(client, session_factory, campaign):
    org_id, _, campaign_id, _ = campaign
    await create_white_label(session_factory, org_id, company_name="Northwind Social")
    pack = await _pack(client, session_factory, org_id, campaign_id)
    assert pack["agency"]["name"] == "Northwind Social"
    assert "Prepared by Northwind Social" in pack["disclosure"]


async def test_pack_is_org_scoped(client, session_factory, campaign):
    _, _, campaign_id, _ = campaign
    other = await create_org(session_factory, "Other Agency")
    headers = await auth_for(session_factory, other)
    for suffix in ("pack", "pack.html"):
        resp = await client.get(f"{API}/campaigns/{campaign_id}/{suffix}", headers=headers)
        assert resp.status_code == 404


async def test_latest_rerun_wins(client, session_factory, campaign):
    org_id, _, campaign_id, _ = campaign
    newer = json.loads(json.dumps(STRATEGY))
    newer["strategy"]["campaign_theme"] = "Second pass"
    await _run(session_factory, org_id, campaign_id, "strategise", newer)
    pack = await _pack(client, session_factory, org_id, campaign_id)
    assert pack["strategy"]["theme"] == "Second pass"
