"""Demo seed: what the board looks like after `python -m worker.reset_demo`."""

import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from worker.reset_demo import SEED_PATH, build_rows

NOW = datetime(2026, 10, 26, 18, 0, tzinfo=timezone.utc)


def rows():
    return build_rows(json.loads(Path(SEED_PATH).read_text(encoding="utf-8")), NOW)


def test_thirty_demo_candidates_with_fake_numbers():
    cands, _ = rows()
    assert len(cands) == 30
    assert all(c["is_demo"] and c["source"] == "seed" for c in cands)
    assert all(re.fullmatch(r"\+346000000\d\d", c["phone"]) for c in cands)
    assert len({c["phone"] for c in cands}) == 30


def test_stage_spread():
    cands, _ = rows()
    assert Counter(c["stage"] for c in cands) == {"queue": 6, "revision": 5, "accepted": 10, "rejected": 9}


def test_screened_candidates_have_summary_answers_and_an_answered_call():
    cands, calls = rows()
    answered = {c["candidate_id"] for c in calls if c["answered"]}
    for c in cands:
        if c["stage"] != "queue":
            assert c["summary"], c["phone"]
            assert c["answers"], c["phone"]
            assert c["transcript"], c["phone"]
            assert c["id"] in answered, c["phone"]
            assert c["decided_by"]


def test_rejected_have_a_reason_and_revision_has_review_reasons():
    cands, _ = rows()
    for c in cands:
        if c["stage"] == "rejected":
            assert c["disqualify_reason"], c["phone"]
        if c["stage"] == "revision":
            assert c["review_reasons"], c["phone"]


def test_calls_fall_in_the_last_14_days_and_are_finished():
    _, calls = rows()
    assert calls
    for call in calls:
        t = datetime.fromisoformat(call["created_at"])
        assert NOW - timedelta(days=14) <= t <= NOW
        assert call["status"] in {"done", "no_answer"}
        assert call["candidate_id"]


def test_queue_has_retries_and_one_never_called():
    cands, calls = rows()
    queue = [c for c in cands if c["stage"] == "queue"]
    called = {c["candidate_id"] for c in calls}
    assert sum(1 for c in queue if c["retry_reason"] == "no_answer") >= 2
    assert any(c["id"] not in called for c in queue)


def test_stage_changed_after_created():
    cands, _ = rows()
    for c in cands:
        assert c["created_at"] <= c["stage_changed_at"] <= NOW.isoformat()


def test_start_date_is_an_iso_date_like_the_agent_writes():
    cands, _ = rows()
    dates = [c["answers"]["start_date"]["value"] for c in cands if "start_date" in c["answers"]]
    assert dates
    for d in dates:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)
        assert d >= NOW.date().isoformat()
