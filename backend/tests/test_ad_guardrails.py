"""Pure ad guardrails — ported from the Cadence prototype's tests/logic.test.js
(validateAdAssets, findTrademarkRisks, findPersonalAttributeRisks, adCopyText,
META_CTA_OPTIONS), plus the extras this port adds (sitelink description lines,
competitor-name collection)."""

import re

import pytest

from agency.agents.ads import (
    CREATIVE_BRIEF_DISCLOSURE,
    MalformedAdSetError,
    normalize_google,
    normalize_meta,
)
from agency.services.ad_guardrails import (
    AD_LIMITS,
    META_CTA_OPTIONS,
    ad_copy_text,
    collect_competitor_names,
    find_personal_attribute_risks,
    find_trademark_risks,
    validate_ad_assets,
)


def _any(problems: list[str], *patterns: str) -> bool:
    return any(all(re.search(p, x) for p in patterns) for x in problems)


# --- validate_ad_assets — Google ------------------------------------------------

GOOGLE_OK = {
    "headlines": ["Ship Faster Every Week"] * 15,
    "descriptions": ["Plan, build and launch without the busywork that slows small teams down."]
    * 4,
}


def test_google_compliant_set_passes():
    assert validate_ad_assets("google", GOOGLE_OK) == []


def test_google_headline_over_hard_limit_is_rejected():
    bad = {
        **GOOGLE_OK,
        "headlines": ["Ship Faster"] * 14 + ["This Headline Is Far Too Long To Ever Run"],
    }
    assert _any(validate_ad_assets("google", bad), r"Headline 15", r"rejected")


def test_google_requires_at_least_three_headlines():
    assert _any(
        validate_ad_assets("google", {**GOOGLE_OK, "headlines": ["Only One"]}), r"at least 3"
    )


def test_google_too_many_descriptions():
    problems = validate_ad_assets(
        "google", {**GOOGLE_OK, "descriptions": ["Short description."] * 6}
    )
    assert _any(problems, r"maximum is 4")


def test_google_counts_spaces_toward_limit():
    exactly31 = "a" * 29 + " b"
    problems = validate_ad_assets(
        "google", {**GOOGLE_OK, "headlines": ["Ship Faster"] * 14 + [exactly31]}
    )
    assert _any(problems, r"31 chars")


def test_google_sitelink_description_lines_checked():
    assets = {**GOOGLE_OK, "sitelinks": [{"text": "Pricing", "desc1": "x" * 36, "desc2": "ok"}]}
    assert _any(validate_ad_assets("google", assets), r"Sitelink 1 description line 1", r"rejected")


# --- validate_ad_assets — Meta --------------------------------------------------


def test_meta_headline_past_27_warns_without_calling_it_invalid():
    problems = validate_ad_assets(
        "meta",
        {
            "primary_texts": ["Support tickets pile up fast at small companies."],
            "headlines": ["A headline of thirty-five chars ok"],
        },
    )
    assert _any(problems, r"Facebook Feed shows only")
    assert not _any(problems, r"truncated")


def test_meta_primary_text_past_visible_threshold_is_truncated_not_rejected():
    problems = validate_ad_assets("meta", {"primary_texts": ["x" * 200], "headlines": ["Short"]})
    assert _any(problems, r"truncated")
    assert not _any(problems, r"rejected")


def test_meta_copy_at_visible_thresholds_passes():
    assert (
        validate_ad_assets(
            "meta",
            {"primary_texts": ["Support tickets pile up fast."], "headlines": ["Ship faster"]},
        )
        == []
    )


def test_meta_uses_visible_thresholds_far_below_hard_caps():
    assert AD_LIMITS["meta"]["primary_texts"]["max"] == 125
    assert AD_LIMITS["meta"]["headlines"]["preferred"] < AD_LIMITS["meta"]["headlines"]["max"]


def test_unknown_network_or_missing_assets_returns_empty():
    assert validate_ad_assets("tiktok", {"headlines": ["x"]}) == []
    assert validate_ad_assets("google", None) == []


# --- META_CTA_OPTIONS -----------------------------------------------------------


def test_meta_accepts_every_real_preset_cta():
    assert len(META_CTA_OPTIONS) == 7
    for cta in META_CTA_OPTIONS:
        assert validate_ad_assets("meta", {"headlines": ["Short"], "cta": cta}) == []


def test_meta_flags_freeform_cta():
    problems = validate_ad_assets("meta", {"headlines": ["Short"], "cta": "Get Yours Now"})
    assert _any(problems, r'CTA "Get Yours Now"', r"preset")


def test_meta_missing_cta_is_not_a_format_violation():
    assert validate_ad_assets("meta", {"headlines": ["Short"]}) == []


def test_google_never_checks_cta():
    assets = {
        "headlines": ["Ship Faster"] * 3,
        "descriptions": ["Plan and launch fast."] * 2,
        "cta": "Anything Goes",
    }
    assert validate_ad_assets("google", assets) == []


# --- find_trademark_risks -------------------------------------------------------

RIVALS = ["Buffer", "Later", "Hootsuite"]


def test_trademark_catches_leaked_competitor():
    assert find_trademark_risks("A faster Buffer alternative for founders", RIVALS) == ["buffer"]


