"""Pure helpers behind Amplify (services/repurpose.py)."""

from datetime import UTC, datetime

from agency.agents.amplify import build_prompt, format_brand_context
from agency.services.repurpose import (
    MAX_ATOMS,
    PLATFORM_CHAR_LIMITS,
    REPURPOSE_ANGLES,
    drip_schedule,
    is_angle_duplicate,
    jaccard,
    plan_atoms,
    rendered_length,
    validate_atoms,
)


def _atom(platform="linkedin", angle="hook", body="A real post body.", **kw):
    return {"platform": platform, "angle": angle, "title": "T", "body": body, **kw}


# --- taxonomy / limits --------------------------------------------------------


def test_angle_enum_is_closed_and_caps_atoms():
    assert REPURPOSE_ANGLES == (
        "hook",
        "how-to",
        "contrarian",
        "story",
        "data-point",
        "question",
        "behind-the-scenes",
        "listicle",
    )
    assert MAX_ATOMS == 8


def test_char_limits_reuse_content_agent_constant():
    from agency.agents.content_writer import PLATFORM_GUIDELINES

    assert PLATFORM_CHAR_LIMITS["twitter"] == 280
    expected = {k: v["max_length"] for k, v in PLATFORM_GUIDELINES.items()}
    assert expected == PLATFORM_CHAR_LIMITS


# --- is_angle_duplicate -------------------------------------------------------


def test_duplicate_flags_reworded_copy():
    recent = ["Our new onboarding flow cuts setup time from an hour to five minutes."]
    candidate = "The new onboarding flow cuts setup time from an hour to five minutes!"
    assert is_angle_duplicate(candidate, recent)


def test_duplicate_ignores_different_post():
    recent = ["Our new onboarding flow cuts setup time from an hour to five minutes."]
    candidate = "Ask me anything about pricing experiments we ran last quarter."
    assert not is_angle_duplicate(candidate, recent)


def test_duplicate_threshold_is_respected():
    a = "alpha beta gamma delta"
    b = "alpha beta gamma epsilon"  # 3 shared of 5 distinct -> 0.6
    assert jaccard(a, b) == 0.6
    assert is_angle_duplicate(a, [b], threshold=0.6)
    assert not is_angle_duplicate(a, [b], threshold=0.61)


def test_duplicate_empty_inputs_never_flag():
    assert not is_angle_duplicate("", ["anything"])
    assert not is_angle_duplicate("something", [])
    assert not is_angle_duplicate("the and of", ["the and of"])  # stopwords only


# --- drip_schedule ------------------------------------------------------------


def test_drip_crosses_month_boundary():
    start = datetime(2026, 1, 30, 15, 45, tzinfo=UTC)
    slots = drip_schedule(3, start, per_week=7)
    assert [s.date().isoformat() for s in slots] == ["2026-01-31", "2026-02-01", "2026-02-02"]
    assert all((s.hour, s.minute) == (9, 0) for s in slots)
    assert all(s.tzinfo is UTC for s in slots)


def test_drip_spacing_and_never_same_day():
    start = datetime(2026, 9, 21, 8, 0)
    slots = drip_schedule(4, start, per_week=3)  # round(7/3) = 2 days apart
    assert [s.day for s in slots] == [23, 25, 27, 29]
    assert slots[0].date() > start.date()


def test_drip_degenerate_cadence_and_count():
    start = datetime(2026, 9, 21)
    assert drip_schedule(0, start) == []
    slots = drip_schedule(3, start, per_week=0)  # floored, not collapsed
    assert len({s.date() for s in slots}) == 3


# --- plan_atoms ---------------------------------------------------------------


def test_plan_assigns_unique_angles_and_rotates_platforms():
    plan = plan_atoms(["twitter", "linkedin"], 8)
    assert [p["angle"] for p in plan] == list(REPURPOSE_ANGLES)
    assert [p["platform"] for p in plan[:4]] == ["twitter", "linkedin", "twitter", "linkedin"]


def test_plan_caps_and_prefers_unused_angles():
    assert len(plan_atoms(["twitter"], 99)) == MAX_ATOMS
    plan = plan_atoms(["twitter"], 3, used_angles=["hook", "how-to"])
    assert [p["angle"] for p in plan] == ["contrarian", "story", "data-point"]
    assert plan_atoms(["myspace"], 3) == []


# --- validate_atoms -----------------------------------------------------------


def test_validate_drops_bad_atoms_with_reasons():
    raw = [
        _atom(angle="hook"),
        _atom(angle="hook", body="second hook"),  # duplicate angle
        _atom(angle="rant"),  # not in the enum
        _atom(platform="tiktok"),  # platform not requested
        _atom(angle="story", body="   "),  # empty
        _atom(platform="twitter", angle="question", body="x" * 281),  # over limit
        "not a dict",
        _atom(angle="listicle", hashtags=["#growth", "growth", 3, ""]),
    ]
    out = validate_atoms(raw, ["linkedin", "twitter"])
    assert [a["angle"] for a in out.kept] == ["hook", "listicle"]
    assert out.kept[1]["hashtags"] == ["growth"]
    assert len(out.dropped) == 6


def test_validate_counts_hashtags_toward_limit():
    body = "y" * 270
    assert rendered_length(body, ["abcdefgh"]) == 270 + 2 + 9
    out = validate_atoms([_atom(platform="twitter", body=body, hashtags=["abcdefgh"])], ["twitter"])
    assert out.kept == []
    assert "over twitter limit" in out.dropped[0]


def test_validate_caps_at_max_atoms():
    raw = [_atom(angle=a) for a in REPURPOSE_ANGLES]
    assert len(validate_atoms(raw, ["linkedin"], max_atoms=3).kept) == 3
    assert len(validate_atoms(raw, ["linkedin"], max_atoms=50).kept) == MAX_ATOMS
    assert validate_atoms({"atoms": raw}, ["linkedin"]).kept == []  # not a list


# --- prompt -------------------------------------------------------------------


def test_prompt_carries_brand_voice_examples_and_campaign():
    brand = {
        "brand_name": "Sunrise Coffee",
        "voice_description": "warm, neighbourly",
        "vocabulary_include": ["single-origin"],
        "vocabulary_exclude": ["synergy"],
        "example_posts": [{"body": "Fresh roast Friday is back."}, "Plain string example"],
        "style_rules": ["No exclamation marks"],
        "emoji_policy": "none",
    }
    prompt = build_prompt(
        source_text="We roast every Friday.",
        requests=plan_atoms(["twitter"], 2),
        brand=brand,
        campaign_brief="Campaign: Autumn launch",
    )
    for needle in (
        "warm, neighbourly",
        "single-origin",
        "NEVER use these words: synergy",
        "Fresh roast Friday is back.",
        "Plain string example",
        "No exclamation marks",
        "Emoji policy: none",
        "Campaign: Autumn launch",
        "platform=twitter angle=hook",
        "platform=twitter angle=how-to",
        "hard limit 280",
    ):
        assert needle in prompt, needle
    assert "listicle:" not in prompt  # glossary only lists the angles requested


def test_brand_context_without_profile_is_explicit():
    assert "No brand profile" in format_brand_context({})
