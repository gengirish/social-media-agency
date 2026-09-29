# Manual publishing ("Post it yourself") — phased plan

Created 260929. Branch off `main` as `feat/manual-publish`.

For the operator who created their business pages **outside** CampaignForge and does not want
the product touching them. The product generates, moderates, approves and tracks; a human
opens the platform in a new tab and posts. Nothing about the approval gate changes.

Handover document. Every agent reads **§1 Locked decisions** and **§2 Ground rules** before
touching anything. The decisions are settled — an agent that disagrees writes it in its final
report and implements the decision anyway.

---

## 1. Locked decisions

**A manual channel is a `platform_account` row with `status = 'manual'` and no tokens.**
Not a new table, and *not* a separate `connection_type` column alongside `status = 'connected'`.

The reason is failure direction. Eight places filter `PlatformAccount.status == "connected"`:

| Call site | Needs a real token? | Action |
|---|---|---|
| `routers/publishing.py` (publish_now) | yes | leave as-is |
| `services/scheduler.py` (_publish_piece) | yes | leave as-is |
| `routers/inbox.py` | yes | leave as-is |
| `services/analytics_fetcher.py` | yes | leave as-is |
| `services/insights.py` | yes | leave as-is |
| `services/post_studio.py` | yes | leave as-is |
| `routers/setup.py` (client_accounts) | no — display | widen to include `'manual'` |
| `routers/clients.py` (overview counts) | no — display | widen to include `'manual'` |

With `status = 'manual'`, every token-requiring path excludes manual rows **by default** and
only the two display paths change. A `connection_type` column would invert that: all eight
keep matching, and six of them would silently select a row with `access_token_enc IS NULL`.
Fail-closed beats fail-open — six silent breakages vs. two deliberate widenings.

**Mode is per channel, not per org or per client.** A client can have LinkedIn connected via
OAuth and Instagram manual. The mode is a property of the `platform_account` row.

**Only X prefills post text.** This is a product-rule-1 constraint, not a detail:

| Platform | Composer URL | Prefills body? |
|---|---|---|
| X / Twitter | `https://x.com/intent/post?text=<encoded>` | **yes** |
| LinkedIn | `https://www.linkedin.com/feed/?shareActive=true` | no |
| Facebook Page | the channel's `profile_url`, else `https://business.facebook.com/latest/composer` | no |
| Instagram | the channel's `profile_url`, else `https://www.instagram.com/` | no |
| TikTok | `https://www.tiktok.com/tiktokstudio/upload` | no |

**The clipboard is the payload carrier; the deep link only lands the user in the right
composer.** UI copy must say "copied — paste it into the composer" for the four that do not
prefill, and must never say "publish" for a manual channel. Button label: **Post it yourself**.

**Quota counts, charged on confirm only.** `posts_limit` is the product's only usage meter and
the plan copy sells it as "30 published posts/mo" (`services/billing.py`). Free manual posts
would make manual mode an unlimited free tier. Charge on "I posted it", never on the
open-tab click — an abandoned composer tab costs nothing. Check quota at click time too, so
nobody composes into a tab and then eats a 402 on confirm.

**The post URL is optional.** Forcing it strands anyone who posted from their phone: they
could never mark the post done, and the queue would fill with `approved` rows that are
actually live — a wrong record is worse than a missing metric. Optional, with a permanent
"Add link" affordance and an explicit Insights empty state (product rule 4: never a zero
standing in for an unknown).

**New capability `publish.manual`, granted to `owner`/`admin`/`member`, not `viewer`.** The
matrix comment in `permissions.py` gates `publish.write` away from `member` because "publish
posts to a live client account". Manual mode removes that premise — the product posts nothing.
What is left is bookkeeping, and a `member` who already holds `content.approve` is trusted to
say the copy is fine. Record `posted_by` so it stays attributable.

**Reminders: in-app always, Slack when the org already has a channel configured, no email.**
A due-time reminder per post is the highest-volume mail this product would ever send, and
this repo has burned itself on claimed-but-absent email before. **Digest, not per-post:** one
notification per due batch per client, linking to the filtered Queue. Twelve due posts must
not be twelve pings.

