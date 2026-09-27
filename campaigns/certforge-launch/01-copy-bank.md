# Copy Bank — CertForge Cohort-Credentials Launch

Source of truth: `00-campaign-control.md`. Facts verified 21-Sep-2026 from `certforge.intelliforge.tech` + `/pricing` 🔍 WEB SOURCE.
Founder: **Girish Hiremath, IntelliForge** (confirmed in `campaigns/ai-upskill-cohort/00-campaign-control.md`).
Voice: operator-to-operator, plain, specific, a little dry. No hype. ≤2 emoji per post. Grade 6–8 readability.

**Only promise the ✅ Live column:** verification page, Open Badges 3.0 export, CSV bulk issuance (Starter+), single-credential API, on-demand rendering, issuer revocation. Never: passports, claim-by-email, custom templates, self-serve upgrade, "blockchain," "unforgeable," "fraud-proof," "tamper-proof," invented numbers/testimonials.

**Links.** Primary CTA: `https://certforge.intelliforge.tech/sign-up`. Secondary: `mailto:support@intelliforge.tech`. API docs: `https://api.certforge.intelliforge.tech/docs`. Every tracked link appends:
`?utm_source={linkedin|x|email|whatsapp|community}&utm_medium={organic|dm|outreach}&utm_campaign=cohort-launch-oct26&utm_content={post-id}`
Note: `mailto:` links can't carry query-string UTM in most clients, so outreach emails also carry a distinct subject-line tag matching the `utm_content` id — the mailto string below documents attribution intent even where the client strips it. Demo credential link is not live yet (control doc §2, action open) — every mention uses the placeholder `{DEMO_VERIFY_URL}` with a "pending" note.

---

## 1. Positioning one-liners (5)

1. Certificates your graduates can prove are real — no login, no email, just the ID.
2. One CSV in, a signed credential out for every graduate in the cohort.
3. Revoke a certificate you shouldn't have issued. Edit one, and its signature breaks.
4. Open Badges 3.0, HMAC-SHA256 signed — credentials that don't live and die with one app.
5. Built by an operator who was tired of certificates nobody could check.

### Homepage hero variants (3)

**Hero A — Trust (P1)**
- Headline (48 chars): `Certificates recruiters can verify in one click.`
- Sub: "Sign a cohort's credentials. Each one gets a public verification page any employer can check by ID — no login required."
- CTA: **Start free** → `/sign-up`

**Hero B — honest fix for the "one upload" mismatch**
- Headline (47 chars): `Community is free. CSV bulk issuing is Starter.`
- Sub: "Issue up to 500 credentials a month free, no card — one at a time. Uploading a whole cohort from one CSV is a Starter feature (₹2,999/mo)."
- CTA: **Start free** → `/sign-up` · secondary: **See Starter pricing** → `/pricing`
- Why this variant exists: the current homepage headline ("Ship a cohort's credentials in one upload") describes a Starter-only capability while pointing at the free CTA. Use Hero B wherever traffic is likely to land on Community, until control doc §2 issue 2 (site fix) is resolved.

**Hero C — Control (P3)**
- Headline (50 chars): `Issue certificates you can revoke, not just print.`
- Sub: "Every CertForge credential is signed and publicly verifiable by ID. Issue the wrong one? Revoke it. Edit one? The signature breaks."
- CTA: **Start free** → `/sign-up`

---

## 2. LinkedIn — founder posts (9)

Each labeled: **Phase · Pillar · ICP · utm_content**. Link = `/sign-up` unless noted.

### li-01 — Founder launch post
**Phase 1 · Pillar P1 (Trust) · ICP A · Format: problem → product**

