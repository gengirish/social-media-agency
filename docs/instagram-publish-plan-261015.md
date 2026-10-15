# Phase 7 — Instagram connected publishing

Created 261015. Phase 7 of [`docs/media-generation-plan-261009.md`](media-generation-plan-261009.md),
split into its own document because it is gated on an **external approval with a multi-week lead
time** and the code is useless until that lands.

Branch off `main` as `feat/instagram-publish`, but **start Part A today and the code later** —
Part A is calendar time, not work time.

Phases 0-6 shipped in `84e790c8`. Instagram visual posting already works **on a manual channel**
(generate → approve → download → post by hand), so this phase converts Instagram from manual to
connected. It is an improvement, not an unblock.

---

## 0. What is actually missing

I audited this rather than trusting the parent plan, which said Phase 7 was "the container flow
plus removing two dict entries". It is more than that.

| Piece | State |
|---|---|
| `_publish_instagram` (`services/publishing.py:584`) | **A stub that returns a success-shaped body** — `post_id: ""`, no exception. Only `UNAVAILABLE_PUBLISH_PLATFORMS` stops it |
| `UNAVAILABLE_PUBLISH_PLATFORMS["instagram"]` | Present, and the sole guard |
| `platforms.ts::UNAVAILABLE_PUBLISH_PLATFORMS` | The frontend mirror; **moves in lockstep or the UI lies** |
| **`instagram` in `OAUTH_CONFIGS`** | **ABSENT.** Not in `PLATFORM_CLIENT_KEYS` either |
| **`instagram` in `MAX_MEDIA_PER_POST`** | **ABSENT** — `.get(platform, 1)` means a carousel silently truncates to one image |
| `instagram: 2200` char limit (`moderation.py:50`) | Present ✓ |
| `PLATFORM_ASPECT_RATIOS["instagram"] = "square"` | Present ✓ |
| Media as a public URL | Required. Graph **fetches** media; it takes no upload |

**The missing OAuth config is the part the parent plan got wrong.** There is no Instagram
connection flow at all — `GET /oauth/instagram/authorize` cannot work today. Phase 7 is two
features (connect, then publish), not one.

### Facebook publishing is broken in production. This is not a Phase 7 prerequisite — it is a
### shipped bug of its own severity.

Confirmed in code on 261015, not inferred. The callback's `account_handle` defaulted to
`f"{platform}_user"` and nothing resolved it server-side; the frontend's **OAuth** path sends no
handle (only the *manual channel* path does, where a human types it). Both
`routers/publishing.py` and `services/scheduler.py` then pass `page_id=account.account_handle`, so
every OAuth-connected Facebook Page has been posting to
`https://graph.facebook.com/v19.0/facebook_user/feed` since connect shipped.

Fixed here for **new** connections, by resolving the real Page id during the callback. **Existing
rows still hold the placeholder**, so Facebook stays broken for them — see *Backfill* below.

**The stub is the dangerous part.** `publish()` wraps a publisher's normal return as
`{"success": True, ...}`, so the moment `instagram` leaves `UNAVAILABLE_PUBLISH_PLATFORMS` while
that stub is still in place, every Instagram post is marked `published`, burns post quota, and
posts nothing. The comment at `publishing.py:24` records this happening before. **Delete the stub
body in the same commit that removes the dict entry** — never one without the other.

---

## Part A — Meta App Review. Start now; it is the critical path.

Nothing in Part B can be tested without this.

### A1. Preconditions on the Instagram side (check before anything else)

- The target Instagram account must be **Business or Creator**. A personal account can **never**
  publish via the API — no permission fixes that, and it is the most common reason this project
  dies at the demo.
- It must be **linked to a Facebook Page**, because the API addresses Instagram *through* that
  Page. This is also why `instagram` reuses Facebook's OAuth endpoints in Part B.
- You must be an admin of that Page.

Tell beta clients this early. "Convert your Instagram to a Business account and link it to a Page"
is a prerequisite you cannot implement around, and discovering it during onboarding is worse than
stating it up front.

### A2. Permissions to request

| Permission | For |
|---|---|
| `instagram_basic` | Reading the IG account and its id |
| `instagram_content_publish` | **The actual publish grant.** This is the one under review |
| `pages_show_list` | Listing the Pages the user administers |
| `pages_read_engagement` | Already requested for Facebook |
| `business_management` | Often required for Business-owned accounts; request it if the flow touches a Business asset |

