"""The campaign pack — one client-ready document per campaign, under the agency's name.

This is the deliverable an agency puts in front of its client: the brief, the
strategy, keyword research, every post and ad variant, the brand-QA findings, and
the approval record (moderation, who approved, what the client said), closed by a
plain statement of where AI was used.

:func:`build_pack` assembles it as JSON from rows that already exist — the
campaign, its ``content_piece`` rows, and the ``agent_run`` output of the
strategy, SEO and QA nodes. :func:`render_pack_html` turns that into one
self-contained HTML file with print styles, so "Save as PDF" in any browser is the
PDF path and no PDF engine has to ship in the backend image.

Product rule 4 shapes what is left out as much as what is put in:

* No QA *scores*. The QA agent rates its own run 0–10; in a client document that
  reads as a quality metric, which it is not. Pass/fail, issues and the summary are
  kept, and an unparsed QA run says the campaign was **not** quality-checked.
* No keyword volumes or difficulty. Nothing measures them; the SEO agent guesses.
* KPIs are labelled targets the strategy agent proposed, never results.
* An approval with no record says "approver not recorded", not a name.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from html import escape
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agency.models.tables import AgentRun, Campaign, Client, ContentPiece, Organization, User
from agency.services.url_safety import UnsafeURLError, assert_safe_link
from agency.services.white_label import agency_branding

#: Graph node names (graph.py) whose recorded output the pack reads.
NODE_STRATEGY: Final = "strategise"
NODE_SEO: Final = "seo_research"
NODE_QA: Final = "qa_check"

#: Statuses that mean "a person approved this" (published implies it was approved).
APPROVED_STATUSES: Final = frozenset({"approved", "scheduled", "published"})
#: Pieces not worth putting in front of a client: nothing usable was generated.
EXCLUDED_STATUSES: Final = frozenset({"failed"})

PLATFORM_LABELS: Final = {
    "twitter": "X",
    "linkedin": "LinkedIn",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "google": "Google Ads",
    "meta": "Meta Ads",
}


class PackError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [t for t in (_text(v) for v in _list(value)) if t]


async def _latest_outputs(
    db: AsyncSession, *, org_id: UUID, campaign_id: UUID
) -> dict[str, dict[str, Any]]:
    """``{node: parsed output}`` for the most recent *completed* run of each node.

    A re-run adds rows rather than replacing them, so "latest" is what the current
    content came from. Output that is not a JSON object is skipped, not guessed at.
    """
    rows = (
        await db.execute(
            select(AgentRun.agent_name, AgentRun.output)
            .where(
                AgentRun.org_id == org_id,
                AgentRun.campaign_id == campaign_id,
                AgentRun.status == "completed",
                AgentRun.agent_name.in_((NODE_STRATEGY, NODE_SEO, NODE_QA)),
            )
            .order_by(AgentRun.created_at.desc())
        )
    ).all()
    out: dict[str, dict[str, Any]] = {}
    for name, raw in rows:
        if name in out:
            continue
        try:
            parsed = json.loads(raw or "")
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            out[name] = parsed
    return out


def _strategy_section(output: dict[str, Any] | None) -> dict[str, Any] | None:
    strategy = _dict((output or {}).get("strategy"))
    if not strategy:
        return None
    if strategy.get("raw_output") and len(strategy) == 1:
        return {"raw": _text(strategy["raw_output"])}
    audience = _dict(strategy.get("target_audience"))
    channels = []
    for platform, plan in _dict(strategy.get("channel_strategy")).items():
        plan = _dict(plan)
        channels.append(
            {
                "platform": str(platform),
                "role": _text(plan.get("role")),
                "posting_frequency": _text(plan.get("posting_frequency")),
                "content_mix": _strings(plan.get("content_mix")),
                "best_times": _strings(plan.get("best_times")),
            }
        )
    return {
        "theme": _text(strategy.get("campaign_theme")),
        "audience": {
            "primary": _text(audience.get("primary")) or _text(strategy.get("target_audience")),
            "secondary": _text(audience.get("secondary")),
            "pain_points": _strings(audience.get("pain_points")),
            "motivations": _strings(audience.get("motivations")),
        },
        "pillars": _strings(strategy.get("content_pillars")),
        "channels": channels,
        "timeline": [
            {
                "week": _text(_dict(w).get("week")),
                "theme": _text(_dict(w).get("theme")),
                "focus": _text(_dict(w).get("focus")),
            }
            for w in _list(strategy.get("campaign_timeline"))
            if isinstance(w, dict)
        ],
        "proposed_kpis": [
            {
                "metric": _text(_dict(k).get("metric")),
                "target": _text(_dict(k).get("target")),
                "measurement": _text(_dict(k).get("measurement")),
            }
            for k in _list(strategy.get("kpis"))
            if isinstance(k, dict) and _text(k.get("metric"))
        ],
        "competitive_angle": _text(strategy.get("competitive_angle")),
    }


def _seo_section(output: dict[str, Any] | None) -> dict[str, Any] | None:
    keywords = []
    for kw in _list((output or {}).get("seo_keywords")):
        if isinstance(kw, dict) and _text(kw.get("keyword")):
            keywords.append({"keyword": _text(kw["keyword"]), "intent": _text(kw.get("intent"))})
        elif _text(kw):
            keywords.append({"keyword": _text(kw), "intent": ""})
    return {"keywords": keywords} if keywords else None


def _qa_section(output: dict[str, Any] | None) -> dict[str, Any] | None:
    qa = _dict((output or {}).get("qa_feedback"))
    if not qa:
        return None
    coverage = _dict(qa.get("coverage"))
    passed = qa.get("pass")
    return {
        "checked": not qa.get("error"),
        "error": _text(qa.get("error")) or None,
        "passed": passed if isinstance(passed, bool) else None,
        "summary": _text(qa.get("summary")) if not qa.get("error") else "",
        "issues": [
            {
                "severity": _text(_dict(i).get("severity")) or "note",
                "issue": _text(_dict(i).get("issue")),
                "fix": _text(_dict(i).get("fix_suggestion")),
            }
            for i in _list(qa.get("issues"))
            if isinstance(i, dict) and _text(i.get("issue"))
        ],
        "strengths": _strings(qa.get("strengths")),
        "coverage": {
            "content_reviewed": coverage.get("content_reviewed"),
            "content_total": coverage.get("content_total"),
            "ads_reviewed": coverage.get("ads_reviewed"),
            "ads_total": coverage.get("ads_total"),
            "complete": coverage.get("complete"),
        }
        if coverage
        else None,
    }


def _safe_link(value: Any) -> str | None:
    """A link the document may render as ``href`` — checked again, never trusted."""
    text = _text(value)
    if not text:
        return None
    try:
        return assert_safe_link(text)
    except UnsafeURLError:
        return None


def _record(piece: Any, users: dict[str, str]) -> dict[str, Any]:
    """The approval trail of one piece, in words a client can read."""
    meta = _dict(piece.metadata_)
    moderation = _dict(meta.get("moderation"))
    approval = _dict(meta.get("approval"))
    review = _dict(meta.get("client_review"))

    mod_status = _text(moderation.get("status")) or None
    override_by = moderation.get("override_by")
    approved = piece.status in APPROVED_STATUSES
    approver: str | None = None
    if approved and approval:
        if approval.get("via") == "client_link":
            name = _text(approval.get("name"))
            approver = f"Client ({name})" if name else "Client"
        else:
            approver = users.get(str(approval.get("by")), "A team member")
    return {
        "approved": approved,
        "approved_at": approval.get("at") if approved else None,
        "approved_via": approval.get("via") if approved else None,
        "approved_by": approver,
        "approver_recorded": bool(approved and approval),
        "moderation": {
            "status": mod_status,
            "issue_count": len(_list(moderation.get("issues"))),
            "override_by": users.get(str(override_by), "A team member") if override_by else None,
        }
        if mod_status
        else None,
        "client_review": {
            "decision": _text(review.get("decision")),
            "comment": _text(review.get("comment")) or None,
            "name": _text(review.get("name")) or None,
            "at": review.get("at"),
        }
        if review.get("decision")
        else None,
        "edited_before_approval": bool(meta.get("edited_before_approval")),
    }


def _piece_entry(piece: Any, users: dict[str, str]) -> dict[str, Any]:
    meta = _dict(piece.metadata_)
    ad = _dict(meta.get("ad"))
    return {
        "id": str(piece.id),
        "platform": piece.platform,
        "kind": "ad" if ad.get("fields") else "post",
        "title": piece.title or "",
        "body": piece.body or "",
        "hashtags": _strings(piece.hashtags),
        "media_count": len(_list(piece.media_urls)),
        "ad": {
            "angle": _text(ad.get("angle")),
            "cta": _text(ad.get("cta")),
            "fields": {k: v for k, v in _dict(ad.get("fields")).items() if v},
        }
        if ad.get("fields")
        else None,
        "status": piece.status,
        "scheduled_at": _iso(piece.scheduled_at),
        "published_at": _iso(piece.published_at),
        "post_url": _safe_link(meta.get("post_url")),
        "record": _record(piece, users),
    }


async def build_pack(db: AsyncSession, *, org_id: UUID, campaign_id: UUID) -> dict[str, Any]:
    """The pack as JSON. 404 when the campaign is not this org's."""
    campaign = (
        await db.execute(
            select(Campaign).where(Campaign.id == campaign_id, Campaign.org_id == org_id)
        )
    ).scalar_one_or_none()
    if campaign is None:
        raise PackError(404, "Campaign not found")
    org = (
        await db.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one()
    client = (
        await db.execute(
            select(Client).where(Client.id == campaign.client_id, Client.org_id == org_id)
        )
    ).scalar_one_or_none()

    pieces = [
        p
        for p in (
            await db.execute(
                select(ContentPiece)
                .where(ContentPiece.org_id == org_id, ContentPiece.campaign_id == campaign_id)
                .order_by(ContentPiece.platform, ContentPiece.created_at)
            )
        )
        .scalars()
        .all()
        if p.status not in EXCLUDED_STATUSES
    ]

    user_ids: set[str] = set()
    for p in pieces:
        meta = _dict(p.metadata_)
        for value in (
            _dict(meta.get("approval")).get("by"),
            _dict(meta.get("moderation")).get("override_by"),
        ):
            if value:
                user_ids.add(str(value))
    users: dict[str, str] = {}
    valid_ids: list[UUID] = []
    for uid in user_ids:
        try:
            valid_ids.append(UUID(uid))
        except ValueError:
            continue
    if valid_ids:
        for uid, full_name, email in (
            await db.execute(
                select(User.id, User.full_name, User.email).where(
                    User.org_id == org_id, User.id.in_(valid_ids)
                )
            )
        ).all():
            users[str(uid)] = full_name or email

    outputs = await _latest_outputs(db, org_id=org_id, campaign_id=campaign_id)
    entries = [_piece_entry(p, users) for p in pieces]
    posts = [e for e in entries if e["kind"] == "post"]
    ads = [e for e in entries if e["kind"] == "ad"]

    approved = sum(1 for e in entries if e["record"]["approved"])
    summary = {
        "items": len(entries),
        "posts": len(posts),
        "ads": len(ads),
        "approved": approved,
        "pending": sum(1 for e in entries if e["status"] in ("draft", "rejected")),
        "scheduled": sum(1 for e in entries if e["status"] == "scheduled"),
        "published": sum(1 for e in entries if e["status"] == "published"),
        "client_approved": sum(
            1 for e in entries if e["record"]["approved_via"] == "client_link"
        ),
        "changes_requested": sum(
            1
            for e in entries
            if (e["record"]["client_review"] or {}).get("decision") == "changes_requested"
            and not e["record"]["approved"]
        ),
        "moderation_overridden": sum(
            1 for e in entries if (e["record"]["moderation"] or {}).get("status") == "overridden"
        ),
    }
    agency = await agency_branding(db, org)
    budget = _dict(campaign.budget).get("total_usd")
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "agency": agency,
        "client": {"id": str(campaign.client_id), "name": client.brand_name if client else ""},
        "campaign": {
            "id": str(campaign.id),
            "name": campaign.name,
            "objective": campaign.objective or "",
            "channels": list(campaign.channels or []),
            "start_date": str(campaign.start_date) if campaign.start_date else None,
            "end_date": str(campaign.end_date) if campaign.end_date else None,
            "status": campaign.status,
            "budget_usd": budget if isinstance(budget, (int, float)) and budget > 0 else None,
        },
        "strategy": _strategy_section(outputs.get(NODE_STRATEGY)),
        "seo": _seo_section(outputs.get(NODE_SEO)),
        "qa": _qa_section(outputs.get(NODE_QA)),
        "posts": posts,
        "ads": ads,
        "summary": summary,
        "disclosure": disclosure_text(agency["name"], summary),
    }


