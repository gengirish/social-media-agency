"""Durable storage for generated media, behind one interface and two drivers.

Why this exists at all: the provider hands back a CDN URL that expires. Writing
that URL into ``content_piece.media_urls`` — which is what
``POST /content/{id}/generate-image`` did before 261013 — produces a post whose
image is gone by the time anyone publishes it.

Two drivers, chosen by configuration:

``r2``
    Cloudflare R2 over the S3-compatible API. Production. Chosen on egress:
    generated media is pulled repeatedly (platform upload, Queue thumbnails on
    every render, portal, client review, manual download) and R2 does not bill
    it. The backend runs on Fly, not Vercel, so Vercel Blob's one advantage —
    native integration — does not apply and would add egress out of Vercel on
    every upload.

``local``
    Filesystem, served back through ``routers/media.py``. Dev, CI, and any
    environment with blank credentials. **Not a stub**: same keys, same
    derivative, same return shape, so every later phase is testable and
    demoable before the R2 account exists.

The resolved driver is logged once at startup as ``media_storage_driver``. A
silent ``local`` driver in production means media that vanishes on redeploy —
the same failure shape as the checkpointer's memory fallback, and just as quiet,
which is why it is a startup warning rather than a line in a debug log.
"""

from __future__ import annotations

import hashlib
import io
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import structlog

from agency.config import get_settings

logger = structlog.get_logger()

#: Longest edge of the derivative, in pixels. Thumbnails are what the Queue
#: renders; serving originals there is the first performance regression this
#: feature can produce (a 12-card view pulling 1MP PNGs).
THUMB_MAX_EDGE = 400

#: Generous, because this is one fetch of an already-generated file, not the
#: generation itself.
FETCH_TIMEOUT_SECONDS = 60

#: Refuse anything larger. A provider returning something unexpected should not
#: be able to fill the bucket or the dyno's disk.
MAX_BYTES = 64 * 1024 * 1024

#: What we are willing to store. Checked against the fetched bytes' declared
#: type, not the URL's extension.
ALLOWED_MIME_PREFIXES = ("image/", "video/")


@dataclass(frozen=True)
class StoredMedia:
    """One persisted asset. ``thumb_url`` is ``""`` when no derivative was made."""

    storage_key: str
    url: str
    thumb_url: str
    mime: str
    bytes: int
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None


class MediaStorageError(RuntimeError):
    """Storage failed. Callers charge no credits and save nothing."""


def _settings() -> Any:
    return get_settings()


def active_driver() -> str:
    """``"r2"`` when R2 is fully configured, else ``"local"``.

    All three of endpoint, key and secret are required. A partially configured
    bucket is a misconfiguration, not a reason to half-use it — falling back to
    ``local`` keeps the failure visible at startup instead of at the first
    upload.
    """
    s = _settings()
    if s.s3_endpoint_url and s.aws_access_key_id and s.aws_secret_access_key:
        return "r2"
    return "local"


def log_driver_at_startup() -> str:
    """Log the resolved driver once. Called from the FastAPI startup hook."""
    driver = active_driver()
    if driver == "local":
        # Deliberately a warning: in production this means media that does not
        # survive a redeploy, and the symptom (broken images, later) is far from
        # the cause (blank credentials, now).
        logger.warning(
            "media_storage_driver",
            driver=driver,
            detail=(
                "Local filesystem storage. Set S3_ENDPOINT_URL, AWS_ACCESS_KEY_ID "
                "and AWS_SECRET_ACCESS_KEY for durable storage; media written now "
                "will not survive a redeploy."
            ),
        )
    else:
        logger.info("media_storage_driver", driver=driver, bucket=_settings().s3_bucket_name)
    return driver


def build_key(
    *,
    org_id: UUID,
    client_id: UUID,
    content_id: UUID | None,
    ext: str,
    asset_id: UUID | None = None,
) -> str:
    """``{org}/{client}/{content|unattached}/{asset}.{ext}``.

    The org prefix is what makes bulk delete on churn and per-tenant usage
    accounting a prefix scan rather than a table join.
    """
    aid = asset_id or uuid4()
    scope = str(content_id) if content_id else "unattached"
    clean = ext.lstrip(".").lower() or "bin"
    return f"{org_id}/{client_id}/{scope}/{aid}.{clean}"


def public_url(storage_key: str) -> str:
    """Public URL for a stored key, per the active driver."""
    s = _settings()
    if active_driver() == "local":
        return f"/api/v1/media/{storage_key}"
    base = (s.media_public_base_url or "").rstrip("/")
    if base:
        return f"{base}/{storage_key}"
    # Endpoint+bucket works but is uncached — a custom domain is what puts the
    # CDN in front of thumbnails.
    return f"{s.s3_endpoint_url.rstrip('/')}/{s.s3_bucket_name}/{storage_key}"


def prompt_hash(*, prompt: str, model: str, params: dict[str, Any] | None = None) -> str:
    """Stable hash over everything that changes the output.

    Dedupe key: a repeated generate returns the existing asset and charges
    nothing, which is the single largest cost saving in this feature because
    users re-click. ``params`` is sorted so dict ordering cannot produce two
    hashes for one request.
    """
    parts = [prompt.strip(), model.strip()]
    for key in sorted((params or {}).keys()):
        parts.append(f"{key}={(params or {})[key]!r}")
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


