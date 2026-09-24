# CampaignForge form field map

**Last checked:** 260921 against `origin/main` (`700b39e`). Re-read the code before relying on this — the code wins.

## New Client — `frontend/src/app/(dashboard)/clients/page.tsx`

| Field | Required | Notes |
|---|---|---|
| Website | no | **Read website** button calls `api.extractBrand(url)` and fills Brand Name / Industry / Description where the user hasn't typed, and attaches a brand profile saved with the client. Review it: it reads the homepage and inherits stale claims. |
| Brand Name | yes | |
| Industry | yes | Free text |
| Description | no | Free text — put the verified one-paragraph product summary here |
| Contact Email | no | |

The brand profile (voice, vocabulary, audience) feeds every agent via `BrandContext`; Amplify and moderation also read `vocabulary_exclude`.

## New Campaign — `frontend/src/app/(dashboard)/campaigns/new/page.tsx`

Posts to `api.createCampaign(...)`. Launch is blocked unless the three required fields are filled.

| Field | Required | Payload key | Notes |
|---|---|---|---|
| Client | yes | `client_id` | Select from existing clients — create the client first |
| Campaign Name | yes | `campaign_name` | |
| Campaign Objective | yes | `objective` | Free text |
| Target Audience | no | `target_audience` | Free text |
| Key Messages | no | `key_messages` | **Split on newlines**, empty lines dropped — one message per line, no bullets |
| Channels | no | `channels` | `linkedin`, `twitter`, `instagram`, `facebook`, `tiktok`; default `linkedin` + `twitter`. Instagram/TikTok cannot be auto-published (`lib/platforms.ts`) |
| Start Date | no | `start_date` | Defaults to today if blank |
| End Date | no | `end_date` | Defaults to today + 30 days if blank |
| Budget (USD) | no | `budget_usd` | Number, USD |
| Additional Context | no | `additional_context` | Free text — the guardrail field |

After launch: the pipeline pauses at Human Review (`PATCH /campaigns/{id}/review`); drafts are `draft` = **Pending** in Posts › Queue; approve runs moderation (`services/moderation.py`).
