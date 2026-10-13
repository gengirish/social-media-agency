"""Serves generated media when the ``local`` storage driver is active.

Production uses R2 and the browser fetches straight from the CDN, so this router
is a dev/CI path only — but it is a real one, which is what lets every later
phase be built and demoed before the R2 account exists.

Authenticated and org-scoped: the key's first segment **is** the owning org, so
the check is a string comparison rather than a query. Without it any signed-in
user could read any tenant's media by guessing a path, and this is the one place
in the app where a bucket key doubles as an access decision.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from agency.dependencies import get_current_user, get_org_id
from agency.services import media_storage

router = APIRouter(prefix="/media", tags=["Media"])


@router.get("/{storage_key:path}")
async def get_media(
    storage_key: str,
    user: dict[str, Any] = Depends(get_current_user),
    org_id: UUID = Depends(get_org_id),
) -> Response:
    """Return one locally stored object.

    404 for a key outside the caller's org — not 403, which would confirm that
    another tenant holds that key.
    """
    if media_storage.active_driver() != "local":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media is not served by this deployment")

    if not storage_key.startswith(f"{org_id}/"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")

    found = await media_storage.read_local(storage_key)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")

    payload, mime = found
    return Response(
        content=payload,
        media_type=mime,
        # Keys are uuid-addressed and never rewritten, so this is safe to cache
        # hard even in dev — and it keeps the Queue from refetching thumbnails
        # on every render.
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )
