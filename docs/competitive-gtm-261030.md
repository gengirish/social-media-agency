# CampaignForge AI — Competitive deep dive, GTM, build-next

<!-- created: 261030 -->

Re-run of [competitive-analysis-gtm.md](competitive-analysis-gtm.md) (260817) against the 260926 pricing ($20 / $36 / $168) and the market as of 261030. Supersedes that doc's §3–§7. Internal facts come from code read today; external prices marked **(official, 261030)** were fetched from the vendor's own pricing page today, everything else is third-party and dated. Nothing is projected.

---

## Bottom line

1. **The hole is still open and nobody has moved into it.** No agency scheduler, AI-native social tool, platform freebie or funded autonomous agent produces a *client-ready, approved, branded campaign pack* from one brief. Everyone's AI still starts after the strategy exists. But the hole has narrowed: Pomelli (free, global) kills the SMB-direct story, Sprites and Epiminds now say "for agencies", and GoHighLevel sells AI inside the platform most small agencies already run on.
2. **The product today *is* the export-first wedge** the 260817 analysis asked for — `OAUTH_CONNECT_ENABLED = false` since 260930, so a new user can only generate → moderate → approve → post it themselves. The landing page still says "Publish straight to X, LinkedIn, and Facebook". That is a rule-1 violation and the cheapest fix in this doc.
3. **Pricing was re-anchored to the wrong category.** Metricool's $25 Starter is a scheduler price for solo marketers; CampaignForge does not replace Metricool (it cannot even connect an account right now). At $36 for 10 clients the product charges $3.60 per client against a $2,107 average retainer. Do not re-price a third time pre-revenue — but stop treating the anchor as settled.
4. **GTM is unchanged and still blocked on the same thing:** five design partners. Nothing else (SEO pages, Zapier listing, cold email, free tool) is worth doing until one agency has run a real retainer through it.
5. **Build next, in order:** (1) landing honesty, (2) the branded Campaign Pack export — the deliverable that is the whole wedge, (3) hand-off to the scheduler they already use, (4) per-client approval links — which is also a security fix: the portal is unauthenticated, org-wide, and lets anyone with the slug approve any client's content.

---

## 1. What changed since 260817

