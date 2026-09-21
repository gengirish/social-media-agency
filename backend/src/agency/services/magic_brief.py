"""Magic Brief — paste a URL, auto-extract brand voice and profile."""

import json
import re
from typing import Any

import httpx
import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from agency.services.llm_provider import get_worker_llm
from agency.services.url_safety import UnsafeURLError, fetch_public_page

logger = structlog.get_logger()

EXTRACTION_PROMPT = """You are a brand analyst. Given the HTML content of a company's website, extract a comprehensive brand profile.

## Website Content
{content}

## Extract the following as JSON:
{{
    "brand_name": "Company name",
    "industry": "Primary industry (e.g., Technology, Food & Beverage, Healthcare)",
    "description": "2-3 sentence company description",
    "voice_description": "How the brand communicates (e.g., Professional and authoritative, Casual and fun)",
    "tone_attributes": {{
        "formality": 0.0-1.0,
        "humor": 0.0-1.0,
        "warmth": 0.0-1.0,
        "authority": 0.0-1.0,
        "urgency": 0.0-1.0
    }},
    "target_audience": "Who this brand targets",
    "style_rules": ["Rule 1", "Rule 2"],
    "vocabulary_include": ["words they use often"],
    "vocabulary_exclude": ["words they avoid"],
    "emoji_policy": "none|minimal|moderate|heavy",
    "competitor_differentiation": "What makes them unique",
    "suggested_channels": ["linkedin", "twitter", "instagram"],
    "content_pillars": ["Topic 1", "Topic 2", "Topic 3"]
}}

Return ONLY valid JSON."""


async def extract_brand_from_url(url: str) -> dict[str, Any]:
    """Scrape a URL and extract brand profile using LLM."""
    try:
        url = url.strip()
        # Not urlparse().scheme: "localhost:8080" parses with scheme "localhost".
        if "://" not in url:
            url = f"https://{url}"

        # The URL is user-supplied and fetched from inside our network, so every
        # hop must resolve to a public address (see services/url_safety.py).
        async with httpx.AsyncClient(timeout=15.0) as client:
            html = await fetch_public_page(url, client)

        # Strip HTML to text (basic approach)
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = text[:4000]

        if len(text) < 50:
            return {"error": "Could not extract meaningful content from URL"}

        llm = get_worker_llm(temperature=0.3)
        messages = [
            SystemMessage(content=EXTRACTION_PROMPT.format(content=text)),
            HumanMessage(content=f"Analyze the website at {url} and extract the brand profile."),
        ]

        response = await llm.ainvoke(messages)
        raw_content = response.content if isinstance(response.content, str) else str(response.content)

        try:
            profile: dict[str, Any] = json.loads(raw_content)
        except json.JSONDecodeError:
            start = raw_content.find("{")
            end = raw_content.rfind("}") + 1
            if start != -1 and end > start:
                profile = json.loads(raw_content[start:end])
            else:
                return {
                    "error": "Failed to parse brand profile",
                    "raw": raw_content[:500],
                }

        profile["source_url"] = url
        logger.info("brand_extracted", url=url, brand=profile.get("brand_name"))
        return profile

    except UnsafeURLError as e:
        logger.warning("magic_brief_url_refused", url=url, reason=str(e))
        return {"error": str(e)}
    except httpx.HTTPError as e:
        return {"error": f"Failed to fetch URL: {str(e)}"}
    except Exception as e:
        return {"error": f"Brand extraction failed: {str(e)}"}
