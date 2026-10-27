"""Puts the demo board back to its starting state: python -m worker.reset_demo

Deletes every candidate and call in Supabase (including ones added during a demo) and inserts the
seeded candidates from worker/seed.json, dated relative to now. Seeded numbers are never dialled.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED_PATH = Path(__file__).with_name("seed.json")
CANDIDATE_FIELDS = ("phone", "name", "stage", "decided_by", "agent_status", "summary", "answers", "review_reasons",
                    "disqualify_reason", "transcript", "team_note", "attempts", "retry_reason")


def build_rows(seed: dict, now: datetime) -> tuple[list[dict], list[dict]]:
    """Candidate and call rows for the seed, with timestamps computed from `now`."""
    candidates, calls = [], []
    for c in seed["candidates"]:
        cid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sazon-demo/{c['phone']}"))
        created = (now - timedelta(days=c["days_ago"])).replace(hour=9, minute=0, second=0, microsecond=0)
        created = min(created, now - timedelta(hours=c["hours_in_stage"] + 1))
        changed = max(created, now - timedelta(hours=c["hours_in_stage"]))
        row = {k: c[k] for k in CANDIDATE_FIELDS}
        start = row["answers"].get("start_date")
        if start and isinstance(start["value"], dict):  # seed says "in N days"; the agent stores a date
            row["answers"] = {**row["answers"], "start_date": {
                **start, "value": (now + timedelta(days=start["value"]["in_days"])).date().isoformat()}}
        row.update(id=cid, source="seed", is_demo=True, created_at=created.isoformat(),
                   stage_changed_at=changed.isoformat(), updated_at=changed.isoformat())
        candidates.append(row)
        for call in c["calls"]:
            at = (now - timedelta(days=call["days_ago"])).replace(hour=call["hour"], minute=0, second=0, microsecond=0)
            at = min(max(at, created), now)
            calls.append({
                "candidate_id": cid, "requested_by": "demo", "answered": call["answered"],
                "status": "done" if call["answered"] else "no_answer",
                "created_at": at.isoformat(), "started_at": at.isoformat(),
                "ended_at": (at + timedelta(minutes=4 if call["answered"] else 1)).isoformat(),
            })
    return candidates, calls


def main() -> None:
    from src.config import ROOT  # noqa: F401  (loads .env)

    from .db import Db

    db = Db.from_env()
    candidates, calls = build_rows(json.loads(SEED_PATH.read_text(encoding="utf-8")), datetime.now(timezone.utc))
    db.delete("calls", {"id": "not.is.null"})
    db.delete("candidates", {"id": "not.is.null"})
    db.insert("candidates", candidates)
    db.insert("calls", calls)
    print(f"{len(candidates)} candidates, {len(calls)} calls")


if __name__ == "__main__":
    main()
