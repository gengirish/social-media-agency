"""Langfuse tracing for LLM calls, off unless both keys are set.

Every traced call goes through :func:`trace_config`, which returns a LangChain
``RunnableConfig`` fragment to pass as ``config=``. With tracing disabled it
returns ``{}``, so call sites never branch on whether Langfuse is configured.

Two shapes of trace:

- **Campaign pipeline** — one trace per campaign, covering every graph node and
  LLM call. The graph pauses at ``human_review`` and resumes from a *different*
  request, often much later and possibly on a restarted machine, so Langfuse's
  own in-memory interrupt/resume stitching cannot link the two halves. Instead
  the trace id is derived from ``campaign_id`` (``trace_seed``): the initial run
  and every resume land in the same trace without any state to persist.
- **Standalone calls** (repurpose, variants, magic brief, …) — one trace each,
  named after the feature.

Handlers are created per run. A handler holds per-run state, and sharing one
across concurrent campaigns would interleave them.

Traces carry prompt and completion text — client briefs and brand context — so
everything passes through :func:`mask_trace_data` before export, per
``LANGFUSE_MASK_MODE``:

- ``pii`` (default) — prompts stay readable; emails, phone numbers, card
  numbers, credentials and IP addresses are replaced with ``[email]`` etc. The
  brief and brand text itself is still sent.
- ``full`` — every string becomes ``[redacted N chars]``, except the ids needed
  to find a trace (org/campaign/client, graph node, model). Timing, token
  usage and cost are unaffected; they are not part of the masked fields.
- ``off`` — nothing masked.

An unrecognised mode falls back to ``full``: a typo must not disable masking.
"""

import asyncio
import re
from collections.abc import Callable
from typing import Any

import structlog

from agency.config import get_settings

logger = structlog.get_logger()

_client: Any = None
_mask_mode = "full"

MASK_MODES = ("pii", "full", "off")

