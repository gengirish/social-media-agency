"""Media moderation at generation time — product rule 3 for images and video.

The verdict is written when the asset is created; the approve path only looks
for its presence (:func:`media_moderation.verdict_missing`). So two properties
matter more than the wording of any issue:

- an asset that was screened must never produce an empty ``moderation`` dict,
  which the gate would read as "not yet screened" and refuse forever;
- the module must never raise, and ``unavailable`` must mean genuinely
  unavailable — an LLM failure, a missing provider and a video all come back
  ``unavailable`` with a ``media_moderation_unavailable`` log, while a clean
  rung 1 is a real ``passed`` carrying ``reason == "provider_only"``.

The brain-tier LLM is replaced by a recording stub; no test touches a real
provider.
"""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from structlog.testing import capture_logs

from agency.services import media_moderation
from agency.services.media_moderation import moderate_media, verdict_missing

CLEAN = '{"issues": []}'
FLAGGED = (
    '{"issues": [{"severity": "high", "message": "The price panel reads $19 but is cut off."}]}'
)

#: A prompt that asks for rendered words, so the text heuristic escalates.
TEXT_PROMPT = {"prompt": 'launch poster with the headline "Ship it today"'}
#: A prompt with no text intent at all.
PLAIN_PROMPT = {"prompt": "a photo of a ceramic coffee cup on a wooden desk, soft light"}


class StubVisionLLM:
    """Stands in for the brain-tier vision model; records calls, optionally fails."""

    def __init__(self, reply: str = CLEAN, *, error: Exception | None = None, delay: float = 0):
        self.reply = reply
        self.error = error
        self.delay = delay
        self.calls: list[Any] = []
        self.configs: list[Any] = []

    async def ainvoke(self, messages: Any, config: Any = None) -> SimpleNamespace:
        self.calls.append(messages)
        self.configs.append(config)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return SimpleNamespace(content=self.reply)


@pytest.fixture
def vision(monkeypatch):
    """Install a brain-tier stub; returns the installer."""

    def _install(reply: str = CLEAN, **kwargs: Any) -> StubVisionLLM:
        stub = StubVisionLLM(reply, **kwargs)
        monkeypatch.setattr("agency.services.llm_provider.get_brain_llm", lambda *a, **k: stub)
        return stub

    return _install


# --- the happy path: escalated, looked at, nothing wrong -------------------


