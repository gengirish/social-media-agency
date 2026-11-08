"""Agency branding (white-label): the name, logo and colour a client sees.

Where it shows: the client review page (``/review/{token}``) and the campaign
pack. Nothing here re-skins the app itself — there is no custom domain and no
themed dashboard — and Settings › Branding says so.

The logo is stored as bytes in ``white_label.logo_data`` rather than through
``services/media_storage.py``, on purpose:

* the pack is one self-contained HTML file a client opens anywhere, so the logo
  has to travel inside it as a ``data:`` URI, which means reading the bytes back
  on every render rather than linking to a bucket;
* the review page is public, and under the ``local`` media driver
  ``/api/v1/media/…`` is authenticated and org-scoped, so a linked logo would be
  a broken image in every environment without R2;
* a logo is small (:data:`LOGO_MAX_BYTES`) and there is one per org.

``logo_url`` (an externally hosted image) is still honoured when nothing has
been uploaded; the upload wins when both exist.
"""

from __future__ import annotations

import base64
import io
import re
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import WhiteLabel
from agency.services.url_safety import UnsafeURLError, assert_safe_link

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

#: Upload cap. A logo is a header mark, not artwork; 512 KB covers a 2000 px
#: PNG with transparency and keeps the pack and the review-page JSON small.
LOGO_MAX_BYTES: Final = 512 * 1024

#: Longest edge accepted. The pack renders it at 40 px high; anything larger is
#: wasted bytes in every document that carries it.
LOGO_MAX_EDGE: Final = 2000

#: Pillow format name → MIME. SVG is deliberately absent: Pillow cannot read it,
#: so its bytes could not be checked, and it would be the one format that can
#: carry script.
LOGO_FORMATS: Final[dict[str, str]] = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}

#: Columns ``PUT /integrations/white-label`` may set. ``logo_data`` and
#: ``logo_mime`` are not here: the logo only changes through the upload route,
#: which validates the bytes.
_SETTABLE: Final = (
    "custom_domain",
    "logo_url",
    "primary_color",
    "company_name",
    "support_email",
    "portal_enabled",
    "email_from_name",
    "is_active",
)


