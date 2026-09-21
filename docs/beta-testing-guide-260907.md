# CampaignForge AI — Beta Testing Guide

<!-- created: 260907 -->

**Who this is for:** beta testers. It tells you what to try, in what order, what is deliberately missing, and what to report.

Companion doc: [beta-testing-plan.md](beta-testing-plan.md) is the internal programme design — goals, recruitment, exit criteria. This guide is the thing you hand a tester. Where the two disagree, this one is current — see [Appendix A](#appendix-a--corrections-to-the-test-matrix).

---

## 1. What You Are Testing

CampaignForge runs a full marketing campaign — strategy, SEO, content, ad copy, brand QA — through seven specialised AI agents, with a human sign-off gate in the middle.

```
Orchestrator → [Strategy ∥ SEO] → [Content ∥ Ad Copy]
             → Human Review → QA/Brand → Compile → Analytics
```

**Built for:** a freelancer or small agency running 3–15 client brands.

**Two things make it different from a chat prompt**, and they are what we most need you to stress:

1. **Agents run in parallel, not in a chain.** Strategy and SEO run at the same time; Content and Ad Copy then run at the same time off both their outputs.
2. **The pipeline genuinely stops at Human Review.** It is not a progress bar. Graph state is checkpointed to Postgres. Close your laptop, come back tomorrow, and the campaign is still sitting there waiting for you.

### Environments

| | URL |
|---|---|
| App | `https://campaignforge.intelliforge.tech` |
| API | `https://campaignforge-api.fly.dev` |
| API docs | `https://campaignforge-api.fly.dev/api/docs` |

The backend sleeps when idle. **Your first request of the session may take several seconds.** That is a cold start, not a bug — do not report it.

---

## 2. Before You Start

1. Sign up with the email your invite went to. Clerk provisions your org, user, and a free subscription on first sign-in.
2. Create **at least two clients** before testing anything else. Most of the product is client-scoped, and empty states will make it look broken.
3. Fill in a brand profile for one client (voice, audience, style rules). Half of what we need to learn is whether generated copy actually sounds like the brand.
4. Use a real brand you know well — your own, or a client's. Generic test data produces generic output and tells us nothing.

Budget **30–40 minutes** for Track 1. Tracks 2–5 can be spread across the week.

---

## 3. Test Tracks

Run them in order. Track 1 is mandatory; the rest are by interest.

### Track 1 — Brief to approved campaign (mandatory, ~30 min)

The core loop. If only one track gets run, make it this one.

| # | Do this | Watch for | Report if |
|---|---|---|---|
| 1.1 | **Read website.** `/clients` → **Add Client**, paste a client's website URL, press **Read website**, then **Create Client**. | Does the generated brand profile actually match the site? Voice, audience, positioning. | The profile is generic, wrong, or invents facts not on the site. |
| 1.2 | **Create a campaign.** `/campaigns/new`. Set objective, dates, and pick channels. | Instagram and TikTok carry a "draft only" badge. That is intentional. | The badge is missing, or a badged channel behaves as if it will publish. |
| 1.3 | **Watch the pipeline live.** Stay on the campaign detail page. | Progress streams over SSE. Strategy and SEO should move together, then Content and Ads together. | The stream dies, stalls with no message, or the two fan-outs run one after another instead of together. |
| 1.4 | **Hit the review gate.** The run halts at Human Review. Read every generated piece. | Is this genuinely client-ready, or does it need a rewrite? This is the single most important judgement you can give us. | Copy is off-brand, factually wrong, or generic enough that you would not send it. |
| 1.5 | **Test that the pause is real.** Close the tab. Wait at least 10 minutes. Come back to the campaign. | It should be exactly where you left it. | State was lost, the campaign shows as failed, or it silently continued without you. |
| 1.6 | **Request revisions** on one piece, approve the rest. | Revisions route back to the writing agent, then through brand QA. | Revised copy ignores your note, or the revision never routes back. |
| 1.7 | **Read the QA output**, then the compiled campaign. | QA should give specific, actionable brand feedback. | QA passes something you would not, or gives no score with no explanation. |

**The question we most need answered in Track 1:** at step 1.4, how much editing would this need before you would send it to a paying client? A number is fine. "About 20% rewritten" is more useful than "pretty good".

### Track 2 — Publishing and scheduling (~20 min)

| # | Do this | Notes |
|---|---|---|
| 2.1 | Connect a platform in Settings. | **Known issue:** the OAuth loop is not closed in-app — the authorize page opens in a new tab and nothing handles the return. Tell us how far you got. |
| 2.2 | Publish a piece to X, LinkedIn, or Facebook. | These three are the only platforms that publish. |
| 2.3 | Schedule a piece for a future time. | The background scheduler should pick it up. |
| 2.4 | Open `/calendar` and drag a scheduled post to a different day. | Drag-and-drop is real and should persist. |
| 2.5 | Try to publish an Instagram or TikTok piece. | You should see an amber "Publishing unavailable" badge instead of a button. **Report if you find a way to publish anyway** — a false success here is a P0. |

### Track 3 — Multi-client and content library (~20 min)

| # | Do this | Notes |
|---|---|---|
| 3.1 | Run campaigns for two different clients. | Does the second campaign sound like the second brand, or like the first? |
| 3.2 | Repurpose a piece across platforms (`/content`). | Watch for output that is truncated, prose-wrapped, or contains raw code fences — a known parse-failure mode. |
| 3.3 | *(API only — variant generation has no UI. Technical testers: `POST /content/{id}/variants`.)* | Are the variants meaningfully different, or cosmetic rewordings? |
| 3.4 | *(Skipped — no client portal UI exists yet. The API is built; the page is not. See §4.)* | |
| 3.5 | *(Skipped — white-label branding has no UI either. See §4.)* | |

### Track 4 — Billing and team (~15 min)

| # | Do this | Notes |
|---|---|---|
| 4.1 | Hit a free-tier limit (1 client, 5 campaigns/mo). | You should get an upgrade prompt with real usage numbers, not a hard error. |
| 4.2 | Run Stripe checkout to Starter. | Test mode unless told otherwise. Confirm limits actually lift afterwards. |
| 4.3 | Invite a team member. | If AgentMail is not configured for your org, you will get a warning toast carrying a temporary password to share out of band. That is intended, not a failure. |
| 4.4 | Note the amber banner on `/team`. | **Roles are labels, not restrictions.** Nothing is enforced yet. Do not staff your org assuming otherwise. |

### Track 5 — API and integrations (technical testers, ~20 min)

| # | Do this | Notes |
|---|---|---|
| 5.1 | Create an API key in Settings, call the public API with `X-API-Key`. | |
| 5.2 | Register a webhook via the API, run a campaign, confirm delivery. | **API only — no UI.** Deliveries are DB-backed and HMAC-signed. |
| 5.3 | Run a competitive intel scan via the API. | **API only — no UI.** Findings are gated on real source URLs. Report anything asserted without a citation. |
| 5.4 | Try the Slack bot. | `/campaignforge create` is **disabled** and will tell you so. `/status` and mentions work. |

---

## 4. Known Gaps — Please Do Not Report These

Everything here is already on the board. Each is visibly marked in the UI rather than quietly broken.

### Deliberately not built yet

| Feature | What you will see |
|---|---|
| Instagram / TikTok publishing | "Publishing unavailable" badge; API returns `success: false`. Content is still generated and scheduled. |
| Instagram metrics | Content analytics shows an unavailable reason. |
| Notifications | Bell says notifications are not generated yet. Settings → Notifications shows "Not available yet". |
| Audit log | `GET /audit` returns `status: unavailable`. |
| RBAC enforcement | Amber banner on `/team`. Roles are stored, not enforced. |
| Content `performance_score` | `/content/suggestions` returns `status: unavailable` — nothing writes the score yet. |
| Client portal UI | API is built; no page exists in the app. |
| White-label branding UI | Config API is built; no page calls it. |
| Org logo upload | "Logo upload not available yet" chip. |
| Slack campaign creation | Replies that it is unavailable, points you at the dashboard. |
| Analytics agent insights | Returns `status: unavailable` until there is published, measured content. |

### Rough edges with workarounds

| Issue | Workaround |
|---|---|
| `/templates` has no nav link, and launching a template drops its channels/objective | Reachable by URL; expect a blank wizard. Create campaigns manually for now. |
| OAuth return is not handled in-app | Report how far the connect flow got. |
| Image generation calls the wrong fal.ai endpoint and always errors | Skip it. Already diagnosed. |
| Autonomous operator has no UI | API only (`POST /campaigns/autonomous`). |

### On missing numbers

You will see `unavailable` and blank metrics in places. **This is a deliberate policy, not an outage.** The codebase was audited end-to-end for fabricated data ([stub-audit-260817.md](stub-audit-260817.md)); anywhere a number cannot be measured, we return `null` with a stated reason rather than invent a plausible one.

So: **an honest blank is not a bug. A confident number you cannot trace to a real source is.** If you ever see a metric, score, or "top performing" label you suspect was made up, that is a **P0** and the single most valuable thing you can report.

---

## 5. How to Report

### Severity

| Level | Means | We respond in |
|---|---|---|
| **P0** | Data loss, security issue, wrong client's data visible, **or a fabricated number presented as real** | 2 hours |
| **P1** | Core flow broken with no workaround | 4 hours |
| **P2** | Degraded but usable | 24 hours |
| **P3** | Cosmetic, copy, minor UX | 48 hours |

### Template

```
Title:
Severity:      P0 / P1 / P2 / P3
Track/step:    e.g. 1.4
Client/brand:  which one, so we can reproduce with the same profile
Steps:
  1.
  2.
Expected:
Actual:
Campaign ID:   from the URL — lets us pull the exact agent run
Browser/OS:
Screenshot:
```

Campaign ID matters more than anything else in that template. With it we can pull the exact graph state and agent outputs for your run.

### Channels

| Channel | For |
|---|---|
| GitHub Issues | Bugs with full detail |
| Slack `#beta-feedback` | Quick reactions, UX friction, "this felt weird" |
| `beta@campaignforge.ai` | Account or billing problems, anything sensitive |

### Beyond bugs — what we actually need

Bug counts are the easy part. These are harder and worth more:

1. **How much would you edit the output before sending it to a client?** Per track 1.4.
2. **Where did you lose confidence?** The exact moment you thought "I'd better check this myself".
3. **What did you try that is not here?** Especially anything you assumed would exist.
4. **Would you pay for this at $49/mo?** And if not, at what price, or what would have to be true.

---

## 6. What We Measure Automatically

Captured server-side in `product_event`, read via `GET /api/v1/beta-metrics?window_days=28`.

Time-to-first-campaign · campaign completion and failure rates · agent-step drop-off · feature adoption · session duration · D1/D7/D14 return rate · error rate by endpoint.

Caveats when reading it: `request_rates` is in-memory and resets on every restart or redeploy (frequent, given Fly's idle stop) — treat it as a live gauge, not a beta-long total. `errors_by_endpoint` is DB-backed and does persist, but 401s and 404s are not recorded. Metrics are per-org; a programme-wide rollup means querying `product_event` directly.

Only client-writable event types are accepted from the browser. Pipeline and error events are server-authored, so a tester cannot skew completion or failure counts.

---

## Appendix A — Corrections to the Test Matrix

Five test cases in [beta-testing-plan.md](beta-testing-plan.md) §5 will fail as written, because the feature was removed or was never wired. Fix the plan or brief testers around them before the cohort starts.

| Plan TC | Says | Reality |
|---|---|---|
| **TC-04** Template-based campaign | "Browse templates → Fork → Customize → Launch" | `/templates` has zero inbound links, and `campaigns/new` never reads `searchParams`, so the template's channels and objective are silently dropped. Tester lands on a blank wizard. |
| **TC-08** QA agent scoring | "Score 7+ with specific feedback" | The hardcoded `overall_score: 7` fallback was **removed** in the 260817 audit — it was fabricated. An unparseable QA response now returns `score_available: false`. A test asserting 7+ asserts the bug. |
| **TC-10** Autonomous operator | UI flow implied | No UI entry point. API only. |
| **TC-21** Slack bot create | "Campaign created, link returned" | Deliberately disabled — it created no campaign and promised a follow-up that could never arrive. Replies unavailable by design. |
| **TC-24** OAuth platform connect | "Platform connected, token stored" | The OAuth loop is not closed in-app. Connection may never complete from the UI. |

TC-14 (calendar drag-and-drop) was checked and **is genuinely implemented** — leave it in.

Also worth reconciling: the plan's goal 2 ("posts delivered to X, LinkedIn, Facebook") and its §5.3 matrix are consistent with what ships, but goal 7 ("< 5 minutes brief to *published* campaign") is not reachable in one sitting if the human review gate is used as designed. Either measure to *review-ready* instead, or state that the clock pauses at the gate.

---

## Unresolved

- Cohort size and start date for this round — the plan says 20–50 over 4 weeks; is that still the shape?
- Is Stripe in test or live mode for beta? Track 4.2 needs the answer.
- Is AgentMail configured for beta orgs? If not, every team invite hits the temporary-password path and Track 4.3 reads as broken.
- Two nav links (Magic Brief, Templates) would remove the most-hit rough edge in §4. Worth doing before the cohort rather than documenting around.
- No in-app feedback widget exists, though the plan's §6 lists one as a channel.
- Nobody is named in the plan's contact table. Testers need a human to escalate a P0 to.
