"""Magic Brief — paste a URL, auto-extract brand voice and profile."""

import json
import re
from html import unescape
from typing import Any
from urllib.parse import unquote, urljoin

import httpx
import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from agency.services.llm_provider import get_worker_llm
from agency.services.url_safety import UnsafeURLError, fetch_public_page

logger = structlog.get_logger()

# --- Contact email -------------------------------------------------------
#
# The email is pulled out of the HTML in code, never asked of the model: a
# plausible-looking address an LLM invents would be written straight into the
# client record and mailed. Preference order is mailto: links first (an address
# the site itself published as a link), then role inboxes, then first seen.

CONTACT_PATHS = ("/contact", "/contact-us", "/about")

_MAILTO_RE = re.compile(r"mailto:([^\"'?>\s]+)", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_ROLE_PREFERENCE = (
    "contact", "hello", "hey", "hi", "info", "enquiries", "inquiries",
    "support", "help", "sales", "team", "press", "admin", "office",
)
# Addresses that are never a brand's contact: unattended senders, vendor
# boilerplate, placeholders, and image/asset names that look like emails
# ("logo@2x.png", a fingerprint in a bundled script).
_EMAIL_REJECT = (
    "noreply", "no-reply", "donotreply", "do-not-reply", "@2x.", "@3x.",
    "example.com", "example.org", "yourdomain", "yourcompany", "domain.com",
    "email.com", "sentry.io", "wixpress.com", "squarespace.com", "sentry-next",
)
_ASSET_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".css", ".js",
    ".map", ".woff", ".woff2", ".ttf", ".mp4", ".pdf",
)


def _clean_email(raw: str) -> str | None:
    """Normalise one candidate, or None if it is not a usable address."""
    value = unquote(unescape(raw)).split("?")[0].strip().strip(".,;:()<>[]\"'").lower()
    if not _EMAIL_RE.fullmatch(value):
        return None
    if any(bad in value for bad in _EMAIL_REJECT):
        return None
    if value.endswith(_ASSET_SUFFIXES):
        return None
    return value


def find_contact_email(html: str) -> str | None:
    """Best contact address published on a page, or None.

    Runs on the raw HTML, not the tag-stripped text, because most sites only
    ever expose the address inside a ``mailto:`` href.
    """
    linked: list[str] = []
    plain: list[str] = []
    for match in _MAILTO_RE.finditer(html):
        email = _clean_email(match.group(1))
        if email and email not in linked:
            linked.append(email)
    for match in _EMAIL_RE.finditer(html):
        email = _clean_email(match.group(0))
        if email and email not in plain:
            plain.append(email)

    for candidates in (linked, plain):
        if not candidates:
            continue
        for role in _ROLE_PREFERENCE:
            for email in candidates:
                if email.split("@")[0] == role:
                    return email
        return candidates[0]
    return None


async def _email_from_contact_pages(url: str, client: httpx.AsyncClient) -> str | None:
    """Look for an address on the usual contact pages of the same site.

    Brands rarely put the address on the landing page, so without this the
    field comes back empty for most sites. Every failure is swallowed: this is
    a nice-to-have on top of an extraction that already succeeded.
    """
    for path in CONTACT_PATHS:
        try:
            html = await fetch_public_page(urljoin(url, path), client)
        except (UnsafeURLError, httpx.HTTPError, UnicodeDecodeError):
            continue
        email = find_contact_email(html)
        if email:
            return email
    return None


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
            contact_email = find_contact_email(html) or await _email_from_contact_pages(url, client)

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

        # Set after parsing so a model that hallucinated the key cannot win.
        profile["contact_email"] = contact_email or ""
        profile["source_url"] = url
        logger.info(
            "brand_extracted",
            url=url,
            brand=profile.get("brand_name"),
            has_contact_email=bool(contact_email),
        )
        return profile

    except UnsafeURLError as e:
        logger.warning("magic_brief_url_refused", url=url, reason=str(e))
        return {"error": str(e)}
    except httpx.HTTPError as e:
        return {"error": f"Failed to fetch URL: {str(e)}"}
    except Exception as e:
        return {"error": f"Brand extraction failed: {str(e)}"}
