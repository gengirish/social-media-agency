"""Generates an image for a content piece, as a proper Create-screen generator.

STAGE 1 CONTRACT — signatures and semantics are frozen; bodies are Phase 2.
Fill these in place. Do not edit `routers/content.py`, `billing.py`,
`config.py`, `tables.py`, `media_credits.py` or `media_moderation.py` — other
agents own those, and `media_storage.py` is already finished. Report anything
that looks like it needs a shared-file change.

What this replaces: ``POST /content/{id}/generate-image`` called
``image_generation.generate_social_image`` directly and appended the provider's
expiring CDN URL to ``media_urls``. No quota, no cancel check, no stored asset,
no moderation, and a prompt built from ``piece.title`` or the first 100 chars of
the body — so brand voice, vocabulary and the client's campaign focus were all
absent from the one output where they are most visible.

Order of operations, which is the whole contract (copied from Amplify):

1. ``get_org_piece`` → ``get_org_client``  (404 across orgs)
2. ``build_image_prompt``                  (no model call — see below)
3. dedupe on ``prompt_hash``               (return the existing asset, charge nothing)
4. ``require_media_credits(db, org_id, "image")``
5. generate → ``media_storage.persist_from_url``
6. ``request.is_disconnected()`` → save nothing, charge nothing
7. ``moderate_media`` → onto the new ``MediaAsset.moderation``
8. write ``MediaAsset`` **and** append to ``content_piece.media_urls``, one transaction
9. ``charge_media_credits`` → commit

A malformed or empty provider response is a ``502`` saying no credits were used,
and nothing is saved.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import MediaAsset


def build_image_prompt(
    *,
    creative_brief: dict[str, Any] | None,
    brand_context: dict[str, Any] | None,
    platform: str,
    body: str,
    title: str = "",
) -> str:
    """Assemble the prompt in code. **No second LLM call.**

    ``metadata.creative_brief`` already exists from a worker-tier call
    (``post_studio.attach_creative_brief``), so deriving the prompt from it
    costs zero extra tokens. Generating a fresh prompt per image would pay a
    model call per image forever, plus the latency.

    Deterministic assembly is also the same discipline as ``plan_atoms``
    assigning Amplify angles in code rather than letting the model choose.

    With no brief, fall back to ``brand_prompt_block`` plus the post body — a
    worse prompt, not an error, because the brief is optional in the UI.
    """
    raise NotImplementedError("Phase 2")


async def generate_image_for_piece(
    db: AsyncSession,
    *,
    org_id: UUID,
    content_id: UUID,
    user_id: Any = None,
    style: str = "professional",
    prompt_override: str | None = None,
    is_disconnected: Any = None,
) -> MediaAsset:
    """Run the full flow above and return the saved asset.

    ``is_disconnected`` is the request's ``is_disconnected`` callable, checked
    **after** the provider returns: a user who navigated away gets nothing saved
    and nothing charged, matching Post Studio. The other generators only stop
    the browser waiting, and say so.

    ``prompt_override`` is for an explicit user-written prompt. It still goes
    through the brand block, because an override of the subject is not an
    override of the brand.
    """
    raise NotImplementedError("Phase 2")
