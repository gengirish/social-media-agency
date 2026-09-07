# Fix Plan — Four Defects

<!-- created: 260907 -->

Covers the four items from [build-status-260907.md](build-status-260907.md) §4. Ordered by the sequence they should ship in, not by severity.

| # | Defect | Effort | Ships as |
|---|---|---|---|
| 1 | Scheduler pins Neon awake 24/7 | ~half day | `services/scheduler.py` + one call site |
| 2 | `cross_learning` has no org scoping | ~2h | `services/cross_learning.py` + router |
| 3 | `_handle_subscription_updated` is a no-op | ~2h | `services/billing.py` |
| 4 | fal.ai calls the queue endpoint | ~15 min | one line + response parse |

Do 4 first (trivial, unblocks a feature), then 1, then 3, then 2. Rationale for that order is in §5.

---

## 1. Scheduler — sleep until due, not every 60s

### 1.1 The meter arithmetic

State this before changing anything, because it determines whether the fix is worth doing and it bounds what to promise.

`services/scheduler.py:48-57` runs:

```python
while self._running:
    await self._process_due_content()   # opens a session, runs a SELECT
    await self.refresh_analytics()      # in-memory day guard, no DB on most ticks
    await asyncio.sleep(60)
```

`_process_due_content` opens a real session and executes `SELECT ... FROM content_piece WHERE status='scheduled' AND scheduled_at <= now() LIMIT 10` — verified, it is genuine I/O, not a lazily-connected no-op. That is **1,440 queries/day, every day, at zero traffic.**

**The counterintuitive part, and the thing to design around:** the cost driver is the number of *wakes*, not the number of queries. Every wake restarts Neon's idle timer, so each one costs a full idle-timeout window of billed compute:

| Wake interval | Wakes/day | Neon awake/day (5-min timeout) | Saving |
|---|---|---|---|
| 60s (today) | 1,440 | **24h — pinned, can never suspend** | — |
| 15 min | 96 | ~8h | ~67% |
| 1 hour | 24 | ~2h | ~92% |
| Event-driven only | ~2 | ~10 min | ~99% |

This is why "just make the sleep longer" is a weak fix. Going 60s → 15 min feels like a 15× improvement and delivers 67%. The lever is *not waking at all* when there is nothing to do.

**Before implementing, confirm the actual timeout** — do not assume 5 minutes. Read it from the Neon API, not the dashboard:

```bash
curl -H "Authorization: Bearer $NEON_API_KEY" \
  https://console.neon.tech/api/v2/projects/$PROJECT_ID/endpoints
```

Check `suspend_timeout_seconds` on **every branch**, not just the default one — non-default branches bill their own compute. Note the sentinel values: `0` means *plan default*, `-1` means *never suspend*. A dashboard row reading "always on" is observed behaviour, not a stored setting — it is exactly what this bug produces even when autosuspend is configured correctly.

Also re-derive the baseline from the billing page (CU-hours over a known window, normalized per-day) so there is a number to verify against afterwards.

### 1.2 Both causes, and why fixing one alone does nothing

| | Cause | Status here |
|---|---|---|
| **A** | Idle-to-zero disabled outright | **Fly: yes, deliberately.** `min_machines_running = 1` with a documented reason (the campaign pipeline is a detached asyncio task; stopping the machine mid-run kills it — checkpoints survive but nothing resumes them). **Neon: unknown until 1.1 is run.** |
| **B** | A heartbeat resets the timer | **Yes — the scheduler, and only the scheduler.** |

These are independent. If Neon's autosuspend is already enabled correctly, changing console settings will produce no observable change while the 60s loop runs, and the natural conclusion is "the setting is broken." It isn't.

**Fly is a separate bill from Neon and is not fixed by this change.** `min_machines_running = 1` is a defensible call given detached pipeline tasks, but it should be priced deliberately rather than inherited. The real fix for Fly is making campaign runs resumable (a startup pass that picks up checkpointed-but-unfinished campaigns), after which `min_machines_running = 0` becomes safe. That is feature work and out of scope here — flagging it so the Fly line item doesn't get mistaken for something this plan addresses.

### 1.3 Suspects cleared

Both of these look like heartbeats and are not. Recording them so nobody "fixes" them later:

