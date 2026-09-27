# CertForge — Paid Plan ($100 test)

**Budget:** USD 100 total, approved 21-Sep-2026 (user-provided). Organic plan (`00`–`03`) is unchanged; paid runs alongside it in Phases 2–4.
**Purpose:** learn *which search intent brings operators who issue a credential* — not to drive volume. At this budget, treat every result as a signal, not a verdict.
**Performance forecasts:** none. No CPC/CTR/conversion estimates are given — there is no ads or keyword MCP connected (⚠️ NOT AVAILABLE). Judge on real data from week 1 of spend.

---

## 1. Allocation

| Channel | Budget | When | Why |
|---|---|---|---|
| **Google Search** | **$70** | Mon 05-Oct → Sun 25-Oct (≈ $3.30/day) | Only channel that reaches operators *while they are looking* for a certificate tool. Starts Phase 2, after the demo credential and site fixes are live. |
| **LinkedIn Thought Leader Ad** | **$30** | 3 days in Phase 3 (Tue 13 → Thu 15-Oct) | Boost the best-performing *organic* founder post (by comments/sign-ups from its UTM) to ICP A/B job titles. Promotes a post that already proved it resonates instead of guessing with new creative. LinkedIn enforces a minimum daily budget (currently $10/day — confirm in Campaign Manager), so $30 = 3 days. |
| Meta | $0 | — | Weak B2B job-title targeting; $100 is too small to split three ways. |

**Hold rule:** if homepage inconsistency #1 (the "one upload" headline vs Starter-only CSV, control doc §1) is not fixed by Sun 04-Oct, **do not start Google** — paid clicks would land on a promise the free plan can't keep. Move the $70 to Phase 3–4 instead.

---

## 2. Prerequisites (Setup week, before any spend)

1. **Sign-up conversion tracking.** Add the Google tag / GA4 to certforge.intelliforge.tech and fire a `sign_up` event on successful Community registration. Import it as the Google Ads conversion. Without it, bid on clicks and judge from the admin DB (§5).
2. **UTM links** from control doc §6: `utm_source=google|linkedin`, `utm_medium=paid`, `utm_campaign=cohort-launch-oct26`.
3. **Billing:** Google Ads bills in the account currency; set the account-level budget cap so total spend cannot exceed the USD 100 equivalent.
4. **Landing page:** Google → `/sign-up` only once fix #1 is live; otherwise → `/pricing` (states plans honestly).

---

## 3. Google Search setup

| Setting | Value |
|---|---|
| Campaign type | Search only (untick Display Network and Search Partners) |
| Location | India — "Presence: people in or regularly in" (not "interest in") |
| Language | English |
| Bidding | **Maximize clicks** with a max CPC cap until ≥15 tracked sign-ups exist; do not use conversion bidding on no data |
| Schedule | Mon–Sat, 09:00–20:00 IST (operators search in working hours) |
| Ad group structure | 3 ad groups below, 1 RSA each |

### Ad groups and keywords (phrase + exact match only — no broad match at this budget)

Search volumes: ⚠️ NOT AVAILABLE (no SEO/keyword MCP). Use Google Keyword Planner in the account to drop any keyword with no volume before launch.

| Ad group | Keywords (phrase unless [exact]) | ICP |
|---|---|---|
| **AG1 · Bulk issuing** | "bulk certificate generator" · "certificate generator for students" · "certificate maker for workshop" · "e certificate generator" · [bulk certificate generator] · "certificate generator from excel" | A/B/C |
| **AG2 · Verifiable** | "verifiable certificates" · "digital credentials platform" · "certificate verification system" · "open badges" · "digital badges for courses" · [verifiable digital certificates] | A/D |
| **AG3 · Events** | "hackathon certificates" · "participation certificate generator" · "webinar certificate generator" · "event certificate software" | C |

### Negative keywords (campaign level) — the most important part at this budget

```
ssl, tls, https, domain, "digital signature", dsc, "class 3", "class 2", emudhra, pfx, openssl, csr,
birth, death, income, caste, domicile, residence, marriage, "character certificate", "bonafide",
gst, pan, aadhaar, "police verification", "medical certificate", "fitness certificate",
"free courses", "online courses", "course with certificate", "free certificate course", nptel, coursera, udemy, "google certificate",
"certificate of deposit", fd, insurance,
template, canva, word, psd, "ms word", ppt, "free download", png, "background",
job, jobs, salary, "internship certificate format", "internship certificate sample",
"how to get", "download my", "my certificate", "lost certificate", "duplicate certificate"
```

Review the **search terms report every 3 days** and add new negatives. Expect most early irrelevant clicks to be learners looking for their own certificate — that is the main waste to cut.

### RSA copy

Use `01-copy-bank.md` §7 headlines/descriptions (character counts verified there). Pin H4 "Signed Cohort Credentials" or H3 "Verify by ID, No Login" to position 1 in AG2; pin H14 "Hackathon Certificates Fast" in AG3. Use description D1 only in AG1 (it names Starter).

---

## 4. LinkedIn Thought Leader Ad

- **Which post:** the founder post (`li-01`…`li-06`) with the most sign-ups by `utm_content` after two weeks; tie-break on comments from ICP A/B. Not a new ad.
- **Audience (India):** Job functions *Education* + *Human Resources* + *Operations*; titles like Founder, Co-founder, Program Manager, Training Manager, Placement Officer, Community Manager, Head of Learning; company industries *E-Learning Providers*, *Education Administration Programs*, *Higher Education*, *Events Services*. Keep the audience above LinkedIn's minimum size.
- **Objective:** Website visits. **Budget:** $10/day × 3 days, lifetime cap $30.
- Tracked link: swap the post's link for the same URL with `utm_medium=paid&utm_content=ad-li-boost` (a promoted post's clicks must not be counted as organic).

---

## 5. Measurement and decisions

| Metric | Source | Check |
|---|---|---|
| Spend, clicks, search terms | Google Ads / LinkedIn Campaign Manager | Every 3 days |
| Sign-ups with `utm_medium=paid` | CertForge admin DB (org created + first-touch UTM) | Weekly |
| Paid sign-ups that issued ≥1 credential | CertForge admin DB | Weekly |
| Cost per activated issuer | Spend ÷ activated paid sign-ups | End of sprint |

Decision rules (write the real numbers in, don't estimate):
- **Pause an ad group** when it has spent $20 with zero sign-ups *and* its search terms show learner/government intent.
- **Shift budget** to the ad group with the most activated issuers, not the most clicks.
- **After the sprint:** paid continues only if at least one paid sign-up activated. Otherwise the $100 bought a negative-keyword list and a clear "not yet" — record that in the retro.

---

## 6. Claims check for ads

Same guardrails as control doc §8, plus platform policy:
- No competitor names in ad text (trademark policy).
- "Free" only alongside what's free: 500 credentials/month on Community; CSV and API are Starter.
- No "blockchain", "fraud-proof", "tamper-proof", no numbers that aren't in the control doc.

## Unresolved questions

1. Who owns the Google Ads and LinkedIn Campaign Manager accounts, and is a payment method attached?
2. Is fix #1 (headline vs Starter CSV) going live before Sun 04-Oct? If not, Google starts in Phase 3 on `/pricing`.
3. Can the CertForge admin record a sign-up's first-touch UTM? If not, paid attribution is click-only.