> Founder: if you have a *real* moment where a certificate got questioned, swap it in for the first two paragraphs — in your words, with nothing invented. Don't add a story that didn't happen.
```
A lot of cohorts end with a folder of PDFs.

They look official. But the first time a recruiter asks a graduate "how do we know this is real?", there's no good answer — a PDF can be edited in minutes, and checking it means emailing the issuer and waiting.

We run cohorts at IntelliForge too, so we built CertForge.

What it does: sign a cohort's credentials, and give each one a public page any employer can check from the credential ID alone. No login for the recruiter. No emailing the issuer. No spreadsheet only you can read.

Verification is free and public, forever.

If you run bootcamps, internships or events and you're still hoping nobody asks a graduate to "prove it" — this is for you.

Free to start: 500 credentials/month, hosted verification pages, QR codes, no card.

Start free → https://certforge.intelliforge.tech/sign-up?utm_source=linkedin&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=li-01
```

### li-02 — How it works
**Phase 1 · Pillar P2 (Time) · ICP A/B · Format: how-it-works**
```
How a cohort actually gets signed:

1. You add credential data — one at a time, or (on Starter) upload a CSV for the whole batch.
2. CertForge validates every row before anything is signed. Bad row = flagged, not a broken certificate.
3. Each credential is signed (HMAC-SHA256) and rendered on demand — no giant PDF folder to store.
4. Every credential gets its own public verification page. Recipients don't need an account to have one, and employers don't need one to check it.
5. Issued the wrong thing? You can revoke it. Editing a signed credential breaks the signature — that's the point.

Free tier covers 500 credentials/month. Starter (₹2,999/mo) adds CSV bulk upload and API access for bigger cohorts.

Docs → https://api.certforge.intelliforge.tech/docs?utm_source=linkedin&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=li-02
```

### li-03 — Myth vs fact: "PDF certificates"
**Phase 1 · Pillar P1 (Trust) · ICP A · Format: myth vs fact**
```
Myth: "A PDF certificate with our logo is proof enough."

Fact: it's proof of nothing. Anyone can open it in an editor and change the name, the date, the grade. There's no way for a recruiter to tell the real one from the edited one.

What actually holds up: a credential that's signed, where editing it breaks the signature, and where anyone can check it independently — by the credential ID, no login, no email to your team.

That's the bar CertForge sets. Not "looks official." Checkable.

Start free → https://certforge.intelliforge.tech/sign-up?utm_source=linkedin&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=li-03
```

### li-04 — Checklist (ties to lead magnet)
**Phase 2 · Pillar P2 (Time) · ICP A/B · Format: checklist**
```
Before your next cohort ends, check these five things:

☐ Does every certificate have a unique ID a recruiter can look up?
☐ Can someone verify a certificate without emailing you?
☐ If you issue a wrong one, can you revoke it — or is it just "out there"?
☐ If a graduate loses their file, can they get a new copy without you touching Canva again?
☐ Is your validation step before you sign 60 certificates, or after someone spots the typo?

We wrote a one-page version of this for operators — free, no fabricated stats, just the checklist. Grab it and start free: https://certforge.intelliforge.tech/sign-up?utm_source=linkedin&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=li-04
```

### li-05 — Behind the build: validation before signing
**Phase 2 · Pillar P2/P3 · ICP A · Format: behind-the-build**
```
The feature I argued hardest for internally wasn't the signing. It was the step before it.

When you upload a cohort's data, CertForge validates every row first — and shows you the errors row by row, before anything gets signed.

Why that matters: a signed credential can't be quietly edited. The signature breaks. Which means the moment to fix a misspelled name isn't "after the batch is printed" — it's before the sign step, where it's just a data fix, not a reissue.

Small feature. Saves the most annoying part of running a cohort.

Start free → https://certforge.intelliforge.tech/sign-up?utm_source=linkedin&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=li-05
```

### li-06 — API post
**Phase 2 · Pillar P4 (No lock-in) · ICP D · Format: technical**
```
If you're building your own LMS or internal tool and don't want to build a signing + verification layer from scratch — CertForge has a single-credential REST API.

Issue signed, Open Badges 3.0-compliant credentials from your own app. Each one still gets a public verification page and a revocation option, without you building either.

API access is on Starter (₹2,999/mo) — same tier as CSV bulk issuance.

Docs → https://api.certforge.intelliforge.tech/docs?utm_source=linkedin&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=li-06
```

