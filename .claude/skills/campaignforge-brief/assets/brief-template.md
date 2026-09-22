# CampaignForge brief — {PRODUCT}

Sources: {HOMEPAGE_URL} · {PRICING_URL} · {API_SPEC_URL} 🔍 fetched {DD-Mon-YYYY} · campaign pack: `campaigns/{slug}/` (if any)

## Step 1: New Client (Setup › Clients)

| Field | Value |
|---|---|
| Website | `{HOMEPAGE_URL}` → click **Read website** |
| Brand Name * | `{BRAND}` |
| Industry * | `{INDUSTRY}` |
| Description | `{ONE_PARAGRAPH_VERIFIED_SUMMARY}` |
| Contact Email | `{CONTACT}` |

> Review the extracted brand profile before saving — remove anything that promises a not-live feature.

## Step 2: New Campaign (Create › Campaigns)

**Client \*** — `{BRAND}`

**Campaign Name \***
```
{BRAND} — {THEME} ({Mon YYYY})
```

**Campaign Objective \***
```
{PRIMARY_ACTION_AND_WHO}. Primary goal: {ACTIVATION_DEFINITION}. Secondary goal: {SALES_OR_UPGRADE_STEP}. {GOALS_IF_USER_SET_THEM}
```

**Target Audience**
```
Primary: {ICP_A + pain}. Secondary: {ICP_B, ICP_C}. Tertiary: {ICP_D}. {GEOGRAPHY}, {LANGUAGE}.
```

**Key Messages (one per line)**
```
{live benefit 1 — proof feature}
{live benefit 2}
{live benefit 3}
{live benefit 4}
{free-plan offer, exact limits}
{paid-plan feature — name the plan and price}
```

**Channels:** {ticked} — leave {unticked} off because {reason}.

| Field | Value |
|---|---|
| Start Date | `{YYYY-MM-DD}` |
| End Date | `{YYYY-MM-DD}` |
| Budget (USD) | `{USER_BUDGET}` |

**Additional Context**
```
Source of truth: {campaign pack path or "this brief"}.

PRICING ({CURRENCY}/{PERIOD}): {plan — price (limits, features)} · ... · {which plans are self-serve vs "talk to us"}.

ONLY PROMISE LIVE FEATURES: {live list}. Do NOT present {in-API/in-build/not-yet list} as available.

{PAID_FEATURE} is a {PLAN} feature — never imply it's free.

{PRODUCT-SPECIFIC WORDING BANS, e.g. say "X", never "Y"}.

NO invented numbers: no customer counts, testimonials, time-saved %, industry statistics or "trusted by". Only numbers above.

No competitor names in any copy or ads.

Voice: {voice}; {founder/brand attribution}. Grade 6–8 readability, max 2 emoji per post, one CTA per piece.

CTAs: primary "{CTA}" → {URL} ; secondary "{CTA2}" → {URL2} ; {audience} → {URL3}.
UTM: ?utm_source={sources}&utm_medium={mediums}&utm_campaign={campaign-id}&utm_content={piece-id}

PAID (${BUDGET}): {split, channels, targeting, key negatives, plan-naming rule for ads}.

{PENDING PLACEHOLDERS and claims that must wait until they have happened}.
```

## After launch
The run pauses at **Human Review**; drafts land in **Posts › Queue** as Pending; approving runs moderation. Check drafts against the campaign pack and reject anything that breaks the guardrails above.

## Unresolved questions
- {missing budget / unverified feature / site contradiction}
