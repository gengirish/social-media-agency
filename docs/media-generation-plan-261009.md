# Image & short-video generation → attached to a post — phased plan

Created 261009. Revised 261013 — the five open questions are now decided defaults (**§7**), so
there is nothing to answer before starting. Branch off `main` as `feat/media-generation`.

Turns the Queue's two disabled stubs (**Create image**, **Short video** in
`components/posts/post-card.tsx`) into real features, and carries the resulting media through
approval to the platform. Nothing about the approval gate is relaxed.

Handover document. Every agent reads **§1 Locked decisions** and **§2 Ground rules** before
touching anything. The decisions are settled — an agent that disagrees writes it in its final
report and implements the decision anyway.

---

## 0. What already exists

Do not rebuild these. The feature is roughly 30% written and disconnected at both ends.

| Piece | State |
|---|---|
| `services/image_generation.py` | **Real** fal.ai `flux/schnell` call, sync `fal.run`, per-platform aspect ratios, three-state return (`skipped` / `error` / `generated`) |
| `POST /content/{id}/generate-image` (`routers/content.py:596`) | **Real**, org-scoped, appends the URL to `content_piece.media_urls` |
| `content_piece.media_urls JSONB` | Exists in `db/init.sql` and `models/tables.py` |
| `services/post_studio.py::attach_creative_brief` | **Real** — writes `metadata.creative_brief`, words for a human designer, no image |
| `content_approval.py:95` | Already treats a piece with media and an empty body as non-empty |
| `post-card.tsx` `ComingSoonAction` ×2 | Disabled stubs with a note explaining why |
| `config.py:118-120` `s3_bucket_name` / `aws_*` | **Aspirational** — no `boto3` in `pyproject.toml`, nothing reads them |
| Short video | **Nothing.** The `fal-ai-media` skill is marketing-layer prompt config, not product code |

Four gaps, by severity:

1. **Media never reaches a publisher.** Both call sites build the same three-key dict —
   `routers/publishing.py:115` and `services/scheduler.py:270` — `body`, `hashtags`, `title`.
   `media_urls` is dropped. No publisher accepts it either: `_publish_twitter` posts
   `{"text": body}`, LinkedIn does a text share. Generate an image today and the post still goes
   out as text.
2. **No durable storage.** `media_urls` holds the raw fal.ai CDN URL, which expires.
3. **Moderation is text-only.** `moderate_content` works on
   `published_text(body, platform, hashtags)`. An image attached after approval reaches a live
   account unreviewed — product rule 3, with publishing real.
4. **The endpoint skips the generator contract.** No `require_generation_quota`, no
   `charge_generation`, no `is_disconnected()` check, no brand context — the prompt is
   `piece.title` or the first 100 chars of the body, so voice, palette and campaign focus are all
   absent.

---

## 1. Locked decisions

### A. Manual channels ship first. They need no platform media API at all.

This is the ordering decision everything else follows from, and it is new since 260929.

A manual channel (`platform_account.status = 'manual'`, no tokens) already means a **human**
opens the composer and posts. So a generated image needs only to be *downloadable* — no X media
upload, no LinkedIn `registerUpload`, no Meta Graph container, **no Meta app review**.

Consequence: **Instagram visual posting works end to end at Phase 5**, months before the
connected-channel path, because Instagram is the platform operators are most likely to run manual
anyway (`needsVisual` in `post-card.tsx:392` already special-cases it).

The clipboard stays the text carrier. Media gets a **Download** button, not a clipboard write —
image-to-clipboard is unreliable across browsers, and a silent failure there looks like the
product lost the asset. Same user-gesture rule as the composer deep link: trigger the download in
the gesture, before any `await`.

Copy constraint, product rule 1: on a manual channel the UI says "Download the image, then attach
it in the composer". It must never imply the product attached or published anything.

### B. Storage is Cloudflare R2, through the S3-compatible API.

Decided on egress. These bytes get pulled repeatedly — platform upload, Queue thumbnails on every
render, portal, client review, manual download. R2 bills zero egress; S3 bills ~$0.09/GB out;
Vercel Blob bills bandwidth and is priciest per GB.

Second reason: the backend is **Fly.io `sin`, not Vercel**. The one argument for Blob is native
Vercel integration, which a Fly container does not get, and reaching it would pay egress out of
Vercel on every upload.

R2 is S3-compatible, so `aioboto3` works and the existing `s3_bucket_name` /
`aws_access_key_id` / `aws_secret_access_key` fields become real with one addition:
**`s3_endpoint_url`**. Do not add a vendor SDK.

