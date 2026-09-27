# CertForge — Cohort Credentials Launch (Control Doc)

**Source of truth:** https://certforge.intelliforge.tech/ + `/pricing` 🔍 WEB SOURCE (fetched 21-Sep-2026)
**Sprint:** 4 weeks live → **Mon 28-Sep → Sun 25-Oct-2026** (setup Tue 22-Sep → Sun 27-Sep)
**Channels:** LinkedIn (founder + company page, primary) · founder-led outreach (email + LinkedIn DM) · X/dev communities (API angle) · WhatsApp/Telegram edtech & organiser groups
**Baseline:** ⚠️ NOT AVAILABLE — no analytics/CRM MCP connected and no CertForge usage API access from this workspace. Pull signups / active issuers / credentials issued from the CertForge admin before 28-Sep and write them here.

---

## 1. Verified product facts 🔍

| Fact | Value (verbatim where quoted) |
|------|-------------------------------|
| Product | CertForge, by IntelliForge |
| Headline | "Ship a cohort's credentials in one upload." |
| Sub | "CertForge mints tamper-evident certificates for bootcamps, internships and events." |
| Standard | Open Badges 3.0, HMAC-SHA256 signed |
| Verification | Employer verifies from the credential ID alone — no login, no emailing the issuer. **"Verification is free and public, forever."** |
| Issuance | CSV bulk or REST API · validation **before** signing with row-by-row errors |
| Other | Custom certificate artwork · issuer revocation · no recipient account required · public verification pages · rendered on demand |
| API docs | https://api.certforge.intelliforge.tech/docs |
| Contact | support@intelliforge.tech (paid plans are "Talk to us") |

### Feature status — what copy may and may not promise

| ✅ Live (OK to promise) | 🟡 In API, UI unverified (promise only after the end-to-end test in §2) | 🚧 In build (do NOT promise) | ❌ Not yet |
|---|---|---|---|
| Verification page · Open Badges export · CSV bulk issuance (Starter) · single-credential API · on-demand rendering · issuer revocation · **email delivery** (`send_email` on create-credential) | Recipient passports (Growth) · claim a credential into a passport · usage reporting · checkout (Razorpay) | Custom templates marketed as a feature · email reporting | Webhook retries |

**Evidence (🔍 21-Sep):** `api.certforge.intelliforge.tech/openapi.json` has `GET /api/v1/passports/{username}`, idempotent `POST /api/v1/claims/{credential_id}`, credential status `issued|revoked|pending|claimed`, `CredentialCreate.send_email`, `GET /orgs/{slug}/usage`, `POST /orgs/{slug}/checkout`. The public `GET /api/v1/tiers` returns the pricing page's plan features verbatim. So the pricing page reflects the product; the homepage "Status (as of Aug 2026)" block is stale.

**Rule:** only ✅ goes in public copy. 🟡 moves to ✅ the day someone completes the flow in the real UI (the AI Bootcamp issuance in §2 is that test). 🚧 may appear only as "coming soon" in a roadmap post, never as a reason to buy.

### Pricing 🔍 (/pricing, INR per month)

| Plan | Price | Credentials/mo | Templates | Notable inclusions |
|---|---|---|---|---|
| **Community** | Free, no card | 500 | 1 | Hosted verification pages, QR codes, email delivery |
| **Starter** | ₹2,999 | 500 | 5 | + custom artwork, **CSV bulk issuance**, API keys/webhooks |
| **Growth** | ₹9,999 | 2,000 | 25 | + AI field placement, recipient passports, priority support |
| **Scale** | ₹24,999 | Unlimited | Unlimited | + custom verification domain, SLA, onboarding |

CTAs: Community → "Start free" (`/sign-up`). Paid → "Talk to us" (support@intelliforge.tech). No self-serve upgrade today.

### ⚠️ Site inconsistencies — recommended fixes

**Recommendation: the pricing page is correct; update the homepage.** The pricing page matches the live `/tiers` API word for word and the endpoints exist; the homepage status block was written in August and hasn't kept up.

1. **Headline vs plan (fix before paid traffic — gates Google Ads, `04-paid-plan.md`).** The hero sells "one upload", but CSV bulk is Starter. Recommended hero — benefit first, plan stated honestly in the sub (53 chars):
   > **Sign a cohort's certificates. Let anyone verify them.**
   > Free for 500 credentials a month. Upload the whole cohort from one CSV on Starter.
   Blunter alternative: `01` §1 Hero B ("Community is free. CSV bulk issuing is Starter.").
2. **Replace the homepage "Status" block** with:
   > **Live:** verification pages · Open Badges 3.0 export · CSV bulk issuance · single-credential API · email delivery · on-demand rendering · revocation
   > **Rolling out on Growth:** recipient passports and claiming
   > **Coming next:** email reporting · webhook retries
   Move passports/claiming to "Live" once the §2 end-to-end test passes. If checkout is switched on, drop "Talk to us" for Starter and say so on /pricing.
