# CampaignForge AI — Beta Testing Plan

> Version 1.0 | March 2026

---

## 1. Overview

CampaignForge is an AI-powered marketing platform with 7 specialized agents that collaborate to plan, create, review, and publish full campaigns from a single brief. This document outlines the beta testing program for validating core workflows, gathering user feedback, and preparing for public launch.

**Beta Duration:** 4 weeks (Weeks 1–4 post-invite)
**Beta Cohort Size:** 20–50 users
**Environments:**
- Frontend: `campaignforge-ai-three.vercel.app`
- Backend: `campaignforge-api.fly.dev`

---

## 2. Beta Goals

| # | Goal | Success Metric |
|---|------|---------------|
| 1 | Validate end-to-end campaign creation | 80%+ of users complete at least one campaign |
| 2 | Verify multi-platform publishing | Posts successfully delivered to X, LinkedIn, Facebook |
| 3 | Test agent pipeline reliability | < 5% pipeline failure rate |
| 4 | Collect UX feedback | NPS score 30+ |
| 5 | Validate billing flow | 50%+ trial → paid conversion on Starter plan |
| 6 | Identify critical bugs | Zero P0 bugs unresolved by end of beta |
| 7 | Measure time-to-value | < 5 minutes from brief to published campaign |

---

## 3. Beta User Personas

| Persona | Description | Why Included |
|---------|------------|-------------|
| **Freelance Marketer** | Solo operator managing 3–5 SMB clients | Primary ICP — tests multi-client workflows |
| **Startup Founder** | Non-marketer doing their own marketing | Tests simplicity, time-to-value |
| **Agency Team** | 3–5 person marketing team | Tests collaboration, white-label, template sharing |
| **Content Creator** | Blogger/influencer producing regular content | Tests content quality, scheduling, multi-platform |
| **Developer/Technical** | API-first user, headless integration | Tests REST API, webhooks, Slack bot |

---

## 4. Recruitment Channels

| Channel | Target | Approach |
|---------|--------|----------|
| X/Twitter | 10 users | "Building CampaignForge in public" — invite followers |
| LinkedIn | 5 users | Direct outreach to marketing freelancers |
| Product Hunt Upcoming | 5 users | Collect waitlist signups |
| Reddit (r/startups, r/marketing) | 5 users | Share founder story, invite testers |
| Personal network | 5 users | Direct invite to marketing professionals |

---

## 5. Test Scenarios

### 5.1 Campaign Creation (Core Flow)

| Test ID | Scenario | Steps | Expected Result |
|---------|----------|-------|----------------|
| TC-01 | Create first campaign | Sign up → Type brief → Watch agents → Review → Approve | Campaign created with strategy, content, and ads |
| TC-02 | Campaign with brand voice | Set brand profile → Create campaign → Verify tone | Content matches brand guidelines |
| TC-03 | Multi-platform campaign | Create campaign → Select X + LinkedIn + Facebook | Content adapted per platform |
| TC-04 | Template-based campaign | Browse templates → Fork → Customize → Launch | Campaign created from template |
| TC-05 | A/B variant generation | Create campaign → Request variants → Compare | 2+ content variants generated |

### 5.2 Agent Pipeline

| Test ID | Scenario | Steps | Expected Result |
|---------|----------|-------|----------------|
| TC-06 | Real-time SSE streaming | Start campaign → Watch dashboard | Agent progress updates in real time |
| TC-07 | Human review gate | Campaign reaches review → Edit → Approve | Changes reflected in final output |
| TC-08 | QA agent scoring | Create campaign → Check QA score | Score 7+ with specific feedback |
| TC-09 | Pipeline failure recovery | Interrupt mid-pipeline → Retry | Campaign resumes or restarts cleanly |
| TC-10 | Autonomous operator | Set weekly goal → Let agent plan → Review output | Agent generates weekly content plan |

### 5.3 Publishing & Scheduling

| Test ID | Scenario | Steps | Expected Result |
|---------|----------|-------|----------------|
| TC-11 | Publish to X | Create post → Publish to Twitter/X | Post appears on X feed |
| TC-12 | Publish to LinkedIn | Create post → Publish to LinkedIn | Post appears on LinkedIn feed |
| TC-13 | Schedule future post | Create post → Set date/time → Schedule | Post queued, published at scheduled time |
| TC-14 | Calendar drag-and-drop | Open calendar → Drag post → Drop to new date | Post rescheduled |
| TC-15 | Bulk scheduling | Create campaign → Auto-schedule all posts | All posts distributed across calendar |

### 5.4 Billing & Account

| Test ID | Scenario | Steps | Expected Result |
|---------|----------|-------|----------------|
| TC-16 | Free tier limits | Create 2 clients → Attempt 3rd | Upgrade prompt shown |
| TC-17 | Stripe checkout | Click upgrade → Complete Stripe checkout | Plan upgraded, features unlocked |
| TC-18 | Campaign quota enforcement | Exceed monthly limit → Attempt new campaign | Upgrade prompt with usage stats |
| TC-19 | Team invite | Settings → Invite team member → Accept invite | New member has access |
| TC-20 | White-label setup | Settings → Configure branding → View portal | Client portal shows custom branding |

### 5.5 Integrations

| Test ID | Scenario | Steps | Expected Result |
|---------|----------|-------|----------------|
| TC-21 | Slack bot | `/campaignforge create [brief]` in Slack | Campaign created, link returned |
| TC-22 | REST API | `POST /api/v1/campaigns` with API key | Campaign created via API |
| TC-23 | Webhook delivery | Register webhook → Create campaign → Check delivery | Webhook POST received |
| TC-24 | OAuth platform connect | Settings → Connect X → Authorize | Platform connected, token stored |
| TC-25 | Competitive intel | Enter competitor URL → Run analysis | Competitor report generated |

