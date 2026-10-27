"""Call worker: mapping a screening onto the board and handling one call request."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.models import Conversation, FieldValue, Message, ScreeningData, Status
from worker.mapping import allowed, candidate_patch, parse_allowlist, stage_for
from worker.process import process_call

MY_PHONE = "+34600111222"
T0 = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


class CallError(Exception):
    """Stand-in for telephony.calls.CallError: the worker only reads `sip_status`."""

    def __init__(self, message, sip_status=None):
        super().__init__(message)
        self.sip_status = sip_status


class FakeDb:
    def __init__(self):
        self.updates: list[tuple[str, dict, dict]] = []

    def update(self, table, match, patch):
        self.updates.append((table, match, patch))
        return [patch]

    def patches(self, table):
        merged: dict = {}
        for t, _, patch in self.updates:
            if t == table:
                merged.update(patch)
        return merged


def conv(status=Status.QUALIFIED, summary="Apto.", created=T0, **data):
    fields = {"full_name": FieldValue(value="Ana López"), "has_license": FieldValue(value="yes")}
    fields.update(data)
    return Conversation(
        id=MY_PHONE, contact=MY_PHONE, status=status, summary=summary, created_at=created,
        data=ScreeningData(**fields),
        messages=[Message(role="agent", text="Hola, soy Sofía."), Message(role="candidate", text="Hola")],
    )


def run(candidate=None, *, dial=None, still_on=None, reads=None, allowlist=None, finish=None, max_call=600, call=None):
    """Runs process_call with fakes. `reads` are the successive read_conv results."""
    db = FakeDb()
    calls = {"dial": 0, "hang_up": 0, "finish": 0, "still_on": 0}
    reads = list(reads if reads is not None else [None, conv()])
    on = iter(still_on if still_on is not None else [False])

    async def _dial(phone):
        calls["dial"] += 1
        if dial:
            raise dial
        return "handle"

    async def _still_on(handle):
        calls["still_on"] += 1
        item = next(on, True)
        if isinstance(item, Exception):
            raise item
        return item

    async def _hang_up(handle):
        calls["hang_up"] += 1

    def _read(phone):
        return reads.pop(0) if len(reads) > 1 else reads[0]

    def _finish(phone):
        calls["finish"] += 1
        if finish is not None:
            reads[:] = [finish]

    async def _sleep(s):
        pass

    clock = iter(T0 + timedelta(seconds=2 * i) for i in range(10_000))
    status = asyncio.run(process_call(
        call or {"id": "call-1", "created_at": T0.isoformat()}, candidate or {"id": "cand-1", "phone": MY_PHONE, "is_demo": False, "attempts": 0},
        db=db, dial=_dial, still_on=_still_on, hang_up=_hang_up, read_conv=_read, finish_summary=_finish,
        allowlist=allowlist or {MY_PHONE}, now=lambda: next(clock), sleep=_sleep, max_call=max_call,
    ))
    return status, db, calls


# --- mapping ---------------------------------------------------------------------------

@pytest.mark.parametrize("status,stage", [
    ("qualified", "accepted"), ("needs_review", "revision"), ("disqualified", "rejected"),
    ("declined", "rejected"), ("abandoned", "queue"), ("in_progress", "queue"),
])
def test_stage_for_maps_every_status(status, stage):
    assert stage_for(status) == stage


def test_candidate_patch_qualified():
    p = candidate_patch(conv())
    assert p["stage"] == "accepted"
    assert p["decided_by"] == "agent"
    assert p["agent_status"] == "qualified"
    assert p["answers"]["has_license"]["value"] == "yes"
    assert p["name"] == "Ana López"
    assert [(m["role"], m["text"]) for m in p["transcript"]] == [("agent", "Hola, soy Sofía."), ("candidate", "Hola")]
    assert "retry_reason" not in p or p["retry_reason"] is None


def test_candidate_patch_in_progress_is_hung_up():
    p = candidate_patch(conv(status=Status.IN_PROGRESS, summary=None))
    assert p["stage"] == "queue"
    assert p["retry_reason"] == "hung_up"
    assert p["decided_by"] is None


def test_candidate_patch_without_name_keeps_existing_name():
    assert "name" not in candidate_patch(conv(full_name=FieldValue()))


def test_parse_allowlist_defaults():
    assert parse_allowlist(None, MY_PHONE) == {MY_PHONE}
    assert parse_allowlist(" +34611000000, +34622000000 ", MY_PHONE) == {"+34611000000", "+34622000000"}
    assert parse_allowlist(None, None) == set()


def test_allowed():
    assert allowed(MY_PHONE, {MY_PHONE})
    assert not allowed("+34699999999", {MY_PHONE})


# --- process_call ----------------------------------------------------------------------

def test_demo_candidate_is_blocked():
    status, db, calls = run({"id": "c", "phone": MY_PHONE, "is_demo": True, "attempts": 0})
    assert status == "blocked"
    assert calls["dial"] == 0
    assert db.patches("calls")["status"] == "blocked"
    assert db.patches("candidates") == {}


def test_number_outside_allowlist_is_blocked():
    status, db, calls = run({"id": "c", "phone": "+34699999999", "is_demo": False, "attempts": 0})
    assert status == "blocked"
    assert calls["dial"] == 0


def test_no_answer_goes_back_to_queue():
    status, db, _ = run(dial=CallError("busy", "486"))
    assert status == "no_answer"
    cand = db.patches("candidates")
    assert cand["stage"] == "queue"
    assert cand["attempts"] == 1
    assert cand["retry_reason"] == "no_answer"
    assert db.patches("calls")["status"] == "no_answer"


def test_other_dial_error_is_failed():
    status, db, _ = run(dial=CallError("trunk missing"))
    assert status == "failed"
    assert db.patches("candidates")["retry_reason"] == "failed"
    assert db.patches("calls")["error"]


def test_stale_conversation_is_failed():
    old = conv(created=T0 - timedelta(hours=1))
    status, db, _ = run(reads=[old, old])
    assert status == "failed"
    assert db.patches("candidates")["stage"] == "queue"


def test_finished_call_writes_outcome():
    done = conv(status=Status.NEEDS_REVIEW, summary="Revisar distancia.")
    status, db, _ = run(still_on=[True, True, False], reads=[None, done])
    assert status == "done"
    cand = db.patches("candidates")
    assert cand["stage"] == "revision"
    assert cand["summary"] == "Revisar distancia."
    call = db.patches("calls")
    assert call["answered"] is True and call["status"] == "done" and call["ended_at"]


def test_hung_up_mid_screening_counts_an_attempt():
    status, db, _ = run(reads=[None, conv(status=Status.IN_PROGRESS, summary=None)])
    assert status == "done"
    cand = db.patches("candidates")
    assert cand["stage"] == "queue" and cand["retry_reason"] == "hung_up" and cand["attempts"] == 1


def test_waits_for_summary():
    status, db, calls = run(reads=[None, conv(summary=None), conv(summary="Listo.")])
    assert db.patches("candidates")["summary"] == "Listo."
    assert calls["finish"] == 0


def test_missing_summary_is_finished_by_worker():
    status, db, calls = run(reads=[None, conv(summary=None)], finish=conv(summary="Hecho por el worker."))
    assert calls["finish"] == 1
    assert db.patches("candidates")["summary"] == "Hecho por el worker."


def test_long_call_is_hung_up():
    status, _, calls = run(still_on=[True] * 100, max_call=4)
    assert calls["hang_up"] == 1
    assert status == "done"


# --- Supabase REST client --------------------------------------------------------------

def test_db_sends_postgrest_requests():
    import httpx

    from worker.db import Db

    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=[{"id": "x"}])

    db = Db("https://proj.supabase.co", "service-key", transport=httpx.MockTransport(handler))
    db.update("calls", {"id": "abc"}, {"status": "done"})
    db.select("calls", {"status": "eq.requested", "limit": "1"})
    db.delete("candidates", {"id": "not.is.null"})

    patch, get, delete = seen
    assert patch.method == "PATCH" and patch.url.path == "/rest/v1/calls"
    assert patch.url.params["id"] == "eq.abc"
    assert patch.headers["apikey"] == "service-key"
    assert patch.headers["authorization"] == "Bearer service-key"
    assert get.method == "GET" and get.url.params["status"] == "eq.requested"
    assert delete.method == "DELETE" and delete.url.params["id"] == "not.is.null"


# --- review fixes ----------------------------------------------------------------------

def test_allowlist_entries_are_normalised():
    assert parse_allowlist("+34 612 345 678, 612345679", None) == {"+34612345678", "+34612345679"}
    assert parse_allowlist(None, "0034 600 111 222") == {"+34600111222"}


def test_missed_call_again_keeps_the_recruiters_decision():
    cand = {"id": "c", "phone": MY_PHONE, "is_demo": False, "attempts": 0, "stage": "accepted"}
    status, db, _ = run(cand, dial=CallError("busy", "486"))
    assert status == "no_answer"
    patch = db.patches("candidates")
    assert "stage" not in patch and "decided_by" not in patch
    assert patch["attempts"] == 1 and patch["retry_reason"] == "no_answer"


def test_expired_request_is_not_dialled():
    old = {"id": "call-1", "created_at": (T0 - timedelta(hours=3)).isoformat()}
    status, db, calls = run(call=old)
    assert status == "failed"
    assert calls["dial"] == 0
    assert "expired" in db.patches("calls")["error"]
    assert db.patches("candidates") == {}


def test_waits_for_the_last_turn_after_a_quick_hang_up():
    still_talking = conv(status=Status.IN_PROGRESS, summary=None)
    finished = conv(status=Status.QUALIFIED, summary="Apto.")
    finished.messages.append(Message(role="agent", text="¡Genial!"))
    status, db, _ = run(reads=[None, still_talking, finished])
    assert db.patches("candidates")["stage"] == "accepted"


def test_a_livekit_blip_does_not_end_the_call():
    boom = RuntimeError("livekit timeout")
    status, _, calls = run(still_on=[True, boom, True, False], reads=[None, conv()])
    assert status == "done"
    assert calls["still_on"] == 4  # kept watching after the error


def test_three_livekit_errors_in_a_row_end_the_call():
    boom = RuntimeError("room not found")
    status, _, calls = run(still_on=[boom, boom, boom, True, True])
    assert status == "done"
    assert calls["still_on"] == 3


def test_star_allows_any_number_but_never_demo_candidates():
    anyone = parse_allowlist("*", MY_PHONE)
    assert allowed("+34699999999", anyone)
    status, _, calls = run({"id": "c", "phone": "+34699999999", "is_demo": False, "attempts": 0}, allowlist=anyone)
    assert calls["dial"] == 1 and status == "done"
    status, _, calls = run({"id": "c", "phone": "+34699999999", "is_demo": True, "attempts": 0}, allowlist=anyone)
    assert status == "blocked" and calls["dial"] == 0