### li-07 — Coming soon (roadmap, clearly not-yet-available)
**Phase 3 · Pillar general · ICP A/B/C · Format: roadmap**
```
What's live today vs. what we're still building — being upfront about both.

Live now: public verification pages, Open Badges 3.0 export, CSV bulk issuance and API access (Starter+), issuer revocation, on-demand rendering.

In build, not available yet: recipient credential "passports," claim-by-email, custom certificate templates, usage/quota reporting. None of these are ready — don't plan a launch around them landing on a specific date. We'll post here when they ship.

If today's feature set solves your cohort's problem, start free. If you need something from the "in build" list, tell us — it helps us prioritize.

https://certforge.intelliforge.tech/sign-up?utm_source=linkedin&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=li-07
```

### li-08 — Objection / Control: "why not just keep using PDFs"
**Phase 3 · Pillar P3 (Control) · ICP C · Format: objection**
```
Ran a hackathon or workshop and issued 200 "certificates of participation" as PDFs? Here's what you can't do with those:

— You can't revoke one if you issued it by mistake.
— You can't prove, to anyone who asks, that it wasn't edited after the fact.
— You can't point a recruiter anywhere to check it. They just have to trust the PDF.

A signed CertForge credential fixes all three: revocable, tamper-evident (editing breaks the signature), and checkable by ID with no login. Community plan covers up to 500 credentials/month free — enough for most single events.

Start free → https://certforge.intelliforge.tech/sign-up?utm_source=linkedin&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=li-08
```

### li-09 — Direct offer (Phase 4 convert)
**Phase 4 · Pillar P2/P4 · ICP A/B · Format: direct offer**
```
If you've been testing CertForge on Community and your next cohort needs CSV bulk upload, custom artwork, or API access — that's Starter, ₹2,999/month.

No self-serve checkout yet — email support@intelliforge.tech and tell us your cohort size and start date. I personally reply to every "Starter" email within a business day.

Talk to us → mailto:support@intelliforge.tech?utm_source=email&utm_medium=outreach&utm_campaign=cohort-launch-oct26&utm_content=li-09 (subject: "Starter — [your org]")
```

---

## 3. LinkedIn company page (4 shorter posts)

### lc-01 — Phase 1 · P1 Trust
```
A certificate that only your team can vouch for isn't a credential — it's a promise. CertForge signs each one and gives it a public page any employer can check by ID. No login needed on either end.

Free to start, 500 credentials/month → https://certforge.intelliforge.tech/sign-up?utm_source=linkedin&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=lc-01
```

### lc-02 — Phase 2 · P2 Time
```
Cohort ending? Issue every credential in one place, with validation before anything is signed — so typos get caught before certificates go out, not after.

CSV bulk issuance is on Starter; Community is free for single issuance up to 500/month.
https://certforge.intelliforge.tech/sign-up?utm_source=linkedin&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=lc-02
```

### lc-03 — Phase 3 · P4 No lock-in
```
Your credentials shouldn't be trapped in one vendor's app. CertForge exports to Open Badges 3.0 — an open standard, not a proprietary badge only our site can read.

https://certforge.intelliforge.tech/sign-up?utm_source=linkedin&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=lc-03
```

### lc-04 — Phase 4 · P3 Control
```
Issued the wrong credential? Revoke it. Someone edits a signed one? The signature breaks and it stops verifying. That's what "tamper-evident" means here — not a marketing word, the actual mechanism.

Talk to us about your next cohort → mailto:support@intelliforge.tech?utm_source=email&utm_medium=outreach&utm_campaign=cohort-launch-oct26&utm_content=lc-04
```

---

## 4. X / dev community (6 posts)

### x-01 — Thread: "How verification by ID works" (5 tweets)
**Phase 2 · Pillar P1/P4 · ICP D**