- **SSE stream** (`routers/campaigns.py:518`) — `while True` with `await asyncio.wait_for(queue.get(), timeout=120)`. That waits on an in-memory `asyncio.Queue`; the 120s heartbeat is yielded to the client and issues **no SQL**. One DB query at connection setup for the auth check, then nothing. Not a cost driver.
- **Frontend analytics flush** (`lib/analytics.ts:101`) — `setInterval` every 10s, but `flush()` returns immediately on `queue.length === 0`, so an idle tab makes no network call. It also ends the session on `visibilitychange → hidden`. Correctly built.

`pool_pre_ping=True` pings on pool checkout, not on a timer — fine.

**Not greppable, so confirm with the user:** any external uptime monitor (UptimeRobot, Pingdom, BetterStack, Checkly, Datadog synthetics) pointed at `/api/v1/health/db`. A 1-minute check against that endpoint would reproduce this bug entirely from outside the codebase and no amount of code reading will find it. `/api/v1/health` (no DB) is the safe target; `/health/db` is not.

### 1.4 The change

Decision taken: **cap the sleep at 1 hour** — ~24 wakes/day, ~92% saving, worst-case lateness bounded at 1h.

Replace the fixed sleep with a computed wake time:

```python
#: Never sleep longer than this. Bounds worst-case lateness when a *different*
#: machine schedules content this machine has not seen. Every wake costs a full
#: Neon idle-timeout window, so this is the main cost dial — raise it to save
#: more, lower it to publish more punctually.
MAX_SLEEP_SECONDS: Final = 3600
MIN_SLEEP_SECONDS: Final = 5

async def _seconds_until_next_wake(self, db, now) -> float:
    """Seconds until the next scheduled item is due, or the daily refresh.

    Returns ``MAX_SLEEP_SECONDS`` when nothing is scheduled. This is the whole
    point of the loop: with an empty queue it must issue no further queries
    until something is actually due, so Neon can suspend.
    """
    next_due = (await db.execute(
        select(func.min(ContentPiece.scheduled_at)).where(
            ContentPiece.status == "scheduled",
            ContentPiece.scheduled_at > now,
        )
    )).scalar()

    candidates = [MAX_SLEEP_SECONDS]
    if next_due is not None:
        candidates.append((next_due - now).total_seconds())
    candidates.append(self._seconds_until_next_daily_refresh(now))
    return max(MIN_SLEEP_SECONDS, min(candidates))
```

and drive the loop from it, with an interrupt so same-machine scheduling is instant:

```python
async def _run_loop(self):
    while self._running:
        try:
            await self._process_due_content()
        except Exception as e:
            logger.error("scheduler_error", error=str(e))
        try:
            await self.refresh_analytics()
        except Exception as e:
            logger.error("metrics_refresh_error", error=str(e))

        delay = await self._compute_next_wake()
        logger.info("scheduler_sleeping", seconds=round(delay))
        try:
            # Woken early by _wake.set() when content is scheduled on THIS
            # machine; otherwise sleeps the full computed delay.
            await asyncio.wait_for(self._wake.wait(), timeout=delay)
        except TimeoutError:
            pass
        finally:
            self._wake.clear()
```

`self._wake = asyncio.Event()` on the engine. Then in `routers/publishing.py`, after a successful `POST /content/{id}/schedule` commit:

```python
scheduler_engine.notify_scheduled()   # sets _wake
```

so a post scheduled for two minutes out still fires on time rather than waiting for the next computed wake.

`_compute_next_wake` needs its own short-lived session (the loop has no request session) — reuse `get_session_factory()` exactly as `_process_due_content` does, and let it close before sleeping so the connection is not held open across the sleep. **Holding a connection open defeats the entire fix** — Neon cannot suspend with an open connection regardless of query volume. Worth an explicit assertion in review.

### 1.5 Tests

`tests/test_scheduler.py` (216 tests currently pass; keep them green):

1. Empty queue → `_compute_next_wake()` returns `MAX_SLEEP_SECONDS`. This is the regression test for the whole bug.
2. One item due in 90s → returns ~90.
3. One item due in 5 days → returns `MAX_SLEEP_SECONDS`, not 5 days (cap holds).
4. Item due in the past → returns `MIN_SLEEP_SECONDS`, loop makes progress rather than spinning.
5. `notify_scheduled()` during a long sleep → loop wakes within a tick.
6. Daily refresh boundary is respected when it falls sooner than the cap.