| | 260817 | 261030 |
|---|---|---|
| Pricing | $49 / $149 / $399, agency-anchored | $20 / $36 / $168, 20% under Metricool |
| Direct publishing | X, LinkedIn, FB connectable | OAuth connect **off** in UI ("Coming soon"); manual channels are the path. Publishers intact |
| Instagram | not implemented | publisher built (#16), switched off; needs Meta review |
| Media | fal.ai images | images + video credits, attached to posts |
| Create surface | campaigns + Amplify | Content, Email, Launch, Ads, Post Studio, Brand Voice, Strategy Lens, Inbox, Insights |
| Billing | Stripe, unprovisioned | Dodo, provisioned, **zero charges ever** |
| Design partners | none | none |
| Market | Uplane launch, Pomelli not yet public | Uplane $4.5M seed; Pomelli free + global; Sprites/Epiminds "for agencies"; Hootsuite/Sprout shipped agents; $3.7B into AI sales/marketing YTD by May |

Net: the product got much wider and the price got much lower, and neither was tested on a customer.

---

## 2. Competitive map — five rings

### Ring A — Agency schedulers (what the ICP pays for today)

| Platform | Entry | Mid | Agency / white-label | Seats | Approval | AI scope |
|---|---|---|---|---|---|---|
| **Metricool** (official, 261030) | from $25/mo, 5 brands ($20 annual) | Advanced from $67/mo, 15 brands (annual: 15/$53, 25/$85, 50/$159) | WL **Custom only**, quote | not published | Advanced+ | 5 / 20 / 35 AI credits per brand/mo |
| **Cloud Campaign** (official, 261030) | $49 Freelancer, 1+ workspace | $199 Team, 5+ ws | $299 Agency, advanced WL; extra workspace $29–35 | **unlimited, all tiers** | all tiers | captions, images, inbox replies |
| **Vista Social** (official, 261030) | $99, 15 profiles, 2 users | $199, 30 profiles | $449 Scale, 70 profiles, WL | 2 / 3 / 4 | all tiers | 1,000–3,500 credits; "Ask Vista + **MCP**" |
| **SocialPilot** (official, 261030) | $20, 5 accounts | $40 | $100 Premium: WL reports, unlimited client seats, approval · $200 Ultimate: advanced WL, unlimited users | 1 / 3 / 6 / ∞ | Premium+ | 500 → unlimited credits |
| **Sendible** (3rd-party, Aug 2026) | $35 Core | $99 / $199 | $299 Elite + WL add-on (price disputed, $240–349) · $750 Enterprise | unlimited | Plus+ | assistant |
| **Planable** (3rd-party, Oct 2026) | $39 / **workspace** | $59 / workspace | Enterprise quote; Inbox +$9, Analytics +$12 | — | **core product** | minimal / disputed |
| Hootsuite / Sprout (3rd-party) | $99 Pro / $199 per seat | | internal teams, not resale | per seat | yes | Hootsuite "Social OS" + Wisdom agent (Jun 2026); Sprout Trellis — both draft, humans send |
| Buffer (3rd-party) | $6 / channel | | none | | | caption assistant |

Read: the segment has converged on **per-workspace** or **per-brand** metering, unlimited or generous seats, and approval workflows as table stakes. White-label is a $100–$449 feature. None of them do strategy; AI is captions and replies on credit meters.

### Ring B — AI-native social content (SMB, prosumer)

FeedHive and Ocoya $29 / $79 / $199 Agency (pooled brands); Blaze ~$27–85 + $20/mo white-label add-on; Predis ~$29–36. All third-party, several conflicting. Per-post generation with a scheduler; no strategy layer, no SEO, no ads, no client sign-off. Price floor for "AI writes my posts" is ~$27 and falling.

### Ring C — Funded autonomous marketing agents

| Company | Money | Buyer | Scope | Price |
|---|---|---|---|---|
| Uplane (YC F25) | $4.5M seed, Apr 2026 (Play Ventures, YC, 20VC) | brand / enterprise, "managed growth" | ads, landing pages, Meta/Google/TikTok spend | undisclosed, sales-led |
| Sprites (YC) | — | **"agencies and enterprise"** | Google/Meta/LinkedIn/TikTok/Reddit ads + SEO + AI visibility; **white-label reporting included** | undisclosed |
| Epiminds "Lucy" (Stockholm) | $6.6M, Oct 2025 | **agencies first**; claims 240+ brands | 20+ agents: reporting, pacing, bidding, creative; Slack/email | beta |
| Kana | $15M seed, Feb 2026 (Mayfield) | marketers | agentic marketing | — |
| Gradial | $65M Series C, Jun 2026 | enterprise (T-Mobile) | marketing ops | — |
| AdsGency / Playad / Plurio | $12M / $5.4M / $3.5M | performance teams | ad creative + testing | — |

Sector: ~$3.7B raised into AI sales & marketing by May 2026 (Crunchbase via ppc.land). Centre of gravity is **paid media and enterprise**, sold by humans. "For agencies" now appears in two of their taglines, so the 260817 claim "they sell to the brand, we sell to the agency" is no longer clean. What is still true: none of them do organic social fulfilment for a 2–10 person shop, none has a client approval gate, and none is self-serve.

### Ring D — Platform-owned and free

- **Google Pomelli** (Labs × DeepMind): free, no caps during beta, global rollout 9 Mar 2026, no pricing announced. URL → "Business DNA" → campaign ideas + editable assets. SMB-only: no multi-client, no approval, no publishing, no white-label. **This is the floor for "campaign from a URL" — $0.** Any pitch to the brand directly now competes with free Google.
- **HubSpot Breeze** Content/Social agents inside Marketing Pro ($800/mo). Enterprise-mid.
- **Canva Magic**, **Meta Advantage+ creative**: inside the tools the client already has.
- **ChatGPT / Claude Projects** with a brand doc: the actual incumbent for the strategy half of every retainer. Unbilled, un-versioned, no approval trail.

### Ring E — The agency operating system

**GoHighLevel** (official, 261030): $97 (3 sub-accounts) · $297 (unlimited) · $497 (SaaS mode, resell under your brand). Social planner + Content AI are core features at every tier; **AI Employee $50–97 per sub-account/mo**; white-label mobile app +$497. A large share of small agencies run their CRM, funnels, email and social from here, and this is where they will buy "AI": inside the platform, per sub-account. The 260817 analysis missed it entirely. It is both the biggest threat (GHL ships "campaign from brief" into Content AI) and the best distribution target (an integration into Social Planner reaches the ICP where it already lives).

### Voice of customer (surveys, not vendor blogs)

- Metricool *State of AI in Social Media 2026* (700+ pros): 95% use AI, 75% daily, ~40% use 4+ tools, 1 in 7 spends >$100/mo on AI (+400% YoY), **trust in output slipping**.
- Sociality.io 2026: **78.4% edit AI content moderately or extensively** before it ships.
- Sprout Q1 2026: 56% of audiences see "AI slop" often or very often.
- Agency owners (Gain, 2026 predictions): clients will want **visibility into where AI was used** in production.
- Approval bottlenecks are a top operational complaint in Sprout's agency research (via Apaya).
- Retainers: $500–5,000/client/mo across 2026 guides; HeyOrca survey (May 2024) average **$2,107/mo for one client on three platforms**.

Read: the buyer is drowning in tools, doesn't trust raw output, edits everything, and is starting to be asked by clients to show their AI work. That is an argument for a *review and record* layer, not another generator.

### Platform API risk (why "post it yourself" is strategy, not a hack)

X API is pay-per-use (~$0.015/write, $0.20/post with a URL, vendor-reported); Later dropped X in Aug 2025. Meta's v26 restrictions extended to all API versions on 27 Oct 2026 (vendor-reported; verify against Meta's changelog). LinkedIn is free behind a partner wall. Buffer's public API is gone. For a one-founder vendor, owning publishing is a cost centre with liability; schedulers absorb it at scale. Sit above them.

