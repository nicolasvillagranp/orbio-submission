"""Jev response parsing, with fake responses so tests never call the API."""

from types import SimpleNamespace as NS

import pytest

from src.classifier import build_questions, certainty, parse

BASE_NOULS = {"asks_question": 0.02, "wants_human": 0.01, "delete_data": 0.0, "abusive": 0.0, "manipulation": 0.01,
              "wants_to_leave": 0.0}


def fake_response(choices=None, nouls=None):
    """Shape of a typesafe_sdk SystemOneResponse: .choices / .nouls / .scores dicts."""
    choices = {"language": ("es", 1.0), **(choices or {})}
    return NS(
        choices={k: NS(choice=c, confidence=conf) for k, (c, conf) in choices.items()},
        nouls={k: NS(noul=p) for k, p in {**BASE_NOULS, **(nouls or {})}.items()},
        scores={"frustration": NS(score=0.1)},
    )


@pytest.mark.parametrize("p,expected", [(0.97, 0.94), (0.03, 0.94), (0.5, 0.0), (1.0, 1.0)])
def test_certainty(p, expected):
    assert certainty(p) == pytest.approx(expected)


def test_only_open_fields_are_asked():
    q = build_questions({"has_license"}, {}, recap_pending=False)
    assert "has_license" in q and "consent" not in q and "availability_mentioned" not in q
    assert {"language", "wants_human", "manipulation", "frustration"} <= q.keys()


def test_confirmation_and_recap_questions_are_added():
    q = build_questions(set(), {"has_license": "the candidate has no driver's license"}, recap_pending=True)
    assert "confirms__has_license" in q and "confirms_recap" in q


def test_not_stated_choice_is_left_out():
    resp = fake_response(choices={"has_license": ("not_stated", 1.0)})
    assert parse(resp, {"has_license"}, {}, False)["fields"] == {}


def test_choice_answer_keeps_jev_confidence():
    resp = fake_response(choices={"has_license": ("yes", 0.83)})
    c = parse(resp, {"has_license"}, {}, False)["fields"]["has_license"]
    assert (c.value, c.confidence) == ("yes", 0.83)


def test_multi_select_confidence_is_least_certain_picked_option():
    nouls = {
        "availability_mentioned": 0.98,
        "availability__full_time": 0.02,
        "availability__part_time": 0.80,  # picked, certainty 0.6
        "availability__weekends": 0.97,   # picked, certainty 0.94
    }
    c = parse(fake_response(nouls=nouls), {"availability"}, {}, False)["fields"]["availability"]
    assert c.value == ["part_time", "weekends"]
    assert c.confidence == pytest.approx(0.6)


def test_unpicked_options_dont_lower_confidence():
    # "por las tardes": afternoon 0.97, evening 0.12 (a clear-enough no)
    nouls = {"schedule_mentioned": 0.98, "schedule__morning": 0.02, "schedule__afternoon": 0.97,
             "schedule__evening": 0.12, "schedule__flexible": 0.02}
    c = parse(fake_response(nouls=nouls), {"schedule"}, {}, False)["fields"]["schedule"]
    assert c.value == ["afternoon"] and c.confidence == pytest.approx(0.94)


def test_borderline_option_is_ignored_when_there_is_a_clear_pick():
    # "solo findes": weekends clear, part-time 50/50
    nouls = {"availability_mentioned": 0.98, "availability__full_time": 0.02,
             "availability__part_time": 0.52, "availability__weekends": 0.95}
    c = parse(fake_response(nouls=nouls), {"availability"}, {}, False)["fields"]["availability"]
    assert c.value == ["weekends"] and c.confidence == pytest.approx(0.9)


def test_only_borderline_options_give_low_confidence():
    nouls = {"availability_mentioned": 0.9, "availability__full_time": 0.1,
             "availability__part_time": 0.55, "availability__weekends": 0.2}
    c = parse(fake_response(nouls=nouls), {"availability"}, {}, False)["fields"]["availability"]
    assert c.value == ["part_time"] and c.confidence < 0.6


def test_flexible_replaces_other_shifts():
    nouls = {"schedule_mentioned": 0.71, "schedule__morning": 0.63, "schedule__afternoon": 0.67,
             "schedule__evening": 0.51, "schedule__flexible": 0.93}
    c = parse(fake_response(nouls=nouls), {"schedule"}, {}, False)["fields"]["schedule"]
    assert c.value == ["flexible"]


def test_multi_select_not_mentioned_is_left_out():
    nouls = {"schedule_mentioned": 0.1, **{f"schedule__{o}": 0.0 for o in ("morning", "afternoon", "evening", "flexible")}}
    assert parse(fake_response(nouls=nouls), {"schedule"}, {}, False)["fields"] == {}


def test_confirms_and_signals_are_returned():
    resp = fake_response(choices={"language": ("en", 1.0)}, nouls={
        "confirms__has_license": 0.91, "rejects__has_license": 0.03,
        "confirms_recap": 0.88, "rejects_recap": 0.05, "wants_human": 0.95})
    out = parse(resp, set(), {"has_license": "x"}, True)
    assert out["confirms"] == {"has_license": 0.91, "recap": 0.88}
    assert out["rejects"] == {"has_license": 0.03, "recap": 0.05}
    assert out["signals"]["language"] == "en" and out["signals"]["wants_human"] == 0.95