Required from day one, not later:

- **Derivative at write time** — a ~400px WebP thumbnail. Never render originals in the Queue; a
  12-card view pulling 1MP PNGs is the first perf regression this feature will produce.
- **Key layout** `{org_id}/{client_id}/{content_id}/{asset_id}.{ext}`. The org prefix makes bulk
  delete on churn and per-tenant usage accounting trivial.
- **Custom domain + `Cache-Control: public, max-age=31536000, immutable`.** Keys are
  content-addressed, so nothing is ever invalidated.

### C. Media is a new `media_asset` table. Not `creative_asset`.

`creative_asset` is long-form **text** in a JSONB `payload` behind a closed `ASSET_KINDS` and a
generic `/assets` CRUD that renders it as prose. A binary needs a storage key, mime type,
dimensions, duration, a moderation verdict and a prompt hash — none of which fit `payload` without
the `/assets` screens showing garbage. The existing rule also says social-post content never goes
in `creative_asset` because the approval gate must apply; media attached to a post is part of that
post.

`content_piece.media_urls` **stays** as the publish-facing list of resolved public URLs —
`content_approval.py:95` already depends on it and the publishers will read it. `media_asset` is
the record; `media_urls` is the denormalized projection. Both are written in the same transaction.

### D. Media quota is a separate, weighted counter. Never the shared `generations_used`.

Agency is `generations_limit: 9999` at $168 (`billing.py:85`). If one generation can be a video,
worst-case fal spend is orders of magnitude above revenue. Growth is worse per dollar: 250
generations on $36.

- Keep `generations_used` for text. Add `media_credits_used` / `media_credits_limit`.
- **Image = 1 credit, video = 10**, and the weights live in a **`MEDIA_CREDIT_WEIGHTS` dict in
  `config.py`, not inline at the call sites.** The 10:1 ratio is an estimate of the real cost
  ratio; making it configuration means re-pricing after the first month of real fal invoices is an
  env change, not a migration and not a code review. Read the weight, never hardcode `10`.
- **Video is Growth and above.** Free and Starter get images only. Starter at 50 credits would be
  5 videos, which reads as worse than offering none — a meter that empties after five clicks
  generates support load, not upgrades. "Video on Growth and above" is also one sentence on a
  pricing page.
- Credit limits per tier:

  | Tier | `media_credits_limit` | Video | Video sub-cap |
  |---|---|---|---|
  | free | 5 | no | — |
  | starter | 50 | no | — |
  | growth | 250 | yes | 10 videos / period |
  | agency | 2000 | yes | 60 videos / period |

- **The video sub-cap is separate from the credit total, and applies on agency too.** `9999` is a
  sentinel meaning unlimited; unlimited video generation is unbounded loss, and "unlimited" is the
  one pricing word that cannot be walked back. Agency's 60 videos still leaves 1400 credits for
  images.
- Video off on free is also the abuse boundary: free tier + expensive generation + no card is the
  classic drain.
- `media_credits_limit IS NULL` falls back to the tier's `PLAN_CONFIG` value, exactly as
  `generations_limit_for` (`billing.py:189`) does — orgs provisioned before this migration must
  not read as zero.

**The check and increment must be atomic here**, unlike the known Amplify race. Overshooting an
Amplify pack by one costs pennies; overshooting video costs money. Conditional
`UPDATE ... WHERE media_credits_used < limit RETURNING` and branch on rowcount.

**Dedupe by hash.** Hash prompt + model + params; a repeat returns the existing asset and charges
nothing. Users re-click; this is the largest real saving in the whole plan, larger than tier
sizing.

Charge on success only — the house pattern, unchanged.

### E. Moderation runs at generation time, not approval time.

A vision call on the approve path roughly doubles its latency for every post, including the ones
with no media. Instead:

1. **Screen when the image is created.** The user is already waiting on fal.ai; the check is free
   in perceived time. Approval latency does not move.
2. **Provider signal first.** flux returns `has_nsfw_concepts` synchronously with the image, at no
   extra cost. Escalate to a **brain-tier** vision call only when it trips, or when the image
   carries rendered text — which is where the real risk lives: a wrong price, an unapproved claim,
   a competitor's mark. Same risk class `ad_guardrails.py` already handles for copy.
3. **Cache the verdict on `media_asset`**, keyed by content hash. A text edit resets the piece to
   `draft` and re-moderates the copy; the unchanged image must not be rescanned.