---

## 3. Where CampaignForge stands today, honestly

| Capability | Status in code | vs Ring A | vs Ring C/D |
|---|---|---|---|
| Brief → strategy + SEO + content + ad copy + QA in one run | real, 9-node graph, SSE | **nobody has it** | Pomelli: ideas + assets, no strategy/QA; agents: paid media |
| Moderation-before-approval on every creation path, recorded override | real, enforced, tested | approvals exist, moderation doesn't | nobody |
| Multi-tenant client workspaces, white-label settings | real (`white_label.py` is settings only; no custom domain, no logo upload) | table stakes, they're deeper | agents: no |
| Direct publishing | X/LinkedIn/FB publishers real; **UI connect switched off**; Instagram built, off | they own this | — |
| Manual channels + reminders + mark-posted | real, unique | nobody | nobody |
| Client-facing deliverable | **none** — `reporting.py` computes counts on request, nothing persisted, nothing branded | they have branded *reports* (metrics) | Pomelli exports assets |
| Client approval link | portal exists but **unauthenticated, org-slug-wide, no client scoping** — anyone with the slug sees and approves every client's drafts | Planable's entire product | — |
| Metrics / reporting | real pulls where tokens exist; manual posts permanently unmeasurable | their core recurring value | — |
| Amplify, Post Studio, Email, Launch, Ads, Inbox, Insights | real, quota-metered | partial overlap | — |
| Hand-off to other tools | `content.approved` + `campaign.completed` webhooks (HMAC); public API has only `/me` and `/campaigns` | Vista ships MCP; CC/GHL have APIs | — |