3. **Email:** no conflict once worded as above — *email delivery* (issuer sends the credential; live via `send_email`) is a different thing from *claiming* (recipient adds it to a passport). The homepage used "claim-by-email" for the second; say "claiming" instead.
4. Community and Starter have the same 500/mo cap — the upgrade reason is features, not volume. Copy sells Starter on CSV + artwork + API, not on volume.

Until 1 is live, campaign copy keeps stating "CSV on Starter" wherever it mentions uploads.

---

## 2. Positioning

**For** bootcamp, internship and event operators **who** hand out certificates that nobody can check, **CertForge** is a credential issuer **that** signs a whole cohort from one CSV and gives every certificate a public page any employer can verify from its ID — free, forever. **Unlike** PDF-in-a-Drive-folder, a CertForge certificate can be revoked, can't be edited without breaking its signature, and exports to the Open Badges 3.0 standard.

### Four message pillars (each maps to a live feature)

| # | Pillar | Proof (feature) | Line |
|---|---|---|---|
| P1 | **Trust** — certificates employers can actually check | Public verification by ID, no login | "Your graduate's certificate, checkable in one click by any recruiter." |
| P2 | **Time** — a cohort in one upload, no reprints | CSV bulk + row-by-row validation before signing | "Fix the typo before it's signed, not after 60 are printed." |
| P3 | **Control** — mistakes and fraud are reversible | Issuer revocation · tamper-evident signature | "Issued the wrong one? Revoke it. Edited one? The signature breaks." |
| P4 | **No lock-in** — an open standard | Open Badges 3.0 export · REST API | "Open Badges 3.0 out of the box. Your credentials aren't trapped in our app." |

### Built-by-an-operator angle ✅
IntelliForge runs its own cohort programme (IntelliForge AI Bootcamp — see `campaigns/ai-upskill-cohort/`). CertForge is positioned as the tool an operator built for their own cohort. **Confirmed 21-Sep: the AI Bootcamp's certificates go through CertForge this week** (calendar Thu 25-Sep). Do it as the end-to-end test: issue with `send_email` on → a graduate receives it → opens the verification page → claims it into a passport. Record what worked. Then (a) set `{DEMO_VERIFY_URL}` to one consenting graduate's verification page, (b) copy may say *"we issued our own AI Bootcamp cohort's certificates on CertForge"* — only after it has happened — and (c) move whatever passed from 🟡 to ✅.

---

## 3. Audience (ICPs)

| ICP | Who | Pain | Entry offer | Channel |
|---|---|---|---|---|
| **A · Bootcamp / cohort-course operators** (primary) | Founders/ops leads of Indian upskilling bootcamps, cohort courses, training institutes | Graduates' certificates are PDFs anyone can fake; recruiters can't check them; reissuing is manual | Community → Starter (CSV) | LinkedIn, founder DM/email |
| **B · Internship programme managers** | College T&P cells, startup intern programmes, HR for intern cohorts | Seasonal batches, name-spelling errors, "please resend my certificate" emails | Community → Starter | LinkedIn, email |
| **C · Event & hackathon organisers** | Hackathons, workshops, conferences, meetups | Hundreds of participation certs in one day, then silence | Community (free up to 500/mo — confirm the event's size fits) | Organiser communities, X, LinkedIn |
| **D · Developers / LMS builders** (secondary) | Teams who want to issue from their own app | Building signing + verification themselves | API docs → Starter (API keys) | X, dev communities, API docs |

Pricing is in INR and support is via an Indian contact, so the launch geography is **India-first**. English copy; no regional-language variants in v1.

---

## 4. Funnel and offers

```
Content / outreach ──► "Start free" (Community, /sign-up)
                        │  activation = first credential issued + verification page opened
                        ▼
                  "Talk to us" (support@intelliforge.tech)
                        │  cohort ≥ ~30 or needs CSV/artwork/API
                        ▼
                  Starter ₹2,999 → Growth ₹9,999
```

- **Primary CTA:** Start free → `https://certforge.intelliforge.tech/sign-up` (UTM-tagged, §6).
- **Secondary CTA (ICP A/B with a cohort date):** "Talk to us about your next cohort" → support@intelliforge.tech.
- **Lead magnet:** *The Cohort Certificate Checklist* — a 1-page operator checklist (see `02-lead-magnet.md`). **Ungated** — a free download (PDF/Doc link, `{CHECKLIST_URL}`), because it's used as the value-first follow-up in cold outreach. It sells by being useful; the sign-up CTA sits in its closing box. No fabricated stats.
- **Paid conversion is manual** (no self-serve billing). Every "Talk to us" email must get a founder reply within 1 business day — that SLA *is* the conversion path this month.

---

## 5. Sprint calendar

| Phase | Dates | Focus | Goal |
|---|---|---|---|
| 0 — Setup | Tue 22-Sep → Sun 27-Sep | Fix site inconsistencies, UTM links, demo credential, prospect list, assets | Ready to launch |
| 1 — Launch | Mon 28-Sep → Sun 04-Oct | Founder launch post, P1 Trust, first 25 outreach touches | First free signups |
| 2 — Proof | Mon 05-Oct → Sun 11-Oct | Live demo walkthrough, P2 Time, API post for ICP D | First activated issuers |
| 3 — Objections | Mon 12-Oct → Sun 18-Oct | P3 Control + P4 No lock-in, "why not PDFs" | First "Talk to us" conversations |
| 4 — Convert | Mon 19-Oct → Sun 25-Oct | Case/demo recap, direct offers to activated issuers | First paid Starter |
| Review | Mon 26-Oct | Retro against KPIs, decide next sprint | — |

Day-by-day actions: `03-content-calendar.csv`.

---

## 6. KPIs and tracking

Targets are **goals set by this plan**, not forecasts; replace with real baselines once pulled.

| Stage | Metric | Source | Sprint target |
|---|---|---|---|
| Reach | LinkedIn impressions (founder + page) | LinkedIn analytics | set after week 1 baseline |
| Traffic | Sessions to certforge.intelliforge.tech with `utm_campaign=cohort-launch-oct26` | ⚠️ NOT AVAILABLE — no web analytics MCP; add GA4/Plausible before 28-Sep | set after week 1 |
| Acquisition | Community sign-ups | CertForge admin DB | goal: 40 |
| Activation | Orgs that issued ≥1 credential | CertForge admin DB | goal: 15 |
| Intent | "Talk to us" emails | support@ inbox | goal: 8 |
| Revenue | Paid Starter+ orgs | Billing (manual) | goal: 3 |
| Paid | Spend · paid sign-ups · paid sign-ups that issued ≥1 credential | Ads consoles + admin DB | $100 cap · no target until week-1 data (`04` §5) |
| Outreach | Personalised touches sent / replies | Tracker sheet | 100 sent · reply rate tracked, no target until baseline |

**UTM convention:** `?utm_source={linkedin|x|email|whatsapp|community|google}&utm_medium={organic|dm|outreach|nurture|paid}&utm_campaign=cohort-launch-oct26&utm_content={post-id}`

`whatsapp` = our own WhatsApp profile/broadcasts; `community` = posts in other people's groups (with admin permission). `paid`/`google` are reserved for the DRAFT ads only.

**Setup gaps (⚠️ NOT AVAILABLE):** no Google Analytics / Search Console / CRM MCP is configured here. To enable: add the server to `.mcp.json` (see `.claude/mcp.json.example`) or export weekly numbers into `campaigns/certforge-launch/data/`.

---

## 7. Competitive context 🔍 (vendor-published; verify before any public comparison)

| Tool | Free tier (as published) | Source |
|---|---|---|
| Sertifier | 250 recipients / year; Pro from $250/yr | sertifier.com/blog/best-digital-credentialing-platforms-2026 |
| Certifier | 250 credentials / year | certifier.io/blog/certifier-alternative |
| Certopus | 50 certificates; Standard $29.99/mo for 100/mo | certopus.com/blog/best-digital-credential-platform |
| Credly, Accredible | No free plan | sertifier.com/blog/digital-badge-platforms |

**Implication:** CertForge Community's **500/month free** is materially larger than published free tiers — a strong internal talking point. **Do not name competitors in ads** (platform trademark policies) and re-verify each competitor's current pricing page before using any comparison publicly.

---

## 8. Claims guardrails

- ✅ Say: tamper-evident, signed, verifiable by ID with no login, revocable, Open Badges 3.0, CSV (Starter+) and API, 500 free credentials/month, verification free forever.
- ❌ Don't say: "blockchain", "unforgeable", "fraud-proof", "trusted by N institutions", any conversion/time-saved number, passports or claim-by-email as available, self-serve upgrade.
- "Tamper-evident" ≠ "tamper-proof": editing breaks the signature; it doesn't prevent someone making a fake PDF. Copy should always point the verifier to the ID lookup.

---

## Files

| File | Contents |
|---|---|
| `00-campaign-control.md` | This doc — facts, positioning, funnel, KPIs |
| `01-copy-bank.md` | LinkedIn/X posts, hero variants, ad copy, DM scripts |
| `02-lead-magnet.md` | *The Cohort Certificate Checklist* + outreach email sequence |
| `03-content-calendar.csv` | Day-by-day plan, 22-Sep → 26-Oct |
| `04-paid-plan.md` | $100 test: Google Search + LinkedIn boost, keywords, negatives, decision rules |
| `05-campaignforge-brief.md` | Paste-ready inputs for CampaignForge's New Client / New Campaign forms (`campaignforge-brief` skill) |

## Decisions log

| Date | Decision |
|---|---|
| 21-Sep | Ad budget **USD 100** → `04-paid-plan.md` ($70 Google Search, $30 LinkedIn boost) |
| 21-Sep | AI Bootcamp certificates issued via CertForge this week; doubles as passport/claim test |
| 21-Sep | Pricing page is authoritative; homepage status block to be updated (recommendation above) |

## Unresolved questions

1. Real baselines (signups, active issuers, credentials issued) — who pulls them from the CertForge admin?
2. Is the homepage hero fix going live before Sun 04-Oct? (Gates Google Ads start.)
3. Is Razorpay checkout switched on for real customers? If yes, "Talk to us" can become "Upgrade".
4. Who owns the support@ inbox reply SLA and the ad accounts during the sprint?
5. Which graduate consents to being the public demo credential?
