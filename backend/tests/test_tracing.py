"""Langfuse tracing: off by default, and a campaign's runs share one trace."""

from types import SimpleNamespace

import pytest

from agency.services import tracing


@pytest.fixture
def langfuse_on(monkeypatch):
    """Tracing enabled with a stand-in client, so nothing is exported."""
    settings = SimpleNamespace(langfuse_public_key="pk-lf-test", langfuse_secret_key="sk-lf-test")
    monkeypatch.setattr(tracing, "get_settings", lambda: settings)
    monkeypatch.setattr(tracing, "_client", object())


def test_disabled_without_keys_returns_empty_config(monkeypatch):
    monkeypatch.setattr(tracing, "_client", None)
    assert tracing.trace_config("repurpose", org_id="org-1") == {}


def test_init_is_a_noop_without_keys(monkeypatch):
    settings = SimpleNamespace(langfuse_public_key="", langfuse_secret_key="")
    monkeypatch.setattr(tracing, "get_settings", lambda: settings)
    monkeypatch.setattr(tracing, "_client", None)
    tracing.init_langfuse()
    assert tracing._client is None


def test_one_key_alone_does_not_enable(monkeypatch):
    settings = SimpleNamespace(langfuse_public_key="pk-lf-test", langfuse_secret_key="")
    monkeypatch.setattr(tracing, "get_settings", lambda: settings)
    assert tracing.langfuse_enabled() is False


def test_enabled_config_carries_handler_and_trace_attributes(langfuse_on):
    from langfuse.langchain import CallbackHandler

    cfg = tracing.trace_config(
        "repurpose", org_id="org-1", user_id="user-1", session_id="camp-1", tags=["x"]
    )

    assert cfg["run_name"] == "repurpose"
    assert len(cfg["callbacks"]) == 1
    assert isinstance(cfg["callbacks"][0], CallbackHandler)
    meta = cfg["metadata"]
    assert meta["org_id"] == "org-1"
    assert meta["langfuse_user_id"] == "user-1"
    assert meta["langfuse_session_id"] == "camp-1"
    assert set(meta["langfuse_tags"]) == {"x", "org:org-1"}


def test_uuid_ids_are_stringified(langfuse_on):
    """The handler drops non-string trace attributes silently."""
    from uuid import uuid4

    org = uuid4()
    meta = tracing.trace_config("ab-variants", org_id=org, user_id=org)["metadata"]
    assert meta["org_id"] == str(org)
    assert meta["langfuse_user_id"] == str(org)


def test_each_run_gets_its_own_handler(langfuse_on):
    """Handlers hold per-run state; a shared one would interleave campaigns."""
    a = tracing.trace_config("x")["callbacks"][0]
    b = tracing.trace_config("x")["callbacks"][0]
    assert a is not b


def test_start_and_resume_of_a_campaign_share_a_trace_id(langfuse_on):
    """The resume after human review runs in a later request, possibly after a
    restart — only a seeded id can put both halves in the same trace."""
    start = tracing.trace_config("campaign-pipeline:start", trace_seed="campaign:abc")
    resume = tracing.trace_config("campaign-pipeline:resume", trace_seed="campaign:abc")
    other = tracing.trace_config("campaign-pipeline:start", trace_seed="campaign:xyz")

    start_id = start["callbacks"][0]._trace_context["trace_id"]
    assert start_id == resume["callbacks"][0]._trace_context["trace_id"]
    assert start_id != other["callbacks"][0]._trace_context["trace_id"]
    assert len(start_id) == 32


def test_merge_keeps_checkpointer_thread_id():
    base = {"configurable": {"thread_id": "camp-1"}, "metadata": {"a": 1}}
    merged = tracing.merge_config(base, {"callbacks": ["h"], "metadata": {"b": 2}})

    assert merged["configurable"] == {"thread_id": "camp-1"}
    assert merged["metadata"] == {"a": 1, "b": 2}
    assert merged["callbacks"] == ["h"]
    assert "callbacks" not in base


def test_merge_with_tracing_off_returns_base_unchanged():
    base = {"configurable": {"thread_id": "camp-1"}}
    assert tracing.merge_config(base, {}) is base