**Position that survives all five rings:** *the fulfilment layer above the scheduler* — one brief in, a client-ready, moderated, approved campaign pack out under the agency's brand, with a record of what AI did and who signed off, handed to whatever they already post with. Nobody else is standing there. Generation alone does not defend it (Pomelli is free); the **deliverable + the approval record + the hand-off** do.

---

## 4. Pricing: right ballpark on 260817, wrong category on 260926

Per-client cost of the Growth tier (10 clients) against what the agency bills:

| Tool, 10 clients | $/mo | $/client | % of one $2,107 retainer |
|---|---|---|---|
| CampaignForge Growth (today) | $36 | $3.60 | 0.17% |
| Metricool Starter 10 brands (annual) | $36 | $3.60 | 0.17% |
| SocialPilot Premium | $100 | $10 | 0.5% |
| Cloud Campaign Team + 5 extra ws | $199 + ~$160 | ~$36 | 1.7% |
| Planable Pro × 10 workspaces | $590 | $59 | 2.8% |
| GoHighLevel Unlimited + AI Employee ×10 | $297 + $500–970 | $80–127 | 4–6% |

Metricool's brand meter is the price of *scheduling* a brand. The 260817 proposal ($149 Studio / $349 Agency) priced the *fulfilment* work and sat inside the Cloud Campaign / SocialPilot Ultimate band. The 260926 re-price moved the product into the "cheaper scheduler" slot — the one claim it cannot make while connect is off.

**Position:** the anchor is wrong, and it is not urgent. With zero paying customers a third re-price is a spreadsheet exercise. Freeze `PLAN_CONFIG` until a design partner has run one full retainer; then price the Growth tier per workspace between SocialPilot Ultimate ($200) and Cloud Campaign Agency ($299), with unlimited seats, and let partners react to a number before it goes into Dodo. P1-7 (re-meter to workspaces) stays queued behind that evidence, not ahead of it.

---

## 5. Go-to-market

**Positioning.** For social and content agencies of 2–10 people and senior freelancers running 3–15 client brands, who lose unbilled hours to strategy, briefs and client sign-off at the front of every retainer, CampaignForge is the campaign-fulfilment layer that turns one brief into a client-ready, moderated, approved campaign pack under the agency's own brand — unlike Metricool, Cloud Campaign or Planable, whose AI starts after the strategy exists, and unlike Pomelli or ChatGPT, which hand back drafts with no approval record and no client branding.

**Not for:** brands marketing themselves (Pomelli is free), performance/paid-media shops (Ring C), enterprise social teams (Hootsuite/Sprout), anyone who needs the product to be their scheduler.

**Buyer:** the owner. **Trigger:** a new client kickoff, or the moment they decide whether to take client #6 without hiring. **Metric they care about:** hours per client per month at the front of the retainer.

### Motion — one, gated

| Phase | Gate to exit | Build | Sell |
|---|---|---|---|
| **Now · Make it honest + pack it** | Landing matches capability; Campaign Pack export ships; portal client-scoped | §6 items 1–2, 4 | Hand-recruit **5 design partners**, free 90 days, weekly 30-min session each. Source: GoHighLevel / Metricool / Cloud Campaign community groups, freelance SMM groups (HeyOrca, Social Media Pro). Offer = "we build the pack with you". |
| **Next · Make it theirs** | 1 partner runs a full client retainer unassisted; a client approves via the link | §6 item 3 (hand-off); Zapier recipes; white-label logo/domain | Capture before/after hours per client; first two case studies; re-price with partners' numbers |
| **Later · Make it findable** | 10 paying agencies, ≥3 active workspaces each | free "Client Kickoff Brief" tool from `magic_brief.py` (URL → branded brief, email-gated — the agency version of what Pomelli does for the brand); 6 comparison pages; Zapier/GHL marketplace listings | Convert partners; comparison SEO ("Planable alternative with strategy", "Metricool + AI campaign", "GoHighLevel Content AI alternative"); cold email via AgentMail only after a case study |

