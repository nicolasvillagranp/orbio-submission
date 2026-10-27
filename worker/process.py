"""One call request, start to finish: dial, wait for the hang-up, report the screening."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .mapping import allowed, candidate_patch

NO_ANSWER_SIP = {"408", "480", "486", "487", "603"}
POLL = 2  # seconds
REQUEST_TTL = 600  # a request older than this was made while the worker was off: don't dial it
SETTLE = 30  # max seconds to wait for the agent to finish the last turn after the hang-up
LIVEKIT_ERRORS = 3  # consecutive failed checks before a call counts as ended


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(t: datetime) -> str:
    return t.isoformat()


def _shape(conv):
    return None if conv is None else (conv.created_at, len(conv.messages), conv.status, conv.summary)


async def process_call(call, candidate, *, db, dial, still_on, hang_up, read_conv, finish_summary, allowlist,
                       now=utcnow, sleep=asyncio.sleep, summary_wait=20, max_call=600) -> str:
    """Returns the call's final status. `dial` raises an error carrying `sip_status` when the
    call doesn't connect; `read_conv(phone)` reads the agent's conversation from SQLite."""
    phone = candidate["phone"]

    def set_call(**patch):
        db.update("calls", {"id": call["id"]}, patch)

    def back_to_queue(reason: str):
        patch = {"retry_reason": reason, "attempts": candidate.get("attempts", 0) + 1}
        if candidate.get("stage", "queue") == "queue":  # a recruiter's Accept/Reject stands
            patch.update(stage="queue", decided_by=None)
        db.update("candidates", {"id": candidate["id"]}, patch)

    if candidate.get("is_demo") or not allowed(phone, allowlist):
        why = "demo candidate" if candidate.get("is_demo") else f"{phone} is not in CALL_ALLOWLIST"
        set_call(status="blocked", error=why, ended_at=_iso(now()))
        return "blocked"

    if call.get("created_at"):
        age = (now() - datetime.fromisoformat(call["created_at"])).total_seconds()
        if age > REQUEST_TTL:
            set_call(status="failed", error=f"request expired ({int(age // 60)} min old): ask again", ended_at=_iso(now()))
            return "failed"

    before = read_conv(phone)
    before_created = before.created_at if before else None

    set_call(status="dialling", started_at=_iso(now()))
    try:
        handle = await dial(phone)
    except Exception as e:  # telephony.calls.CallError, or LiveKit unreachable
        sip = getattr(e, "sip_status", None)
        text = str(e).lower()
        status = "no_answer" if sip in NO_ANSWER_SIP or "no answer" in text or "busy" in text else "failed"
        set_call(status=status, error=str(e), ended_at=_iso(now()))
        back_to_queue(status)
        return status

    answered_at = now()
    set_call(status="in_call", answered=True)
    errors = 0
    while True:
        try:
            on = await still_on(handle)
            errors = 0
        except Exception:  # the room is gone (agent hung up), or LiveKit hiccuped: retry a few times
            errors += 1
            on = errors < LIVEKIT_ERRORS
        if not on:
            break
        if (now() - answered_at).total_seconds() >= max_call:
            await hang_up(handle)
            break
        await sleep(POLL)

    # The agent may still be processing the candidate's last words: wait until nothing changes.
    conv, waited, stable = read_conv(phone), 0, 0
    while waited < SETTLE and stable < 2:
        await sleep(POLL)
        waited += POLL
        latest = read_conv(phone)
        stable = stable + 1 if _shape(latest) == _shape(conv) else 0
        conv = latest
    if conv is None or conv.created_at == before_created:
        set_call(status="failed", error="the agent never started a screening", ended_at=_iso(now()))
        back_to_queue("failed")
        return "failed"

    if conv.status.value != "in_progress" and not conv.summary:
        waited = 0
        while waited < summary_wait and not conv.summary:
            await sleep(POLL)
            waited += POLL
            conv = read_conv(phone)
        if not conv.summary:
            await asyncio.to_thread(finish_summary, phone)
            conv = read_conv(phone)

    patch = candidate_patch(conv)
    if patch["stage"] == "queue":
        patch["attempts"] = candidate.get("attempts", 0) + 1
    db.update("candidates", {"id": candidate["id"]}, patch)
    set_call(status="done", ended_at=_iso(now()))
    return "done"