# --- Masking ---


@pytest.fixture
def mask_mode(monkeypatch):
    def set_mode(mode):
        monkeypatch.setattr(tracing, "_mask_mode", mode)

    return set_mode


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Contact jane.doe+ops@acme.co.uk today", "Contact [email] today"),
        ("Call +1 (415) 555-0132 now", "Call [phone] now"),
        ("Card 4242 4242 4242 4242 on file", "Card [card] on file"),
        ("key sk-ant-api03-AbCdEfGhIjKlMnOp here", "key [secret] here"),
        ("Authorization: Bearer abcdefghijklmnopqrstuvwxyz123", "Authorization: [secret]"),
        ("from 192.168.10.4", "from [ip]"),
    ],
)
def test_pii_patterns_are_masked(text, expected):
    assert tracing.mask_pii(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Launch on 2026-09-21 with a $50,000 budget",  # date: 8 digits, not a phone
        "Target 12% CTR across 3 channels in Q4",
        "Visit https://acme.com/pricing",  # brand URLs are not PII
    ],
)
def test_pii_mode_leaves_ordinary_campaign_text_alone(text):
    assert tracing.mask_pii(text) == text


def test_luhn_failure_is_not_labelled_a_card():
    """A 13-digit order number is not a card. It may still be masked as a
    phone — masking errs toward over-redaction — but never as [card]."""
    assert "[card]" not in tracing.mask_pii("Order 1234567890123")


def test_pii_mode_walks_langchain_message_structure(mask_mode):
    mask_mode("pii")
    data = [{"role": "user", "content": "Brief from ceo@acme.com"}, {"role": "assistant"}]
    assert tracing.mask_trace_data(data=data) == [
        {"role": "user", "content": "Brief from [email]"},
        {"role": "assistant"},
    ]


def test_full_mode_redacts_content_but_keeps_lookup_ids(mask_mode):
    mask_mode("full")
    data = {
        "org_id": "org-1",
        "campaign_id": "camp-1",
        "langgraph_node": "create_content",
        "ls_model_name": "claude-sonnet-5",
        "brand_context": {"company": "Acme", "voice": "bold"},
        "messages": [{"role": "user", "content": "Acme's secret launch"}],
        "retry_count": 2,
    }
    out = tracing.mask_trace_data(data=data)

    assert out["org_id"] == "org-1"
    assert out["campaign_id"] == "camp-1"
    assert out["langgraph_node"] == "create_content"
    assert out["ls_model_name"] == "claude-sonnet-5"
    assert out["brand_context"] == {"company": "[redacted 4 chars]", "voice": "[redacted 4 chars]"}
    assert out["messages"] == [{"role": "user", "content": "[redacted 20 chars]"}]
    assert out["retry_count"] == 2
    assert "Acme" not in repr(out)


def test_full_mode_redacts_a_bare_prompt_string(mask_mode):
    mask_mode("full")
    assert tracing.mask_trace_data(data="Acme brief") == "[redacted 10 chars]"


def test_off_mode_passes_data_through(mask_mode):
    mask_mode("off")
    data = {"content": "ceo@acme.com"}
    assert tracing.mask_trace_data(data=data) is data


def test_unknown_mask_mode_fails_safe_to_full():
    """A typo in LANGFUSE_MASK_MODE must not turn masking off."""
    assert tracing._resolve_mask_mode("pi") == "full"
    assert tracing._resolve_mask_mode("") == "full"
    assert tracing._resolve_mask_mode(" PII ") == "pii"


async def test_shutdown_is_bounded_when_langfuse_hangs(monkeypatch):
    """An unreachable Langfuse must not stall app shutdown."""
    import threading
    import time

    release = threading.Event()

    class HangingClient:
        def shutdown(self):
            release.wait(10)

    monkeypatch.setattr(tracing, "_client", HangingClient())
    start = time.monotonic()
    await tracing.shutdown_langfuse(timeout=0.2)
    release.set()

    assert time.monotonic() - start < 2
    assert tracing._client is None