**Do not do yet:** Product Hunt (prosumers), paid ads, cold email, more generators, Instagram app review. None of them produce a logo, a quote or a before/after number — only partners do.

### Metrics

| Leading (weekly, per partner) | Lagging (90 days) |
|---|---|
| Campaign Packs exported (**activation** — instrument `trackFeature("campaign-pack-export")`) | Partners converting to paid |
| Posts approved via client link | Active workspaces per paying org |
| % of posts edited before approval (industry 78%; target < 50% — a quality signal nobody else can show) | 30-day retention |
| Hours/client/month reported, before vs after | MRR |

### Risks and kill signals

| Risk | Pre-committed response |
|---|---|
| Partners export the pack but rewrite the strategy section every time | Upstream work isn't valued → shrink to approval + hand-off layer (a cheaper Planable with moderation) or kill |
| Partners won't put their logo on the output | Quality bar unmet → fix `worker` prompts before any growth spend |
| GoHighLevel ships "campaign from brief" in Content AI / AI Employee | Be the integration, not the alternative: push packs into Social Planner |
| Pomelli adds multi-brand or agency mode | Free generation is a given; defend on approval record, hand-off, brand — never on generation |
| Metricool/Cloud Campaign ship a strategy prompt | Lead with the approval trail and moderation, which are harder to retrofit than a prompt box |
| Client approval via unauthenticated portal leaks drafts across clients | Fix before any client sees a link (§6 item 4) |

---

## 6. What to build next

Ranked. Effort uses the backlog's scale (S ≤1d · M 2–4d · L 1–2wk).