```
1/5
How does a CertForge credential actually get verified? A short thread on the mechanism, not the marketing. 🧵

2/5
Every credential is signed with HMAC-SHA256 at issuance. The signature is tied to the credential's data — name, issuer, date, etc. Change any of it after signing, and the signature no longer matches. That's the "tamper-evident" part.

3/5
Each credential exports to Open Badges 3.0, an open standard — not a proprietary format you're locked into reading only on our site.

4/5
Every credential gets its own public verification page, rendered on demand from the credential ID. No login for the verifier. No email to the issuer. Just the ID.

5/5
Issuer makes a mistake? They can revoke the credential — the public page reflects that. Build your own issuance flow on this via the API: https://api.certforge.intelliforge.tech/docs?utm_source=x&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=x-01
```

### x-02 — Phase 1 · P1 · ICP A
```
A PDF certificate proves you own image-editing software. It doesn't prove anything about the credential. CertForge signs each one so it can be checked independently, by ID. Free to start: https://certforge.intelliforge.tech/sign-up?utm_source=x&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=x-02
```

### x-03 — Phase 2 · P2 · ICP A/B
```
Validation runs before signing, not after. Row-by-row errors on your CSV get flagged before a single credential is issued. Fix the typo before it's signed, not after 60 are printed. https://certforge.intelliforge.tech/sign-up?utm_source=x&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=x-03
```

### x-04 — Phase 2 · P4 · ICP D
```
Building credentialing into your own app? Single-credential REST API, Open Badges 3.0 output, public verification pages handled for you. Docs: https://api.certforge.intelliforge.tech/docs?utm_source=x&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=x-04
```

### x-05 — Phase 3 · P3 · ICP C
```
Ran a hackathon and issued 300 participation certs as PDFs? You can't revoke one, can't prove none were edited, can't give anyone a way to check them. Free tier covers 500/month if you want a fix for the next one. https://certforge.intelliforge.tech/sign-up?utm_source=x&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=x-05
```

### x-06 — Phase 4 · P2/P4 · ICP A/B
```
500 free credentials/month, forever, no card. CSV bulk + API on Starter (₹2,999/mo) when a cohort outgrows one-at-a-time. No blockchain, no "trust us" — just a signature you can check. https://certforge.intelliforge.tech/sign-up?utm_source=x&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=x-06
```

---

## 5. WhatsApp/Telegram community blurbs (3)

For organiser/edtech groups you don't own. Ask admin permission before posting; do not mass-DM members.

**Admin permission line (send first, in every group):** "Hi — I run CertForge, a credential-issuing tool for cohorts/events. Mind if I share a short, non-promotional post about certificate verification for the group? Happy to skip if it's not a fit."

### wa-01 — general edtech/organiser groups
```
Quick one for anyone issuing certificates to a batch/cohort: if a recruiter or sponsor ever asks "how do I know this is real," a PDF with your logo doesn't answer that.

We built CertForge for exactly this — each certificate gets a public page checkable by its ID, no login needed by whoever's checking. Free for up to 500/month, no card.

Not selling anything in this thread, just flagging it in case it's useful: https://certforge.intelliforge.tech/sign-up?utm_source=community&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=wa-01
```

### wa-02 — hackathon/event organiser groups
```
For event organisers: if you're printing "certificate of participation" PDFs for 100+ people and then getting "can you resend mine" DMs for weeks after — there's a lighter way. Sign once, each person gets their own verification page, no reprints.

Community plan is free, 500 credentials/month. Sharing in case anyone here is running an event soon: https://certforge.intelliforge.tech/sign-up?utm_source=community&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=wa-02
```

### wa-03 — bootcamp/internship operator groups
```
For anyone running a bootcamp or internship cohort: worth checking whether your certificates are actually verifiable, not just nice-looking. CertForge signs each credential and gives it a public check-by-ID page — built by someone running his own AI cohort who hit this exact problem.

Free to try, 500/month, no card: https://certforge.intelliforge.tech/sign-up?utm_source=community&utm_medium=organic&utm_campaign=cohort-launch-oct26&utm_content=wa-03
```

