"""CF-12 — a form's own label must not be accepted as a value.

VettD's "Product Launch" campaign was saved with the objective
"Campaign Objective *": browser autofill matches on label text and wrote the
label into the field it names. Nothing stopped it, and the value then reached the
strategy prompt as the campaign's actual goal.
"""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from agency.models.schemas import CampaignBrief, normalise_label, reject_field_label

BRIEF = {
    "client_id": "11111111-1111-1111-1111-111111111111",
    "campaign_name": "Product Launch",
    "objective": "Increase sign-ups among mid-market CTOs this quarter.",
    "start_date": date.today(),
    "end_date": date.today() + timedelta(days=30),
}


class TestNormaliseLabel:
    def test_case_punctuation_and_spacing_do_not_matter(self):
        # The reported value carried a trailing " *" from the required marker.
        assert normalise_label("Campaign Objective *") == "campaign objective"
        assert normalise_label("  CAMPAIGN   objective:  ") == "campaign objective"


class TestRejectFieldLabel:
    def test_a_real_value_passes_through_unchanged(self):
        value = "Increase sign-ups among mid-market CTOs."
        assert reject_field_label(value, "objective") == value

    @pytest.mark.parametrize(
        "value", ["Campaign Objective *", "campaign objective", "Target Audience", "Key Messages"]
    )
    def test_a_bare_label_is_refused(self, value):
        with pytest.raises(ValueError, match="label"):
            reject_field_label(value, "objective")

    def test_a_value_that_merely_mentions_the_label_is_kept(self):
        # The check is deliberately narrow: only a value that *is* a label.
        value = "Campaign objective: grow signups among CTOs"
        assert reject_field_label(value, "objective") == value


class TestCampaignBrief:
    def test_a_normal_brief_validates(self):
        assert CampaignBrief(**BRIEF).objective == BRIEF["objective"]

    def test_the_reported_objective_is_rejected(self):
        # Long enough to clear min_length=10, so only this check catches it.
        with pytest.raises(ValidationError, match="label"):
            CampaignBrief(**{**BRIEF, "objective": "Campaign Objective *"})

    def test_a_label_in_the_campaign_name_is_rejected(self):
        with pytest.raises(ValidationError, match="label"):
            CampaignBrief(**{**BRIEF, "campaign_name": "Campaign Name"})

    def test_a_label_in_the_target_audience_is_rejected(self):
        with pytest.raises(ValidationError, match="label"):
            CampaignBrief(**{**BRIEF, "target_audience": "Target Audience"})

    def test_an_empty_target_audience_is_still_allowed(self):
        # It is optional; the guard must not turn "" into a validation error.
        assert CampaignBrief(**{**BRIEF, "target_audience": ""}).target_audience == ""
