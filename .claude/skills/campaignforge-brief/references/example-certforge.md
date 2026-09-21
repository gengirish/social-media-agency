# Worked example — CertForge (260921)

**Output:** `campaigns/certforge-launch/05-campaignforge-brief.md` (the full paste-ready brief).
**Built from:** `campaigns/certforge-launch/00-campaign-control.md` + live research.

What this example demonstrates, step by step:

## Research found three sources that disagreed

| Source | Said |
|---|---|
| Homepage | Headline "Ship a cohort's credentials in one upload." Status block (Aug 2026): passports and claim-by-email *in build* |
| Pricing page | CSV bulk issuance is **Starter** (₹2,999), not free. Passports listed under **Growth**. "Email delivery" on the free plan |
| `openapi.json` + public `/api/v1/tiers` | Tiers endpoint returns the pricing page's features verbatim. Endpoints exist for passports, claims, `send_email`, usage, checkout |

**Resolution:** pricing page = product truth (matches the API); homepage status block is stale. Email *delivery* (live, `send_email`) ≠ *claiming* (in API, UI unverified). Recorded as a feature-status table with a middle 🟡 column: "in API, UI unverified — promise only after an end-to-end test".

## How that shaped the brief

- **Key Messages** use only live features, and the CSV line names the plan and price: *"Upload a whole cohort from one CSV on Starter (₹2,999/mo)"*. The homepage's own headline was *not* reused, because it implies a paid feature on the free CTA.
- **Additional Context** carries the do-not-promise list (passports, claiming, custom templates…), a plan-gating sentence, and product-specific wording bans ("tamper-evident", never "tamper-proof"/"blockchain" — it's HMAC-signed).
- **Channels:** LinkedIn + X only. Instagram/TikTok are unpublishable in CampaignForge, and the plan was LinkedIn-first.
- **Budget:** the user's number ($100), with the split described so the ad-copy agent writes for Google Search + a LinkedIn boost, not a generic ad set.
- **Goals** (40 sign-ups, 15 activated…) appear only because the campaign plan set them as labelled goals — not as forecasts.
- **Pending proof:** the demo verification link is `{DEMO_VERIFY_URL}` and the claim "we issued our own cohort on CertForge" is explicitly held until it has happened.

## Mistakes caught during the run (avoid repeating)

- A drafted founder post invented an anecdote ("a graduate texted me…", "60 PDFs"). Nothing in the brief or copy may put words or events in the founder's mouth — offer a placeholder for a real story instead.
- A Google ad description said "Sign a cohort's certificates from one CSV" while landing on the free sign-up — the plan-gating rule applies to ads too.
- The form's `key_messages` is split on newlines; bullets or numbering end up inside the messages.