| # | Priority | Item | Effort | Why this, why now |
|---|---|---|---|---|
| 1 | **Must** | **Landing honesty.** `page.tsx:177` says "Publish straight to X, LinkedIn, and Facebook" while `OAUTH_CONNECT_ENABLED = false`. Either flip the constant (publishers and PKCE flow are intact — "the whole re-enable") or change the copy to "Approve here, post from your scheduler or by hand." Decision: keep connect off for the partner phase (X API cost, Meta review) and fix the copy. | S | Rule 1. A design partner who signs up and cannot connect X will not sign up twice. |
| 2 | **Must** | **Campaign Pack export.** One branded document per campaign under the org's white-label: brief, strategy, SEO angle, calendar, every post per platform, ad variants, QA findings, moderation flags + overrides, approval log with names/timestamps, and an "AI assisted / human approved" disclosure line. PDF + shareable HTML. `reporting.py` is counts-only and persists nothing; `white_label.py` is settings-only, so this also needs logo upload (currently "not available yet"). Emit `campaign-pack-export`. | M–L | This *is* the product in the positioning statement. It is the activation metric, the thing a partner shows a client, the thing nobody in five rings produces, and the answer to "clients want to see where AI was used". |
| 3 | **Should** | **Hand-off to the scheduler they already use.** (a) S: add `GET /public/content?status=approved` to `public_api.py`, document `content.approved` webhook → Zapier/Make recipes for GoHighLevel, Metricool, Cloud Campaign. (b) M: native push of approved posts into **GoHighLevel Social Planner** as drafts (largest ICP install base, open API). Verify each API before committing — Buffer's is gone. Replaces the clipboard as the primary "post it yourself" path. | S then M | Removes switching cost to zero and turns the biggest threat into distribution. Vista already ships MCP; the segment expects this. |
| 4 | **Must (security)** | **Per-client approval links.** `portal.py` lists all org content with no client filter and no auth; `PATCH` approves on the org slug alone. Replace with signed, expiring, per-client links (reuse `oauth_state.py`'s signed-token pattern), client-scoped queries, client name + agency brand on the page, and a comment-back field. | M | A client approval link is Planable's whole $39–59/workspace business and we already have the gate — but today's portal would show client A's drafts to client B. Must land before any partner sends a link. |
| 5 | Should | **Re-meter to workspaces, unlimited seats** (P1-7) | M | Only after a partner has run a retainer — see §4. |
| 6 | Could | **Instagram switch-on** (publisher exists, #16) + OAuth connect re-enable | S code + Meta review | Gate on a partner asking for it in writing. Manual channel covers it meanwhile. |
| 7 | Could | **Free "Client Kickoff Brief"** tool from `magic_brief.py` | M | Distribution asset; only useful once the Pack exists to funnel into. |
| — | **Won't (this cycle)** | Autonomous operator expansion · paid-ads execution or spend · any new Create generator · video depth · TikTok · DMs / inbox depth · competitive-intel grounding · RAG upgrades · template marketplace · Slack bot · Product Hunt | — | Each is a feature-count play against better-funded rings or a prosumer play against free. None produces the first logo. |

Order: 1 → 4 → 2 → 3a → (partners) → 3b → 5. Item 4 before 2 because 2 ends with "send this to your client" and the link it points at must be safe first.

**Status 261031:** items 1, 2, 3a and 4 shipped on branch `feat/client-review-pack-handoff` — see [features/changelog.md](features/changelog.md) (261031). Two things surfaced on the way: the API Keys screen discarded every key it created (fixed — shown once now), and no screen could register a webhook (added under Settings › API & webhooks). Item 3b (GoHighLevel push) is a plan, blocked on a test sub-account: [ghl-handoff-plan-261031.md](ghl-handoff-plan-261031.md). Logo upload, assumed in item 2, was **not** built: there is still no white-label settings UI, so the pack and review page carry the workspace name.

---

## 7. Open questions (owner · date)

1. **Keep OAuth connect off, or flip it?** Owner: Girish. Needed before item 1 is written. Recommendation: off, fix copy.
2. **Design partners — any names yet?** Owner: Girish. Open since 260817 in two docs. Everything in §5 waits on this.
3. **Pack format.** PDF only, or PDF + hosted HTML page under the agency's slug? Hosted needs the portal fix first. Owner: Girish, decide at item 2 kickoff.
4. **GoHighLevel API terms** for pushing third-party content into Social Planner — not verified today. Owner: whoever picks up item 3b.
5. **Meta v26 restrictions (27 Oct 2026)** — vendor-reported; check Meta's changelog for impact on `platform_metrics.py` reads.
6. **Sendible white-label add-on price** — disputed across sources ($240–349); matters only if a comparison page targets Sendible.
7. **yc-pitch.md §7–§8** still carry the $49/$149/$399 table and the "different buyer" argument that Sprites/Epiminds now undercut. Rewrite from this doc. Owner: Girish.
8. No competitor churn, CAC or conversion data was verifiable from a public source. Still needs partner interviews, not estimates.

---

## Sources

**Official pricing pages, fetched 261030:** [metricool.com/pricing](https://metricool.com/pricing/) · [cloudcampaign.com/pricing](https://www.cloudcampaign.com/pricing) · [vistasocial.com/pricing](https://vistasocial.com/pricing/) · [socialpilot.co/pricing](https://www.socialpilot.co/pricing) · [gohighlevel.com/pricing](https://www.gohighlevel.com/pricing). Sendible's page rendered without amounts; figures from [Blotato](https://www.blotato.com/blog/sendible-pricing), [RecurPost](https://recurpost.com/social-media-tools/sendible), [CostBench](https://costbench.com/software/social-media-management/sendible/).

**Planable:** [Postiv (checked 19 Oct 2026)](https://postiv.ai/blog/planable-pricing) · [PricingSaaS](https://pricingsaas.com/companies/planable) · [CostBench](https://costbench.com/software/social-media-management/planable/).
**Ring B:** [SocialRails on Blaze](https://socialrails.com/blog/blaze-ai-pricing) · [CostBench Blaze change Apr 2026](https://costbench.com/changelog/blaze-ai-price-increase-2026-04/) · [AI Agent Index Ocoya vs FeedHive](https://theaiagentindex.com/compare/ocoya-vs-feedhive).
**Ring C:** [Uplane seed](https://tamradar.com/funding-rounds/uplane-seed-4-5m) · [Seedtable Uplane](https://seedtable.com/companies/uplane/funding-rounds/seed-2026-04) · [Sprites enterprise](https://www.sprites.ai/enterprise) · [Sprites YC](https://ycombinator.com/companies/sprites) · [Epiminds raise](https://tech.eu/2025/10/14/epiminds-exits-stealth-with-66m-to-power-ai-first-marketing-teams/) · [Epiminds review](https://cogny.com/blog/epiminds-lucy-review-pricing-alternatives) · [Kana $15M](https://news.lavx.hu/article/kana-emerges-from-stealth-with-15m-to-build-ai-marketing-agents-that-do-the-heavy-lifting) · [Gradial $65M](https://siliconangle.com/2026/06/18/agentic-marketing-ai-startup-gradial-grabs-65m-fresh-funding/) · [AdsGency](https://mobilemarketingreads.com/?p=49368) · [Playad](https://www.crowdfundinsider.com/2026/01/257932-startup-playad-raises-5-4m-to-build-ai-marketing-agents-for-ad-creative/) · [Plurio](https://www.pulse.bot/ai/news/plurio-raises-35-million-to-bring-agentic-ai-to-performance-marketing-14514e33-a333-4715-bf0e-461eca244dcb/) · [ppc.land sector total](https://ppc.land/ai-sales-and-marketing-startups-raised-3-7b-globally-in-2026/).
**Ring D:** [SEJ on Pomelli launch](https://www.searchenginejournal.com/google-labs-deepmind-launch-pomelli-ai-marketing-tool/559569/) · [Pomelli pricing 2026](https://pikes.ai/blog/pomelli-pricing-2026) · [Pomelli 2026 review](https://www.dataslayer.ai/blog/google-pomelli-ai) · [HubSpot Breeze agents](https://www.eesel.ai/blog/breeze-agents) · [Hootsuite Social OS review](https://smartkeys.org/hootsuite-review/) · [Sprout Trellis](https://gravity.fast/blog/ai-agent-for-social-media/).
**VoC:** [Metricool State of AI 2026 press release](https://metricool.com/press-release-state-of-ai-in-social-media-study/) · [Metricool report page](https://metricool.com/social-media-ai-report-2026) · [Netinfluencer on trust](https://www.netinfluencer.com/social-media-professionals-are-spending-more-on-ai-but-trust-in-the-output-is-slipping-report-finds/) · [Sociality.io 2026 survey](https://www.sociality.io/blog/ai-in-social-media-marketing/) · [Gain: approval predictions](https://blog.gainapp.com/ai-content-approval-process-predictions/) · [Apaya on approval bottlenecks](https://apaya.com/blog/social-media-approval-workflows-for-agencies) · [Digiday agency confessions](https://digiday.com/marketing/is-it-even-worth-it-confessions-of-an-agency-exec-on-client-challenges-with-generative-ai-peak) · [HeyOrca survey via SolidGigs](https://solidgigs.com/blog/freelance-social-media-manager-rates/) · [Digital Applied 2026 pricing](https://www.digitalapplied.com/blog/social-media-marketing-costs-2026-pricing-guide).
**Platform APIs:** [Later drops X](https://www.webpronews.com/later-cuts-ties-with-x-over-api-changes-and-musk-demands) · [X API per-post pricing](https://www.blotato.com/blog/social-media-api) · [Meta v26 placement changes](https://adligator.com/blog/meta-graph-api-v26-placement-changes) · [LinkedIn API pricing](https://schedpilot.com/linkedin-api-pricing/) · [Buffer API gone](https://website-apn.pages.dev/blog/what-happened-to-buffer-api-alternatives-for-developers).