Assert on **query count**, not just timing — patch the session factory and count `execute` calls over a simulated idle hour. A test that only checks the sleep duration will not catch a regression that reintroduces a per-tick query.

### 1.6 Verification

Unverified until a full idle window longer than the timeout has been watched — ideally 24h.

- Neon metrics should show **flat gaps**, not a continuous line.
- Expected remaining wakes to enumerate up front so the leftover spikes read as expected rather than as failure: real user traffic, the daily analytics refresh, each scheduled publish, and any deploy.
- Re-derive CU-h/day and compare against the §1.1 baseline.

Expected saving: **~90% of the Neon variable line, floored by the plan's base fee.** Report it as a range against that floor, never as a single number — and note again that the Fly line is unchanged by this work.

### 1.7 Related bug found while tracing — not a cost driver

`_process_due_content` does `SELECT ... LIMIT 10` with **no row locking**. `min_machines_running = 1` keeps one machine warm, but `auto_start_machines = true` can add more under connection load, and each machine runs its own `SchedulerEngine`. Two machines can select the same due rows and **publish the same post twice**.

Fix alongside, since the query is being touched anyway:

```python
.with_for_update(skip_locked=True)
```

Listing it separately because it is a correctness bug, not part of the idle-cost problem, and it should not be used to justify the cost work or vice versa.

---

## 2. `cross_learning` — cross-org benchmarks with a k-anonymity floor

Decision taken: **keep it cross-org, add a minimum-contributing-orgs floor.**

The reasoning: scoping to a single org makes "industry benchmark" meaningless — you would be comparing an org to itself. Cross-org aggregation is the actual differentiator here, and it is a legitimate feature. What is *not* legitimate is the current form, where an org in a thin industry can infer a competitor's numbers from an average over a handful of rows.

### 2.1 The change

In `services/cross_learning.py::get_industry_benchmarks`:

```python
#: Minimum distinct orgs that must contribute before a benchmark is returned.
#: Below this, an average is close enough to a single org's numbers to be an
#: inference channel — an org in a thin industry could read a competitor's
#: performance off it. This is a privacy floor, not a quality threshold.
MIN_CONTRIBUTING_ORGS: Final = 5
```

Add `func.count(distinct(Client.org_id))` to the existing select — same query, one more aggregate, no extra round trip. Then gate before returning:

```python
if contributing_orgs < MIN_CONTRIBUTING_ORGS:
    return {
        "industry": industry,
        "status": "unavailable",
        "reason": (
            f"Benchmarks need at least {MIN_CONTRIBUTING_ORGS} organisations "
            "contributing measured data in this industry. Fewer are available, "
            "so publishing an average could expose an individual account's "
            "performance."
        ),
        "avg_impressions": None, "avg_engagement": None,
        "avg_clicks": None, "avg_likes": None,
        "sample_size": 0,
    }
```

Return `contributing_orgs` alongside `sample_size` on the success path — a benchmark over 200 snapshots from 5 orgs is a different claim from 200 snapshots from 50, and the caller should be able to tell.

Keep `sample_size: 0` in the suppressed response rather than the true count. Returning the real sample size when suppressing leaks the very signal being suppressed.

### 2.2 Document it as deliberate

The module docstring must say cross-org aggregation is intentional and floor-protected, because this query knowingly violates the project's own "every org-scoped query filters on `org_id`" rule. Without that note, the next person to read it files it as the same bug again — which is exactly what happened between 260817 and now.

Also worth adding to `CLAUDE.md` under the tenant-isolation section: one named, documented exception is fine; an undocumented one is indistinguishable from a mistake.

### 2.3 Tests

1. 4 orgs contributing → `status: "unavailable"`, all averages `None`, `sample_size: 0`.
2. 5 orgs → `status: "available"`, averages populated, `contributing_orgs: 5`.
3. Existing zero-rows case still returns its current "no snapshots yet" reason (distinct from the privacy suppression — different reasons, both `unavailable`).
4. One org with 500 snapshots → still suppressed. Guards against anyone "fixing" the floor to count snapshots instead of orgs.

### 2.4 Frontend

`analytics/page.tsx` already calls `getCrossLearning` and gates on `sample_size > 0`, so suppression degrades correctly with no change. Improve the copy to surface the new `reason` verbatim rather than rendering an empty card — the reason now explains something the user might otherwise read as a bug.

