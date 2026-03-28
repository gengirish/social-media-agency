"""Video/podcast script agent — generate scripts for video and audio content."""

import json

import structlog

from agency.services.llm_provider import get_worker_llm

logger = structlog.get_logger()

SCRIPT_FORMATS = {
    "tiktok": {
        "structure": "Hook (0-3s) → Body (3-45s) → CTA (45-60s)",
        "max_duration": "60s",
        "style": "Fast-paced, trending sounds, Gen-Z friendly",
    },
    "youtube": {
        "structure": "Hook → Intro → Chapters → Outro + CTA",
        "max_duration": "10-15min",
        "style": "Educational or entertaining, chapter-based",
    },
    "reels": {
        "structure": "Hook → Value → CTA",
        "max_duration": "90s",
        "style": "Visual-first, trending audio, quick cuts",
    },
    "podcast": {
        "structure": "Intro → Segment 1 → Segment 2 → Segment 3 → Outro",
        "max_duration": "30-60min",
        "style": "Conversational, story-driven, listener engagement",
    },
}


async def generate_script(
    format: str,
    topic: str,
    brand_context: dict,
    target_audience: str = "",
) -> dict:
    """Generate a video/podcast script."""
    llm = get_worker_llm()

    fmt = SCRIPT_FORMATS.get(format, SCRIPT_FORMATS["youtube"])

    prompt = f"""You are a video/audio script writer.

Format: {format}
Structure: {fmt['structure']}
Duration: {fmt['max_duration']}
Style: {fmt['style']}
Topic: {topic}
Brand: {brand_context.get('brand_name', 'Unknown')}
Industry: {brand_context.get('industry', 'Unknown')}
Target audience: {target_audience or 'General'}

Write a complete script with:
1. Scene/segment descriptions
2. Spoken dialogue/narration
3. Visual/audio cues
4. Timestamps

Return JSON:
{{
    "title": "...",
    "format": "{format}",
    "duration": "...",
    "segments": [
        {{
            "timestamp": "0:00",
            "type": "hook|intro|body|cta|outro",
            "narration": "...",
            "visual_cue": "...",
            "audio_cue": "..."
        }}
    ],
    "hashtags": ["..."],
    "thumbnail_idea": "..."
}}"""

    response = await llm.ainvoke(prompt)
    text = response.content if hasattr(response, "content") else str(response)
    text = text.strip()

    try:
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)
    except Exception:
        return {
            "title": topic,
            "format": format,
            "segments": [],
            "raw_script": text[:1000],
        }