**Nothing auto-approves, nothing auto-posts.** `mark-posted` accepts only `approved` /
`scheduled`, via the existing `ensure_publishable`. Manual mode is not a moderation bypass.

---

## 2. Ground rules

- `db/init.sql` **and** `models/tables.py` **and** a dated forward-only script in
  `db/migrations/`. `init.sql` only runs on a fresh database — Neon prod needs the script run
  by hand.
- Every new org-scoped query filters on `org_id`. There is no RLS. Any id from the client
  (path, body, query) is resolved against `org_id` before being written to or joined on.
- Add each new route to `tests/test_tenancy_routers.py`, and verify the test fails when its
  `org_id` filter is deleted.
- Add each new gate to `tests/test_approval_gate.py`, same property.
- **A new capability also means editing `tests/test_provisioning_roles.py`.** It asserts
  `/auth/me`'s capability list **verbatim**, per role and per `account_type`, plus one
  legacy-role case — so a new entry in `CAPS` fails those tests until every role's expected
  list is updated. That is the point: it forces a deliberate decision about all four roles, so
  a capability cannot reach `viewer` by copy-paste. Never relax the assertion to a subset check.
  Update the matrix in `docs/rbac-phase-plan-260923.md` and `docs/features/auth-and-rbac.md` in
  the same change.
- Mirror `UNAVAILABLE_PUBLISH_PLATFORMS` honesty in `frontend/src/lib/platforms.ts`; the
  composer-URL map lives beside it so the two honesty maps stay together.
- Before presenting: `ruff` + `mypy` + `pytest` (backend), `npm run lint` + `npm run build`
  (frontend). A clean compile has missed runtime crashes here before.
- `get_current_user` returns the **JWT payload dict**, never an ORM `User`. Use
  `get_current_user_id`.

---

## 3. Phases

Dependency shape: **P1 and P2 are independent and can run in parallel.** P3 needs both.
P4 needs P1. P5 needs P2 + P3. P6 is last.

### Phase 1 — Manual channels (no tokens)

*Goal: a user can register a page they own, without OAuth, and see it in Setup › Accounts.*

- `db/migrations/260929_manual_channels.sql`: `ALTER TABLE platform_account ADD COLUMN IF NOT EXISTS profile_url TEXT;` — `access_token_enc` is already nullable. Mirror in `db/init.sql` and `models/tables.py`.
- `POST /api/v1/setup/{client_id}/accounts/manual` — platform, `account_handle`,
  `profile_url`; writes `status = 'manual'`. Gate on `Capability.OAUTH_CONNECT` (registering
  a channel is the same shape of act as connecting one).
- `PATCH` / `DELETE` for the same row.
- Widen the two display filters to `status.in_(("connected", "manual"))`:
  `routers/setup.py::client_accounts`, `routers/clients.py` overview counts. **Touch no
  others** (see §1 table).
- `profile_url` validation through `services/url_safety.py` — it is rendered as a link and
  opened in a new tab.
- Accounts UI: "Add a page you manage yourself" alongside the OAuth buttons; manual rows get
  a distinct badge, not a green "Connected".

**Tests:** tenancy for all three routes; a manual row does **not** appear to
`publish_now`'s lookup; a manual row **does** appear in `client_accounts`.

### Phase 2 — `mark-posted` + `publish.manual`

*Goal: an approved post can be recorded as posted, with no connected account.*

- `Capability.PUBLISH_MANUAL = "publish.manual"` in `permissions.py`; add to `CAPS` for
  owner/admin/member. Update the matrix table in `docs/rbac-phase-plan-260923.md` and in
  `docs/features/` auth docs.
- `POST /api/v1/publishing/{content_id}/mark-posted`, gated on `PUBLISH_MANUAL`. Body:
  `{post_url?: str}`. Runs `ensure_publishable` + `ensure_client_active` +
  `billing.check_quota(resource="posts")`. Calls **no** publisher and requires **no**
  connected account — but does require a `status='manual'` channel for that client+platform,
  so it cannot be used to fake a post on a channel the org never registered.
