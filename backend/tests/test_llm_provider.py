"""Provider chain resolution — the logic that decides which model runs an agent.

`get_settings` is `lru_cache`d, so each test clears it after mutating the env.
"""

import pytest

from agency.config import get_settings
from agency.services import llm_provider as lp

PROVIDER_ENV = [
    "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY",
    "NVIDIA_NIM_API_KEY", "OPENROUTER_API_KEY", "BONSAI_API_KEY",
    "LLM_PROVIDER_ORDER", "LLM_BRAIN_PROVIDER", "LLM_WORKER_PROVIDER",
    "LLM_AD_COPY_PROVIDER", "LLM_LITE_PROVIDER", "LLM_BRAIN_MODEL",
    "LLM_WORKER_MODEL", "LLM_AD_COPY_MODEL", "LLM_LITE_MODEL",
    "NVIDIA_NIM_MODEL", "GEMINI_MODEL",
]


@pytest.fixture
def env(monkeypatch):
    """Start from no providers configured, and reset the settings cache."""
    for name in PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()

    def setenv(**values: str):
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()

    yield setenv
    get_settings.cache_clear()


def test_no_provider_raises_a_actionable_error(env):
    """The old code built a client with an empty key and died inside an agent."""
    with pytest.raises(ValueError) as exc:
        lp.resolve_provider(lp.BRAIN)
    message = str(exc.value)
    assert "No LLM provider is configured" in message
    assert "NVIDIA_NIM_API_KEY" in message


def test_gemini_api_key_is_accepted_as_an_alias(env):
    """Their existing env uses GEMINI_API_KEY; the app reads google_api_key."""
    env(GEMINI_API_KEY="test-key")
    assert get_settings().google_api_key == "test-key"
    assert lp.resolve_provider(lp.WORKER).name == "google"


def test_google_default_model_is_not_the_rate_limited_one(env):
    """gemini-2.0-flash returns 429 on the current key; 2.5-flash does not."""
    env(GOOGLE_API_KEY="k")
    spec = lp.resolve_provider(lp.WORKER)
    assert spec.models[lp.WORKER] == "gemini-2.5-flash"


def test_nvidia_alone_serves_every_tier(env):
    env(NVIDIA_NIM_API_KEY="nv")
    for tier in (lp.BRAIN, lp.WORKER, lp.AD_COPY):
        spec = lp.resolve_provider(tier)
        assert spec.name == "nvidia"
        assert spec.base_url == "https://integrate.api.nvidia.com/v1"
        assert spec.kind == "openai_compatible"


def test_default_order_prefers_anthropic_over_gateways(env):
    env(NVIDIA_NIM_API_KEY="nv", ANTHROPIC_API_KEY="an", GOOGLE_API_KEY="g")
    assert lp.resolve_provider(lp.BRAIN).name == "anthropic"


def test_explicit_order_overrides_the_default(env):
    env(NVIDIA_NIM_API_KEY="nv", ANTHROPIC_API_KEY="an",
        LLM_PROVIDER_ORDER="nvidia,anthropic")
    assert lp.resolve_provider(lp.BRAIN).name == "nvidia"


def test_unconfigured_providers_are_skipped_in_the_order(env):
    env(NVIDIA_NIM_API_KEY="nv", LLM_PROVIDER_ORDER="anthropic,openai,nvidia")
    assert lp.resolve_provider(lp.BRAIN).name == "nvidia"


def test_unknown_names_in_order_are_ignored_not_fatal(env):
    env(NVIDIA_NIM_API_KEY="nv", LLM_PROVIDER_ORDER="nope,nvidia")
    assert lp.resolve_provider(lp.BRAIN).name == "nvidia"


def test_order_of_only_unknown_names_falls_back_to_default(env):
    env(GOOGLE_API_KEY="g", LLM_PROVIDER_ORDER="nope,alsonope")
    assert lp.resolve_provider(lp.WORKER).name == "google"


def test_tier_pin_splits_brain_and_worker(env):
    env(NVIDIA_NIM_API_KEY="nv", GOOGLE_API_KEY="g",
        LLM_BRAIN_PROVIDER="nvidia", LLM_WORKER_PROVIDER="google")
    assert lp.resolve_provider(lp.BRAIN).name == "nvidia"
    assert lp.resolve_provider(lp.WORKER).name == "google"


def test_tier_pin_to_a_keyless_provider_is_rejected(env):
    env(NVIDIA_NIM_API_KEY="nv", LLM_BRAIN_PROVIDER="anthropic")
    with pytest.raises(ValueError, match="API key is unset"):
        lp.resolve_provider(lp.BRAIN)


def test_tier_pin_to_an_unknown_provider_is_rejected(env):
    env(NVIDIA_NIM_API_KEY="nv", LLM_BRAIN_PROVIDER="hal9000")
    with pytest.raises(ValueError, match="not a known provider"):
        lp.resolve_provider(lp.BRAIN)


def test_unknown_tier_is_rejected(env):
    env(NVIDIA_NIM_API_KEY="nv")
    with pytest.raises(ValueError, match="Unknown tier"):
        lp.get_llm("supervisor")


def test_describe_providers_reports_state_without_leaking_keys(env):
    env(NVIDIA_NIM_API_KEY="super-secret", GOOGLE_API_KEY="also-secret",
        LLM_PROVIDER_ORDER="nvidia,google")

    described = lp.describe_providers()
    assert described["configured"] == ["google", "nvidia"]
    assert "anthropic" in described["unconfigured"]
    assert described["tiers"][lp.BRAIN]["provider"] == "nvidia"
    assert described["tiers"][lp.BRAIN]["model"] == "deepseek-ai/deepseek-v4-flash"

    blob = repr(described)
    assert "super-secret" not in blob
    assert "also-secret" not in blob


