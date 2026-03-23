"""Utility functions for agent JSON parsing with resilience."""

import json
import re


def parse_llm_json(content: str, fallback_key: str = "raw_output") -> dict | list:
    """Parse JSON from LLM output with multiple fallback strategies."""
    content = content.strip()

    # Strategy 1: Direct parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", content)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategy 3: Find first JSON object
    obj_match = re.search(r"\{[\s\S]*\}", content)
    if obj_match:
        try:
            return json.loads(obj_match.group())
        except json.JSONDecodeError:
            pass

    # Strategy 4: Find first JSON array
    arr_match = re.search(r"\[[\s\S]*\]", content)
    if arr_match:
        try:
            return json.loads(arr_match.group())
        except json.JSONDecodeError:
            pass

    # Strategy 5: Return raw as fallback
    return {fallback_key: content[:2000]}