class BrandingError(Exception):
    """A branding refusal. ``detail`` is the structured API error body."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(code)
        self.status_code = status_code
        self.detail = {"code": code, "message": message}


def _data_url(wl: Any) -> str | None:
    """The uploaded logo as a ``data:`` URI, or ``None`` when none is stored."""
    data = wl.logo_data
    if not data:
        return None
    mime = wl.logo_mime or "image/png"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _serialize(wl: Any) -> dict[str, Any]:
    has_logo = bool(wl.logo_data)
    return {
        "id": str(wl.id),
        "custom_domain": wl.custom_domain,
        "logo_url": wl.logo_url,
        "primary_color": wl.primary_color,
        "company_name": wl.company_name,
        "support_email": wl.support_email,
        "portal_enabled": wl.portal_enabled,
        "email_from_name": wl.email_from_name,
        "is_active": wl.is_active,
        "has_logo": has_logo,
        "logo_mime": wl.logo_mime if has_logo else None,
        "logo_bytes": len(wl.logo_data) if has_logo else None,
        "logo_data_url": _data_url(wl),
    }


async def _row(db: AsyncSession, org_id: UUID) -> Any:
    result = await db.execute(select(WhiteLabel).where(WhiteLabel.org_id == org_id))
    return result.scalar_one_or_none()


async def get_white_label(db: AsyncSession, org_id: UUID) -> dict[str, Any] | None:
    wl = await _row(db, org_id)
    return _serialize(wl) if wl else None


async def upsert_white_label(
    db: AsyncSession, org_id: UUID, data: dict[str, Any]
) -> dict[str, Any]:
    """Apply the fields in ``data`` (shape-validated by the router's schema).

    ``logo_url`` is re-checked here as a safe browser link, because a bad one
    would otherwise be stored and then silently dropped by :func:`agency_branding`
    — the person who typed it would never learn why their logo is missing.
    """
    if data.get("logo_url"):
        try:
            data["logo_url"] = assert_safe_link(data["logo_url"])
        except UnsafeURLError as exc:
            raise BrandingError(
                422,
                "logo_url_unsafe",
                f"That logo link cannot be used: {exc}. Upload the file instead.",
            ) from None

    wl = await _row(db, org_id)
    fields = {k: v for k, v in data.items() if k in _SETTABLE}
    if wl:
        for key, value in fields.items():
            setattr(wl, key, value)
    else:
        wl = WhiteLabel(org_id=org_id, **fields)
        db.add(wl)

    await db.commit()
    await db.refresh(wl)
    return _serialize(wl)


def validate_logo(payload: bytes) -> tuple[bytes, str]:
    """Check an upload is a small PNG, JPEG or WebP. Returns ``(bytes, mime)``.

    The MIME comes from the bytes, never from the client's declared type or
    the filename. Only the header is decoded (``size`` and ``verify`` on an
    unloaded image), so an oversized or malformed file costs nothing to refuse.
    """
    if not payload:
        raise BrandingError(422, "logo_empty", "The file is empty.")
    if len(payload) > LOGO_MAX_BYTES:
        raise BrandingError(
            413,
            "logo_too_large",
            f"The logo is {len(payload) // 1024} KB; the limit is {LOGO_MAX_BYTES // 1024} KB. "
            "Export it smaller, or as a PNG with fewer colours.",
        )
    try:
        from PIL import Image

        with Image.open(io.BytesIO(payload)) as img:
            fmt = img.format or ""
            width, height = img.size
            img.verify()
    except Exception:  # noqa: BLE001 - any decode failure means "not an image we take"
        raise BrandingError(
            422,
            "logo_unsupported",
            "That file is not a PNG, JPEG or WebP image.",
        ) from None
    mime = LOGO_FORMATS.get(fmt)
    if mime is None:
        raise BrandingError(
            422,
            "logo_unsupported",
            f"{fmt or 'That format'} is not supported. Upload a PNG, JPEG or WebP.",
        )
    if width > LOGO_MAX_EDGE or height > LOGO_MAX_EDGE:
        raise BrandingError(
            422,
            "logo_dimensions",
            f"The logo is {width}×{height} px; the longest edge may be {LOGO_MAX_EDGE} px. "
            "It is shown about 40 px high, so a smaller export loses nothing.",
        )
    return payload, mime


async def set_logo(db: AsyncSession, org_id: UUID, payload: bytes, mime: str) -> dict[str, Any]:
    """Store a validated logo. Creates the branding row when the org has none.

    A first upload also switches ``is_active`` on: uploading a logo is an
    unambiguous wish to be seen, and a row that exists only because of the
    upload would otherwise hide it until someone found the switch. An existing
    row keeps whatever its switch says.
    """
    wl = await _row(db, org_id)
    if wl is None:
        wl = WhiteLabel(org_id=org_id, is_active=True)
        db.add(wl)
    wl.logo_data = payload
    wl.logo_mime = mime
    await db.commit()
    await db.refresh(wl)
    return _serialize(wl)


async def clear_logo(db: AsyncSession, org_id: UUID) -> dict[str, Any] | None:
    """Remove the uploaded logo. ``None`` when the org has no branding row."""
    wl = await _row(db, org_id)
    if wl is None:
        return None
    wl.logo_data = None
    wl.logo_mime = None
    await db.commit()
    await db.refresh(wl)
    return _serialize(wl)


async def agency_branding(db: AsyncSession, org: Any) -> dict[str, Any]:
    """Name, logo and colour an agency's client sees: active white-label, else the org name.

    Used by the client review page and the campaign pack. ``logo_url`` is the
    uploaded logo as a ``data:`` URI when one exists, else the external
    ``logo_url`` re-checked as a safe link (it ends up in a public page and a
    shared document), else ``None``. The colour is re-checked for the same
    reason.
    """
    wl = (
        await db.execute(
            select(WhiteLabel).where(WhiteLabel.org_id == org.id, WhiteLabel.is_active.is_(True))
        )
    ).scalar_one_or_none()
    name = org.name
    logo_url: str | None = None
    color: str | None = None
    support_email: str | None = None
    if wl is not None:
        name = (wl.company_name or "").strip() or org.name
        logo_url = _data_url(wl)
        if logo_url is None and wl.logo_url:
            try:
                logo_url = assert_safe_link(wl.logo_url)
            except UnsafeURLError:
                logo_url = None
        if wl.primary_color and _HEX_COLOR.match(wl.primary_color):
            color = wl.primary_color
        support_email = wl.support_email or None
    return {
        "name": name,
        "logo_url": logo_url,
        "primary_color": color,
        "support_email": support_email,
    }
