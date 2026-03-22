"""LLM provider abstraction with Brain/Worker model routing.

Brain models (Orchestrator, QA): Claude Sonnet 4 — high reasoning
Worker models (Strategy, SEO, Content, Ad Copy): Gemini 2.0 Flash — fast & cheap
"""

from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from agency.config import get_settings

# Model tier constants
BRAIN_MODEL = "claude-sonnet-4-20250514"
WORKER_MODEL = "gemini-2.0-flash"
AD_COPY_MODEL = "claude-3-5-haiku-20241022"


def get_brain_llm():
    """High-reasoning model for Orchestrator and QA agents."""
    settings = get_settings()
    if settings.anthropic_api_key:
        return ChatAnthropic(
            model=BRAIN_MODEL,
            api_key=settings.anthropic_api_key,
            temperature=0.3,
            max_tokens=4096,
        )
    return _get_fallback_llm(temperature=0.3)


def get_worker_llm(temperature: float = 0.7):
    """Fast/cheap model for Strategy, SEO, Content agents."""
    settings = get_settings()
    if settings.google_api_key:
        return ChatGoogleGenerativeAI(
            model=WORKER_MODEL,
            google_api_key=settings.google_api_key,
            temperature=temperature,
            max_output_tokens=4096,
        )
    return _get_fallback_llm(temperature=temperature)


def get_ad_copy_llm():
    """Cost-effective model optimized for ad copy variants."""
    settings = get_settings()
    if settings.anthropic_api_key:
        return ChatAnthropic(
            model=AD_COPY_MODEL,
            api_key=settings.anthropic_api_key,
            temperature=0.8,
            max_tokens=2048,
        )
    return _get_fallback_llm(temperature=0.8)


def _get_fallback_llm(temperature: float = 0.7):
    """OpenAI fallback when primary providers are unavailable."""
    settings = get_settings()
    return ChatOpenAI(
        model="gpt-4o-mini",
        api_key=settings.openai_api_key,
        temperature=temperature,
        max_tokens=4096,
    )
