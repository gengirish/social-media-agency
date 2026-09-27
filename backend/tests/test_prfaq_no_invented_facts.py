"""CF-13 — the PRFAQ stress-test must not invent people or places.

A run produced quotes attributed to "co-founder Ananya Rao" and "columnist Rohan
Mehta" — neither exists — and put the company in the wrong city. The prompt had
asked for a press release written "as if a real tech/industry outlet wrote about
it", which invites exactly that.

These tests assert the prompt's instructions, not the model's output: the model
is not run here, and what can be pinned is the brief it is given.
"""

from agency.agents.launch_pr import build_prfaq_prompt

BRAND = {
    "brand_name": "RemoteForge",
    "industry": "SaaS",
    "description": "Scheduling for freelance designers.",
    "setup": {"campaign_focus": {"description": "Autumn push"}},
}


class TestNoInventedFacts:
    def test_the_prompt_forbids_inventing_a_person(self):
        prompt = build_prfaq_prompt(BRAND)
        assert "NEVER invent a person" in prompt
        assert "[Spokesperson name, title]" in prompt

    def test_the_prompt_forbids_inventing_places_and_figures(self):
        prompt = build_prfaq_prompt(BRAND)
        assert "NEVER invent a location" in prompt
        assert "[Location]" in prompt
        # The wrong city was one half of the report; invented metrics are the
        # same failure and are named explicitly.
        assert "revenue figure" in prompt

    def test_quotes_are_placeholders(self):
        assert "Quotes are placeholders too" in build_prfaq_prompt(BRAND)

    def test_the_invitation_to_imagine_a_real_outlet_is_gone(self):
        # This sentence is what produced the invented journalist.
        assert "imagine a real tech/industry outlet" not in build_prfaq_prompt(BRAND)

    def test_facts_must_come_from_the_brand_context(self):
        assert "must come from the brand context above" in build_prfaq_prompt(BRAND)


class TestLaunchNote:
    def test_the_note_is_included_when_given(self):
        note = "A client-approval flow for freelance designers."
        prompt = build_prfaq_prompt(BRAND, note)
        assert "## What is being launched" in prompt
        assert note in prompt

    def test_no_section_is_added_when_the_note_is_blank(self):
        for blank in ("", "   ", "\n"):
            assert "## What is being launched" not in build_prfaq_prompt(BRAND, blank)

    def test_the_note_does_not_displace_the_fact_rules(self):
        prompt = build_prfaq_prompt(BRAND, "Something new.")
        assert "NEVER invent a person" in prompt
        # Order matters: the rules come after the note, so they are the last
        # word on what may be stated as fact.
        assert prompt.index("## What is being launched") < prompt.index("NEVER invent a person")


def test_the_campaign_focus_is_still_excluded():
    """Unchanged behaviour, guarded: the stress-test judges positioning alone."""
    assert "Autumn push" not in build_prfaq_prompt(BRAND)