### A3. Business Verification — the long pole

Meta requires **Business Verification** for `instagram_content_publish`, and it is slower and
fussier than the app review itself. It wants legal entity documents: registration/incorporation
papers, a verifiable business address, and a domain that matches. Budget weeks, not days, and
expect at least one round of document rejection.

Do this first and in parallel with everything else. The app review cannot be approved while
verification is pending.

### A4. App configuration

- App type **Business**.
- App must be switched **Live**, not Development. Development mode works only for accounts with a
  role on the app — fine for your own testing, invisible to clients.
- Privacy policy URL and a **data deletion** URL. `campaignforge.intelliforge.tech/legal` exists;
  confirm it actually covers deletion, because reviewers check the page content, not just that the
  URL resolves.
- Valid OAuth redirect URI: `https://campaignforge.intelliforge.tech/api/oauth/instagram/callback`
  — the in-app page route, matching the existing X/LinkedIn pattern, and it must sit at exactly
  `{first CORS origin}/api/oauth/{platform}/callback`.

### A5. The screencast is what gets rejected

Most first submissions fail here, not on the code. Record a single unbroken screen capture showing,
in order:

1. A real user signing in to CampaignForge.
2. Clicking Connect Instagram, seeing the Facebook permission dialog, **reading each requested
   permission aloud or on screen**, and granting it.
3. Generating or writing a post, and a human approving it — the review gate is a feature here, not
   an obstacle. Meta wants to see that a person authorises the content.
4. The post publishing, and then the post **visible on the real Instagram account**.
5. Disconnecting the account, showing the user can revoke.

Narrate *why* each permission is needed. Reviewers reject submissions where a permission's purpose
is not demonstrated — requesting `business_management` without showing it used is a rejection, so
drop any permission you cannot film in use.

### A6. Timeline

Business verification: days to weeks. App review: roughly a week per submission round. Assume **two
rounds**. Do not promise Instagram publishing to a client against a date you have not already
cleared.

---

## Part B — The code, once (and only once) A is approved

### B1. The connect flow

Add `instagram` to `OAUTH_CONFIGS` in `routers/oauth.py` **reusing Facebook's endpoints** — Graph
has no separate Instagram OAuth; you authorise through Facebook Login and reach Instagram via the
Page:

```python
"instagram": {
    "authorize_url": "https://www.facebook.com/v18.0/dialog/oauth",
    "token_url": "https://graph.facebook.com/v18.0/oauth/access_token",
    "scopes": "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement",
},
```

and `"instagram": ("meta_app_id", "meta_app_secret")` to `PLATFORM_CLIENT_KEYS`. No PKCE —
`PKCE_PLATFORMS` stays `{"twitter"}`.

Bump the Graph version while you are in here if `v18.0` is near sunset; Meta retires versions on a
schedule and the existing Facebook entry will need it anyway.

### B2. Resolving the account — the step with no analogue in the other platforms

After the token exchange, three calls, in order:

1. `GET /me/accounts` → the Pages this user administers, each with its **own page access token**.
2. `GET /{page-id}?fields=instagram_business_account` → the linked IG Business Account id.
3. `GET /{ig-user-id}?fields=username,followers_count` → the handle to display.

Then store, on the `platform_account` row:

- `platform = "instagram"`
- `account_handle` = the **IG Business Account id**, because that is what the publisher addresses
  (mirroring how Facebook passes `page_id=account.account_handle` into credentials)
- `access_token_enc` = the **Page** access token, **not** the user token. A user token cannot
  publish. This is the single most likely thing to get wrong and the error Graph returns does not
  say so.
- `display_name` = the `username`

**Verify what `account_handle` actually holds for the existing platforms before you copy the
pattern.** CLAUDE.md states account handles are still placeholders (`{platform}_user`). If that is
true of Facebook today, then Facebook publishing is addressing a placeholder page id and is
already broken in production — in which case fix that first, because Instagram will inherit the
same bug and you will debug it twice. Check a real row rather than trusting either source.

If the user administers several Pages, or a Page has no linked IG account, the UI has to say which
and why. Silently picking the first Page is how one client's posts end up on another's account.

The backend now returns `409 {"code": "meta_page_choice_required", "candidates": [...]}` and
accepts an optional `page_id` to disambiguate. **No frontend consumes that yet**, so a multi-Page
Meta login currently fails with a generic error. That is the safe direction — it refuses rather
than guessing — but it is a visible gap and the Page-picker UI needs its own ticket before any
multi-Page client is onboarded.

