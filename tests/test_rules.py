from datetime import date

import pytest

from src import rules
from src.models import Conversation, Decision, Stage, Status
from src.rules import Classification as C

TODAY = date(2026, 10, 18)


def area(status: str) -> dict:
    """A geocoding.check_area() result with the given status."""
    return {"status": status, "query": "x", "place": "x", "restaurant": "Sol, Madrid", "distance_km": 3.0, "options": []}


def conv_at(stage: Stage) -> Conversation:
    """A conversation with every field before `stage` already accepted."""
    conv = Conversation()
    answers = {
        "consent": C("yes", 1.0),
        "full_name": C("Ana López", 1.0),
        "has_license": C("yes", 1.0),
        "location": C(area("in_area"), 1.0),
        "availability": C(["part_time"], 1.0),
        "schedule": C(["evening"], 1.0),
        "experience_years": C(2, 1.0),
        "start_date": C("2026-10-20", 1.0),
    }
    for s, field in rules.STAGE_FIELDS.items():
        if s == stage:
            break
        rules.apply(conv, field, answers[field], today=TODAY)
    assert conv.stage == stage
    return conv


def test_happy_path_reaches_confirmation_then_qualified():
    conv = conv_at(Stage.CONFIRMATION)
    assert rules.missing_fields(conv) == []
    assert rules.finish(conv) is Status.QUALIFIED


def test_no_license_with_high_confidence_disqualifies():
    conv = conv_at(Stage.LICENSE)
    out = rules.apply(conv, "has_license", C("no", 0.97))
    assert out.decision is Decision.DISQUALIFY
    assert conv.status is Status.DISQUALIFIED and conv.disqualify_reason == "no_license"
    assert conv.stage is Stage.DONE


def test_license_in_progress_disqualifies():
    conv = conv_at(Stage.LICENSE)
    out = rules.apply(conv, "has_license", C("in_progress", 1.0))
    assert out.decision is Decision.DISQUALIFY
    assert conv.disqualify_reason == "license_in_progress"


def test_expired_license_is_accepted_with_a_note():
    conv = conv_at(Stage.LICENSE)
    out = rules.apply(conv, "has_license", C("expired", 1.0))
    assert out.decision is Decision.ACCEPT
    assert conv.data.has_license.note == "license_needs_renewal"
    assert conv.review_reasons == [] and conv.stage is Stage.LOCATION


def test_uncertain_no_license_is_confirmed_never_disqualified():
    conv = conv_at(Stage.LICENSE)
    out = rules.apply(conv, "has_license", C("no", 0.7))
    assert out.decision is Decision.CONFIRM
    assert conv.status is Status.IN_PROGRESS
    rules.confirm_pending(conv, "has_license")
    assert conv.status is Status.DISQUALIFIED


@pytest.mark.parametrize("field,value,stage", [
    ("schedule", ["afternoon"], Stage.SCHEDULE),
    ("has_license", "expired", Stage.LICENSE),
    ("availability", ["weekends"], Stage.AVAILABILITY),
])
def test_fairly_sure_answers_are_kept_without_asking(field, value, stage):
    conv = conv_at(stage)
    out = rules.apply(conv, field, C(value, 0.75))
    assert out.decision is Decision.ACCEPT  # no "¿confirmas...?": the final summary verifies it
    assert conv.stage is not stage


def test_clear_knockout_acts_immediately():
    conv = conv_at(Stage.LICENSE)
    assert rules.apply(conv, "has_license", C("no", 0.95)).decision is Decision.DISQUALIFY


def test_low_confidence_reasks_then_flags_for_review():
    conv = conv_at(Stage.AVAILABILITY)
    assert rules.apply(conv, "availability", C(["weekends"], 0.4)).decision is Decision.REASK
    out = rules.apply(conv, "availability", C(["weekends"], 0.5))
    assert out.decision is Decision.FLAG
    assert conv.data.availability.flagged and conv.data.availability.value == ["weekends"]
    assert conv.stage is Stage.SCHEDULE  # conversation carries on


def test_flagged_field_ends_in_needs_review():
    conv = conv_at(Stage.START_DATE)
    out = rules.apply(conv, "start_date", C("2027-03-01", 1.0), today=TODAY)
    assert out.decision is Decision.FLAG and out.reason == "start_date_far"
    assert rules.finish(conv) is Status.NEEDS_REVIEW


@pytest.mark.parametrize("status,decision", [
    ("in_area", Decision.ACCEPT),
    ("review", Decision.FLAG),
    ("out_of_area", Decision.DISQUALIFY),
    ("ambiguous", Decision.REASK),
    ("not_found", Decision.REASK),
    ("unavailable", Decision.FLAG),
])
def test_location_status_maps_to_decision(status, decision):
    conv = conv_at(Stage.LOCATION)
    assert rules.apply(conv, "location", C(area(status), 1.0)).decision is decision


def test_out_of_area_disqualifies():
    conv = conv_at(Stage.LOCATION)
    rules.apply(conv, "location", C(area("out_of_area"), 1.0))
    assert conv.status is Status.DISQUALIFIED and conv.disqualify_reason == "out_of_area"


def test_geocoder_outage_never_disqualifies():
    conv = conv_at(Stage.LOCATION)
    rules.apply(conv, "location", C(area("unavailable"), 1.0))
    assert conv.status is Status.IN_PROGRESS
    assert "geocoder_unavailable" in conv.review_reasons


def test_declined_consent_marks_declined():
    conv = Conversation()
    rules.apply(conv, "consent", C("no", 0.99))
    assert conv.status is Status.DECLINED


def test_single_word_name_asks_for_surname_once():
    conv = conv_at(Stage.NAME)
    assert rules.apply(conv, "full_name", C("Ana", 1.0)).reason == "ask_surname"
    assert rules.apply(conv, "full_name", C("Ana", 1.0)).decision is Decision.ACCEPT


@pytest.mark.parametrize("value,reason", [("2026-10-01", "date_in_past"), ("next week", "date_unparseable")])
def test_bad_start_dates_reask(value, reason):
    conv = conv_at(Stage.START_DATE)
    out = rules.apply(conv, "start_date", C(value, 1.0), today=TODAY)
    assert (out.decision, out.reason) == (Decision.REASK, reason)


def test_years_out_of_range_reasks():
    conv = conv_at(Stage.EXPERIENCE)
    assert rules.apply(conv, "experience_years", C(70, 1.0)).decision is Decision.REASK


def test_answers_out_of_order_are_kept():
    conv = conv_at(Stage.NAME)
    rules.apply(conv, "location", C(area("in_area"), 1.0))  # volunteered early
    rules.apply(conv, "full_name", C("Luis Pérez", 1.0))
    assert conv.stage is Stage.LICENSE
    rules.apply(conv, "has_license", C("yes", 1.0))
    assert conv.stage is Stage.AVAILABILITY  # location already answered
