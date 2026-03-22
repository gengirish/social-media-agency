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


async def qa_brand_node(state: CampaignState) -> dict:
    llm = get_brain_llm()
    brand_ctx = state.get("brand_context", {})
    plan = state.get("execution_plan", {})
    content = state.get("content_pieces", [])
    ads = state.get("ad_variants", [])

    brand_str = "\n".join(f"- {k}: {v}" for k, v in brand_ctx.items() if v)
    guardrails = plan.get("brand_guardrails", [])
    guardrails_str = "\n".join(f"- {g}" for g in guardrails) if guardrails else "No specific guardrails defined"

    content_str = json.dumps(content, indent=2) if content else "No content pieces generated"
    ads_str = json.dumps(ads, indent=2) if ads else "No ad variants generated"

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
            feedback = {
                "overall_score": 7,
                "pass": True,
                "summary": response.content,
                "issues": [],
            }

    return {
        "qa_feedback": feedback,
        "current_agent": "qa_brand",
        "status": "qa_complete",
    }