def disclosure_text(agency_name: str, summary: dict[str, Any]) -> str:
    """The AI-use statement. Every clause is true by construction of the product.

    Moderation-before-approval and "nothing published without approval" are
    enforced in code (services/content_approval.py), so they can be stated; the
    counts are read from the rows, so they can be stated too.
    """
    pending = summary["pending"]
    lines = [
        f"Prepared by {agency_name} with AI assistance. The strategy, keyword research, "
        "post copy, ad copy and brand-QA review in this pack were drafted by AI agents "
        f"and reviewed by {agency_name}.",
        "Every item marked Approved went through an automated moderation check and was "
        "approved by a person before it could be scheduled or published; nothing is "
        "published without that approval. Where the check was unavailable, or flagged "
        "something a person chose to approve anyway, the approval record says so.",
    ]
    if pending:
        lines.append(
            f"{pending} item{'s' if pending != 1 else ''} in this pack "
            f"{'are' if pending != 1 else 'is'} still pending and "
            f"{'have' if pending != 1 else 'has'} not been approved."
        )
    return " ".join(lines)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
_DEFAULT_ACCENT: Final = "#1f3a5f"

_STATUS_LABELS: Final = {
    "draft": "Pending",
    "rejected": "Pending",
    "approved": "Approved",
    "scheduled": "Scheduled",
    "published": "Published",
}


