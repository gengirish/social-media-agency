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


# ---------------------------------------------------------------------------
# Pipeline nodes: parse, or repair once, never raise.
#
# The graph nodes used to do ``json.loads(content)`` and, on failure, a second
# bare ``json.loads`` on the outermost {...} slice. A single missing comma in a
# 5 KB strategy then raised out of the node and failed the whole campaign
# (production 260923: "Expecting ',' delimiter"). Models do emit malformed JSON
# at this length, so one repair pass is worth a cheap call.
# ---------------------------------------------------------------------------

_REPAIR_PROMPT = (
    "The text below was meant to be a single valid JSON {kind} but it does not parse "
    "({error}). Return ONLY the corrected JSON {kind}: same keys, same values, same "
    "order. Fix syntax only (missing commas, quotes, brackets, trailing commas). "
    "No prose, no code fences.\n\n{content}"
)


def text_of(content: object) -> str:
    """LangChain message content as text (Anthropic can return a list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def _strip_json_noise(text: str) -> str:
    """Drop whole-line ``//`` comments and trailing commas before ``]``/``}``."""
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("//")]
    return re.sub(r",(\s*[\]}])", r"\1", "\n".join(lines))


def _try_parse(content: str, expect: type) -> tuple[object | None, str]:
    """Cheap strategies only. Returns (value, last_error)."""
    open_ch, close_ch = ("[", "]") if expect is list else ("{", "}")
    stripped = content.strip()
    unfenced = re.sub(r"\n?```\s*$", "", re.sub(r"^```(?:json)?\s*\n?", "", stripped))
    candidates = [stripped, unfenced]
    start, end = content.find(open_ch), content.rfind(close_ch) + 1
    if start != -1 and end > start:
        candidates.append(content[start:end])
        # Models copy habits from prompt examples: whole-line // comments and
        # trailing commas. Both are unambiguous to strip outside string values
        # (a whole-line comment cannot sit inside a JSON string).
        candidates.append(_strip_json_noise(content[start:end]))
    error = "no JSON found"
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError as exc:
            error = str(exc)
            continue
        if isinstance(value, expect) or (expect is list and isinstance(value, dict)):
            return value, ""
    return None, error


async def parse_agent_json(
    content: object, *, agent: str, expect: type = dict
) -> object | None:
    """Parse a pipeline node's JSON; on failure make ONE lite-tier repair call.

    Returns the parsed value (a dict, or for ``expect=list`` a list or a single
    dict), or ``None`` when even the repair fails, so the caller keeps its own
    fallback shape. Never raises for bad model output.
    """
    import structlog

    log = structlog.get_logger()
    text = text_of(content)
    value, error = _try_parse(text, expect)
    if value is not None:
        return value
    if not text.strip():
        log.warning("agent_json_unparseable", agent=agent, error="empty output")
        return None

    from agency.services.llm_provider import get_lite_llm

    kind = "array" if expect is list else "object"
    try:
        repaired = await get_lite_llm(0).ainvoke(
            _REPAIR_PROMPT.format(kind=kind, error=error, content=text)
        )
        value, repair_error = _try_parse(text_of(repaired.content), expect)
    except Exception as exc:  # repair is best-effort; the node has a fallback
        value, repair_error = None, f"repair call failed: {exc}"
    if value is not None:
        log.info("agent_json_repaired", agent=agent, original_error=error)
        return value
    log.warning(
        "agent_json_unparseable",
        agent=agent,
        error=error,
        repair_error=repair_error,
        near=_error_context(text),
        length=len(text),
    )
    return None


def _error_context(text: str, width: int = 160) -> str:
    """The characters around the first parse error, for diagnosing model output."""
    try:
        json.loads(text[text.find("{"):] if "{" in text else text)
    except json.JSONDecodeError as exc:
        start = max(0, exc.pos - width)
        return text[start : exc.pos + width // 2]
    return ""
