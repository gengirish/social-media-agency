"""Settings › Branding — the uploaded logo, and where it ends up.

The logo goes on two things a client sees: the campaign pack (one self-contained
HTML file, so it must travel inside as a ``data:`` URI) and the public review
page. These tests follow it from upload to both, and check the refusals that
keep the row small and the bytes honest: the MIME comes from the file, not the
client's claim; SVG is out; a member cannot change what the agency's clients see.
"""

import io
from uuid import UUID

import pytest
from PIL import Image

from tests.conftest import (
    auth_for,
    create_campaign_row,
    create_client_row,
    create_org,
    create_white_label,
)

API = "/api/v1"
WL = f"{API}/integrations/white-label"


def _png(width: int = 64, height: int = 32) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (width, height), (31, 58, 95, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _image(fmt: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), (200, 120, 0)).save(buf, format=fmt)
    return buf.getvalue()


def _upload(payload: bytes, *, name: str = "logo.png", declared: str = "image/png") -> dict:
    return {"file": (name, payload, declared)}


@pytest.fixture
async def agency(session_factory):
    org_id = await create_org(session_factory, "Northwind Social")
    client_id = await create_client_row(session_factory, org_id, "Sunrise Coffee")
    campaign_id = await create_campaign_row(
        session_factory, org_id, client_id, "Cold Brew Launch", channels=["linkedin"]
    )
    owner = await auth_for(session_factory, org_id, role="owner")
    return org_id, client_id, campaign_id, owner


# ---------------------------------------------------------------------------
# Upload, read back, remove
# ---------------------------------------------------------------------------
async def test_upload_stores_logo_and_returns_data_url(client, agency):
    org_id, _, _, owner = agency
    resp = await client.post(f"{WL}/logo", files=_upload(_png()), headers=owner)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_logo"] is True
    assert body["logo_mime"] == "image/png"
    assert body["logo_bytes"] == len(_png())
    assert body["logo_data_url"].startswith("data:image/png;base64,")
    # A first upload is a wish to be seen: the row it created is switched on.
    assert body["is_active"] is True

    again = (await client.get(WL, headers=owner)).json()
    assert again["logo_data_url"] == body["logo_data_url"]


async def test_mime_comes_from_the_bytes_not_the_claim(client, agency):
    _, _, _, owner = agency
    resp = await client.post(
        f"{WL}/logo",
        files=_upload(_image("WEBP"), name="logo.png", declared="image/png"),
        headers=owner,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["logo_mime"] == "image/webp"
    assert resp.json()["logo_data_url"].startswith("data:image/webp;base64,")


async def test_upload_keeps_an_existing_rows_switch(client, session_factory, agency):
    org_id, _, _, owner = agency
    await create_white_label(session_factory, org_id, is_active=False, company_name="Off Co")
    resp = await client.post(f"{WL}/logo", files=_upload(_png()), headers=owner)
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False
    assert resp.json()["company_name"] == "Off Co"


async def test_remove_logo_keeps_the_rest(client, agency):
    _, _, _, owner = agency
    await client.post(f"{WL}/logo", files=_upload(_png()), headers=owner)
    saved = await client.put(WL, json={"company_name": "Northwind"}, headers=owner)
    assert saved.status_code == 200, saved.text

    resp = await client.delete(f"{WL}/logo", headers=owner)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_logo"] is False
    assert body["logo_data_url"] is None
    assert body["logo_bytes"] is None
    assert body["company_name"] == "Northwind"


async def test_remove_logo_without_a_row_is_a_no_op(client, agency):
    _, _, _, owner = agency
    resp = await client.delete(f"{WL}/logo", headers=owner)
    assert resp.status_code == 200
    assert resp.json() == {"is_active": False}


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------
async def test_rejects_oversized_upload(client, agency):
    _, _, _, owner = agency
    from agency.services.white_label import LOGO_MAX_BYTES

    resp = await client.post(
        f"{WL}/logo", files=_upload(b"\x89PNG" + b"0" * LOGO_MAX_BYTES), headers=owner
    )
    assert resp.status_code == 413
    assert resp.json()["detail"]["code"] == "logo_too_large"
    assert (await client.get(WL, headers=owner)).json() == {"is_active": False}


@pytest.mark.parametrize(
    "payload, name",
    [
        (b"not an image at all", "logo.png"),
        (b"", "empty.png"),
        (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "logo.svg"),
    ],
)
async def test_rejects_non_images_and_svg(client, agency, payload, name):
    _, _, _, owner = agency
    resp = await client.post(f"{WL}/logo", files=_upload(payload, name=name), headers=owner)
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] in {"logo_unsupported", "logo_empty"}


async def test_rejects_gif(client, agency):
    _, _, _, owner = agency
    files = _upload(_image("GIF"), name="logo.gif", declared="image/gif")
    resp = await client.post(f"{WL}/logo", files=files, headers=owner)
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "logo_unsupported"


async def test_rejects_oversized_pixels(client, agency):
    _, _, _, owner = agency
    resp = await client.post(f"{WL}/logo", files=_upload(_png(2001, 10)), headers=owner)
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "logo_dimensions"