- On success: `status = "published"`, `published_at = now()`, metadata
  `{publish_mode: "manual", posted_by: <user id>, post_url: <or None>, publish_blocked: None, publish_error: None}`,
  then `billing.record_post_published`.
- `GET /publishing/calendar` and the Queue serializer expose `publish_mode`.

**Tests:** tenancy; `draft` → `409 not_approved`; already-`published` → 409 (no double
count); quota exhausted → 402 and **nothing** written; no manual channel → 400; a `member`
succeeds and a `viewer` gets 403.

### Phase 3 — The Queue flow

*Goal: one click copies the text, opens the composer, and offers confirm.*

- `frontend/src/lib/platforms.ts`: `manualComposerUrl(platform, {body, hashtags, profileUrl})`
  and `prefillsBody(platform)` from the §1 table.
- `post-card.tsx`: when the piece's channel is manual and status is `approved`/`scheduled`,
  replace Schedule / Publish now with **Post it yourself** (+ Schedule as a reminder, from P4).
- Click handler order matters: write the clipboard **and** call
  `window.open(url, "_blank", "noopener,noreferrer")` in the same user gesture, before any
  `await`. A popup opened after an await is blocked.
- Then a confirm panel: **I posted it** (optional post-URL field) / **Cancel**. Cancel writes
  nothing and charges nothing.
- Copy differs by platform: prefilled (X) vs "copied — paste it into the composer".
- `trackFeature("content-post-manual", { platform })` on confirm.

**Tests:** `e2e/` spec — a manual-channel approved post shows "Post it yourself" and no
"Publish now"; Cancel leaves status `approved`; confirm moves it to Published.

### Phase 4 — Scheduled = reminder

*Goal: a manual post can be scheduled without the scheduler ever posting it.*

- Lift `ensure_schedulable`'s `platform_unavailable` refusal **when the channel is manual** —
  Instagram and TikTok become schedulable, because nothing autoposts them.
- `scheduler._process_due_content`: a due piece whose channel is manual stays `scheduled`,
  gets a digest notification, and records `metadata.reminder_sent_at` so it is not re-notified
  on every wake. It must never reach `_publish_piece`.
- Digest: group due pieces by client, one `create_notification(type="posts_due", ...)` per
  client per batch, linking to the filtered Queue. `send_slack_message` too when the org has a
  channel configured; no email.
- Queue and Calendar copy for a scheduled manual post reads "Reminder <time>", never
  "Publishes <time>".

**Tests:** a due manual piece stays `scheduled` and is **not** `failed`; it is notified once
across two scheduler wakes; a due OAuth piece still publishes (no regression).

**Shipped 260929, with one deviation.** The copy reads "Reminder **around** \<time\>", not
"Reminder \<time\>" — see §5 on the wake cap. Two additions the plan did not name: a
`scheduleUnavailableReason(platform, {manual})` beside `publishUnavailableReason`, because "can
a time be set" and "can this be published" stopped being the same question, and
`lib/manual-channels.ts::useManualChannels` so the Queue and the Calendar branch on one fact.

### Phase 5 — Link later + honest Insights

*Goal: a missing post URL is visible, fixable, and never becomes a fake zero.*

- `PATCH /publishing/{content_id}/post-url` to attach the link after the fact; gate
  `PUBLISH_MANUAL`; allowed on `published` pieces only (this is the one field an edit may
  change without resetting to `draft` — it is a record of reality, not the copy).
- Queue badge **Published · no link** with an inline "Add link" that never expires.
- Insights / `platform_metrics`: a manually-posted piece with no link renders "Posted manually
  — no link, metrics unavailable". Not `0`. Excluded from averages rather than averaged as zero.

**Tests:** a `draft` rejects the post-URL patch; attaching a URL does not reset status;
insights aggregation excludes link-less manual posts from averages.

### Phase 6 — Docs and copy honesty pass

- `feature-docs` skill over `docs/features/` — new endpoints, the new capability, the schema
  column, the Accounts and Queue pages.