# --- Masking ---

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Credentials first: they can contain digit runs the phone rule would claim.
_SECRETS = re.compile(
    r"\b(?:sk|pk)-[A-Za-z0-9_-]{16,}"  # OpenAI/Anthropic/Langfuse-style keys
    r"|\bAKIA[0-9A-Z]{16}\b"  # AWS access key id
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}"  # GitHub tokens
    r"|\bxox[abpr]-[A-Za-z0-9-]{10,}"  # Slack tokens
    r"|\bAIza[0-9A-Za-z_-]{30,}"  # Google API keys
    r"|\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}"  # JWTs
    r"|\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*",
)
_CARD_CANDIDATE = re.compile(r"(?<![\d-])\d(?:[ -]?\d){12,18}(?![\d-])")
_PHONE_CANDIDATE = re.compile(r"(?<![\w+])\+?\d[\d\s().-]{7,}\d(?!\w)")
_IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def _mask_card(m: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", m.group())
    return "[card]" if _luhn_ok(digits) else m.group()


def _mask_phone(m: re.Match[str]) -> str:
    # 9-15 digits: long enough to skip dates (8) and budgets, short of an id.
    n = sum(c.isdigit() for c in m.group())
    return "[phone]" if 9 <= n <= 15 else m.group()


def mask_pii(text: str) -> str:
    text = _SECRETS.sub("[secret]", text)
    text = _EMAIL.sub("[email]", text)
    text = _CARD_CANDIDATE.sub(_mask_card, text)
    # IPs before phones: the phone rule accepts dots and would claim them.
    text = _IPV4.sub("[ip]", text)
    # Errs toward masking: a bare 9-15 digit run (an order number, say) is
    # treated as a phone. Losing an id from a trace beats leaking a number.
    return _PHONE_CANDIDATE.sub(_mask_phone, text)


def _redact(text: str) -> str:
    return f"[redacted {len(text)} chars]" if text else text


# Keys whose values are kept whole in ``full`` mode: trace-lookup ids, graph
# position and model identity — never prompt or brand content.
_FULL_MODE_KEEP_KEYS = frozenset(
    {"org_id", "campaign_id", "client_id", "phase", "thread_id", "role", "type"}
)
_FULL_MODE_KEEP_PREFIXES = ("langgraph_", "ls_", "checkpoint_")


def _keep_in_full_mode(key: Any) -> bool:
    return isinstance(key, str) and (
        key in _FULL_MODE_KEEP_KEYS or key.startswith(_FULL_MODE_KEEP_PREFIXES)
    )


def _walk(data: Any, on_str: Callable[[str], str], full: bool) -> Any:
    if isinstance(data, str):
        return on_str(data)
    if isinstance(data, dict):
        return {
            k: v if full and _keep_in_full_mode(k) else _walk(v, on_str, full)
            for k, v in data.items()
        }
    if isinstance(data, list | tuple):
        return [_walk(v, on_str, full) for v in data]
    return data  # numbers, bools, None: no text to leak


def mask_trace_data(*, data: Any, **_: Any) -> Any:
    """Langfuse ``mask`` hook, applied to every observation's input, output and
    metadata before export. Dict keys are structure, not content, and are kept."""
    if _mask_mode == "off":
        return data
    if _mask_mode == "pii":
        return _walk(data, mask_pii, full=False)
    return _walk(data, _redact, full=True)


def _resolve_mask_mode(raw: str) -> str:
    mode = (raw or "").strip().lower()
    if mode in MASK_MODES:
        return mode
    logger.warning("langfuse_mask_mode_unknown", value=raw, using="full", valid=MASK_MODES)
    return "full"


def langfuse_enabled() -> bool:
    s = get_settings()
    return bool(s.langfuse_public_key and s.langfuse_secret_key)


def init_langfuse() -> None:
    """Build the Langfuse client once at startup, or log why it is off.

    Settings are read from ``.env`` by pydantic and never reach ``os.environ``,
    so the client is configured explicitly rather than via Langfuse's own
    ``LANGFUSE_*`` environment lookup.
    """
    global _client, _mask_mode
    if not langfuse_enabled():
        logger.info("langfuse_disabled", reason="LANGFUSE_PUBLIC_KEY/SECRET_KEY unset")
        return

    from langfuse import Langfuse

    s = get_settings()
    _mask_mode = _resolve_mask_mode(s.langfuse_mask_mode)
    _client = Langfuse(
        public_key=s.langfuse_public_key,
        secret_key=s.langfuse_secret_key,
        base_url=s.langfuse_base_url,
        environment=s.app_env,
        sample_rate=s.langfuse_sample_rate,
        mask=mask_trace_data,
    )
    logger.info(
        "langfuse_enabled",
        base_url=s.langfuse_base_url,
        environment=s.app_env,
        sample_rate=s.langfuse_sample_rate,
        mask_mode=_mask_mode,
    )


async def shutdown_langfuse(timeout: float = 5.0) -> None:
    """Flush buffered spans. Export is batched, so skipping this drops the tail.

    Bounded: with Langfuse unreachable, ``shutdown()`` blocks on retries for
    ~15s, and telemetry must not stall a deploy. Past the timeout the tail is
    dropped and the flush thread is left to die with the process.
    """
    global _client
    if _client is None:
        return
    client, _client = _client, None
    try:
        await asyncio.wait_for(asyncio.to_thread(client.shutdown), timeout)
    except TimeoutError:
        logger.warning("langfuse_shutdown_timeout", timeout_s=timeout)
    except Exception as exc:
        logger.warning("langfuse_shutdown_failed", error=str(exc))


def trace_id_for(seed: str) -> str:
    """Deterministic 32-hex trace id, so separate runs can share one trace."""
    from langfuse import Langfuse

    return Langfuse.create_trace_id(seed=seed)


def trace_config(
    name: str,
    *,
    org_id: Any = None,
    user_id: Any = None,
    session_id: Any = None,
    trace_seed: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """RunnableConfig fragment that traces one run to Langfuse, or ``{}``.

    ``org_id`` is also added as an ``org:<id>`` tag so traces filter by tenant.
    ``user_id`` and ``session_id`` map to Langfuse's own user and session
    fields. Ids may be UUIDs; they are stringified, since the handler only reads
    string values and silently drops anything else.
    """
    if _client is None:
        return {}

    from langfuse.langchain import CallbackHandler

    s = get_settings()
    handler = CallbackHandler(
        public_key=s.langfuse_public_key,
        trace_context={"trace_id": trace_id_for(trace_seed)} if trace_seed else None,
    )

    all_tags = list(tags or [])
    meta: dict[str, Any] = dict(metadata or {})
    if org_id is not None:
        meta["org_id"] = str(org_id)
        all_tags.append(f"org:{org_id}")
    if user_id is not None:
        meta["langfuse_user_id"] = str(user_id)
    if session_id is not None:
        meta["langfuse_session_id"] = str(session_id)
    if all_tags:
        meta["langfuse_tags"] = all_tags

    return {"callbacks": [handler], "run_name": name, "metadata": meta}


def merge_config(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Overlay a :func:`trace_config` fragment on an existing RunnableConfig.

    The graph config carries ``configurable.thread_id`` for the checkpointer;
    this keeps that intact and merges metadata instead of replacing it.
    """
    if not extra:
        return base
    merged = {**base, **extra}
    if "metadata" in base or "metadata" in extra:
        merged["metadata"] = {**base.get("metadata", {}), **extra.get("metadata", {})}
    return merged
