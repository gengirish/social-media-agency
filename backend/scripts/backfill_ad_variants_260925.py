"""CF-03 backfill — reshape ad variants written before ``services/ad_variants.py``.

**This script is not run automatically and must not be run against production
without a dry run first.** It is listed in the PR for Girish to run.

What it repairs
---------------
Until 260925 the pipeline stored an ad variant as::

    body     = json.dumps(ad["headlines"])     # '["Headline A", "Headline B"]'
    metadata = <the agent's raw dict>

which made a Google ad's body a literal JSON list on screen and a Meta or
LinkedIn ad's body ``[]`` — those networks' copy comes back under
``primary_text``, and the model gives them no headlines at all.

This rewrites each affected row to the current shape: the normalised variant under
``metadata.ad``, the same copy flattened into ``body``, the agent's original dict
preserved under ``metadata.raw`` so nothing is destroyed, and a variant with no
usable copy moved from ``draft`` to ``failed`` so it cannot be approved (CF-05).

Rows already carrying ``metadata.ad`` are skipped, so the script is idempotent and
safe to re-run.

What it deliberately does not do
--------------------------------
- It never invents copy. A variant the agent returned empty stays empty; it is
  only re-labelled so the UI stops offering it for approval.
- It does not touch a piece whose status is past ``draft``/``failed``. An ad that
  a human already approved, scheduled or published is a decision on the copy as it
  was shown; silently rewriting it afterwards is not this script's business. Those
  rows are counted and listed instead.

Usage
-----
::

    # Read-only: prints every change it would make and touches nothing.
    python scripts/backfill_ad_variants_260925.py

    # Apply, against the database in DATABASE_URL.
    python scripts/backfill_ad_variants_260925.py --apply

    # Limit to one org while verifying.
    python scripts/backfill_ad_variants_260925.py --org-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# Run from backend/ without installing: src/ holds the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import or_, select  # noqa: E402

from agency.models.database import get_session_factory  # noqa: E402
from agency.models.tables import ContentPiece  # noqa: E402
from agency.services.ad_variants import normalize, render_body  # noqa: E402

#: The content types the ad path writes. ``linkedin_ad`` is included even though
#: the old prompt rarely produced one.
AD_CONTENT_TYPES = ("google_ad", "meta_ad", "linkedin_ad")

#: Statuses this script may rewrite. Anything further along records a human
#: decision about the copy as displayed.
REWRITABLE_STATUSES = frozenset({"draft", "failed"})


def _looks_stringified(body: str | None) -> bool:
    """True when the body is a JSON list/dict dumped into a text column."""
    text = (body or "").strip()
    if not text or text[0] not in "[{":
        return False
    try:
        json.loads(text)
    except ValueError:
        return False
    return True


def _raw_variant(piece: ContentPiece) -> dict[str, Any]:
    """The agent's original dict for this piece.

    Old rows stored it as the whole of ``metadata``. Newer ones (written by a
    partially-migrated deploy) keep it under ``metadata.raw``.
    """
    metadata = dict(piece.metadata_ or {})
    raw = metadata.get("raw")
    if isinstance(raw, dict) and raw:
        return raw
    # Drop the keys the app adds, so only the agent's own fields are normalised.
    return {k: v for k, v in metadata.items() if k not in {"ad", "generation", "moderation", "raw"}}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the changes. Without it the script only reports (default).",
    )
    parser.add_argument("--org-id", help="Restrict to one organization's rows.")
    args = parser.parse_args()

    factory = get_session_factory()

    rewritten = 0
    emptied = 0
    already_current = 0
    locked: list[str] = []

    async with factory() as db:
        query = select(ContentPiece).where(
            or_(
                ContentPiece.content_type.in_(AD_CONTENT_TYPES),
                ContentPiece.platform.in_(("google", "meta", "linkedin")),
            )
        )
        if args.org_id:
            query = query.where(ContentPiece.org_id == args.org_id)

        pieces = (await db.execute(query.order_by(ContentPiece.created_at))).scalars().all()

        for piece in pieces:
            metadata = dict(piece.metadata_ or {})

            # Already in the current shape.
            if isinstance(metadata.get("ad"), dict) and metadata["ad"].get("fields"):
                already_current += 1
                continue

            # Only ad-shaped rows: a social post that merely lives on `linkedin`
            # is matched by the platform clause and must be left alone.
            if piece.content_type not in AD_CONTENT_TYPES:
                continue

            if piece.status not in REWRITABLE_STATUSES:
                locked.append(f"{piece.id} ({piece.status}, {piece.content_type})")
                continue

            raw = _raw_variant(piece)
            ad = normalize(raw, index=1)
            body = render_body(ad)

            new_metadata: dict[str, Any] = {
                k: v for k, v in metadata.items() if k in {"moderation"}
            }
            new_metadata["ad"] = ad
            new_metadata["raw"] = raw
            new_status = piece.status
            if ad["is_empty"]:
                new_metadata["generation"] = {
                    "status": "failed",
                    "reason": "The ad copy agent returned no usable copy for this variant.",
                }
                new_status = "failed"
                emptied += 1
            elif ad["missing"]:
                new_metadata["generation"] = {"status": "incomplete", "missing": ad["missing"]}

            rewritten += 1
            print(
                f"{'APPLY ' if args.apply else 'DRY   '}{piece.id}  {piece.content_type:<12}"
                f"{piece.status} -> {new_status}"
            )
            print(f"        was body: {(piece.body or '')[:90]!r}"
                  f"{'  (stringified list)' if _looks_stringified(piece.body) else ''}")
            print(f"        new body: {body[:90]!r}")

            if args.apply:
                piece.body = body
                piece.metadata_ = new_metadata
                piece.status = new_status

        if args.apply:
            await db.commit()

    print()
    print(f"ad rows needing a rewrite : {rewritten}")
    print(f"  of which empty -> failed: {emptied}")
    print(f"already in current shape  : {already_current}")
    if locked:
        print(f"left alone (past draft)   : {len(locked)}")
        for row in locked:
            print(f"    {row}")
        print("    ^ approved or later: the copy as shown was signed off by a human.")
    if not args.apply:
        print()
        print("Dry run — nothing was written. Re-run with --apply to commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
