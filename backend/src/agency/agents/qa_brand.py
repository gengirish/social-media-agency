"""QA / Brand Agent — The Quality Gate.

Reviews all generated content and ad copy against brand voice, tone,
consistency, and compliance. Uses Brain-tier model (Claude Sonnet) for
strong judgment and nuanced brand voice evaluation.
"""

import json

from langchain_core.messages import SystemMessage

from agency.agents.state import CampaignState
from agency.services.llm_provider import get_brain_llm

SYSTEM_PROMPT = """You are the QA/Brand Agent of CampaignForge, the final quality gate before content delivery.

Your job is to review ALL generated content and ad copy for:
1. **Brand Voice Consistency** — Does it match the brand's tone and personality?
2. **Factual Accuracy** — No false claims, no made-up statistics
3. **Platform Appropriateness** — Content fits the platform's culture and format
4. **Compliance** — No problematic claims (especially for healthcare, finance, etc.)
5. **Quality** — Is it actually good? Would a human marketer approve this?
6. **CTA Effectiveness** — Are calls-to-action clear and compelling?
7. **Consistency** — Do all pieces feel like they came from the same brand?

## Brand Profile
{brand_context}

## Brand Guardrails
{guardrails}

## Content to Review
{content_pieces}

## Ad Copy to Review
{ad_variants}

## Response Format
Return a JSON object:
{{
    "overall_score": 8.5,
    "pass": true,
    "brand_voice_score": 9,
    "content_quality_score": 8,
    "compliance_score": 10,
    "consistency_score": 8,
    "issues": [
        {{
            "piece_index": 0,
            "type": "content|ad",
            "severity": "critical|warning|suggestion",
            "issue": "Description of the problem",
            "fix_suggestion": "How to fix it"
        }}
    ],
    "strengths": ["What was done well"],
    "summary": "Overall assessment in 2-3 sentences"
}}

If overall_score < 7 or any critical issues exist, set "pass" to false."""


#: QA is the one graph node whose input grows with campaign output — it is
#: handed every generated piece. Left uncapped, a large campaign inflates this
#: prompt without bound and can push the response into truncation. Reviewing a
#: bounded sample is fine; *claiming* to have reviewed everything is not, so
#: whatever is trimmed is reported back in ``qa_feedback.coverage``.
MAX_ITEMS_REVIEWED = 12
MAX_BODY_CHARS = 1200


def _trim_for_review(items: list, limit: int = MAX_ITEMS_REVIEWED) -> tuple[list, int]:
    """Return (reviewed subset with trimmed bodies, count omitted)."""
    if not isinstance(items, list):
        return [], 0
    subset = items[:limit]
    trimmed = []
    for item in subset:
        if not isinstance(item, dict):
            trimmed.append(item)
            continue
        entry = dict(item)
        body = entry.get("body")
        if isinstance(body, str) and len(body) > MAX_BODY_CHARS:
            entry["body"] = body[:MAX_BODY_CHARS] + " …[truncated for review]"
        trimmed.append(entry)
    return trimmed, max(0, len(items) - len(subset))


async def qa_brand_node(state: CampaignState) -> dict:
    llm = get_brain_llm()
    brand_ctx = state.get("brand_context", {})
    plan = state.get("execution_plan", {})
    content = state.get("content_pieces", [])
    ads = state.get("ad_variants", [])

    brand_str = "\n".join(f"- {k}: {v}" for k, v in brand_ctx.items() if v)
    guardrails = plan.get("brand_guardrails", [])
    guardrails_str = "\n".join(f"- {g}" for g in guardrails) if guardrails else "No specific guardrails defined"

    reviewed_content, content_omitted = _trim_for_review(content)
    reviewed_ads, ads_omitted = _trim_for_review(ads)

    content_str = (
        json.dumps(reviewed_content, separators=(",", ":"))
        if reviewed_content
        else "No content pieces generated"
    )
    ads_str = (
        json.dumps(reviewed_ads, separators=(",", ":"))
        if reviewed_ads
        else "No ad variants generated"
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT.format(
            brand_context=brand_str,
            guardrails=guardrails_str,
            content_pieces=content_str,
            ad_variants=ads_str,
        )),
        ("human", "Review all generated content and ad copy. Be thorough but fair."),
    ]

    response = await llm.ainvoke(messages)

    try:
        feedback = json.loads(response.content)
    except json.JSONDecodeError:
        content_text = response.content
        start = content_text.find("{")
        end = content_text.rfind("}") + 1
        if start != -1 and end > start:
            feedback = json.loads(content_text[start:end])
        else:
            # Never fabricate a score. A previous version returned
            # ``{"overall_score": 7, "pass": True}`` here, which turned an
            # unparseable QA response into a quality gate that silently passed
            # with an invented 7/10. Report the failure instead.
            feedback = {
                "overall_score": None,
                "pass": None,
                "score_available": False,
                "summary": response.content,
                "issues": [],
                "error": (
                    "QA response could not be parsed as JSON — this campaign was "
                    "NOT quality-checked. Review the content manually."
                ),
            }

    # Say plainly what was and was not looked at, so a "pass" can never be read
    # as covering items the model never saw.
    if isinstance(feedback, dict):
        feedback["coverage"] = {
            "content_reviewed": len(reviewed_content),
            "content_total": len(content) if isinstance(content, list) else 0,
            "content_omitted": content_omitted,
            "ads_reviewed": len(reviewed_ads),
            "ads_total": len(ads) if isinstance(ads, list) else 0,
            "ads_omitted": ads_omitted,
            "complete": content_omitted == 0 and ads_omitted == 0,
        }

    return {
        "qa_feedback": feedback,
        "current_agent": "qa_brand",
        "status": "qa_complete",
    }