Two smaller limits, both flagged rather than fixed: `/me/accounts` is **paginated** and only page
one is read (fine for an operator, truncating for someone administering 100+ Pages); and the
resolved **Page id is dropped** for Instagram, because `platform_account` has no metadata column.
Every publish call is `/{ig-user-id}/...` and `content_publishing_limit` is per IG user, so nothing
today needs it — but Page-level insights would, and that means a column or a re-resolve.

`followers_count` is deliberately **not** fetched at connect time. `platform_metrics.py` owns that
number; capturing it here would freeze a value at connect and make it look invented later.

### Connectable is derived from publishable — a coupling to know about

`oauth_platform_status()` now omits any platform still in `UNAVAILABLE_PUBLISH_PLATFORMS`.
Without it, adding `instagram` to `OAUTH_CONFIGS` would immediately show a "Connect Instagram"
affordance while publishing is refused and Meta has granted nothing — product rule 1. Deriving it
from that one dict means the go-live commit flips connect and publish on together, with no third
edit to forget.

The coupling is only correct while "connectable" and "publishable" mean the same thing. They
would diverge the moment we want a connection for analytics or Inbox reads **without** publishing
— at that point this needs its own `UNAVAILABLE_CONNECT_PLATFORMS`, not a widened dict.

### Backfill: force a reconnect, do not script it blind

A backfill would have to decrypt each row's stored token and re-resolve — but **the stored token
is the user token**, which may have expired, and for a multi-Page login it raises
`MetaAccountChoiceRequired` with nobody present to answer. So the honest fix is to flip affected
rows to `disconnected` and let the UI prompt a reconnect.

Check the affected row count on Neon first:

```sql
SELECT platform, count(*) FROM platform_account
WHERE platform IN ('facebook','instagram') AND status = 'connected'
  AND account_handle !~ '^[0-9]+$'
GROUP BY platform;
```

If that is a handful, reconnect them by hand. A script is only worth writing if it is not.

### B3. The publisher

Replace the stub body entirely. Three shapes:

**Single image** — container, then publish:
```
POST /{ig-user-id}/media         image_url=<public url>&caption=<text>   → {"id": creation_id}
POST /{ig-user-id}/media_publish creation_id=<id>                        → {"id": media_id}
```

**Carousel** (2-10 items) — a container per child, then a parent:
```
POST /{ig-user-id}/media  image_url=<url>&is_carousel_item=true          (per child)
POST /{ig-user-id}/media  media_type=CAROUSEL&children=<ids>&caption=<text>
POST /{ig-user-id}/media_publish creation_id=<parent id>
```

**Reels** (Phase 8 territory, but the shape belongs here):
```
POST /{ig-user-id}/media media_type=REELS&video_url=<url>&caption=<text>
GET  /{creation_id}?fields=status_code        → poll until "FINISHED"
POST /{ig-user-id}/media_publish creation_id=<id>
```

Also add `"instagram": 10` to `MAX_MEDIA_PER_POST`, or carousels truncate to one image with only a
`publish_media_truncated` log to show for it.

**`media_publish` returns only a media id — no URL**, and an Instagram permalink cannot be derived
from an id. A fourth call is needed: `GET /{media_id}?fields=permalink`. If it fails, leave
`metadata.post_url` empty rather than constructing a plausible link; product rule 4 applies to a
URL as much as to a metric, and a wrong permalink is worse than none because it looks checkable.

**`media_publish` must NOT go through `_with_http_retries`.** A retried publish after a
transport-level failure on a call that actually succeeded posts twice. An orphaned container simply
expires, so the asymmetry is entirely one-sided. Container creation and the status poll are safe to
retry; the publish is not.

*Pre-existing, same class, not fixed here:* `_publish_facebook`'s `/feed` post and
`_publish_twitter`'s tweet are both wrapped in `_with_http_retries`, so both carry the same
double-post exposure today. Worth its own change — it is a live-account correctness issue, not an
Instagram one, and bundling it here would hide it.

**Hashtags go in the caption**, capped at Instagram's own limit of 30, mirroring what the X and
LinkedIn publishers already do with `hashtags`. Instagram is the platform where this matters most
and the first draft of this section did not mention it.