4. **Fail open visibly** — `metadata.moderation.status = "unavailable"` plus a
   `moderation_unavailable` log, identical to the text path.

The gate itself still lives before `approved`: **approve refuses when an attached `media_asset`
has no verdict row.** That is a cheap row lookup, not a model call, so rule 3 holds at zero
latency cost.

`PATCH /content/{id}` mutating `media_urls` resets status to `draft`, exactly as editing the body
or hashtags does. Do **not** reason from the `post-url` exception — that one is about a link
recording where a post landed, and CLAUDE.md explicitly says not to widen it.

### F. The image prompt is assembled in code from the creative brief. No second LLM call.

`metadata.creative_brief` already exists from a worker-tier call. Deriving the prompt from it
costs **zero extra LLM tokens**; generating a fresh prompt per image pays a model call per image
forever, plus latency.

Assemble deterministically in code — the same discipline as `plan_atoms` assigning Amplify angles
in code rather than letting the model pick. Combine the brief,
`brand_prompt_block(load_brand_context(...))` and the platform aspect ratio.

**Keep the brief intact.** It is useful on its own, and it is what a manual Instagram post needs
when the operator wants a human designer instead of a generated image.

Store the resolved prompt string and its hash on `media_asset`, so dedupe is stable and a
regenerate is reproducible.

### G. Video uses the async queue endpoint and a job row. Never the sync endpoint.

`image_generation.py` uses sync `fal.run` with a 60s timeout, holding a Fly worker for the whole
generation. Fine for `flux/schnell` at a few seconds — **fatal** for video at minutes: starved
workers, then Fly's request timeout. The file's own comment already warns about this.

Video goes through `queue.fal.run` + a `media_job` row + poll or webhook, with progress on the
existing SSE channel.

Model choice: **Seedance or Kling, not Veo 3.** Veo 3 is roughly an order of magnitude more per
second and fits none of the four price points. Default 5s vertical. **Never auto-generate video in
the pipeline** — explicit user click only.

### H. Assume Meta app review is NOT in hand. Phase 7 is out of scope for this branch.

`instagram_content_publish` needs a reviewed Meta app, which takes weeks. **The plan assumes it is
not submitted** — the fail-closed assumption, because the alternative builds a phase that cannot
be tested.

So: submit the review as an **admin task alongside Phase 0**, and treat Phase 7 as a **separate
follow-up branch** that starts only once the permission is granted. Nothing in Phases 0-6 depends
on it. Unreachable publish code is a product-rule-1 capability claim waiting to leak into the UI,
which is exactly what `UNAVAILABLE_PUBLISH_PLATFORMS` and its `platforms.ts` mirror exist to
prevent.

This costs nothing, because **§1A already delivers Instagram visual posting at Phase 5** on manual
channels. Phase 7 only converts Instagram from manual to connected.

Removing `instagram` from that dict (`publishing.py:27`) and from `platforms.ts:14` is the **last**
line of Phase 7, and both move together or the UI lies in the other direction.

### I. Storage sits behind a two-driver interface. R2 provisioning never blocks the branch.

Assume R2 credentials are **not** available at Phase 0. `media_storage.py` exposes one interface
with two drivers, chosen by whether `s3_endpoint_url` and the keys are set:

- **`r2` (production)** — §1B.
- **`local` (dev, CI, and any environment with blank credentials)** — writes under a gitignored
  directory and serves through a `GET /api/v1/media/{key}` route, scoped on `org_id` like any other
  read. Not a stub: the same keys, the same derivative, the same return shape, so Phases 1-6 are
  fully testable and demoable before the R2 account exists.

The driver is logged at startup as `media_storage_driver`, the same way the checkpointer logs its
memory fallback — a silent local driver in production would mean media that vanishes on redeploy.
Blank credentials in production is a **startup warning**, not a crash.

---

## 2. Ground rules

- **Every org-scoped query filters `org_id`.** No RLS in the database. Any `client_id`,
  `content_id` or `asset_id` arriving from a client is resolved against `org_id` before being
  written to or joined on.
- `get_current_user` returns the **JWT payload dict**. Use `get_current_user_id`; `user.id` raises
  `AttributeError` and surfaces as a 500.
- **No new path writes `approved` or `scheduled`.** Every media path leaves the piece `draft`.
- **Never widen a `status == "connected"` filter that leads to a token.** Manual media paths read
  `'manual'` rows; publishing paths keep excluding them.
