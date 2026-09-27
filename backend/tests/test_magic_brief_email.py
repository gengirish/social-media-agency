"""Contact-email extraction for the New Client website read."""

import httpx
import pytest

from agency.services import magic_brief
from agency.services.magic_brief import _email_from_contact_pages, find_contact_email


def test_prefers_mailto_over_body_text():
    html = """
      <p>Reach a human at sales@acme.com</p>
      <a href="mailto:hello@acme.com">Email us</a>
    """
    assert find_contact_email(html) == "hello@acme.com"


def test_prefers_a_role_inbox_over_a_personal_one():
    html = '<a href="mailto:dave.smith@acme.com">Dave</a><a href="mailto:contact@acme.com">Us</a>'
    assert find_contact_email(html) == "contact@acme.com"


def test_reads_plain_text_when_there_is_no_mailto():
    assert find_contact_email("<p>Questions? info@acme.com</p>") == "info@acme.com"


def test_normalises_entities_encoding_and_subject_params():
    html = '<a href="mailto:Hello%40Acme.com?subject=Hi&amp;body=x">mail</a>'
    assert find_contact_email(html) == "hello@acme.com"


@pytest.mark.parametrize(
    "html",
    [
        '<img src="logo@2x.png">',
        "<p>no-reply@acme.com</p>",
        "<p>you@example.com</p>",
        "<p>hello@yourdomain.com</p>",
        "<p>no address here at all</p>",
    ],
)
def test_rejects_non_contact_addresses(html):
    assert find_contact_email(html) is None


async def test_contact_pages_fallback_tries_the_usual_paths(monkeypatch):
    seen: list[str] = []

    async def fake_fetch(url: str, client):
        seen.append(url)
        if url.endswith("/contact-us"):
            return '<a href="mailto:hi@acme.com">Say hi</a>'
        raise httpx.HTTPError("404")

    monkeypatch.setattr(magic_brief, "fetch_public_page", fake_fetch)
    email = await _email_from_contact_pages("https://acme.com/", object())

    assert email == "hi@acme.com"
    assert seen == ["https://acme.com/contact", "https://acme.com/contact-us"]