**One Reel, not a video carousel.** Instagram does support video carousel items, but nothing in
this product generates a mixed image/video pack, so a video present wins and becomes the only
attachment (logging the drop, as X does). Revisit only if a generator starts producing mixed packs.

### B4. Refuse, loudly, in three cases

Raise `MediaUploadError` — **raise, never return** — so `publish()` turns it into an explicit
failure rather than wrapping a stub as success:

1. **No media.** A text-only Instagram post is impossible, not merely unsupported. Say that.
2. **A non-public media URL.** Graph fetches the bytes, so the `local` storage driver can never
   work — identical to the Facebook case already handled in `_publish_facebook_photos`. Reuse that
   check and its message naming `S3_ENDPOINT_URL`.
3. **A container that never reaches `FINISHED`** within a bounded wait. Publishing an unfinished
   container fails with an error that reads like a permissions problem.

### B5. Rate limit — check it, do not discover it

Instagram allows **25 published posts per 24 hours per account** (Meta has used 25 and 50 at
different times — read the current figure from the API, do not hardcode either).
`GET /{ig-user-id}/content_publishing_limit` returns current usage. Check before publishing and
fail with a message naming the window, because the raw Graph error is uninterpretable to an
operator and the scheduler will otherwise retry into the same wall.

This matters more here than elsewhere: the scheduler publishes unattended, so an account can burn
its daily quota overnight with nobody watching.

**An unreadable quota response fails OPEN — it lets the post through — and logs
`publish_quota_unreadable`.** Only a successfully parsed `used >= total` refuses. This is
deliberate: blocking on an empty `data` array or a renamed field would turn a Graph schema change
into a total publishing outage, whereas failing open costs at most one attempt that Graph itself
rejects. It is the same discipline as moderation failing open on an LLM outage — permitted, but
never silent.

### B6. The lockstep removal — last commit, both files together

```
services/publishing.py   → drop "instagram" from UNAVAILABLE_PUBLISH_PLATFORMS
                         → delete the _publish_instagram stub body
frontend/src/lib/platforms.ts → drop "instagram" from UNAVAILABLE_PUBLISH_PLATFORMS
```

All three in one commit. Backend-only leaves the UI refusing something that works; frontend-only
offers something that posts nothing and marks it published.

`tiktok` stays in both. It has no publisher and no OAuth connection, and manual remains its only
mode indefinitely.

---

## Verification

Unit tests in `tests/test_publish_media.py` (extend; do not start a new file):

- single image → container then publish, in that order
- carousel → N child containers, one parent, one publish; `MAX_MEDIA_PER_POST` honoured at 10
- no media → explicit failure, piece **not** marked published
- app-relative media URL → refuses, naming the storage fix
- container stuck pending → refuses rather than publishing early
- rate limit exhausted → refuses with the window in the message
- `test_instagram_stays_unavailable` **will now fail by design** — rewrite it as
  `test_instagram_publishes_with_media`, and keep a `test_tiktok_stays_unavailable`

Then end-to-end against one real Business account before any client sees it: connect, generate,
approve, publish, confirm the post on Instagram, disconnect. That run is also your A5 screencast —
record it the first time it works and you will not have to stage it twice.

Finally: `ruff`, `mypy`, `pytest`, `npm run lint`, `npm run build`, and refresh `docs/features/`
via the `feature-docs` skill.

---

## What stays impossible after this

Say so in the UI rather than letting someone infer otherwise:

- **Instagram Stories** — a separate publishing surface, not covered by this flow.
- **First comment** auto-posting (where people park hashtags) — a different permission.
- **Tagging users or products** — more permissions, more review.
- **Personal Instagram accounts** — permanently out of reach via any API.
- **TikTok** — no publisher, no OAuth, manual only.

---

## Unresolved

- **Is Business Verification started?** If not, that is the only thing that matters this week; the
  code is a day or two of work against a multi-week approval.
- **Does `account_handle` hold a real id for Facebook today, or the `{platform}_user` placeholder?**
  Determines whether B2 is new work or a pre-existing bug fix that Facebook also needs.
- **Which Graph version?** `v18.0` is in `OAUTH_CONFIGS` now; check its sunset date and bump
  Facebook and Instagram together rather than leaving two versions in one file.
- **Multi-Page accounts:** does the connect UI let the user choose the Page/IG pair, or refuse when
  there is more than one? Refusing is safe and shippable; choosing is better and is UI work this
  document does not scope.