---

## 3. `_handle_subscription_updated` — implement it

`services/billing.py:203` is `return {"status": "noted"}`. It is registered in the handler map, so `customer.subscription.updated` returns a success-shaped body and changes nothing. Every upgrade, downgrade, and `past_due` transition is silently discarded.

Consequences today: a customer who downgrades keeps their old limits indefinitely; one who upgrades gets nothing until a fresh checkout runs; a failed payment never restricts anything.

### 3.1 The change

Stripe sends the price id on the subscription object, so map it back to a tier. `PLAN_CONFIG` already carries `price_id` per tier:

```python
def _tier_for_price_id(price_id: str) -> str | None:
    """Reverse PLAN_CONFIG's price_id -> tier. Returns None if unrecognised."""
    for tier, cfg in PLAN_CONFIG.items():
        if cfg["price_id"] and cfg["price_id"] == price_id:
            return tier
    return None
```

Then:

```python
async def _handle_subscription_updated(self, db: AsyncSession, data: dict) -> dict:
    sub_id = data.get("id")
    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == sub_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        # Mirror _handle_invoice_paid: an unmatched subscription is an
        # operational signal, not a no-op.
        logger.warning("stripe_subscription_updated_no_local_sub", subscription_id=sub_id)
        return {"status": "ignored", "reason": "no_local_subscription"}

    items = data.get("items", {}).get("data", [])
    price_id = items[0].get("price", {}).get("id", "") if items else ""
    tier = _tier_for_price_id(price_id)

    if tier is None:
        # Never guess a tier. Applying the wrong limits is worse than applying
        # none — record it loudly and leave entitlements untouched.
        logger.error(
            "stripe_unknown_price_id",
            subscription_id=sub_id, price_id=price_id, org_id=str(sub.org_id),
        )
        return {"status": "error", "reason": "unknown_price_id", "price_id": price_id}

    plan = PLAN_CONFIG[tier]
    sub.plan_tier = tier
    sub.clients_limit = plan["clients_limit"]
    sub.posts_limit = plan["posts_limit"]
    sub.status = data.get("status", sub.status)

    for field, key in (
        ("current_period_start", "current_period_start"),
        ("current_period_end", "current_period_end"),
    ):
        ts = data.get(key)
        if ts:
            setattr(sub, field, datetime.fromtimestamp(ts, tz=UTC))

    await db.commit()
    logger.info(
        "subscription_updated",
        org_id=str(sub.org_id), plan=tier, status=sub.status,
    )
    return {"status": "updated", "plan": tier, "subscription_status": sub.status}
```

Two deliberate choices worth defending in review:

- **`status` is taken from Stripe verbatim**, so `past_due` / `unpaid` / `incomplete` land in the DB. Whether those states restrict access is a separate policy decision — nothing enforces on `status` today. Do not silently invent that enforcement inside a webhook handler; if lockout on `past_due` is wanted, it belongs in the limit checks as its own change.
- **An unrecognised price id changes nothing and logs at ERROR.** The tempting alternative — default to `starter` — hands out or removes entitlements based on a guess. A misconfigured `STRIPE_PRICE_*` env var would then quietly downgrade every paying customer.

`current_period_start/end` are already columns on `Subscription` and are currently never populated by any handler. This fills them.

### 3.2 Tests

1. Upgrade starter → growth: limits become 10 / 1000, `plan_tier == "growth"`.
2. Downgrade growth → starter: limits drop to 3 / 200.
3. `status: "past_due"` is persisted; limits unchanged.
4. Unknown price id: returns `status: "error"`, subscription row **untouched**.
5. No local subscription for the Stripe id: returns `ignored`, no exception.
6. Period timestamps are converted to tz-aware datetimes.

### 3.3 Manual verification

Stripe CLI against a local instance:

```bash
stripe listen --forward-to localhost:8001/api/v1/billing/webhook
stripe trigger customer.subscription.updated
```

`STRIPE_WEBHOOK_SECRET` must be set — the endpoint returns 503 without it, which is correct behaviour and not a bug to work around.

---

## 4. fal.ai — wrong endpoint