async def fetch_bytes(url: str) -> tuple[bytes, str]:
    """Download a provider result. Returns ``(payload, mime)``.

    Raises :class:`MediaStorageError` on anything unexpected — a non-2xx, a type
    we do not store, or an oversized body. The caller treats that as a failed
    generation and charges nothing.
    """
    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True) as c:
            resp = await c.get(url)
            resp.raise_for_status()
            payload = resp.content
            mime = (resp.headers.get("content-type") or "").split(";")[0].strip()
    except httpx.HTTPError as exc:
        raise MediaStorageError(f"Could not fetch generated media: {exc}") from exc

    if not mime:
        mime = mimetypes.guess_type(url)[0] or "application/octet-stream"
    if not mime.startswith(ALLOWED_MIME_PREFIXES):
        raise MediaStorageError(f"Refusing to store media of type {mime!r}")
    if len(payload) > MAX_BYTES:
        raise MediaStorageError(
            f"Generated media is {len(payload)} bytes, over the {MAX_BYTES} byte cap"
        )
    if not payload:
        raise MediaStorageError("Provider returned an empty body")
    return payload, mime


def _ext_for(mime: str) -> str:
    return (mimetypes.guess_extension(mime) or ".bin").lstrip(".")


def _image_dimensions(payload: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(payload)) as img:
            return int(img.width), int(img.height)
    except Exception:  # noqa: BLE001 - dimensions are metadata, never fatal
        return None, None


def make_thumbnail(payload: bytes) -> bytes | None:
    """A WebP derivative, longest edge :data:`THUMB_MAX_EDGE`. ``None`` on failure.

    Never fatal: a missing thumbnail degrades the Queue to loading the original,
    which is slow but correct. Losing the whole generation over it would not be.
    """
    try:
        from PIL import Image

        with Image.open(io.BytesIO(payload)) as img:
            img = img.convert("RGB")
            img.thumbnail((THUMB_MAX_EDGE, THUMB_MAX_EDGE))
            out = io.BytesIO()
            img.save(out, format="WEBP", quality=82, method=4)
            return out.getvalue()
    except Exception as exc:  # noqa: BLE001
        logger.warning("media_thumbnail_failed", error=str(exc))
        return None


async def _put_local(storage_key: str, payload: bytes) -> None:
    root = Path(_settings().media_local_dir).resolve()
    dest = (root / storage_key).resolve()
    # The key is built from uuids, never from user input — but resolve-and-check
    # anyway, because that is one line and a traversal here writes anywhere the
    # process can.
    if not str(dest).startswith(str(root)):
        raise MediaStorageError("Refusing to write outside the media directory")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)


async def _put_r2(storage_key: str, payload: bytes, mime: str) -> None:
    s = _settings()
    try:
        import aioboto3
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise MediaStorageError("aioboto3 is not installed; cannot use the r2 driver") from exc

    session = aioboto3.Session()
    try:
        async with session.client(
            "s3",
            endpoint_url=s.s3_endpoint_url,
            aws_access_key_id=s.aws_access_key_id,
            aws_secret_access_key=s.aws_secret_access_key,
        ) as client:
            await client.put_object(
                Bucket=s.s3_bucket_name,
                Key=storage_key,
                Body=payload,
                ContentType=mime,
                # Keys are uuid-addressed and never rewritten, so nothing is
                # ever invalidated and the CDN can hold these forever.
                CacheControl="public, max-age=31536000, immutable",
            )
    except Exception as exc:  # noqa: BLE001 - boto raises a wide family
        raise MediaStorageError(f"Upload failed: {exc}") from exc


async def put(storage_key: str, payload: bytes, mime: str) -> None:
    """Write one object through the active driver."""
    if active_driver() == "local":
        await _put_local(storage_key, payload)
    else:
        await _put_r2(storage_key, payload, mime)


async def read_local(storage_key: str) -> tuple[bytes, str] | None:
    """Read a ``local``-driver object back. ``None`` when it is not there.

    Only the ``local`` driver serves through the app; R2 objects are fetched by
    the browser straight from the CDN.
    """
    root = Path(_settings().media_local_dir).resolve()
    src = (root / storage_key).resolve()
    if not str(src).startswith(str(root)) or not src.is_file():
        return None
    mime = mimetypes.guess_type(src.name)[0] or "application/octet-stream"
    return src.read_bytes(), mime


async def persist_from_url(
    source_url: str,
    *,
    org_id: UUID,
    client_id: UUID,
    content_id: UUID | None,
    asset_id: UUID | None = None,
    duration_ms: int | None = None,
) -> StoredMedia:
    """Fetch a provider result and store it, plus a derivative. The main entry point.

    Raises :class:`MediaStorageError` on any failure — callers must save nothing
    and charge nothing, because a generation the user cannot see is not one they
    should pay for.
    """
    payload, mime = await fetch_bytes(source_url)
    aid = asset_id or uuid4()
    storage_key = build_key(
        org_id=org_id,
        client_id=client_id,
        content_id=content_id,
        ext=_ext_for(mime),
        asset_id=aid,
    )
    await put(storage_key, payload, mime)

    thumb_url = ""
    width = height = None
    if mime.startswith("image/"):
        width, height = _image_dimensions(payload)
        thumb = make_thumbnail(payload)
        if thumb is not None:
            thumb_key = f"{storage_key.rsplit('.', 1)[0]}.thumb.webp"
            await put(thumb_key, thumb, "image/webp")
            thumb_url = public_url(thumb_key)

    logger.info(
        "media_stored",
        driver=active_driver(),
        org_id=str(org_id),
        kind="image" if mime.startswith("image/") else "video",
        bytes=len(payload),
        has_thumb=bool(thumb_url),
    )
    return StoredMedia(
        storage_key=storage_key,
        url=public_url(storage_key),
        thumb_url=thumb_url,
        mime=mime,
        bytes=len(payload),
        width=width,
        height=height,
        duration_ms=duration_ms,
    )