async def test_put_validates_colour_email_and_logo_link(client, agency):
    _, _, _, owner = agency
    assert (await client.put(WL, json={"primary_color": "red"}, headers=owner)).status_code == 422
    assert (await client.put(WL, json={"support_email": "nope"}, headers=owner)).status_code == 422
    bad_link = await client.put(WL, json={"logo_url": "javascript:alert(1)"}, headers=owner)
    assert bad_link.status_code == 422
    assert bad_link.json()["detail"]["code"] == "logo_url_unsafe"

    # Blank strings clear a field; the screen sends "" for an emptied input.
    ok = await client.put(
        WL,
        json={"company_name": "  Northwind  ", "primary_color": "", "support_email": ""},
        headers=owner,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["company_name"] == "Northwind"
    assert ok.json()["primary_color"] is None
    assert ok.json()["support_email"] is None


# ---------------------------------------------------------------------------
# Who may change it
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", ["member", "viewer"])
async def test_only_workspace_admins_change_branding(client, session_factory, agency, role):
    org_id, _, _, owner = agency
    seat = await auth_for(session_factory, org_id, role=role)
    assert (await client.post(f"{WL}/logo", files=_upload(_png()), headers=seat)).status_code == 403
    assert (await client.put(WL, json={"company_name": "X"}, headers=seat)).status_code == 403
    assert (await client.delete(f"{WL}/logo", headers=seat)).status_code == 403
    # Reading is fine: the pack and the review page show it to every seat anyway.
    assert (await client.get(WL, headers=seat)).status_code == 200
    assert (await client.get(WL, headers=owner)).json() == {"is_active": False}


async def test_logo_is_org_scoped(client, session_factory, agency):
    org_id, _, _, owner = agency
    await client.post(f"{WL}/logo", files=_upload(_png()), headers=owner)

    other = await create_org(session_factory, "Other Agency")
    other_owner = await auth_for(session_factory, other, role="owner")
    assert (await client.get(WL, headers=other_owner)).json() == {"is_active": False}
    # The other org's delete touches nothing of ours.
    assert (await client.delete(f"{WL}/logo", headers=other_owner)).json() == {"is_active": False}
    assert (await client.get(WL, headers=owner)).json()["has_logo"] is True


# ---------------------------------------------------------------------------
# Where it ends up
# ---------------------------------------------------------------------------
async def test_pack_inlines_the_logo(client, session_factory, agency):
    org_id, _, campaign_id, owner = agency
    await client.post(f"{WL}/logo", files=_upload(_png()), headers=owner)
    await client.put(WL, json={"company_name": "Northwind Social"}, headers=owner)

    viewer = await auth_for(session_factory, org_id, role="viewer")
    pack = (await client.get(f"{API}/campaigns/{campaign_id}/pack", headers=viewer)).json()
    assert pack["agency"]["name"] == "Northwind Social"
    assert pack["agency"]["logo_url"].startswith("data:image/png;base64,")

    html = (await client.get(f"{API}/campaigns/{campaign_id}/pack.html", headers=viewer)).text
    assert '<img class="logo" src="data:image/png;base64,' in html
    assert 'alt="Northwind Social"' in html


async def test_pack_has_no_logo_after_removal(client, session_factory, agency):
    org_id, _, campaign_id, owner = agency
    await client.post(f"{WL}/logo", files=_upload(_png()), headers=owner)
    await client.delete(f"{WL}/logo", headers=owner)
    html = (await client.get(f"{API}/campaigns/{campaign_id}/pack.html", headers=owner)).text
    assert '<img class="logo"' not in html


async def test_inactive_branding_keeps_the_logo_off_the_pack(client, session_factory, agency):
    org_id, _, campaign_id, owner = agency
    await client.post(f"{WL}/logo", files=_upload(_png()), headers=owner)
    await client.put(WL, json={"is_active": False}, headers=owner)
    pack = (await client.get(f"{API}/campaigns/{campaign_id}/pack", headers=owner)).json()
    assert pack["agency"]["logo_url"] is None
    assert pack["agency"]["name"] == "Northwind Social"  # the org name, not the row's


async def test_uploaded_logo_wins_over_logo_url(client, agency):
    _, _, campaign_id, owner = agency
    await client.put(
        WL, json={"logo_url": "https://cdn.example.com/logo.png", "is_active": True}, headers=owner
    )
    before = (await client.get(f"{API}/campaigns/{campaign_id}/pack", headers=owner)).json()
    assert before["agency"]["logo_url"] == "https://cdn.example.com/logo.png"

    await client.post(f"{WL}/logo", files=_upload(_png()), headers=owner)
    after = (await client.get(f"{API}/campaigns/{campaign_id}/pack", headers=owner)).json()
    assert after["agency"]["logo_url"].startswith("data:image/png;base64,")


async def test_review_page_shows_the_logo(client, agency):
    org_id, client_id, _, owner = agency
    await client.post(f"{WL}/logo", files=_upload(_png()), headers=owner)
    link = await client.post(f"{API}/clients/{client_id}/review-links", json={}, headers=owner)
    assert link.status_code == 200, link.text
    token = link.json()["token"]

    page = (await client.get(f"{API}/portal/review/{token}")).json()
    assert page["agency"]["logo_url"].startswith("data:image/png;base64,")
    assert UUID(str(org_id))  # the org id never appears on the public page
    assert str(org_id) not in page["agency"]["logo_url"]