async def test_clean_image_passes_after_vision_check(vision):
    stub = vision(CLEAN)
    result = await moderate_media(
        kind="image",
        image_url="https://cdn.example.com/a.png",
        provider_flags={"has_nsfw_concepts": [False], **TEXT_PROMPT},
        brand_context={"brand_name": "Acme", "vocabulary_exclude": ["cheap"]},
    )
    assert result.status == "passed"
    assert result.vision_checked is True
    assert result.issues == []
    assert result.reason == "vision"
    assert len(stub.calls) == 1  # the vision check actually ran
    # Multimodal shape: the prompt and the image travel in one user message.
    content = stub.calls[0][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["image_url"]["url"] == "https://cdn.example.com/a.png"
    # trace_config is attached per call; it is {} when Langfuse is off.
    assert isinstance(stub.configs[0], dict)


async def test_vision_issues_are_reported_with_severity(vision):
    vision(FLAGGED)
    result = await moderate_media(
        kind="image", image_url="https://cdn.example.com/a.png", provider_flags=TEXT_PROMPT
    )
    assert result.status == "flagged"
    assert result.vision_checked is True
    assert result.issues[0]["severity"] == "high"
    assert "price" in result.issues[0]["message"]


# --- rung 1: the provider's free signal ------------------------------------


async def test_provider_nsfw_flag_flags_the_asset(vision):
    """The free signal alone is enough to flag, whatever the vision rung says."""
    vision(CLEAN)
    result = await moderate_media(
        kind="image",
        image_url="https://cdn.example.com/a.png",
        provider_flags={"has_nsfw_concepts": [True]},
    )
    assert result.status == "flagged"
    assert result.issues
    assert result.issues[0]["severity"] == "high"
    assert "has_nsfw_concepts" in result.issues[0]["message"]
    assert result.reason == "vision"  # escalated and the model answered


async def test_provider_nsfw_flag_survives_an_llm_outage(vision):
    """Flagged by the provider, with no provider for the escalation: still flagged."""
    vision(error=RuntimeError("no provider configured"))
    result = await moderate_media(
        kind="image",
        image_url="https://cdn.example.com/a.png",
        provider_flags={"has_nsfw_concepts": True},
    )
    assert result.status == "flagged"
    assert result.vision_checked is False
    assert len(result.issues) == 1
    assert result.reason == "llm_error"  # flagged, but say why the rung 2 verdict is missing


async def test_no_vision_call_when_signal_clean_and_no_text(vision):
    """The §1E latency argument only holds if the common case makes no model call."""
    stub = vision(CLEAN)
    result = await moderate_media(
        kind="image",
        image_url="https://cdn.example.com/a.png",
        provider_flags={"has_nsfw_concepts": [False], **PLAIN_PROMPT},
    )
    assert stub.calls == []
    assert result.status == "passed"
    assert result.vision_checked is False


async def test_rung_one_clean_is_a_verdict_not_an_outage(vision):
    """A clean provider signal screens the image; the row says which rung did it.

    ``unavailable`` is reserved for genuine unavailability, so the modal
    image — clean signal, no text — must not land there, or every asset would
    carry an outage badge.
    """
    stub = vision(CLEAN)
    with capture_logs() as logs:
        result = await moderate_media(
            kind="image",
            image_url="https://cdn.example.com/a.png",
            provider_flags={"has_nsfw_concepts": [False], **PLAIN_PROMPT},
        )
    assert result.status == "passed"
    assert result.vision_checked is False
    assert result.reason == "provider_only"
    assert result.issues == []
    assert stub.calls == []
    # Nothing was unavailable, so nothing is logged as such.
    assert not [e for e in logs if e["event"] == "media_moderation_unavailable"]


async def test_explicit_text_flag_escalates_without_the_heuristic(vision):
    stub = vision(CLEAN)
    result = await moderate_media(
        kind="image",
        image_url="https://cdn.example.com/a.png",
        provider_flags={"has_text": True, **PLAIN_PROMPT},
    )
    assert len(stub.calls) == 1
    assert result.status == "passed"
    assert result.vision_checked is True
    assert result.reason == "vision"


def test_text_heuristic_catches_the_risky_prompts():
    carries = media_moderation.image_carries_text
    for prompt in (
        'a banner that says "50% off"',
        "poster with a headline and a price of $19",
        "product shot with the company logo",
        "an infographic of quarterly growth",
        "bold typography over a gradient",
    ):
        assert carries({"prompt": prompt}) is True, prompt
    for prompt in (
        "a ceramic mug on a desk, soft morning light",
        "an abstract gradient background, no people",
        "",
    ):
        assert carries({"prompt": prompt}) is False, prompt
    assert carries(None) is False


# --- fail open, visibly ----------------------------------------------------


async def test_llm_error_is_unavailable_and_logged(vision):
    vision(error=RuntimeError("502 from gateway"))
    with capture_logs() as logs:
        result = await moderate_media(
            kind="image", image_url="https://cdn.example.com/a.png", provider_flags=TEXT_PROMPT
        )
    assert result.status == "unavailable"
    assert result.vision_checked is False
    assert result.issues == []
    assert any(
        e["event"] == "media_moderation_unavailable" and e.get("reason") == "llm_error"
        for e in logs
    )
    assert result.reason == "llm_error"


async def test_timeout_is_unavailable_and_logged(vision, monkeypatch):
    monkeypatch.setattr(media_moderation, "VISION_TIMEOUT_SECONDS", 0.01)
    vision(CLEAN, delay=0.5)
    with capture_logs() as logs:
        result = await moderate_media(
            kind="image", image_url="https://cdn.example.com/a.png", provider_flags=TEXT_PROMPT
        )
    assert result.status == "unavailable"
    assert result.vision_checked is False
    assert any(
        e["event"] == "media_moderation_unavailable" and e.get("reason") == "timeout"
        for e in logs
    )
    assert result.reason == "timeout"


async def test_unparseable_response_is_unavailable_and_logged(vision):
    vision("I had a look and it seems fine to me.")
    with capture_logs() as logs:
        result = await moderate_media(
            kind="image", image_url="https://cdn.example.com/a.png", provider_flags=TEXT_PROMPT
        )
    assert result.status == "unavailable"
    assert result.vision_checked is False
    assert any(
        e["event"] == "media_moderation_unavailable"
        and e.get("reason") == "unparseable_response"
        for e in logs
    )
    assert result.reason == "unparseable_response"


async def test_missing_provider_never_raises(monkeypatch):
    def _boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("No LLM provider configured; set ANTHROPIC_API_KEY")

    monkeypatch.setattr("agency.services.llm_provider.get_brain_llm", _boom)
    result = await moderate_media(
        kind="image", image_url="https://cdn.example.com/a.png", provider_flags=TEXT_PROMPT
    )
    assert result.status == "unavailable"
    assert result.reason == "llm_error"


# --- video: an honest unknown ----------------------------------------------


async def test_video_is_unavailable_never_passed(vision):
    stub = vision(CLEAN)
    with capture_logs() as logs:
        result = await moderate_media(kind="video", image_url="https://cdn.example.com/a.mp4")
    assert result.status == "unavailable"
    assert result.status != "passed"
    assert result.vision_checked is False
    assert stub.calls == []  # no frame sampling, so nothing to look at
    assert any(
        e["event"] == "media_moderation_unavailable" and e.get("reason") == "video_unsupported"
        for e in logs
    )
    assert result.reason == "video_unsupported"


async def test_missing_image_url_is_unavailable_and_logged(vision):
    vision(CLEAN)
    with capture_logs() as logs:
        result = await moderate_media(kind="image", image_url="", provider_flags=TEXT_PROMPT)
    assert result.status == "unavailable"
    assert any(
        e["event"] == "media_moderation_unavailable"
        and e.get("reason") == "missing_image_url"
        for e in logs
    )
    assert result.reason == "missing_image_url"


# --- the property the approve gate depends on ------------------------------


def test_verdict_missing_reads_an_empty_dict_as_unscreened():
    assert verdict_missing({}) is True
    assert verdict_missing(None) is True
    assert verdict_missing({"issues": []}) is True  # no status = never screened


@pytest.mark.parametrize(
    "kind,flags,expected_status,expected_reason",
    [
        # no vision call
        ("image", {"has_nsfw_concepts": [False], **PLAIN_PROMPT}, "passed", "provider_only"),
        # flagged by the provider, then escalated
        ("image", {"has_nsfw_concepts": [True]}, "flagged", "vision"),
        # escalated on rendered text and passed
        ("image", TEXT_PROMPT, "passed", "vision"),
        # not screenable at all
        ("video", None, "unavailable", "video_unsupported"),
    ],
)
async def test_every_screened_asset_is_approvable(
    vision, kind, flags, expected_status, expected_reason
):
    """``as_metadata()`` must never be empty, or the gate refuses forever.

    It also has to carry ``reason``, so the UI can tell a deliberate skip from
    an outage without reading logs.
    """
    vision(CLEAN)
    result = await moderate_media(
        kind=kind, image_url="https://cdn.example.com/a.png", provider_flags=flags
    )
    metadata = result.as_metadata()
    assert metadata != {}
    assert metadata["status"] == expected_status
    assert metadata["reason"] == expected_reason
    assert verdict_missing(metadata) is False
