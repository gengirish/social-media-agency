# Push approved posts into GoHighLevel Social Planner — plan

<!-- created: 261031 -->

**Status: not built.** Item ④b of [competitive-gtm-261030.md](competitive-gtm-261030.md) §6. Everything it depends on shipped on 261031 (hand-off object, `content.approved` carrying the post, `GET /public/content`). Blocked on one thing: **a GoHighLevel sub-account to test against.** An integration that posts into a client's GHL from untested code would break product rule 1, so this stays a plan until a real call has gone through.

## Why GHL first

A large share of 2–10 person agencies run CRM, funnels and social from GoHighLevel, and buy AI inside it per sub-account (AI Employee, $50–97/sub-account/month). Pushing approved posts into its Social Planner makes CampaignForge the fulfilment layer *above* the tool the ICP already pays for, instead of a second scheduler. The generic webhook recipe ([integrations.md › Hand-off](features/integrations.md#hand-off-to-your-scheduler)) already works for GHL via Zapier; native push removes the Zap.

## Verified API facts (fetched 261031 from marketplace.gohighlevel.com)

- `POST https://services.leadconnectorhq.com/social-media-posting/{locationId}/posts`
- Headers: `Authorization: Bearer <token>`, `Version: 2023-02-21`.
- Auth: a **sub-account** OAuth token **or a Private Integration Token (PIT)**. Scope `socialplanner/post.write`.
- Body: `type` (`post` | `story` | `reel`) required. `accountIds` is required **only for non-draft posts**; `summary` is the caption; `media: [{url, type}]` with `type` in `image/jpeg|png|gif`, `video/mp4|mov|webm`; `status` may be `draft`; `scheduleDate` is required only for `scheduled` / `in_review`; `userId` is required only for non-draft OAuth-channel posts.
- 201 → `results.post._id`. Errors 400 / 401 / 422 (bodies undocumented).
- Docs exist for two versions (2021-04-15, 2023-02-21) of this page; pin the header.

## Design

**Push as a GHL draft, never scheduled.** A draft needs no `accountIds` and no `userId`, so CampaignForge never has to map its platforms onto GHL account ids, and a person in GHL picks the accounts and the time. That keeps rule 2 intact on the other side of the hand-off: CampaignForge approves copy, a human schedules it.

| Piece | Shape |
|---|---|
| Table `scheduler_connection` | `org_id`, `client_id`, `provider` (`'gohighlevel'`), `location_id`, `token_enc` (Fernet via `utils/encryption.py`, same as `platform_account.access_token_enc`), `created_by`, `status`, `last_error`, `created_at`. One per client + provider. Not a `platform_account` row: GHL is a destination for many channels, and reusing that table would put a tokened row where eight `status == "connected"` filters look for a *social* account |
| Service `services/ghl_handoff.py` | `push_draft(db, piece)` — refuses anything `handoff.handoff_item` refuses (approved / scheduled / published only); builds `{type: "post", status: "draft", summary: body + hashtags, media: [...]}`; records `metadata.handoff = {provider, external_id, at}`; 409 `already_handed_off` on a second push unless forced |
| Routes | `PUT/DELETE /clients/{id}/scheduler-connections/gohighlevel` (`workspace.manage` — it stores a credential); `POST /content/{id}/handoff/gohighlevel` (`content.approve`) |
| Verify on save | `GET /social-media-posting/{locationId}/accounts` with the token; save only on 200 so a bad PIT fails at setup, not at the first approval |
| Optional auto-push | org setting "send approved posts to GoHighLevel as drafts", run as a background task after approve (same place `content.approved` is dispatched). Off by default |
| UI | Setup › Accounts card per client ("Send approved posts to GoHighLevel — as drafts"); Queue card action **Send to GoHighLevel** on approved posts; card shows "In GoHighLevel as a draft" from `metadata.handoff` |

**Media:** map each `media_urls` entry to a MIME type by extension; skip (and say so on the card) anything not in GHL's list rather than send it unlabelled.

**Failure:** never retried silently into a second draft. 401 → mark the connection `status='invalid'` and say so in Setup; 400/422 → keep GHL's message in `metadata.handoff_error` on the card.

## To start

1. A GHL sub-account (agency trial works) with a Private Integration Token holding `socialplanner/post.write` and `socialplanner/account.readonly`, and the `locationId`.
2. One manual `curl` of create-draft with that token, to confirm the documented shape before any code.
3. Then build in the order above; tests stub `httpx` the way `test_webhooks.py` does.

## Open questions

- Does a GHL draft created by a PIT show an author in Social Planner, or a blank one? Decides whether `createdBy` must be set.
- Rate limits for the Social Planner endpoints are not on the create-post page; check the API overview before enabling auto-push.
- Pricing: native GHL push is the kind of thing the Agency tier should carry. Decide with design partners, not now.