def _e(value: Any) -> str:
    return escape(str(value), quote=True) if value not in (None, "") else ""


def _date(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%d %b %Y")
    except ValueError:
        return value


def _label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform.replace("_", " ").title())


def _record_line(record: dict[str, Any]) -> str:
    if record["approved"]:
        if not record["approver_recorded"]:
            return "Approved — approver not recorded (approved before approvals were logged)"
        via = {
            "client_link": "via client review link",
            "retry": "re-approved after a failed publish",
        }.get(record["approved_via"] or "", "")
        parts = [f"Approved by {record['approved_by']}", via, _date(record["approved_at"])]
        return " · ".join(p for p in parts if p)
    review = record["client_review"] or {}
    if review.get("decision") == "changes_requested":
        who = f"Client ({review['name']})" if review.get("name") else "Client"
        return f"{who} asked for changes · {_date(review.get('at'))}"
    if review.get("decision") == "approval_held":
        return "Client approved — held for the agency to check before approval"
    return "Pending — not yet approved"


def _moderation_line(record: dict[str, Any]) -> str:
    mod = record["moderation"]
    if not mod:
        return "Not yet checked" if not record["approved"] else "No moderation record"
    if mod["status"] == "passed":
        return "Passed"
    if mod["status"] == "unavailable":
        return "Check unavailable at approval time"
    if mod["status"] == "overridden":
        n = mod["issue_count"]
        return f"Flagged {n} issue{'s' if n != 1 else ''}; approved anyway by {mod['override_by']}"
    return _e(mod["status"])


