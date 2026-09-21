---
name: campaignforge-brief
description: Turn a product or brand URL into paste-ready inputs for CampaignForge's own New Client and New Campaign forms (campaignforge.intelliforge.tech/clients and /campaigns/new) — brand name, industry, description, objective, audience, key messages, channels, dates, budget and a guardrail-heavy Additional Context — grounded only in what the product's site, pricing page and public API actually say. Use when the user wants to "create a campaign for <url>", asks for "inputs for the brief", "what do I put in the campaign form", "fill in the new campaign page", or wants to run a client or their own product through the CampaignForge pipeline. Not for writing the campaign's copy itself — that is the campaign pack in campaigns/<slug>/.
---

# CampaignForge Brief — URL → form inputs

Produce the exact values a person pastes into CampaignForge's **New Client** form (Setup › Clients) and **New Campaign** form (Create › Campaigns), so the agent pipeline (strategy → SEO → content ∥ ad copy → human review → QA) starts from verified facts and explicit guardrails instead of guesses.

The form's free-text fields are the pipeline's only brief. Whatever you put in **Additional Context** is what stops the agents promising features that don't exist, inventing stats, or implying a paid feature is free. Treat it as the most important field.

## Rules (non-negotiable)

These mirror CLAUDE.md "Product rules" and `.claude/workflows/data-reliability-rules.md`:

1. **Only verified facts.** Every product claim comes from the site, pricing page, public API/spec, or the user. Mark sources: 🔍 web (with URL + fetch date), 📊 project file, user-provided.
2. **Never invent numbers.** No customer counts, testimonials, conversion or time-saved figures, market stats. KPI targets are allowed only when labelled as goals the user set or accepted — never as forecasts.
3. **Separate live from not-yet.** Build a feature-status table (live / in API but UI unverified / in build / not yet). Only *live* goes in Key Messages; the rest goes in Additional Context as "do NOT promise".
4. **Plan honesty.** If a headline benefit is a paid-plan feature, the brief must say which plan — never let copy imply it is free.
5. **Dates from the shell** (`date +%y%m%d`, `date -d YYYY-MM-DD +%a`), never from model knowledge.

## Workflow

### 1. Read the live form (fields change — don't trust memory)

Read the current form code on the branch that is deployed (`origin/main`):

- `frontend/src/app/(dashboard)/campaigns/new/page.tsx` — fields, required markers, channel options, how `key_messages` is split, date defaults, budget unit.
- `frontend/src/app/(dashboard)/clients/page.tsx` — client fields and whether **Read website** (brand extraction) exists.

`references/form-fields.md` records the field map as of the last check; if the code differs, the code wins — update that file.

### 2. Research the product

In this order, stopping when facts are consistent:

1. **Homepage** — headline and sub verbatim, audience, features, any status/roadmap block, CTAs.
2. **Pricing page** — plan names, exact prices + currency, limits, per-plan features, CTA per plan (self-serve vs "talk to us").
3. **Public API** — try `<api-host>/openapi.json` (or `/docs`, `/swagger.json`) and any public tiers/plans endpoint. Endpoints and fields are strong evidence of what *exists*; they do not prove the UI flow works.
4. **Existing project files** — `campaigns/<slug>/00-campaign-control.md` if a campaign pack already exists: reuse its positioning, pillars, ICPs, UTM convention and decisions. Don't re-derive what's already decided.
5. **Competitors (optional)** — web search, cited, for internal context only. Never put competitor names into the brief (the pipeline writes ads; trademark policy).

Look for **contradictions** between homepage, pricing and API (e.g. a homepage headline that sells a paid-only feature; a feature listed as "in build" on one page and included on another). List them — they become "fix before paid traffic" notes and Additional Context guardrails.

### 3. Decide the brief

- **Objective:** one primary action (e.g. free sign-up that activates) + one secondary (sales conversation / paid plan). Include goal numbers only if the user gave or accepted them.
- **Audience:** primary / secondary / tertiary ICPs with their pain, plus geography and language (infer geography from currency/support contact, and say so).
- **Key messages:** 5–7 lines, one benefit each, each backed by a *live* feature. The form splits on newlines — no bullets, no numbering.
- **Channels:** only channels the plan uses. Check `lib/platforms.ts` / `UNAVAILABLE_PUBLISH_PLATFORMS`: don't select a platform CampaignForge cannot publish to unless the user wants drafts for manual posting — say so.
- **Dates:** real sprint dates from the campaign pack or the user; if none, start next Monday for 4 weeks (compute with `date`).
- **Budget (USD):** the user's number. If none, ask — don't default to the form's placeholder.

### 4. Write Additional Context

Use the template in `assets/brief-template.md`. It must contain, in this order:

1. Source of truth pointer (campaign pack path, if any).
2. Pricing, verbatim numbers + currency, with plan-gated features named.
3. **ONLY PROMISE LIVE FEATURES** list, then the explicit do-not-promise list.
4. Plan-gating sentence for any headline feature that is paid-only.
5. Wording bans specific to the product (e.g. "tamper-evident, never tamper-proof / blockchain").
6. No invented numbers; no competitor names.
7. Voice, readability, emoji cap, one CTA per piece, founder/brand attribution.
8. CTAs with real URLs, and the UTM convention.
9. Paid plan summary if there is a budget (split, targeting, negatives).
10. Pending placeholders (e.g. `{DEMO_VERIFY_URL}`) and claims that must wait until something has actually happened.

### 5. Output

Reply with two paste-ready sections — **Step 1: New Client** (table + note to review what *Read website* extracts, since it reads the homepage and can inherit stale claims) and **Step 2: New Campaign** (each field in its own fenced block so it copies cleanly) — followed by a short **After launch** note: the run pauses at Human Review, drafts land in **Posts › Queue** as Pending, approval runs moderation; check drafts against the campaign pack.

If the user wants it kept, also save it as `campaigns/<slug>/05-campaignforge-brief.md`.

End with unresolved questions (missing budget, unverified features, site contradictions).

## Worked example

`references/example-certforge.md` — CertForge (certforge.intelliforge.tech), built from `campaigns/certforge-launch/`. Shows the contradiction handling (homepage "one upload" vs Starter-only CSV), the API-evidence feature table, and a full Additional Context.

## Related

- Campaign pack (control doc, copy bank, lead magnet, calendar, paid plan): follow `campaigns/certforge-launch/` as the pattern and `.claude/commands/campaign/brief.md`.
- Product behaviour the brief feeds: CLAUDE.md "Agent pipeline", "Approval gate", "Amplify".