def test_trademark_is_case_insensitive():
    assert find_trademark_risks("cheaper than HOOTSUITE", RIVALS) == ["hootsuite"]


def test_trademark_word_boundary():
    assert find_trademark_risks("Schedule it now, publish it later on.", RIVALS) == ["later"]
    assert find_trademark_risks("Ship sooner, not laterally", RIVALS) == []


def test_trademark_reports_each_name_once():
    assert find_trademark_risks("Buffer is fine but Buffer costs more", RIVALS) == ["buffer"]


def test_trademark_clean_copy_or_no_rivals():
    assert find_trademark_risks("The simplest way to plan your week", RIVALS) == []
    assert find_trademark_risks("Anything at all", []) == []
    assert find_trademark_risks("", RIVALS) == []


def test_trademark_escapes_regex_characters():
    assert find_trademark_risks("Better than Acme.io today", ["Acme.io"]) == ["acme.io"]
    assert find_trademark_risks("Better than AcmeXio today", ["Acme.io"]) == []


# --- find_personal_attribute_risks ---------------------------------------------


def test_personal_attribute_flags_second_person_trait():
    risks = find_personal_attribute_risks("Are you a broke founder drowning in support tickets?")
    assert len(risks) == 1
    assert risks[0]["term"] == "broke"


def test_personal_attribute_flags_health_condition():
    assert find_personal_attribute_risks("Struggling with your ADHD at work?")


def test_personal_attribute_ignores_plain_second_person():
    assert find_personal_attribute_risks("Your team ships faster with less busywork.") == []


def test_personal_attribute_ignores_trait_without_you():
    assert find_personal_attribute_risks("Support tickets pile up fast at small companies.") == []
    assert find_personal_attribute_risks("Built for teams with tight budgets.") == []


def test_personal_attribute_is_sentence_scoped():
    text = "Your team ships faster. Debt collection is a hard business."
    assert find_personal_attribute_risks(text) == []


def test_personal_attribute_empty_input():
    assert find_personal_attribute_risks("") == []
    assert find_personal_attribute_risks(None) == []


# --- ad_copy_text ---------------------------------------------------------------


def test_ad_copy_text_google_excludes_keyword_themes():
    assets = {
        "headlines": ["Ship Faster"],
        "descriptions": ["Plan and launch without the busywork."],
        "callouts": ["24/7 support"],
        "sitelinks": [{"text": "Pricing", "desc1": "See plans", "desc2": "No card needed"}],
        "keyword_themes": [
            {"intent": "competitor", "keywords": ["Buffer", "Later"], "note": "bid"}
        ],
    }
    text = ad_copy_text("google", assets)
    assert "Ship Faster" in text and "Pricing" in text
    assert "Buffer" not in text and "Later" not in text


def test_ad_copy_text_meta():
    text = ad_copy_text(
        "meta",
        {
            "primary_texts": ["Support tickets pile up fast."],
            "headlines": ["Ship faster"],
            "descriptions": ["Try it free"],
        },
    )
    for part in ("Support tickets pile up fast.", "Ship faster", "Try it free"):
        assert part in text


def test_ad_copy_text_missing_input():
    assert ad_copy_text("google", {}) == ""
    assert ad_copy_text("google", None) == ""
    assert ad_copy_text("meta", None) == ""


def test_ad_copy_text_tolerates_malformed_sitelink():
    assert ad_copy_text("google", {"sitelinks": [{"text": "Pricing"}, "junk"]}) == "Pricing"


# --- collect_competitor_names ---------------------------------------------------


def test_collect_competitor_names_both_key_styles_deduped():
    payloads = [
        {"competitor_name": "Buffer"},
        {"competitorName": "buffer"},
        {"competitor_names": ["Later", "Hootsuite"]},
        {"competitorNames": ["Sprout"]},
        {"competitors": [{"name": "Loomly"}, "  "]},
        None,
        "junk",
    ]
    assert collect_competitor_names(payloads) == [
        "Buffer",
        "Later",
        "Hootsuite",
        "Sprout",
        "Loomly",
    ]


# --- agent output normalisation -------------------------------------------------


def test_normalize_google_requires_headlines_and_descriptions():
    with pytest.raises(MalformedAdSetError):
        normalize_google({"headlines": ["Only"], "descriptions": []})
    with pytest.raises(MalformedAdSetError):
        normalize_google(["not", "an", "object"])


def test_normalize_google_never_truncates_and_accepts_camel_case():
    long = "x" * 45
    out = normalize_google(
        {"headlines": [long, 3, ""], "descriptions": ["d"], "keywordThemes": [{"keywords": ["a"]}]}
    )
    assert out["headlines"] == [long]
    assert out["keyword_themes"] == [{"intent": "General", "keywords": ["a"], "note": ""}]


def test_normalize_meta_appends_creative_disclosure_and_keeps_cta_verbatim():
    out = normalize_meta(
        {
            "primary_texts": ["p"],
            "headlines": ["h"],
            "cta": "Buy Now!!",
            "creative_direction": "A founder at a desk.",
        }
    )
    assert out["cta"] == "Buy Now!!"
    assert out["creative_direction"].endswith(CREATIVE_BRIEF_DISCLOSURE)
    with pytest.raises(MalformedAdSetError):
        normalize_meta({"primary_texts": [], "headlines": ["h"]})