`services/image_generation.py:50` posts to `https://queue.fal.run/fal-ai/flux/schnell`. The queue endpoint returns `{"request_id", "status_url"}` with HTTP 200 — never `{"images": [...]}`. The parser cannot match, falls through to `{"status": "error", "message": "fal.ai returned 200"}`. **The feature has never worked.**

### 4.1 The change

```python
"https://fal.run/fal-ai/flux/schnell",
```

The sync endpoint returns the images inline, which is what the existing parser already expects — so one line.

But the current code has a second flaw that will survive the URL fix: a 200 with an unexpected body falls into the same branch as a 500, both reporting `"fal.ai returned 200"`. Distinguish them, or the next protocol change is equally invisible:

```python
if resp.status_code == 200:
    data = resp.json()
    images = data.get("images", [])
    if images:
        return {"status": "generated", "image_url": images[0].get("url", ""), "platform": platform}
    # 200 with no images means the response shape changed — say so, rather
    # than reporting it identically to an HTTP failure.
    logger.error("fal_unexpected_response_shape", keys=sorted(data.keys()))
    return {
        "status": "error",
        "message": "fal.ai returned 200 with no images — response shape may have changed.",
        "image_url": None,
    }
return {"status": "error", "message": f"fal.ai returned {resp.status_code}", "image_url": None}
```

Add a timeout note: `flux/schnell` is fast, but the sync endpoint blocks for the full generation. The existing `timeout=60` is adequate for schnell and would not be for a larger model — worth a comment so nobody swaps the model without revisiting it.

### 4.2 Verification

Cannot be verified without a `FAL_API_KEY` — that is why it was left unfixed on 260817. Needs either a key in the dev environment or a recorded-response test. Do not ship it as "fixed" on inspection alone; the whole reason this bug survived is that the failure looked like a configuration problem.

Unit-testable without a key via `httpx.MockTransport` (the pattern already exists in `webhook_dispatcher.py`, which documents the seam):

1. 200 + `{"images": [{"url": ...}]}` → `status: "generated"`.
2. 200 + `{"request_id": ...}` (the current bug's actual response) → `status: "error"` with the shape-changed message, **not** the generic HTTP message. This is the regression test.
3. 500 → generic HTTP message.
4. Blank key → `status: "skipped"`, no HTTP call made.

Note there is no UI caller (`generateImage` is unused), so nothing breaks either way — but it also means fixing this does not surface the feature. That needs the separate UI work in build-status §2.

---

## 5. Sequencing

| Order | Item | Why here |
|---|---|---|
| 1 | **fal.ai (§4)** | 15 minutes, isolated, no dependencies. Clears the decks. |
| 2 | **Scheduler (§1)** | Costs money every day it waits. Needs the Neon reading from §1.1 first, which can start immediately. |
| 3 | **Stripe (§3)** | Revenue-correctness. Only matters once real subscriptions exist — check whether beta is on live mode; if it's test-only this can trail slightly, but not past launch. |
| 4 | **cross_learning (§2)** | Smallest blast radius, and the endpoint's benchmark half is barely reachable today. Do it before any marketing describes benchmarking as a feature. |

§1 and §3 both touch code with real tests; keep them as separate PRs so a revert of one does not drag the other.

**Gates to hold on every PR:** `ruff check src/ tests/` must stay at 0 (it was 290 three weeks ago — do not give that back), and `pytest tests/` must stay at 216+. Mypy is at 414 under `strict = true`; do not let these PRs raise it.

---

## Unresolved

- **Is there an external uptime monitor pointed at `/api/v1/health/db`?** Not findable in the repo. If one exists at a sub-timeout interval, it reproduces §1 entirely from outside the codebase and the fix will appear not to work.
- **Neon's actual `suspend_timeout_seconds`, per branch.** Everything in §1.1 assumes the 5-minute plan default. Read it from the API before quoting a saving.
- **Neon max autoscale CU.** Separate lever from the idle floor, and not yet checked. A high ceiling on a small database is a runaway-cost hazard with no upside.
- **Is beta running Stripe in live or test mode?** Sets the urgency of §3.
- **Does `past_due` restrict access?** Nothing enforces on `status` today. §3 persists the state; someone still has to decide what it means.
- **Is `min_machines_running = 1` load-bearing long-term?** The real fix is resuming checkpointed campaigns at startup, which would let it go to 0 and cut the Fly bill too. Out of scope here, but it is the larger half of the always-on cost.
