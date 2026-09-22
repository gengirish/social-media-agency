# CampaignForge brief — CertForge

Paste-ready inputs for CampaignForge's New Client and New Campaign forms (https://campaignforge.intelliforge.tech/campaigns/new). Built with the `campaignforge-brief` skill from `00-campaign-control.md`.

Sources: https://certforge.intelliforge.tech/ · /pricing · https://api.certforge.intelliforge.tech/openapi.json · `/api/v1/tiers` 🔍 fetched 21-Sep-2026

## Step 1: New Client (Setup › Clients)

| Field | Value |
|---|---|
| Website | `https://certforge.intelliforge.tech` → click **Read website** |
| Brand Name * | `CertForge` |
| Industry * | `EdTech / Credentialing SaaS` |
| Description | `CertForge by IntelliForge mints tamper-evident, verifiable certificates for bootcamps, internships and events. Issuers sign a cohort's credentials (CSV bulk on Starter, or REST API); every credential gets a public verification page any employer can check from its ID alone — no login. Open Badges 3.0, HMAC-SHA256 signed, revocable. Free Community plan: 500 credentials/month.` |
| Contact Email | `support@intelliforge.tech` |

> Review the extracted brand profile before saving — the homepage's status block is stale (shows passports as "in build"). Remove anything promising passports or claim-by-email.

## Step 2: New Campaign (Create › Campaigns)

**Client \*** — `CertForge`

**Campaign Name \***
```
CertForge — Cohort Credentials Launch (Oct 2026)
```

**Campaign Objective \***
```
Get bootcamp, internship and event operators in India to start issuing verifiable certificates on CertForge. Primary goal: free Community sign-ups who issue at least one credential (activation). Secondary goal: "Talk to us" conversations that convert to the Starter plan (₹2,999/mo) for CSV bulk issuance, custom artwork and API access. Sprint goals: 40 sign-ups, 15 activated issuers, 8 "Talk to us" emails, 3 paid Starter orgs.
```

**Target Audience**
```
Primary: founders and ops leads of Indian upskilling bootcamps, cohort courses and training institutes who hand graduates PDF certificates that recruiters can't verify. Secondary: internship programme managers (college T&P cells, startup intern programmes, HR), and hackathon/workshop/event organisers issuing participation certificates in bulk. Tertiary: developers and LMS builders who want to issue signed credentials from their own app via API. India-first, English.
```

**Key Messages (one per line)**
```
Certificates any recruiter can check in one click — verify by credential ID, no login, no emailing the issuer
Verification is free and public, forever
Fix a misspelled name before it's signed — every row is validated before signing
Issued the wrong one? Revoke it. Edit one? The signature breaks — tamper-evident, not a PDF
Open Badges 3.0 export and a REST API — your credentials aren't trapped in our app
Start free: 500 credentials a month, hosted verification pages and QR codes, no card
Upload a whole cohort from one CSV on Starter (₹2,999/mo)
```

**Channels:** tick **LinkedIn** and **X / Twitter** only — Instagram, Facebook, TikTok off (plan is LinkedIn-first; Instagram/TikTok can't be auto-published).

| Field | Value |
|---|---|
| Start Date | `2026-09-28` |
| End Date | `2026-10-25` |
| Budget (USD) | `100` |

**Additional Context**
```
Source of truth: campaigns/certforge-launch/00-campaign-control.md.

PRICING (INR/month): Community free (500 credentials/mo, 1 template, verification pages, QR, email delivery) · Starter ₹2,999 (500/mo, 5 templates, custom artwork, CSV bulk issuance, API keys/webhooks) · Growth ₹9,999 (2,000/mo, 25 templates, AI field placement, recipient passports, priority support) · Scale ₹24,999 (unlimited, custom verification domain, SLA). Paid plans are "Talk to us" via support@intelliforge.tech.

ONLY PROMISE LIVE FEATURES: verification pages, Open Badges 3.0 export, CSV bulk issuance (Starter), single-credential API, on-demand rendering, revocation, email delivery. Do NOT present recipient passports, claiming, custom templates, email reporting or webhook retries as available.

CSV bulk is a Starter feature — never imply it's free.

Say "tamper-evident", never "tamper-proof", "fraud-proof", "unforgeable" or "blockchain" (it's HMAC-SHA256 signed, not on a blockchain).

NO invented numbers: no customer counts, testimonials, time-saved %, fraud statistics or "trusted by". Only numbers above (500/mo, prices, Open Badges 3.0).

No competitor names in any copy or ads.

Voice: operator-to-operator, plain, specific, a little dry; founder-led (Girish Hiremath, IntelliForge — IntelliForge runs its own AI Bootcamp cohorts). Grade 6–8 readability, max 2 emoji per post, one CTA per piece.

CTAs: primary "Start free" → https://certforge.intelliforge.tech/sign-up ; secondary "Talk to us about your next cohort" → support@intelliforge.tech ; developers → https://api.certforge.intelliforge.tech/docs.
UTM: ?utm_source={linkedin|x|google}&utm_medium={organic|paid}&utm_campaign=cohort-launch-oct26&utm_content={piece-id}

PAID ($100): $70 Google Search India (issuer-intent keywords like "bulk certificate generator", "verifiable certificates", "hackathon certificates"; heavy negatives for govt documents, DSC/SSL, learners seeking course certificates) + $30 LinkedIn boost of the best organic founder post. Ad copy must name Starter wherever CSV is mentioned.

Demo credential link is pending — use {DEMO_VERIFY_URL}; do not claim "we issued our own cohort on CertForge" yet.
```

## After launch
The run pauses at **Human Review**; drafts land in **Posts › Queue** as Pending; approving runs moderation. Compare drafts with `01-copy-bank.md` and reject anything that promises passports or implies CSV is free.

## Unresolved questions
- Homepage hero fix (gates Google Ads) — live before Sun 04-Oct?
- Passports/claiming: move to "live" after the AI Bootcamp end-to-end test (Thu 25-Sep); then update this brief's Additional Context.
