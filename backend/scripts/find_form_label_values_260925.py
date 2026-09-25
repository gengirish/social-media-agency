"""CF-12 audit — find rows whose value is a form label.

**Read-only. This script never writes.** It exists so the affected rows can be
corrected by hand, which is the only safe fix: the real objective is known to the
person who created the campaign, and inventing one would be worse than the bug.

What went wrong
---------------
VettD's "Product Launch" campaign was saved with the objective
``"Campaign Objective *"`` — the literal label from step 1 of New Campaign.
Browser autofill matches on label text and will write the label into the field it
names; nothing on the server stopped it, and the value then reached the strategy
prompt as the campaign's actual goal.

The gate is now `models/schemas.py::reject_field_label`, which refuses a value
that *is* a label on `campaign_name`, `objective` and `target_audience`, and the
form fields carry `autoComplete="off"`. This script finds what was written
before that.

Usage
-----
::

    python scripts/find_form_label_values_260925.py
    python scripts/find_form_label_values_260925.py --org-id <uuid>

Output is one line per affected row with its id, so each can be opened and
corrected in the app.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402

from agency.models.database import get_session_factory  # noqa: E402
from agency.models.schemas import FIELD_LABELS, normalise_label  # noqa: E402
from agency.models.tables import Campaign, Client  # noqa: E402


def _is_label(value: str | None) -> bool:
    return bool(value) and normalise_label(value or "") in FIELD_LABELS


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-id", help="Restrict to one organization's rows.")
    args = parser.parse_args()

    factory = get_session_factory()
    found = 0

    async with factory() as db:
        query = select(Campaign)
        if args.org_id:
            query = query.where(Campaign.org_id == args.org_id)
        campaigns = (await db.execute(query.order_by(Campaign.created_at))).scalars().all()

        names = dict(
            (
                await db.execute(select(Client.id, Client.brand_name))
            ).all()
        )

        for campaign in campaigns:
            hits = [
                field
                for field, value in (("name", campaign.name), ("objective", campaign.objective))
                if _is_label(value)
            ]
            if not hits:
                continue
            found += 1
            print(f"campaign {campaign.id}  ({names.get(campaign.client_id, 'unknown client')})")
            print(f"    name      : {campaign.name!r}")
            print(f"    objective : {campaign.objective!r}")
            print(f"    fields that are labels: {', '.join(hits)}")
            print()

    print(f"campaigns holding a form label as a value: {found}")
    if found:
        print()
        print("Fix these by hand — open each campaign and enter the real value.")
        print("Nothing is corrected automatically: only the person who created the")
        print("campaign knows what it was meant to say, and a guess would become")
        print("the brief the agents work from.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
