"""AgentMail transactional email — configuration, sender resolution, failure modes.

None of these tests touch the network. The point is the contract the callers
depend on: ``send_email`` always returns a ``SendResult`` and never raises, and
``sent`` is only ever True when a send actually went through — a team invite
that claims an email went out when it did not is the bug this guards.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agency.config import get_settings
from agency.models.tables import Organization
from agency.services import email_service
from tests.conftest import create_org


@pytest.fixture(autouse=True)
def _clean_email_cache() -> Any:
    """The client and sender inbox are module-level memos; reset around each test."""
    email_service.reset_cache()
    get_settings.cache_clear()
    yield
    email_service.reset_cache()
    get_settings.cache_clear()


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTMAIL_API_KEY", "am_test_key")
    monkeypatch.setenv("AGENTMAIL_FROM_EMAIL", "alerts@intelliforge.tech")
    get_settings.cache_clear()


class _FakeMessages:
    def __init__(self, fail: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail = fail

    async def send(self, inbox_id: str, **kwargs: Any) -> object:
        self.calls.append((inbox_id, kwargs))
        if self.fail is not None:
            raise self.fail
        return object()


class _FakeInboxes:
    def __init__(self, messages: _FakeMessages) -> None:
        self.messages = messages

    async def get(self, inbox_id: str, **_: Any) -> Any:
        return type("Inbox", (), {"inbox_id": inbox_id})()


class _FakeClient:
    def __init__(self, messages: _FakeMessages) -> None:
        self.inboxes = _FakeInboxes(messages)


def _install(monkeypatch: pytest.MonkeyPatch, fail: Exception | None = None) -> _FakeMessages:
    messages = _FakeMessages(fail)
    monkeypatch.setattr(email_service, "_get_client", lambda: _FakeClient(messages))
    return messages


# --- configuration gate ----------------------------------------------------


async def test_send_without_api_key_reports_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTMAIL_API_KEY", "")
    get_settings.cache_clear()

    result = await email_service.send_email(to="a@b.com", subject="s", text="t")

    assert result.sent is False
    assert "AGENTMAIL_API_KEY" in result.reason
    assert email_service.is_configured() is False


async def test_send_returns_false_when_no_sender_inbox(
    monkeypatch: pytest.MonkeyPatch, configured: None
) -> None:
    """An unverified domain leaves us with no inbox — that must not read as sent."""
    _install(monkeypatch)
    monkeypatch.setattr(email_service, "ensure_sender_inbox", _none)

    result = await email_service.send_email(to="a@b.com", subject="s", text="t")

    assert result.sent is False
    assert "sender inbox" in result.reason


async def _none() -> None:
    return None


# --- address parsing -------------------------------------------------------


def test_split_address_uses_domain_from_email(configured: None) -> None:
    assert email_service._split_address("alerts@intelliforge.tech") == (
        "alerts",
        "intelliforge.tech",
    )


def test_split_address_falls_back_to_default_domain(
    monkeypatch: pytest.MonkeyPatch, configured: None
) -> None:
    monkeypatch.setenv("AGENTMAIL_DEFAULT_DOMAIN", "fallback.example")
    get_settings.cache_clear()

    assert email_service._split_address("alerts") == ("alerts", "fallback.example")


# --- sender resolution -----------------------------------------------------


async def test_org_inbox_overrides_shared_sender(
    monkeypatch: pytest.MonkeyPatch,
    configured: None,
    session_factory: async_sessionmaker[AsyncSession],
    db: AsyncSession,
) -> None:
    _install(monkeypatch)
    org_id = await create_org(session_factory, "Inbox Org")
    await db.execute(
        update(Organization)
        .where(Organization.id == org_id)
        .values(agentmail_inbox_id="org-own@intelliforge.tech")
    )
    await db.commit()

    sender = await email_service.resolve_sender(db, org_id)

    assert sender == "org-own@intelliforge.tech"


async def test_org_without_inbox_falls_back_to_shared_sender(
    monkeypatch: pytest.MonkeyPatch,
    configured: None,
    session_factory: async_sessionmaker[AsyncSession],
    db: AsyncSession,
) -> None:
    _install(monkeypatch)
    org_id = await create_org(session_factory, "Bare Org")

    sender = await email_service.resolve_sender(db, org_id)

    assert sender == "alerts@intelliforge.tech"


async def test_unknown_org_falls_back_to_shared_sender(
    monkeypatch: pytest.MonkeyPatch, configured: None, db: AsyncSession
) -> None:
    _install(monkeypatch)

    sender = await email_service.resolve_sender(db, uuid4())

    assert sender == "alerts@intelliforge.tech"


# --- send payload and failure handling -------------------------------------


async def test_send_uses_shared_sender_and_omits_unset_fields(
    monkeypatch: pytest.MonkeyPatch, configured: None
) -> None:
    messages = _install(monkeypatch)

    result = await email_service.send_email(to="a@b.com", subject="Hello", text="Body")

    assert result.sent is True
    assert result.inbox_id == "alerts@intelliforge.tech"
    inbox_id, kwargs = messages.calls[0]
    assert inbox_id == "alerts@intelliforge.tech"
    assert kwargs == {"to": "a@b.com", "subject": "Hello", "text": "Body"}
    # Unset optionals must be absent, not None — the SDK treats an explicit
    # None as a value to serialize.
    assert "html" not in kwargs and "labels" not in kwargs and "reply_to" not in kwargs


async def test_send_forwards_html_labels_and_reply_to(
    monkeypatch: pytest.MonkeyPatch, configured: None
) -> None:
    messages = _install(monkeypatch)

    await email_service.send_email(
        to=["a@b.com", "c@d.com"],
        subject="Hello",
        text="Body",
        html="<p>Body</p>",
        labels=["team-invite"],
        reply_to="support@intelliforge.tech",
    )

    _, kwargs = messages.calls[0]
    assert kwargs["to"] == ["a@b.com", "c@d.com"]
    assert kwargs["html"] == "<p>Body</p>"
    assert kwargs["labels"] == ["team-invite"]
    assert kwargs["reply_to"] == "support@intelliforge.tech"


async def test_send_failure_is_swallowed_and_reported(
    monkeypatch: pytest.MonkeyPatch, configured: None
) -> None:
    """An AgentMail outage must degrade, not propagate into the caller's request."""
    _install(monkeypatch, fail=RuntimeError("upstream 503"))

    result = await email_service.send_email(to="a@b.com", subject="s", text="t")

    assert result.sent is False
    assert "upstream 503" in result.reason