- Schema changes land in **`db/init.sql` and `models/tables.py` and** a dated forward-only script
  in `db/migrations/`, run by hand on Neon. Nothing applies these automatically. SQLAlchemy names
  every mapped column in its `SELECT`, so a skipped migration breaks every read of that table —
  the `260929_manual_channels.sql` lesson.
- Business logic in `services/`. Routers stay thin.
- LLM access only through the four tier getters. The vision escalation is **brain** tier.
- `trace_config("<feature-name>", org_id=...)` on every `ainvoke` / `astream` added.
- Before presenting: `ruff check src/ tests/`, `mypy src/agency/ --ignore-missing-imports`,
  `pytest tests/ -v` for backend; `npm run lint`, `npm run build` for frontend.
- `trackFeature("create-image")` / `("short-video")` at the point of success.
- After the feature lands, refresh `docs/features/` via the `feature-docs` skill.

---

## 3. Phases

### Phase 0 — storage (`services/media_storage.py`)

Prerequisite for everything. Add `aioboto3` + `pillow` to `pyproject.toml` and `s3_endpoint_url`
to `config.py`. Fetch the generator's result, persist original + WebP derivative, return stable
public URLs.

Two drivers per **§1I** — `r2` and `local`, same interface, same keys, same return shape, driver
logged at startup. Build against `local` so nothing waits on the R2 account.

Admin task in parallel, not code: **submit the Meta app review** (§1H).

### Phase 1 — `media_asset` table

Columns: `id`, `org_id`, `client_id`, `content_id` (nullable — a standalone asset is valid),
`kind` (`image` | `video`), `storage_key`, `url`, `thumb_url`, `mime`, `width`, `height`,
`duration_ms` (nullable), `bytes`, `model`, `prompt`, `prompt_hash`, `credits_charged`,
`moderation` JSONB, `created_by`, `created_at`. Index `(org_id, client_id, created_at DESC)` and a
unique index on `(org_id, prompt_hash)` for dedupe.

Plus `media_job` for Phase 8: `id`, `org_id`, `media_asset_id`, `provider_job_id`, `status`,
`error`, timestamps.

### Phase 2 — image generation as a proper generator

Rewrite `routers/content.py:596` to the Amplify shape, logic in `services/media_generation.py`:

`get_org_piece` → `get_org_client` → `require_media_credits(1)` → prompt assembled in code per
**§1F** → dedupe check on `prompt_hash` → `generate_social_image` → persist via Phase 0 →
`request.is_disconnected()` check (save and charge nothing, like Post Studio) → write
`media_asset` + append to `media_urls` → `charge_media_credits` → commit.

Malformed or empty provider response → `502` "no media credits were used", nothing saved.

### Phase 3 — media credits in billing

`PLAN_CONFIG` entries per the §1D table, `MEDIA_CREDIT_WEIGHTS` in `config.py`,
`media_credits_limit_for` with the `None` fallback, `require_media_credits(kind)` /
`charge_media_credits(kind)` with the atomic conditional UPDATE, `402 media_credit_quota_exceeded`,
reset on `invoice.paid` alongside `generations_used`.

Video eligibility is a plan check here, not a Phase 8 concern: `video_enabled` per tier plus the
video sub-cap, returning `402 media_video_not_in_plan` on free/starter. Build it in this phase so
Phase 8 has nothing to decide.

Billing UI gets its own meter row — separate counters behind one meter is how the CF-11 copy/meter
mismatch happened. Free and Starter show no video meter at all rather than a zeroed one.

### Phase 4 — moderation at generation

`moderate_media` in `services/moderation.py`: provider `has_nsfw_concepts` → brain-tier vision
escalation on trip or text-in-image → verdict onto `media_asset.moderation`. Approve refuses when
attached media has no verdict. `PATCH /content/{id}` touching `media_urls` resets to `draft`.

### Phase 5 — Queue UI + manual download ← **first user-visible value**

Render `media_urls` thumbnails on the post card. Swap the **Create image** `ComingSoonAction` for a
live button. Add **Download** for manual channels. Drop the
`needsVisual = platform === "instagram"` gate (`post-card.tsx:392`) — X and LinkedIn take media
too, and on a manual channel every platform does.

**Get creative brief stays, beside Create image.** Both buttons, always; the brief is not replaced
and `BriefPanel` keeps rendering. An operator who uses a human designer, or who wants art direction
before generating, loses nothing — and per §1F the brief is what feeds the prompt, so hiding it
would hide the input to the thing next to it.