---

## 6. Founder outreach — LinkedIn DM scripts

Connection note ≤300 chars + 2 follow-ups, one variant per ICP.

### ICP A — Bootcamp/cohort operators

**Connection note (208 chars):**
```
Hi [Name] — I run IntelliForge (we run cohorts too) and built CertForge so employers can check a certificate from its ID. Saw you run [bootcamp/cohort name] and thought it might be relevant. Open to connecting either way.
```

**Follow-up 1 (after accept):**
```
Thanks for connecting. Quick context on why I reached out: CertForge signs a cohort's certificates and gives each one a public verification page an employer can check by ID — no login, no emailing you. Free for up to 500/month, no card. If certificate verification has ever come up for your graduates, happy to show you how it works — no pitch, just a look. https://certforge.intelliforge.tech/sign-up?utm_source=linkedin&utm_medium=dm&utm_campaign=cohort-launch-oct26&utm_content=dm-a-f1
```

**Follow-up 2 (no reply, ~5 days later):**
```
No worries if this isn't a priority right now — just wanted to leave the door open. If a recruiter or sponsor ever asks how to verify one of your certificates, this solves exactly that, free to start. If your cohort is big enough to need bulk CSV upload, that's on our Starter plan (₹2,999/mo) — happy to talk through it whenever's useful. https://certforge.intelliforge.tech/sign-up?utm_source=linkedin&utm_medium=dm&utm_campaign=cohort-launch-oct26&utm_content=dm-a-f2
```

### ICP B — Internship programme managers

**Connection note (198 chars):**
```
Hi [Name] — I built CertForge, a tool for signing and verifying certificates for cohorts/interns. Noticed you manage internship batches at [org] and thought it might save you the "resend my certificate" emails.
```

**Follow-up 1:**
```
Thanks for connecting. The problem I built this for: seasonal intern batches, name-spelling errors caught after printing, and the endless "can you resend my certificate" thread. CertForge validates each row before signing, so typos get caught first — and every certificate gets its own public page, so interns don't need to email you for proof later. Free for up to 500/month. https://certforge.intelliforge.tech/sign-up?utm_source=linkedin&utm_medium=dm&utm_campaign=cohort-launch-oct26&utm_content=dm-b-f1
```

**Follow-up 2:**
```
Following up in case this got buried — no pressure. If your next intern batch is coming up and you want to try it on one cohort before deciding anything, Community is free and takes a few minutes to set up. Glad to walk through it live if that's easier than reading docs. https://certforge.intelliforge.tech/sign-up?utm_source=linkedin&utm_medium=dm&utm_campaign=cohort-launch-oct26&utm_content=dm-b-f2
```

### ICP C — Event/hackathon organisers

**Connection note (183 chars):**
```
Hi [Name] — saw you organise [event/hackathon]. I built CertForge for issuing participation/winner certificates that people can actually verify. Thought it might be useful for your next one.
```

**Follow-up 1:**
```
Thanks for connecting. If you've ever mass-emailed "certificate of participation" PDFs and then fielded "can you resend mine" for weeks after — CertForge fixes that. Sign once, each attendee gets a public verification page, no reprints, no reissue emails. Free plan covers 500 credentials/month, which handles most single events. https://certforge.intelliforge.tech/sign-up?utm_source=linkedin&utm_medium=dm&utm_campaign=cohort-launch-oct26&utm_content=dm-c-f1
```

**Follow-up 2:**
```
No rush on this — just circling back. If you've got an event coming up, happy to help you set up the credential template beforehand so issuance is a five-minute job right after the event ends, not a week of PDF-making. https://certforge.intelliforge.tech/sign-up?utm_source=linkedin&utm_medium=dm&utm_campaign=cohort-launch-oct26&utm_content=dm-c-f2
```

---

## 7. Ads — ACTIVE ($100 test, see `04-paid-plan.md`)