---

## 6. Bug Reporting

### Severity Levels

| Level | Definition | Response Time | Resolution Target |
|-------|-----------|---------------|-------------------|
| **P0 — Critical** | App crashes, data loss, security issue | < 2 hours | < 24 hours |
| **P1 — Major** | Core feature broken, no workaround | < 4 hours | < 48 hours |
| **P2 — Moderate** | Feature degraded but usable | < 24 hours | < 1 week |
| **P3 — Minor** | Cosmetic, typos, minor UX issues | < 48 hours | Next release |

### Bug Report Template

```
**Title:** [Short description]
**Severity:** P0 / P1 / P2 / P3
**Steps to Reproduce:**
1. ...
2. ...
3. ...
**Expected Result:** [What should happen]
**Actual Result:** [What happened]
**Browser/Device:** [e.g., Chrome 120, Windows 11]
**Screenshot/Video:** [Attach if possible]
```

### Reporting Channels

| Channel | Use For |
|---------|---------|
| GitHub Issues | Bug reports with full detail |
| Slack #beta-feedback | Quick questions, UX feedback |
| Email (beta@campaignforge.ai) | Sensitive issues, account problems |
| In-app feedback widget | Quick reactions while using the product |

---

## 7. Feedback Collection

### Weekly Surveys (Google Form / Typeform)

**Week 1 — Onboarding**
- How easy was signup? (1–5)
- Did you complete your first campaign? (Y/N)
- What confused you?
- Time from signup to first campaign?

**Week 2 — Core Usage**
- How many campaigns did you create?
- Which features did you use most?
- What's missing?
- Would you recommend to a colleague? (1–10)

**Week 3 — Advanced Features**
- Did you try multi-platform publishing?
- Did you use templates?
- Did you try the Slack bot or API?
- Any feature you tried but abandoned? Why?

**Week 4 — Final Assessment**
- NPS: How likely to recommend? (0–10)
- Would you pay $49/month for this? (Y/N)
- Top 3 things to improve?
- Would you switch from your current tool? (Y/N + what tool)

### In-App Analytics (Tracked Automatically)

| Metric | What It Tells Us |
|--------|-----------------|
| Time-to-first-campaign | Onboarding friction |
| Campaign completion rate | Pipeline reliability |
| Agent step drop-offs | Where users lose confidence |
| Feature adoption | Which features resonate |
| Session duration | Engagement depth |
| Return rate (D1, D7, D14) | Retention signal |
| Error rate by endpoint | Backend reliability |

---

## 8. Testing Schedule

| Week | Focus | Key Activities |
|------|-------|---------------|
| **Week 0** | Pre-beta prep | Seed demo data, test all flows internally, set up monitoring |
| **Week 1** | Onboarding + core flow | Invite Cohort 1 (10 users). Focus: signup → first campaign |
| **Week 2** | Publishing + scheduling | Invite Cohort 2 (10 users). Focus: multi-platform publishing |
| **Week 3** | Integrations + billing | Enable Stripe live mode. Focus: upgrades, Slack, API |
| **Week 4** | Stress test + final feedback | Full cohort active. Focus: scale, reliability, final NPS |

---

## 9. Success Criteria (Exit Beta)

| Criterion | Threshold | Measurement |
|-----------|-----------|-------------|
| Campaign completion rate | > 80% | Campaigns created / campaigns started |
| Pipeline failure rate | < 5% | Failed agent runs / total runs |
| NPS score | > 30 | Week 4 survey |
| P0 bugs outstanding | 0 | GitHub Issues |
| P1 bugs outstanding | < 3 | GitHub Issues |
| Time-to-value | < 5 minutes | In-app analytics |
| Trial → Paid conversion | > 50% | Stripe dashboard |
| User retention (14-day) | > 40% | Return rate |

### Exit Decision Matrix

| All criteria met | → **Launch publicly** |
|-----------------|----------------------|
| NPS < 30 but rest passes | → Extend beta 2 weeks, address UX feedback |
| Pipeline failure > 5% | → Fix reliability, re-test with existing cohort |
| Conversion < 50% | → Adjust pricing/packaging, A/B test landing page |

---

## 10. Risk Management

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Low beta signup rate | Medium | High | Over-recruit by 2x; offer free Starter plan for beta testers |
| LLM API outage | Low | High | Fallback to alternative model (Claude → GPT-4o); queue campaigns |
| Social API rate limits | Medium | Medium | Queue-based publishing with per-platform rate limiting |
| Negative feedback overwhelm | Medium | Medium | Triage by severity; focus on P0/P1 first |
| Beta users churn before Week 4 | Medium | Medium | Weekly check-in emails; offer 1-on-1 onboarding calls |
| Data privacy concerns | Low | High | Clear TOS, GDPR-compliant, no data sharing |

---

## 11. Post-Beta Actions

| Action | Timeline | Owner |
|--------|----------|-------|
| Analyze all feedback, prioritize fixes | Beta Week 4 + 1 day | Product |
| Fix all P0 and P1 bugs | Within 1 week post-beta | Engineering |
| Update documentation | Within 1 week post-beta | Product |
| Prepare Product Hunt launch | Beta Week 4 | Marketing |
| Plan pricing adjustments if needed | Post-beta analysis | Founder |
| Send thank-you + lifetime discount to beta testers | Day 1 post-beta | Growth |

---

## 12. Contact

| Role | Name | Channel |
|------|------|---------|
| Founder & Lead | — | Direct Slack DM |
| Beta Coordinator | — | beta@campaignforge.ai |
| Bug Triage | — | GitHub Issues |

---

*CampaignForge AI — Beta Testing Plan v1.0*