def _list_html(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{_e(i)}</li>" for i in items) + "</ul>" if items else ""


def _strategy_html(strategy: dict[str, Any] | None) -> str:
    if not strategy:
        return '<p class="muted">No strategy output is recorded for this campaign.</p>'
    if "raw" in strategy:
        return (
            '<p class="muted">The strategy agent returned unstructured text:</p>'
            f'<pre>{_e(strategy["raw"])}</pre>'
        )
    out = []
    if strategy["theme"]:
        out.append(f'<p class="lede">{_e(strategy["theme"])}</p>')
    aud = strategy["audience"]
    if aud["primary"] or aud["secondary"]:
        out.append("<h3>Audience</h3>")
        if aud["primary"]:
            out.append(f"<p><strong>Primary:</strong> {_e(aud['primary'])}</p>")
        if aud["secondary"]:
            out.append(f"<p><strong>Secondary:</strong> {_e(aud['secondary'])}</p>")
        if aud["pain_points"]:
            out.append("<p><strong>Pain points</strong></p>" + _list_html(aud["pain_points"]))
        if aud["motivations"]:
            out.append("<p><strong>Motivations</strong></p>" + _list_html(aud["motivations"]))
    if strategy["pillars"]:
        out.append("<h3>Content pillars</h3>" + _list_html(strategy["pillars"]))
    if strategy["channels"]:
        rows = "".join(
            f"<tr><td>{_e(_label(c['platform']))}</td><td>{_e(c['role'])}</td>"
            f"<td>{_e(c['posting_frequency'])}</td><td>{_e(', '.join(c['content_mix']))}</td></tr>"
            for c in strategy["channels"]
        )
        out.append(
            "<h3>Channel plan</h3><table><thead><tr><th>Channel</th><th>Role</th>"
            f"<th>Frequency</th><th>Content mix</th></tr></thead><tbody>{rows}</tbody></table>"
        )
    if strategy["timeline"]:
        rows = "".join(
            f"<tr><td>{_e(w['week'])}</td><td>{_e(w['theme'])}</td><td>{_e(w['focus'])}</td></tr>"
            for w in strategy["timeline"]
        )
        out.append(
            "<h3>Timeline</h3><table><thead><tr><th>Week</th><th>Theme</th><th>Focus</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )
    if strategy["proposed_kpis"]:
        rows = "".join(
            f"<tr><td>{_e(k['metric'])}</td><td>{_e(k['target'])}</td><td>{_e(k['measurement'])}</td></tr>"
            for k in strategy["proposed_kpis"]
        )
        out.append(
            "<h3>Proposed KPIs</h3>"
            '<p class="note">Targets the strategy proposes, to agree with you — not results.</p>'
            "<table><thead><tr><th>Metric</th><th>Proposed target</th><th>How measured</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )
    if strategy["competitive_angle"]:
        out.append(f"<h3>Competitive angle</h3><p>{_e(strategy['competitive_angle'])}</p>")
    return "".join(out)


def _seo_html(seo: dict[str, Any] | None) -> str:
    if not seo:
        return '<p class="muted">No keyword research is recorded for this campaign.</p>'
    rows = "".join(
        f"<tr><td>{_e(k['keyword'])}</td><td>{_e(k['intent'])}</td></tr>" for k in seo["keywords"]
    )
    return (
        '<p class="note">Keyword themes chosen by AI research. No search volumes were measured, '
        "so none are shown.</p>"
        "<table><thead><tr><th>Keyword</th><th>Search intent</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _item_html(entry: dict[str, Any]) -> str:
    rec = entry["record"]
    status = _STATUS_LABELS.get(entry["status"], entry["status"].title())
    when = ""
    if entry["status"] == "scheduled" and entry["scheduled_at"]:
        when = f" · {_date(entry['scheduled_at'])}"
    elif entry["status"] == "published" and entry["published_at"]:
        when = f" · {_date(entry['published_at'])}"
    head = (
        f'<div class="item-head"><span class="chip">{_e(_label(entry["platform"]))}</span>'
        f'<span class="status s-{_e(entry["status"])}">{_e(status)}{_e(when)}</span></div>'
    )
    if entry["ad"]:
        ad = entry["ad"]
        fields = []
        for key, value in ad["fields"].items():
            label = key.replace("_", " ").capitalize()
            values = value if isinstance(value, list) else [value]
            fields.append(
                f'<div class="field"><span class="flabel">{_e(label)}</span>'
                + "".join(f"<p>{_e(v)}</p>" for v in values if _text(v))
                + "</div>"
            )
        body = "".join(fields)
        if ad["cta"]:
            body += (
                '<div class="field"><span class="flabel">Call to action</span>'
                f'<p>{_e(ad["cta"])}</p></div>'
            )
        title = f'<h4>{_e(entry["title"])}</h4>' if entry["title"] else ""
    else:
        title = ""
        body = f'<p class="copy">{_e(entry["body"])}</p>'
        if entry["hashtags"]:
            tags = " ".join(f"#{_e(t.lstrip('#'))}" for t in entry["hashtags"])
            body += f'<p class="tags">{tags}</p>'
        if entry["media_count"]:
            n = entry["media_count"]
            body += f'<p class="muted small">{n} image{"s" if n != 1 else ""} attached</p>'
    review = rec["client_review"] or {}
    note = ""
    if review.get("comment"):
        who = review.get("name") or "Client"
        note = f'<p class="client-note"><strong>{_e(who)}:</strong> “{_e(review["comment"])}”</p>'
    link = ""
    if entry["post_url"]:
        link = f'<p class="small"><a href="{_e(entry["post_url"])}">View the live post</a></p>'
    return (
        f'<article class="item">{head}{title}{body}{note}{link}'
        f'<p class="record">{_e(_record_line(rec))}</p></article>'
    )


def _qa_html(qa: dict[str, Any] | None) -> str:
    if not qa:
        return '<p class="muted">No brand-QA run is recorded for this campaign.</p>'
    if not qa["checked"]:
        return f'<p class="warn">{_e(qa["error"] or "This campaign was not quality-checked.")}</p>'
    out = []
    verdicts = {True: "Passed", False: "Issues to resolve", None: "No verdict recorded"}
    verdict = verdicts[qa["passed"]]
    out.append(f'<p><strong>Result:</strong> {_e(verdict)}</p>')
    cov = qa["coverage"]
    if cov and cov.get("complete") is False:
        out.append(
            f'<p class="note">The QA pass reviewed {_e(cov.get("content_reviewed"))} of '
            f'{_e(cov.get("content_total"))} posts and {_e(cov.get("ads_reviewed"))} of '
            f'{_e(cov.get("ads_total"))} ads.</p>'
        )
    if qa["summary"]:
        out.append(f"<p>{_e(qa['summary'])}</p>")
    if qa["issues"]:
        rows = "".join(
            f"<tr><td>{_e(i['severity'])}</td><td>{_e(i['issue'])}</td><td>{_e(i['fix'])}</td></tr>"
            for i in qa["issues"]
        )
        out.append(
            "<h3>Findings</h3><table><thead><tr><th>Severity</th><th>Finding</th>"
            "<th>Suggested fix</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )
    if qa["strengths"]:
        out.append("<h3>Strengths</h3>" + _list_html(qa["strengths"]))
    return "".join(out)


def _record_table(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return '<p class="muted">Nothing to record yet.</p>'
    rows = []
    for e in entries:
        rec = e["record"]
        excerpt = (e["title"] if e["ad"] else e["body"]).strip().replace("\n", " ")
        if len(excerpt) > 70:
            excerpt = excerpt[:69] + "…"
        review = rec["client_review"] or {}
        client = {
            "approved": "Approved",
            "changes_requested": "Asked for changes",
            "approval_held": "Approved (held for agency check)",
        }.get(review.get("decision") or "", "—")
        rows.append(
            f"<tr><td>{_e(_label(e['platform']))}</td><td>{_e(excerpt)}</td>"
            f"<td>{_e(_STATUS_LABELS.get(e['status'], e['status']))}</td>"
            f"<td>{_e(_moderation_line(rec))}</td><td>{_e(_record_line(rec))}</td>"
            f"<td>{_e(client)}</td></tr>"
        )
    return (
        "<table class=\"record-table\"><thead><tr><th>Channel</th><th>Item</th><th>Status</th>"
        "<th>Moderation</th><th>Approval</th><th>Client</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


_CSS: Final = """
/* --accent is set per agency in render_pack_html */
:root { --ink: #16202b; --muted: #5b6672; --line: #dde2e8; --soft: #f5f7f9; }
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #fff;
  color: var(--ink);
  font-size: 15px;
  line-height: 1.55;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, Arial, sans-serif;
}
.page { max-width: 860px; margin: 0 auto; padding: 48px 32px 64px; }
.toolbar {
  position: sticky;
  top: 0;
  background: var(--soft);
  border-bottom: 1px solid var(--line);
  padding: 10px 16px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.toolbar button {
  font: inherit;
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid var(--accent);
  background: var(--accent);
  color: #fff;
  cursor: pointer;
}
header.cover {
  border-bottom: 3px solid var(--accent);
  padding-bottom: 24px;
  margin-bottom: 28px;
}
.agency {
  display: flex;
  align-items: center;
  gap: 12px;
  font-weight: 600;
  font-size: 14px;
  color: var(--muted);
}
.logo { max-height: 40px; max-width: 160px; object-fit: contain; }
h1 { font-size: 30px; line-height: 1.2; margin: 18px 0 6px; }
.kicker {
  text-transform: uppercase;
  letter-spacing: .08em;
  font-size: 11px;
  color: var(--accent);
  font-weight: 700;
}
dl.meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px 20px;
  margin: 18px 0 0;
}
dl.meta dt {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--muted);
}
dl.meta dd { margin: 2px 0 0; font-weight: 600; }
.glance { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 24px 0 8px; }
.stat { border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }
.stat .n { display: block; font-size: 22px; font-weight: 700; }
.stat .l { font-size: 12px; color: var(--muted); }
section { margin-top: 36px; }
h2 {
  font-size: 20px;
  margin: 0 0 12px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--line);
}
h2 .num { color: var(--accent); font-size: 13px; margin-right: 10px; font-weight: 700; }
h3 { font-size: 15px; margin: 20px 0 8px; }
h4 { margin: 6px 0; font-size: 14px; }
.lede { font-size: 17px; font-weight: 600; }
.note { font-size: 13px; color: var(--muted); font-style: italic; }
.muted { color: var(--muted); }
.small { font-size: 12px; }
.warn { border-left: 3px solid #b45309; background: #fffbeb; padding: 10px 12px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; margin: 8px 0; }
th, td {
  text-align: left;
  vertical-align: top;
  padding: 7px 8px;
  border-bottom: 1px solid var(--line);
}
th { background: var(--soft); font-weight: 600; }
.item {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px 16px;
  margin: 10px 0;
  break-inside: avoid;
}
.item-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.chip {
  font-size: 12px;
  font-weight: 600;
  background: var(--soft);
  border: 1px solid var(--line);
  padding: 2px 8px;
  border-radius: 999px;
}
.status { font-size: 12px; font-weight: 600; color: var(--muted); }
.s-approved, .s-scheduled, .s-published { color: #166534; }
.copy { white-space: pre-wrap; margin: 0 0 6px; }
.tags { color: var(--accent); font-size: 13px; margin: 4px 0; }
.field { margin: 6px 0; }
.field p { margin: 2px 0; }
.flabel {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--muted);
}
.client-note {
  background: var(--soft);
  border-left: 3px solid var(--accent);
  padding: 8px 10px;
  font-size: 13px;
}
.record {
  font-size: 12px;
  color: var(--muted);
  border-top: 1px dashed var(--line);
  padding-top: 6px;
  margin: 8px 0 0;
}
.disclosure {
  margin-top: 40px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  font-size: 13px;
  color: var(--muted);
}
pre {
  white-space: pre-wrap;
  background: var(--soft);
  padding: 12px;
  border-radius: 6px;
  font-size: 13px;
}
@media (max-width: 640px) {
  .page { padding: 28px 16px; }
  .glance { grid-template-columns: repeat(2, 1fr); }
  .record-table { font-size: 12px; }
}
@page { margin: 16mm 14mm; }
@media print {
  .toolbar { display: none; }
  .page { padding: 0; max-width: none; }
  section { break-inside: auto; }
  h2 { break-after: avoid; }
  a { color: inherit; }
}
"""


def render_pack_html(pack: dict[str, Any]) -> str:
    """One self-contained, printable HTML document. Every value is escaped."""
    agency = pack["agency"]
    accent = agency.get("primary_color") or _DEFAULT_ACCENT
    campaign = pack["campaign"]
    s = pack["summary"]
    logo = (
        f'<img class="logo" src="{_e(agency["logo_url"])}" alt="{_e(agency["name"])}">'
        if agency.get("logo_url")
        else ""
    )
    dates = (_date(campaign["start_date"]), _date(campaign["end_date"]))
    period = " – ".join(d for d in dates if d)
    channels = ", ".join(_label(c) for c in campaign["channels"])
    meta_rows = [
        ("Client", pack["client"]["name"]),
        ("Campaign", campaign["name"]),
        ("Period", period),
        ("Channels", channels),
        ("Prepared", _date(pack["generated_at"])),
    ]
    if campaign["budget_usd"]:
        meta_rows.insert(4, ("Budget", f"${campaign['budget_usd']:,.0f}"))
    meta_html = "".join(
        f"<div><dt>{_e(k)}</dt><dd>{_e(v)}</dd></div>" for k, v in meta_rows if v
    )
    glance = [
        ("Posts", s["posts"]),
        ("Ad variants", s["ads"]),
        ("Approved", s["approved"]),
        ("Pending", s["pending"]),
    ]
    glance_html = "".join(
        f'<div class="stat"><span class="n">{n}</span><span class="l">{_e(label)}</span></div>'
        for label, n in glance
    )

    by_platform: dict[str, list[dict[str, Any]]] = {}
    for post in pack["posts"]:
        by_platform.setdefault(post["platform"], []).append(post)
    posts_html = "".join(
        f"<h3>{_e(_label(p))}</h3>" + "".join(_item_html(x) for x in items)
        for p, items in by_platform.items()
    ) or '<p class="muted">No posts in this campaign yet.</p>'
    ads_html = "".join(_item_html(a) for a in pack["ads"])

    sections = [
        (
            "Brief",
            f"<p>{_e(campaign['objective'])}</p>"
            if campaign["objective"]
            else '<p class="muted">No brief recorded.</p>',
        ),
        ("Strategy", _strategy_html(pack["strategy"])),
        ("Keyword research", _seo_html(pack["seo"])),
        ("Posts", posts_html),
    ]
    if pack["ads"]:
        no_spend = '<p class="note">Copy and structure only — no ads were created or bought.</p>'
        sections.append(("Ad copy", no_spend + ads_html))
    sections += [
        ("Brand QA", _qa_html(pack["qa"])),
        ("Approval record", _record_table(pack["posts"] + pack["ads"])),
    ]
    body = "".join(
        f'<section><h2><span class="num">{i:02d}</span>{_e(title)}</h2>{content}</section>'
        for i, (title, content) in enumerate(sections, start=1)
    )
    title = f"{campaign['name']} — campaign pack"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}</title>
<style>{_CSS}</style>
<style>:root {{ --accent: {accent}; }}</style>
</head>
<body>
<div class="toolbar">
<button type="button" onclick="window.print()">Print / Save as PDF</button>
</div>
<div class="page">
<header class="cover">
<div class="agency">{logo}<span>{_e(agency["name"])}</span></div>
<p class="kicker">Campaign pack</p>
<h1>{_e(campaign["name"])}</h1>
<dl class="meta">{meta_html}</dl>
<div class="glance">{glance_html}</div>
</header>
{body}
<p class="disclosure"><strong>How this was made.</strong> {_e(pack["disclosure"])}</p>
</div>
</body>
</html>
"""