Budget approved 21-Sep: $70 Google Search (Phases 2–4) + $30 LinkedIn Thought Leader boost of the best organic founder post (Phase 3). The three LinkedIn single-image ads below are **reserve creative** — not in the $100 plan. UTM values `utm_source=google` and `utm_medium=paid` are now in control doc §6.

### LinkedIn single-image ads (3)

**Ad 1 — Trust (P1), ICP A**
- Headline: "Certificates your recruiters can actually check"
- Body: "CertForge signs each credential and gives it a public verification page — checkable by ID, no login. Free for up to 500 credentials/month, no card."
- CTA: **Start free** → `https://certforge.intelliforge.tech/sign-up?utm_source=linkedin&utm_medium=paid&utm_campaign=cohort-launch-oct26&utm_content=ad-li-01`

**Ad 2 — Time/CSV, ICP A/B (Starter, stated honestly)**
- Headline: "Bulk-issue a cohort's certificates from one CSV"
- Body: "Validate every row before anything's signed. CSV bulk issuance is on Starter (₹2,999/mo); Community is free for single-credential issuance up to 500/month."
- CTA: **See plans** → `https://certforge.intelliforge.tech/pricing?utm_source=linkedin&utm_medium=paid&utm_campaign=cohort-launch-oct26&utm_content=ad-li-02`

**Ad 3 — API, ICP D**
- Headline: "Issue signed credentials from your own app"
- Body: "Single-credential REST API, Open Badges 3.0 output, public verification pages handled for you. API access is on Starter (₹2,999/mo)."
- CTA: **View API docs** → `https://api.certforge.intelliforge.tech/docs?utm_source=linkedin&utm_medium=paid&utm_campaign=cohort-launch-oct26&utm_content=ad-li-03`

### Google Search RSA

**15 headlines (≤30 chars, count shown):**
| # | Headline | Chars |
|---|---|---|
| 1 | Free Certificate Issuing | 24 |
| 2 | 500 Free Credentials/Month | 26 |
| 3 | Verify by ID, No Login | 22 |
| 4 | Signed Cohort Credentials | 25 |
| 5 | CSV Bulk Certificate Issuing | 28 |
| 6 | Open Badges 3.0 Export | 22 |
| 7 | Revoke Certificates Anytime | 27 |
| 8 | Tamper-Evident Credentials | 26 |
| 9 | Stop Emailing PDF Certs | 23 |
| 10 | Certificates Anyone Can Verify | 30 |
| 11 | API for Credential Issuing | 26 |
| 12 | No Recipient Account Needed | 27 |
| 13 | Bootcamp Certificate Tool | 25 |
| 14 | Hackathon Certificates Fast | 27 |
| 15 | Start Free, No Card Needed | 26 |

**4 descriptions (≤90 chars, count shown):**
| # | Description | Chars |
|---|---|---|
| 1 | Validate every row, then sign. CSV bulk on Starter; 500 credentials/mo free. | 76 |
| 2 | Verification is free and public, forever — no login, no emailing the issuer. | 76 |
| 3 | 500 credentials/month free. Open Badges 3.0. HMAC-SHA256 signed. Start free today. | 82 |
| 4 | Revoke a wrong certificate instantly. Editing one breaks its signature. | 71 |

Final URL: `https://certforge.intelliforge.tech/sign-up?utm_source=google&utm_medium=paid&utm_campaign=cohort-launch-oct26&utm_content=ad-rsa-01`

---

## 8. Objection handling (8)

1. **"We just email PDFs to graduates."**
   A PDF proves nothing on its own — anyone can edit it. CertForge signs each credential and gives it a public page checkable by ID, so a recruiter doesn't have to take your word (or the PDF's) for it.

2. **"Our LMS already generates certificates."**
   Most LMS-generated certificates aren't independently verifiable — there's no public page or signature check. CertForge sits on top: sign, host a verification page, allow revocation. It doesn't require replacing your LMS.

