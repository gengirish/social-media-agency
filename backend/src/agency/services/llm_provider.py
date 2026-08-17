"""LLM provider abstraction with a configurable multi-provider fallback chain.

Three tiers, so reasoning-heavy work can use a stronger model than bulk drafting:

- **brain** — Orchestrator, QA/Brand. Plans the campaign and judges brand fit.
- **worker** — Strategy, SEO, Content. High volume, cheaper.
- **ad_copy** — Ad Copy. Short, high-temperature variants.

Resolution order for a tier:

1. ``LLM_{TIER}_PROVIDER`` pins one provider, if set.
2. Otherwise the first provider in ``LLM_PROVIDER_ORDER`` (or
   :data:`DEFAULT_PROVIDER_ORDER`) that has an API key configured.

A provider with a blank API key is skipped, so adding a key is all it takes to
bring one online. If nothing is configured, :func:`get_llm` raises with the list
of variables to set — the previous behaviour built a client with an empty key
and failed deep inside the first agent, which is why campaigns hung in
``running`` with no diagnostic.

OpenAI-compatible providers (OpenRouter, NVIDIA NIM, Bonsai, OpenAI itself) all
run through ``ChatOpenAI`` with a ``base_url``; no extra packages needed.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from agency.config import get_settings

logger = structlog.get_logger()

BRAIN = "brain"
WORKER = "worker"
AD_COPY = "ad_copy"
LITE = "lite"

# Native SDK providers first (best reasoning), then OpenAI-compatible gateways.
DEFAULT_PROVIDER_ORDER = ("anthropic", "google", "openai", "nvidia", "openrouter", "bonsai")

# Per-tier generation settings, independent of which provider serves the tier.
#
# ``lite`` exists because output tokens are ~80% of campaign cost and several
# calls are mechanical reformatting, not reasoning: SEO keyword extraction,
# repurposing a post to another platform, generating an A/B variant. Those do
# not need the reasoning tier, and on Anthropic the lite model is 3x cheaper
# ($1/$5 per MTok vs $3/$15). ``max_tokens`` is lower too — these produce one
# short artifact, and an oversized ceiling only invites the model to fill it.
TIER_SETTINGS: dict[str, dict[str, Any]] = {
    BRAIN: {"temperature": 0.3, "max_tokens": 4096},
    WORKER: {"temperature": 0.7, "max_tokens": 4096},
    AD_COPY: {"temperature": 0.8, "max_tokens": 2048},
    LITE: {"temperature": 0.5, "max_tokens": 1536},
}

#: Every tier, in diagnostic order. Providers without a tier split repeat one id.
ALL_TIERS = (BRAIN, WORKER, AD_COPY, LITE)


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    kind: str  # "anthropic" | "google" | "openai_compatible"
    api_key: str
    base_url: str = ""
    # Model per tier; providers without a tier split repeat the same id.
    models: dict[str, str] = field(default_factory=dict)


def _provider_specs() -> dict[str, ProviderSpec]:
    """Build every known provider from settings, configured or not."""
    s = get_settings()

    return {
        "anthropic": ProviderSpec(
            name="anthropic",
            kind="anthropic",
            api_key=s.anthropic_api_key,
            # claude-3-5-haiku-20241022 was RETIRED 2026-02-19 and returns 404;
            # claude-sonnet-4-20250514 is deprecated. Both are replaced here.
            models={
                BRAIN: "claude-sonnet-5",
                WORKER: "claude-sonnet-5",
                AD_COPY: "claude-haiku-4-5",
                LITE: "claude-haiku-4-5",
            },
        ),
        "google": ProviderSpec(
            name="google",
            kind="google",
            api_key=s.google_api_key,
            models=dict.fromkeys(ALL_TIERS, s.gemini_model),
        ),
        "openai": ProviderSpec(
            name="openai",
            kind="openai_compatible",
            api_key=s.openai_api_key,
            base_url=s.openai_base_url,
            models=dict.fromkeys(ALL_TIERS, s.openai_model),
        ),
        "nvidia": ProviderSpec(
            name="nvidia",
            kind="openai_compatible",
            api_key=s.nvidia_nim_api_key,
            base_url=s.nvidia_nim_base_url,
            models=dict.fromkeys(ALL_TIERS, s.nvidia_nim_model),
        ),
        "openrouter": ProviderSpec(
            name="openrouter",
            kind="openai_compatible",
            api_key=s.openrouter_api_key,
            base_url=s.openrouter_base_url,
            models=dict.fromkeys(ALL_TIERS, s.openrouter_model),
        ),
        "bonsai": ProviderSpec(
            name="bonsai",
            kind="openai_compatible",
            api_key=s.bonsai_api_key,
            base_url=s.bonsai_base_url,
            models=dict.fromkeys(ALL_TIERS, s.bonsai_model),
        ),
    }


def _configured_order() -> tuple[str, ...]:
    raw = (get_settings().llm_provider_order or "").strip()
    if not raw:
        return DEFAULT_PROVIDER_ORDER

    known = set(DEFAULT_PROVIDER_ORDER)
    chosen = [p.strip().lower() for p in raw.split(",") if p.strip()]
    unknown = [p for p in chosen if p not in known]
    if unknown:
        logger.warning("llm_unknown_providers_ignored", providers=unknown, known=sorted(known))
    return tuple(p for p in chosen if p in known) or DEFAULT_PROVIDER_ORDER


def _tier_pin(tier: str) -> str:
    s = get_settings()
    return {
        BRAIN: s.llm_brain_provider,
        WORKER: s.llm_worker_provider,
        AD_COPY: s.llm_ad_copy_provider,
        LITE: s.llm_lite_provider,
    }[tier].strip().lower()


def _tier_model_override(tier: str) -> str:
    s = get_settings()
    return {
        BRAIN: s.llm_brain_model,
        WORKER: s.llm_worker_model,
        AD_COPY: s.llm_ad_copy_model,
        LITE: s.llm_lite_model,
    }[tier].strip()


def resolution_chain(tier: str) -> list[ProviderSpec]:
    """Providers to try for ``tier``, best first.

    A pinned tier yields exactly one provider — pinning means "use this one",
    so it is not silently failed over. Otherwise every configured provider is
    returned in preference order, and the tail becomes the runtime fallback
    chain. Raises if nothing is configured.
    """
    specs = _provider_specs()

    pinned = _tier_pin(tier)
    if pinned:
        spec = specs.get(pinned)
        if spec is None:
            raise ValueError(
                f"LLM_{tier.upper()}_PROVIDER={pinned!r} is not a known provider. "
                f"Choose one of: {', '.join(sorted(specs))}."
            )
        if not spec.api_key:
            raise ValueError(
                f"LLM_{tier.upper()}_PROVIDER is pinned to {pinned!r} but its API key is unset."
            )
        return [spec]

    chain = [specs[name] for name in _configured_order() if specs.get(name) and specs[name].api_key]
    if chain:
        return chain

    raise ValueError(
        "No LLM provider is configured. Set at least one of: ANTHROPIC_API_KEY, "
        "GOOGLE_API_KEY (or GEMINI_API_KEY), OPENAI_API_KEY, NVIDIA_NIM_API_KEY, "
        "OPENROUTER_API_KEY, BONSAI_API_KEY."
    )


def resolve_provider(tier: str) -> ProviderSpec:
    """The primary provider serving ``tier``."""
    return resolution_chain(tier)[0]


def _model_for(tier: str, spec: ProviderSpec, is_primary: bool) -> str:
    """Resolve the model id for a provider in the chain.

    ``LLM_{TIER}_MODEL`` applies only to the primary. Model ids are
    provider-specific, so forwarding an NVIDIA id to Gemini would guarantee the
    fallback fails — defeating the point of having one.
    """
    if is_primary:
        return _tier_model_override(tier) or spec.models[tier]
    return spec.models[tier]


def _build_client(tier: str, spec: ProviderSpec, temperature: float | None, is_primary: bool):
    tier_cfg = TIER_SETTINGS[tier]
    model = _model_for(tier, spec, is_primary)
    temp = tier_cfg["temperature"] if temperature is None else temperature
    max_tokens = tier_cfg["max_tokens"]

    if spec.kind == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model, api_key=spec.api_key, temperature=temp, max_tokens=max_tokens
        )

    if spec.kind == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=spec.api_key,
            temperature=temp,
            max_output_tokens=max_tokens,
        )

    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": model,
        "api_key": spec.api_key,
        "temperature": temp,
        "max_tokens": max_tokens,
    }
    if spec.base_url:
        kwargs["base_url"] = spec.base_url
    return ChatOpenAI(**kwargs)


def get_llm(tier: str, temperature: float | None = None):
    """Chat model for ``tier``, with the remaining providers as live fallbacks.

    Free-tier gateways return transient 503s under load (NVIDIA NIM caps
    concurrent requests), so configuring a second provider keeps a campaign
    running instead of failing the whole pipeline on one saturated call.
    """
    if tier not in TIER_SETTINGS:
        raise ValueError(f"Unknown tier {tier!r}; expected one of {sorted(TIER_SETTINGS)}.")

    chain = resolution_chain(tier)
    primary_spec, *fallback_specs = chain

    logger.debug(
        "llm_resolved",
        tier=tier,
        provider=primary_spec.name,
        model=_model_for(tier, primary_spec, True),
        fallbacks=[s.name for s in fallback_specs],
    )

    primary = _build_client(tier, primary_spec, temperature, True)
    if not fallback_specs:
        return primary

    return primary.with_fallbacks(
        [_build_client(tier, spec, temperature, False) for spec in fallback_specs]
    )


def describe_providers() -> dict[str, Any]:
    """Diagnostics for `/health/llm`. Never returns key material."""
    specs = _provider_specs()
    tiers: dict[str, Any] = {}

    for tier in ALL_TIERS:
        try:
            primary, *fallbacks = resolution_chain(tier)
            tiers[tier] = {
                "provider": primary.name,
                "model": _model_for(tier, primary, True),
                "base_url": primary.base_url or None,
                "fallbacks": [
                    {"provider": s.name, "model": _model_for(tier, s, False)} for s in fallbacks
                ],
            }
        except ValueError as exc:
            tiers[tier] = {"error": str(exc)}

    return {
        "order": list(_configured_order()),
        "configured": sorted(n for n, s in specs.items() if s.api_key),
        "unconfigured": sorted(n for n, s in specs.items() if not s.api_key),
        "tiers": tiers,
    }


# --- Tier helpers used by the agents ---


def get_brain_llm():
    """High-reasoning model for Orchestrator and QA agents."""
    return get_llm(BRAIN)


def get_worker_llm(temperature: float = 0.7):
    """Fast/cheap model for Strategy, SEO, Content agents."""
    return get_llm(WORKER, temperature=temperature)


def get_ad_copy_llm():
    """Model tuned for ad copy variants."""
    return get_llm(AD_COPY)


def get_lite_llm(temperature: float | None = None):
    """Cheap model for mechanical reformatting, not reasoning.

    Use for work that transforms text it is handed rather than deciding
    anything: SEO keyword extraction, repurposing a post to another platform,
    generating an A/B variant. Do not use where campaign quality depends on the
    judgement in the output — that is what ``worker`` and ``brain`` are for.
    """
    return get_llm(LITE, temperature=temperature)
