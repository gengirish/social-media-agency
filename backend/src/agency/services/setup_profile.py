"""Setup › Profile: the intake answers and the Brand Voice guide, stored on ``brand_profile``.

Cadence keeps positioning answers, the brand voice guide and the campaign in
one nested ``profile`` object, and shipped the same bug three times: an edit
that rebuilt the object by hand silently wiped everything it did not mention
(``updateProfileAnswers`` exists to stop that). Here the same rule is enforced
column by column:

* approving the intake writes **only** ``target_audience``,
  ``competitor_differentiation`` and the ``register`` key inside
  ``tone_attributes`` (other tone keys — e.g. Magic Brief's 0-1 weights — are
  merged, not replaced), plus ``client.website_url`` when a URL is given;
* approving a brand voice writes **only** ``voice_description``,
  ``vocabulary_include``, ``vocabulary_exclude`` and the one north-star entry
  in ``example_posts`` (other example posts are kept).

Nothing here touches ``style_rules``, ``emoji_policy`` or ``client.settings``
(where the campaign focus lives).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import BrandProfile, Client

#: Cadence's fixed tone registers. Picked by the human, never AI-prefilled.
TONE_REGISTERS: tuple[str, ...] = (
    "Blunt & technical",
    "Friendly & casual",
    "Bold & punchy",
    "Calm & authoritative",
)

#: Question ids the coaching endpoint accepts (tone is fixed-choice: no coaching).
INTAKE_QUESTIONS: dict[str, str] = {
    "audience": "Who is this client actually for?",
    "differentiator": "What makes it different from the closest alternative?",
}

#: ``example_posts`` entry holding the Brand Voice guide's example sentence.
NORTH_STAR_KIND = "voice_north_star"


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def clean_words(values: list[str], limit: int = 20) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        s = v.strip()[:80]
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out[:limit]


def north_star(example_posts: Any) -> str:
    for post in _list(example_posts):
        if isinstance(post, dict) and post.get("kind") == NORTH_STAR_KIND:
            text = post.get("text")
            return text if isinstance(text, str) else ""
    return ""


def with_north_star(example_posts: Any, sentence: str) -> list[Any]:
    """Replace the north-star entry (or drop it when blank); keep every other example."""
    kept = [
        p
        for p in _list(example_posts)
        if not (isinstance(p, dict) and p.get("kind") == NORTH_STAR_KIND)
    ]
    sentence = sentence.strip()
    return ([{"kind": NORTH_STAR_KIND, "text": sentence}] if sentence else []) + kept


def intake_answers(bp: BrandProfile | None) -> dict[str, str]:
    if bp is None:
        return {"audience": "", "differentiator": "", "tone": ""}
    register = _dict(bp.tone_attributes).get("register")
    return {
        "audience": str(bp.target_audience or ""),
        "differentiator": str(bp.competitor_differentiation or ""),
        "tone": register if isinstance(register, str) else "",
    }


def brand_voice_view(bp: BrandProfile | None) -> dict[str, Any] | None:
    """The guide as stored, or ``None`` when nothing voice-related is on file yet."""
    if bp is None:
        return None
    view = {
        "voice_description": str(bp.voice_description or ""),
        "vocabulary_include": list(bp.vocabulary_include or []),
        "vocabulary_exclude": list(bp.vocabulary_exclude or []),
        "example_sentence": north_star(bp.example_posts),
    }
    if not (view["voice_description"] or view["vocabulary_include"] or view["vocabulary_exclude"]):
        return None
    return view


def profile_view(client: Client, bp: BrandProfile | None) -> dict[str, Any]:
    settings = _dict(client.settings)
    focus = _dict(settings.get("campaign_focus"))
    desc = focus.get("description")
    return {
        "client_id": str(client.id),
        "brand_name": client.brand_name,
        "website_url": client.website_url,
        "approved": bp is not None,
        "answers": intake_answers(bp),
        "brand_voice": brand_voice_view(bp),
        "campaign_focus": desc.strip() if isinstance(desc, str) and desc.strip() else None,
        "updated_at": bp.updated_at.isoformat() if bp is not None and bp.updated_at else None,
    }


async def get_profile(db: AsyncSession, client_id: Any, org_id: UUID) -> BrandProfile | None:
    return (
        await db.execute(
            select(BrandProfile).where(
                BrandProfile.client_id == client_id, BrandProfile.org_id == org_id
            )
        )
    ).scalar_one_or_none()


def apply_intake(
    bp: BrandProfile, *, audience: str | None, differentiator: str | None, tone: str | None
) -> None:
    """Merge the intake answers into ``bp``. ``None`` leaves a field as it was."""
    if audience is not None:
        bp.target_audience = audience.strip()  # type: ignore[assignment]
    if differentiator is not None:
        bp.competitor_differentiation = differentiator.strip()  # type: ignore[assignment]
    if tone is not None:
        tone_attrs = _dict(bp.tone_attributes)
        tone_attrs["register"] = tone
        # Reassign (not mutate) so SQLAlchemy sees the JSONB change.
        bp.tone_attributes = tone_attrs  # type: ignore[assignment]


async def approve_intake(
    db: AsyncSession,
    client: Client,
    org_id: UUID,
    *,
    url: str | None,
    audience: str | None,
    differentiator: str | None,
    tone: str | None,
) -> BrandProfile:
    """Create or update the brand profile from the intake.

    ``client`` must already be org-resolved. Caller commits.
    """
    bp = await get_profile(db, client.id, org_id)
    if bp is None:
        bp = BrandProfile(
            client_id=client.id,
            org_id=org_id,
            voice_description="",
            tone_attributes={},
            vocabulary_include=[],
            vocabulary_exclude=[],
            example_posts=[],
            style_rules=[],
            emoji_policy="moderate",
            competitor_differentiation="",
            target_audience="",
        )
        db.add(bp)
    apply_intake(bp, audience=audience, differentiator=differentiator, tone=tone)
    if url is not None and url.strip():
        client.website_url = url.strip()[:500]  # type: ignore[assignment]
    await db.flush()
    return bp


def apply_brand_voice(
    bp: BrandProfile,
    *,
    voice_description: str,
    vocabulary_include: list[str],
    vocabulary_exclude: list[str],
    example_sentence: str,
) -> None:
    bp.voice_description = voice_description.strip()  # type: ignore[assignment]
    bp.vocabulary_include = clean_words(vocabulary_include)  # type: ignore[assignment]
    bp.vocabulary_exclude = clean_words(vocabulary_exclude)  # type: ignore[assignment]
    bp.example_posts = with_north_star(bp.example_posts, example_sentence)  # type: ignore[assignment]