- `CLAUDE.md`: manual mode in the Approval-gate and publishing sections.
- Sweep user-facing copy for "publish" where the product does not publish: Billing meter
  wording, Accounts, Queue, Calendar, empty states.

**Docs half done 260929.** Updated: `docs/features/{api-endpoints,database-schema,services,
frontend-pages,frontend-components,auth-and-rbac,billing,changelog,README}.md` and `CLAUDE.md`
(new *Manual publishing* section, approval-gate exception, migration note). `auth-and-rbac.md`
gained the capability matrix it never had, replacing a three-row role table that predated
`owner` and `require_cap`. Known issues recorded rather than fixed, because they are code and
owned elsewhere: the `connected_accounts` field name now counts manual channels (so `/welcome`
and the client switcher say "connected" about pages nothing is connected to), and the Queue
sidebar's channel chips, which come from the connected-only `GET /post-studio/channels` and
therefore never show a manual channel.

The copy sweep is the remaining half.

---

## 4. Risks

| Risk | Mitigation |
|---|---|
| A `status == "connected"` filter gets widened by reflex and a tokenless row reaches a publisher | §1 table is the checklist; a test asserts `publish_now` 400s on a manual-only client |
| Popup blocker eats the composer tab | `window.open` in the same gesture as the clipboard write, before any await |
| Double-count: user clicks confirm twice | `ensure_publishable` already rejects `published`; confirm button disables on submit |
| Composer deep links rot (platforms change them) | one map in `lib/platforms.ts`; `profile_url` is the per-channel override when a generic link breaks |
| `member` marks posts as done without posting | attributable via `posted_by`; same trust surface as any self-reported field |

---

## 5. Unresolved

Kept as written, with what the implementation settled underneath. The questions stay so the
reasoning survives — an answer without its question is a rule nobody can argue with later.

- Does the Billing page need to distinguish product-published from manually-posted in the
  "published posts" meter, or is one number right?

  **Still open** (260929). One number is what shipped: `mark-posted` runs the same
  `check_quota` / `record_post_published` as a real publish, and `metadata.publish_mode`
  makes a split possible later without a schema change. What the docs pass did note is that
  the meter now counts posts the product did not send, so the *wording* on Billing and in plan
  copy is doing double duty — see `docs/features/billing.md` § Quota Enforcement.

- ~~Should a manual post with no link be excluded from Insights **averages** or from the
  published **count** as well?~~

  **Answered: averages only.** `services/insights.py::is_unmeasurable_manual` skips such a
  piece in `latest_engagement` and reports it as `engagement.manual_unlinked`; it stays inside
  `funnel.published`. Excluding it from the count would make Insights and the Billing post
  meter disagree about the same event, and the piece *was* published — by a human. An unknown
  metric is not an unpublished post, and product rule 4 forbids the alternative (a `0` standing
  in for a number nobody has).

- ~~Reminder lead time: at the scheduled minute, or a configurable lead?~~

  **Answered: "around", not at-the-minute — and not configurable.** The scheduler's sleep is
  capped at `MAX_SLEEP_SECONDS = 3600` and `notify_scheduled()` only wakes the *local* process,
  so a post scheduled on another Fly machine can be reminded up to an hour late. That cap is
  the **Neon idle-cost dial**: every wake restarts the idle timer of everything it touches, and
  the old unconditional 60s loop ran 1,440 queries/day at zero traffic and pinned Neon awake so
  autosuspend was unreachable. Tightening the reminder means paying for that, so the UI says
  "Reminder around \<time\>" and promises nothing sharper. A configurable lead would be a
  second knob on top of an interval the product cannot honour; not built.

- ~~Can `platform_metrics` fetch anything from a pasted link without a token?~~

  **Answered: no, and therefore the P5 empty state is permanent, not a gap to fill.** Every
  platform requires an authorized API call, a manual channel has no tokens by definition, and
  manual mode stores no platform post id — a URL is not a handle anything can be fetched by.
  There is no per-platform analytics path for manual channels to build. "Posted manually — no
  link, metrics unavailable" is the final answer; do not file it as unfinished work, and do not
  let a future change quietly average it as a zero.