**Instagram visual posting is complete at the end of this phase, for manual channels.**

### Phase 6 — media on connected channels

Add `"media_urls": piece.media_urls or []` to both `content_data` dicts
(`routers/publishing.py:115`, `services/scheduler.py:270`), then per platform:

- **X** — `POST /2/media/upload` INIT/APPEND/FINALIZE → `media.media_ids` on the tweet.
- **LinkedIn** — `assets?action=registerUpload` → PUT bytes → `ShareContent` with the asset URN.
- **Facebook** — `/{page_id}/photos` with `url=`, or `published=false` + `attached_media`.

### Phase 7 — Instagram connected (gated on §1H)

Graph API container (`/media`) → `/media_publish`. Last line: remove `instagram` from
`UNAVAILABLE_PUBLISH_PLATFORMS` **and** from `platforms.ts`, together.

### Phase 8 — short video

`services/video_generation.py` mirroring the image service's three-state contract, on
`queue.fal.run` + `media_job` + poll/webhook per **§1G**. `agents/video_script.py` already produces
the script and becomes the prompt source. Storage, credits (Growth-and-above, sub-capped) and
moderation all reuse Phases 0-4 unchanged — this phase adds a provider and a job lifecycle, nothing
else.

Download-for-manual from Phase 5 means **Reels and TikTok both work here without any platform
API**, which is the whole reason video is worth shipping before Phase 7. Connected Reels via the
same container flow with `media_type=REELS` comes with Phase 7; TikTok has no OAuth connection at
all and stays manual indefinitely.

---

## 4. Migrations, in order

1. `261013_media_assets.sql` — `media_asset`, `media_job`, indexes, and
   `subscription.media_credits_used` / `media_credits_limit` / `videos_used` (all nullable or
   defaulted; `NULL` on a limit reads as the tier default).

One script, not two: the columns and the tables ship in the same Stage 1 commit, and a split would
only create an order dependency to get wrong when running them by hand on Neon.

Also into `db/init.sql` and `models/tables.py`.

---

## 5. Tests

| File | Asserts |
|---|---|
| `test_media_storage.py` | key layout, derivative written, both drivers return the same shape, driver selection logs |
| `test_media_generation.py` | quota before generate, dedupe returns existing and charges nothing, `502` saves nothing, cancel saves and charges nothing |
| `test_media_credits.py` | weights read from config not hardcoded, video refused on free/starter, video sub-cap on growth **and agency**, atomic check under concurrency, `NULL` → tier default |
| `test_approval_gate.py` *(extend)* | approve refuses media with no verdict; a `media_urls` edit resets to `draft`. **Each must fail when its gate is deleted** — keep that property |
| `test_tenancy_routers.py` *(extend)* | every new route filters `org_id`; **each must fail when its filter is deleted** |
| `test_publish_media.py` | `media_urls` reaches the publisher; per-platform upload shape |
| `frontend/e2e/media.spec.ts` | thumbnail renders, Create image enabled, manual Download present, copy never implies the product published |

---

## 6. Cost levers, ranked

1. **Dedupe on `prompt_hash`** — biggest real-world saving; users re-click.
2. **Weighted credits + video sub-cap** — caps worst-case spend per tier.
3. **Prompt from the existing brief** — zero extra LLM tokens per image, forever.
4. **`flux/schnell` default**, quality model on paid tiers only.
5. **Seedance/Kling over Veo 3** — roughly 10× cheaper per second.
6. **R2 zero egress** — matters more as thumbnails get hit on every Queue render.
7. **WebP derivatives + immutable cache** — cuts bandwidth and page weight together.

---

## 7. Defaults taken

The five open questions from the first draft are **decided**, as defaults chosen to keep the branch
unblocked. Each is reversible at the cost named, and none of them gates starting Phase 0.

| Was open | Default taken | Where | Cost to reverse |
|---|---|---|---|
| Meta app review in hand? | **Assume not.** Phase 7 becomes a follow-up branch; submit the review as an admin task | §1H | None — Phase 7 just starts earlier |
| Video:image credit ratio | **10:1, but read from `MEDIA_CREDIT_WEIGHTS` in `config.py`** | §1D | Env change. No migration, no code review |
| R2 credentials available? | **Assume not.** Two-driver storage, `local` for dev/CI | §1I | None — flip the driver by setting credentials |
| Video on which tiers? | **Growth and above.** Free/Starter images only | §1D | Widening a plan limit is additive; narrowing one later is not, which is why this starts narrow |
| Keep "Get creative brief"? | **Yes, both buttons, always** | §1F, Phase 5 | None |

