"""CF-03 — ad variants keep the structure their network renders.

The bug these cover: the pipeline stored ``json.dumps(ad["headlines"])`` in
``content_piece.body``, so a Google ad's body was the literal string
``["AI Gig Approvals in Days", ...]`` and a Meta or LinkedIn ad's body was ``[]``,
because the model returns those networks' copy under ``primary_text`` and gives
them no headlines at all.
"""

from agency.services.ad_variants import PLATFORM_LIMITS, normalize, platform_of, render_body


class TestGoogle:
    def test_headlines_and_descriptions_stay_separate_lists(self):
        ad = normalize(
            {
                "platform": "google",
                "variant": 2,
                "angle": "urgency",
                "headlines": ["AI Gig Approvals in Days", "Skip Rejected Applications"],
                "descriptions": ["Get approved fast.", "No more waiting."],
                "cta": "Get Started",
            }
        )

        assert ad["platform"] == "google"
        assert ad["fields"]["headlines"] == [
            "AI Gig Approvals in Days",
            "Skip Rejected Applications",
        ]
        assert ad["fields"]["descriptions"] == ["Get approved fast.", "No more waiting."]
        assert ad["is_empty"] is False
        assert ad["missing"] == []

    def test_body_is_labelled_text_never_a_json_list(self):
        ad = normalize(
            {"platform": "google", "headlines": ["One", "Two"], "descriptions": ["Desc"]}
        )
        body = render_body(ad)

        # The whole point of CF-03: no bracket-wrapped list reaches a user.
        assert "[" not in body
        assert "]" not in body
        assert "Headline: One" in body
        assert "Headline: Two" in body
        assert "Description: Desc" in body

    def test_extra_headlines_beyond_the_networks_limit_are_dropped(self):
        ad = normalize({"platform": "google", "headlines": ["a", "b", "c", "d", "e"]})
        assert ad["fields"]["headlines"] == ["a", "b", "c"]

    def test_primary_text_becomes_the_description_when_there_is_none(self):
        # Google has no long-text field, so primary_text is the model putting the
        # description somewhere else. Keeping it beats discarding the only copy.
        ad = normalize({"platform": "google", "headlines": ["H"], "primary_text": "Long copy"})
        assert ad["fields"]["descriptions"] == ["Long copy"]


class TestMeta:
    def test_primary_text_is_not_lost_when_the_model_sends_no_headlines(self):
        # This exact shape produced "[]" in the UI.
        ad = normalize({"platform": "meta", "primary_text": "Stop losing gigs.", "variant": 1})

        assert ad["fields"]["primary_text"] == "Stop losing gigs."
        assert ad["is_empty"] is False
        assert render_body(ad) == "Primary text: Stop losing gigs."

    def test_single_headline_and_description_are_taken_from_the_lists(self):
        ad = normalize(
            {
                "platform": "meta",
                "primary_text": "Body copy",
                "headlines": ["Headline A", "Headline B"],
                "descriptions": ["Desc A", "Desc B"],
            }
        )
        assert ad["fields"]["headline"] == "Headline A"
        assert ad["fields"]["description"] == "Desc A"

    def test_second_headline_fills_primary_text_when_absent(self):
        ad = normalize({"platform": "meta", "headlines": ["Headline A", "Longer body line"]})
        assert ad["fields"]["primary_text"] == "Longer body line"

    def test_limits_are_the_networks_own(self):
        ad = normalize({"platform": "meta", "primary_text": "x"})
        assert ad["limits"] == PLATFORM_LIMITS["meta"]
        assert ad["limits"]["headline"] == 40

    def test_over_limit_copy_is_reported_not_truncated(self):
        long_headline = "x" * 80
        ad = normalize({"platform": "meta", "primary_text": "b", "headlines": [long_headline]})
        # Truncating would silently alter the agent's output; the UI flags it.
        assert ad["fields"]["headline"] == long_headline


class TestLinkedIn:
    def test_primary_text_maps_to_intro_text(self):
        ad = normalize({"platform": "linkedin", "primary_text": "Intro copy", "headlines": ["H"]})
        assert ad["fields"]["intro_text"] == "Intro copy"
        assert ad["fields"]["headline"] == "H"
        assert "intro_text" not in ad["missing"]

    def test_explicit_intro_text_is_accepted_too(self):
        # The prompt asks for primary_text, but models volunteer the per-platform
        # key often enough that rejecting it would drop good copy.
        ad = normalize({"platform": "linkedin", "intro_text": "Given directly", "headline": "H"})
        assert ad["fields"]["intro_text"] == "Given directly"
        assert ad["fields"]["headline"] == "H"


class TestEmptyAndMalformed:
    def test_a_variant_with_nothing_usable_is_flagged_empty(self):
        ad = normalize({"platform": "meta", "headlines": [], "descriptions": []})
        assert ad["is_empty"] is True
        assert render_body(ad) == ""

    def test_missing_lists_required_fields_that_came_back_blank(self):
        ad = normalize({"platform": "meta", "descriptions": ["only a description"]})
        assert ad["is_empty"] is False
        assert set(ad["missing"]) == {"primary_text", "headline"}

    def test_non_dict_input_does_not_raise(self):
        ad = normalize("not a variant at all")
        assert ad["is_empty"] is True
        assert ad["platform"] == "google"

    def test_nulls_and_numbers_never_reach_the_output_as_text(self):
        ad = normalize({"platform": "google", "headlines": [None, 42, "", "Real"], "angle": None})
        # "None" and "" would both render as visible junk.
        assert ad["fields"]["headlines"] == ["42", "Real"]
        assert ad["angle"] == "general"

    def test_a_bare_string_headline_is_wrapped_not_dropped(self):
        ad = normalize({"platform": "google", "headlines": "Just one"})
        assert ad["fields"]["headlines"] == ["Just one"]

    def test_variant_falls_back_to_the_index_when_unusable(self):
        assert normalize({"platform": "google", "variant": "two"}, index=5)["variant"] == 5
        assert normalize({"platform": "google"}, index=3)["variant"] == 3


class TestPlatformOf:
    def test_network_aliases_map_to_their_platform(self):
        assert platform_of({"platform": "facebook"}) == "meta"
        assert platform_of({"platform": "Instagram"}) == "meta"
        assert platform_of({"platform": "google_ads"}) == "google"
        assert platform_of({"platform": "LinkedIn Ads"}) == "linkedin"

    def test_unknown_or_absent_platform_defaults_to_google(self):
        # Google is the only network the generic prompt shape maps onto unchanged,
        # so an unlabelled variant at least renders instead of vanishing.
        assert platform_of({}) == "google"
        assert platform_of({"platform": "threads"}) == "google"
        assert platform_of(None) == "google"
