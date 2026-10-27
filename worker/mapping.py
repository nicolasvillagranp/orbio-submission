"""How a finished screening shows up on the recruiter board."""

from __future__ import annotations

import re

from src.models import Conversation

STAGES = {
    "qualified": "accepted",
    "needs_review": "revision",
    "disqualified": "rejected",
    "declined": "rejected",
    "abandoned": "queue",
    "in_progress": "queue",  # the phone left before the screening ended
}


def stage_for(status: str) -> str:
    return STAGES[status]


def candidate_patch(conv: Conversation) -> dict:
    """The candidate columns the worker writes after a call."""
    data = conv.model_dump(mode="json")
    stage = stage_for(conv.status.value)
    patch = {
        "stage": stage,
        "decided_by": None if stage == "queue" else "agent",
        "agent_status": conv.status.value,
        "summary": conv.summary,
        "answers": {f: {"value": v["value"], "flagged": v["flagged"], "note": v["note"]} for f, v in data["data"].items()},
        "review_reasons": conv.review_reasons,
        "disqualify_reason": conv.disqualify_reason,
        "transcript": [{"role": m["role"], "text": m["text"], "at": m["at"]} for m in data["messages"]],
        "retry_reason": "hung_up" if stage == "queue" else None,
    }
    if conv.data.full_name.value:
        patch["name"] = conv.data.full_name.value
    return patch


ANY = "*"  # CALL_ALLOWLIST=* lets the worker dial any number (seeded demo candidates are still never called)


def normalize_phone(raw: str) -> str:
    """Same rules as the web app (web/src/lib/phone.ts), so .env numbers match stored ones."""
    s = re.sub(r"[\s\-.()]", "", raw)
    if s.startswith("00"):
        s = "+" + s[2:]
    if re.fullmatch(r"[6789]\d{8}", s):
        s = "+34" + s
    return s


def parse_allowlist(raw: str | None, my_phone: str | None) -> set[str]:
    """Numbers the worker may dial: CALL_ALLOWLIST, or just MY_PHONE_NUMBER."""
    items = raw.split(",") if raw and raw.strip() else [my_phone or ""]
    return {i.strip() if i.strip() == ANY else normalize_phone(i) for i in items if i and i.strip()}


def allowed(phone: str, allowlist: set[str]) -> bool:
    return ANY in allowlist or phone in allowlist