def test_describe_providers_reports_the_error_instead_of_raising(env):
    described = lp.describe_providers()
    assert described["configured"] == []
    assert "No LLM provider is configured" in described["tiers"][lp.BRAIN]["error"]


def test_model_overrides_apply_to_whichever_provider_serves_the_tier(env):
    env(NVIDIA_NIM_API_KEY="nv", LLM_BRAIN_MODEL="meta/llama-3.3-70b-instruct")
    described = lp.describe_providers()
    assert described["tiers"][lp.BRAIN]["model"] == "meta/llama-3.3-70b-instruct"
    # Untouched tiers keep the provider default.
    assert described["tiers"][lp.WORKER]["model"] == "deepseek-ai/deepseek-v4-flash"


def test_provider_model_env_overrides_the_built_in_default(env):
    env(NVIDIA_NIM_API_KEY="nv", NVIDIA_NIM_MODEL="deepseek-ai/deepseek-v4-pro")
    assert lp.resolve_provider(lp.BRAIN).models[lp.BRAIN] == "deepseek-ai/deepseek-v4-pro"


def test_every_tier_has_generation_settings():
    """Assert the invariant, not the literal list, so adding a tier stays cheap."""
    assert set(lp.TIER_SETTINGS) == set(lp.ALL_TIERS)
    assert lp.TIER_SETTINGS[lp.BRAIN]["temperature"] < lp.TIER_SETTINGS[lp.AD_COPY]["temperature"]


def test_every_provider_serves_every_tier(env):
    """A tier missing from a provider's model map is a KeyError at request time."""
    env(ANTHROPIC_API_KEY="a", GOOGLE_API_KEY="g", OPENAI_API_KEY="o",
        NVIDIA_NIM_API_KEY="n", OPENROUTER_API_KEY="r", BONSAI_API_KEY="b")
    for name, spec in lp._provider_specs().items():
        assert set(spec.models) == set(lp.ALL_TIERS), f"{name} is missing a tier"


def test_lite_tier_is_cheaper_and_tighter_than_worker(env):
    """The point of the lite tier: a smaller ceiling, and a distinct model on Anthropic."""
    env(ANTHROPIC_API_KEY="a")
    assert lp.TIER_SETTINGS[lp.LITE]["max_tokens"] < lp.TIER_SETTINGS[lp.WORKER]["max_tokens"]
    spec = lp.resolve_provider(lp.LITE)
    assert spec.models[lp.LITE] != spec.models[lp.WORKER]


def test_lite_tier_can_be_pinned_independently(env):
    env(ANTHROPIC_API_KEY="a", NVIDIA_NIM_API_KEY="nv", LLM_LITE_PROVIDER="nvidia")
    assert lp.resolve_provider(lp.LITE).name == "nvidia"
    assert lp.resolve_provider(lp.WORKER).name == "anthropic"


def test_no_retired_anthropic_models_are_pinned(env):
    """claude-3-5-haiku-20241022 retired 2026-02-19 and 404s; guard against regression."""
    retired = {"claude-3-5-haiku-20241022", "claude-sonnet-4-20250514"}
    assert not (set(lp._provider_specs()["anthropic"].models.values()) & retired)


def test_default_order_covers_every_known_provider(env):
    """A provider missing from the order could never be selected automatically."""
    assert set(lp.DEFAULT_PROVIDER_ORDER) == set(lp._provider_specs())


# --- runtime fallback chain ---


def test_chain_lists_every_configured_provider_in_order(env):
    env(NVIDIA_NIM_API_KEY="nv", GOOGLE_API_KEY="g", ANTHROPIC_API_KEY="an",
        LLM_PROVIDER_ORDER="nvidia,google,anthropic")
    chain = [s.name for s in lp.resolution_chain(lp.BRAIN)]
    assert chain == ["nvidia", "google", "anthropic"]


def test_pinned_tier_has_no_fallbacks(env):
    """Pinning means 'use exactly this', so it must not silently fail over."""
    env(NVIDIA_NIM_API_KEY="nv", GOOGLE_API_KEY="g", LLM_BRAIN_PROVIDER="nvidia")
    assert [s.name for s in lp.resolution_chain(lp.BRAIN)] == ["nvidia"]
    assert lp.describe_providers()["tiers"][lp.BRAIN]["fallbacks"] == []


def test_tier_model_override_does_not_leak_onto_fallbacks(env):
    """An NVIDIA model id sent to Gemini would guarantee the fallback fails."""
    env(NVIDIA_NIM_API_KEY="nv", GOOGLE_API_KEY="g",
        LLM_PROVIDER_ORDER="nvidia,google",
        LLM_BRAIN_MODEL="meta/llama-3.3-70b-instruct")

    brain = lp.describe_providers()["tiers"][lp.BRAIN]
    assert brain["model"] == "meta/llama-3.3-70b-instruct"
    assert brain["fallbacks"] == [{"provider": "google", "model": "gemini-2.5-flash"}]


def test_single_provider_returns_a_bare_client_not_a_fallback_wrapper(env):
    env(NVIDIA_NIM_API_KEY="nv")
    assert not hasattr(lp.get_llm(lp.BRAIN), "fallbacks")


def test_multiple_providers_produce_a_fallback_wrapper(env):
    env(NVIDIA_NIM_API_KEY="nv", GOOGLE_API_KEY="g", LLM_PROVIDER_ORDER="nvidia,google")
    llm = lp.get_llm(lp.BRAIN)
    assert len(llm.fallbacks) == 1


def test_worker_tier_temperature_argument_is_honoured(env):
    env(NVIDIA_NIM_API_KEY="nv")
    assert lp.get_worker_llm(temperature=0.1).temperature == 0.1