3. **"Is this on blockchain?"**
   No. Credentials are signed with HMAC-SHA256, and Open Badges 3.0 is the export standard. Editing a signed credential breaks the signature — that's what makes it tamper-evident. No blockchain involved.

4. **"What if CertForge shuts down someday?"**
   Every credential exports to Open Badges 3.0, an open standard. It isn't locked into our app — a graduate's credential data is portable if that ever happened.

5. **"Do recipients need to create an account?"**
   No. No recipient account is required to receive, hold, or have their credential verified.

6. **"Can we bulk-upload our whole cohort for free?"**
   Not on Community. Community is free for issuing credentials one at a time, up to 500/month. CSV bulk upload and API access are on Starter (₹2,999/mo).

7. **"How is a 'signed' certificate different from a PDF with a QR code to a Google Sheet?"**
   A QR code just links to a sheet you control — anyone with edit access can change it, quietly. A signed credential's data is cryptographically tied to its signature; changing the data invalidates the signature, and that's visible on the public verification page.

8. **"What if I issue the wrong certificate to someone?"**
   Revoke it. Issuer revocation is a live feature — the credential's public page reflects the revoked status.

---

## 9. Visual/creative briefs (5)

No fabricated stats on any image — text pulls only from the verified facts above.

**Brief 1 — Hero split-screen (static)**
Layout: left half a mock certificate card; right half its verification page (credential ID field, green "Verified" state, issuer name, issue date). Text on image: "One credential ID. One public page." Small caption line: "No login to check it." Pairs with hero copy §1 / li-01.

**Brief 2 — "PDF vs. Signed Credential" carousel (4 slides)**
1. Cover: "A PDF certificate vs. a signed credential."
2. Slide: PDF side — "Editable. No independent check. No revoke."
3. Slide: CertForge side — "Signed. Public verification by ID. Revocable."
4. CTA slide: "Free to start — 500 credentials/month, no card." + sign-up link. No comparison numbers or claims beyond these mechanism facts.

**Brief 3 — Community plan card (static)**
Layout: single pricing-card mock styled like the real Community tier. Text on image, verbatim from pricing table only: "Free · 500 credentials/month · 1 template · Hosted verification pages · QR codes · Email delivery." No card. Caption: "No card, no catch."

**Brief 4 — "Fix it before it's signed" screenshot mock**
Layout: mock CSV upload table with one row highlighted red (e.g., misspelled name) and an inline error message, next to a greyed-out "Sign" button until fixed. Text on image: "Caught before it's signed." Ties to li-05 / P2.

**Brief 5 — "How verification works" carousel (4 slides, for x-01 thread / ICP D)**
1. Cover: "How CertForge verification actually works."
2. Slide: "1. Credential is signed (HMAC-SHA256) at issuance."
3. Slide: "2. Anyone can look it up by ID — public page, no login."
4. Slide: "3. Issuer can revoke it anytime; the page reflects that." + API docs link for developers.

---

## Unresolved questions

1. Section 7's ad UTMs need `utm_medium=paid` (and Google needs `utm_source=google`) — neither is in the control doc's §6 UTM value list. Confirm/add before any paid spend.
2. `{DEMO_VERIFY_URL}` isn't live yet (control doc §2, action item 4) — no post here references an actual demo credential; swap the placeholder in once a graduate consents and the link exists.
3. Control doc §6 UTM source list has both `whatsapp` and `community` as separate values but only describes one WhatsApp/Telegram channel (organiser & edtech groups). This bank used `utm_source=community` for §5 blurbs on the assumption that's third-party-group posting, distinct from an owned WhatsApp channel — confirm that split is intended, or that `whatsapp` should be used instead.
4. No web analytics MCP is connected (control doc baseline note) — none of the UTM links in this bank can be verified as tracking correctly until GA4/Plausible (or equivalent) is wired up before 28-Sep.
5. Ad section assumes organic-only per control doc §5 open question — confirm before treating §7 as anything but draft.