Two of these are deliberately the *narrow* choice — video on Growth+, and Phase 7 deferred.
Widening later is additive and announceable; taking a capability back is neither.

### Pre-launch checklist (not blockers — do before the pricing page goes live)

1. **Reconcile `MEDIA_CREDIT_WEIGHTS` against the first month of real fal.ai invoices.** The 10:1
   ratio is an estimate. Product rule 4 applies to the pricing page as much as to a dashboard: ship
   the number you measured, not the one that was convenient.
2. **Confirm the `media_storage_driver` startup log reads `r2` in production.** A `local` driver on
   Fly means media that disappears on redeploy — the same failure shape as the checkpointer's
   memory fallback, and just as quiet.
3. **Check the Meta review outcome** before writing any Phase 7 copy.
4. **Re-run `diff -rq .cursor .claude`** if any marketing-layer skill was touched.
5. **`feature-docs` skill** to refresh `docs/features/`, which has no media coverage at all yet.

### Still genuinely unknown

Nothing blocking. One thing to watch rather than decide now: whether a 400px WebP thumbnail is
enough for the Calendar's denser grid, or whether that view needs a second, smaller derivative.
Decide when the Calendar actually renders media — guessing now means generating a derivative
nothing reads.

---

## 8. Parallel build plan

The phase graph is nearly a chain, and the collisions land in the worst files — `db/init.sql`,
`models/tables.py`, `config.py`, `billing.py`, `platforms.ts`, `post-card.tsx`. Two agents editing
those in one worktree lose work silently; in separate worktrees they conflict exactly where a
mistake is invisible, because a column dropped from `tables.py` during conflict resolution breaks
**every** read of that table.

So: **freeze the contracts in one sequential stage, then fan out.**

### Stage 1 — solo, sequential. Every shared-file edit for the whole feature, once.

Schema (`init.sql` + `tables.py` + the one migration), `config.py` fields and
`MEDIA_CREDIT_WEIGHTS`, `PLAN_CONFIG` entries, the media router registration in `main.py`, the
full Phase 0 storage service — **and typed stubs raising `NotImplementedError`** for everything
Stage 2 fills.

The stubs are the mechanism. Once the signatures exist, Stage 2 agents write bodies in their own
new modules and never touch a shared file or each other's.

Each Stage 2 unit gets **its own module** for this reason, rather than extending a hot one:

| Unit | Module (new) | Not |
|---|---|---|
| Credits | `services/media_credits.py` | `generation_quota.py` |
| Moderation | `services/media_moderation.py` | `moderation.py` |
| Generation | `services/media_generation.py` | `image_generation.py` |

### Stage 2 — 3 parallel agents. Disjoint files, one frozen contract.

Phase 2 (generation), Phase 3 (credits), Phase 4 (moderation). Each fills its own module's stubs
plus its own test file. **No agent edits a file another agent owns**; anything that looks like it
needs a shared-file change gets reported back, not done.

### Stage 3 — 2 parallel agents.

Phase 5 (frontend: thumbnails, live Create image, manual Download) and Phase 6 (publishers). Phase
6 is **one** agent, not three — X, LinkedIn and Facebook are three methods in the same
`publishing.py`.

### Stage 4 — solo.

Integration, then `ruff` + `mypy` + `pytest` and `npm run lint` + `npm run build`. A clean compile
has missed runtime crashes in this repo before; run the tests.

### Review agents — parallel, read-only, after each stage

Higher value than parallel implementation, and no collision risk. Three focused reviewers:

1. **Tenancy** — every new query filters `org_id`; every client-supplied id resolved before it is
   joined on or written to.
2. **Approval gate** — nothing writes `approved`/`scheduled`; a `media_urls` edit resets to
   `draft`; no `status == "connected"` filter widened toward a token.
3. **Product rule 1** — no UI copy implying the product attached or published anything on a manual
   channel.

### Operational notes

- **Do not `fly deploy` while a worktree agent is live.** A git checkout mid-deploy ships a torn
  image and crashloops production.
- Any `.claude/` change must be ported to `.cursor/` — by **one** agent, never two in parallel.
  Confirm with `diff -rq .cursor .claude`.
- Expect roughly 30-40% wall-clock saving, not a multiple of the agent count. The spine is
  sequential; Phase 8 (video) is its own branch afterwards and parallelizes against nothing.
