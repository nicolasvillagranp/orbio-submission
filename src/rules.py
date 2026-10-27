"""The rules layer: code decides.

The classifier (Jev or Claude) turns free text into allowed values plus a confidence,
and the geocoder turns a place into a distance. Everything below is deterministic:
the confidence gate, knockout rules, stage order and final outcome.
No model ever decides on its own that a candidate is out.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .config import CONFIG
from .models import Conversation, Decision, FieldValue, Stage, Status

GATE = CONFIG["confidence_gate"]

AVAILABILITY_OPTIONS = ("full_time", "part_time", "weekends")
SCHEDULE_OPTIONS = ("morning", "afternoon", "evening", "flexible")
LICENSE_OPTIONS = ("yes", "no", "expired", "in_progress")
CONSENT_OPTIONS = ("yes", "no", "unclear")

# Stage -> the field that must be resolved to leave it, in conversation order.
STAGE_FIELDS: dict[Stage, str] = {
    Stage.CONSENT: "consent",
    Stage.NAME: "full_name",
    Stage.LICENSE: "has_license",
    Stage.LOCATION: "location",
    Stage.AVAILABILITY: "availability",
    Stage.SCHEDULE: "schedule",
    Stage.EXPERIENCE: "experience_years",
    Stage.START_DATE: "start_date",
}


@dataclass
class Classification:
    """A classifier's answer for one field: an allowed value and how sure it is."""

    value: Any
    confidence: float


@dataclass
class Outcome:
    field: str
    decision: Decision
    reason: str | None = None  # short machine-readable hint for the conversation model


def gate(confidence: float, rule: Decision) -> Decision:
    """Combine the business rule's verdict with how sure the classifier is.

    Answers we're fairly sure of are kept without asking: the final summary lets the
    candidate correct anything. Only a disqualifying answer that isn't clear is confirmed
    first, because it ends the conversation and there is no summary to correct it in.
    """
    if rule is Decision.REASK or confidence < GATE["keep"]:
        return Decision.REASK
    if rule is Decision.DISQUALIFY and confidence < GATE["knockout"]:
        return Decision.CONFIRM
    return rule


def is_resolved(fv: FieldValue) -> bool:
    return fv.confirmed or fv.flagged


# --- per-field checks -------------------------------------------------------------
# Each returns (decision, reason) given a classified value. They never see raw text.


def _check_consent(value: str) -> tuple[Decision, str | None]:
    if value == "yes":
        return Decision.ACCEPT, None
    if value == "no":
        return Decision.DISQUALIFY, "declined_consent"
    return Decision.REASK, "consent_unclear"


def _check_name(value: str, attempts: int) -> tuple[Decision, str | None]:
    tokens = (value or "").split()
    if not tokens:
        return Decision.REASK, "name_missing"
    if len(tokens) == 1 and attempts == 0:
        return Decision.REASK, "ask_surname"
    return Decision.ACCEPT, None


def _check_license(value: str) -> tuple[Decision, str | None]:
    if value == "yes":
        return Decision.ACCEPT, None
    if value == "no":
        return Decision.DISQUALIFY, "no_license"
    if value == "expired":  # has one, only needs renewal: fine, noted for the recruiter
        return Decision.ACCEPT, "license_needs_renewal"
    if value == "in_progress":  # can't drive yet
        return Decision.DISQUALIFY, "license_in_progress"
    return Decision.REASK, "license_unclear"


# geocoding.check_area() status -> what the screening does with it.
LOCATION_DECISIONS: dict[str, tuple[Decision, str | None]] = {
    "in_area": (Decision.ACCEPT, None),
    "review": (Decision.FLAG, "location_borderline_distance"),
    "out_of_area": (Decision.DISQUALIFY, "out_of_area"),
    "ambiguous": (Decision.REASK, "location_ambiguous"),
    "not_found": (Decision.REASK, "location_not_found"),
    # Our outage must never cost a candidate their application.
    "unavailable": (Decision.FLAG, "geocoder_unavailable"),
}


def _check_location(value: dict) -> tuple[Decision, str | None]:
    return LOCATION_DECISIONS.get((value or {}).get("status"), (Decision.REASK, "location_not_found"))


def _check_options(value: list[str], allowed: tuple[str, ...]) -> tuple[Decision, str | None]:
    picked = [v for v in value or [] if v in allowed]
    if not picked:
        return Decision.REASK, "no_option_matched"
    return Decision.ACCEPT, None


def _check_years(value: Any) -> tuple[Decision, str | None]:
    try:
        years = float(value)
    except (TypeError, ValueError):
        return Decision.REASK, "years_not_a_number"
    if not 0 <= years <= 40:
        return Decision.REASK, "years_out_of_range"
    return Decision.ACCEPT, None


def _check_start_date(value: Any, today: date) -> tuple[Decision, str | None]:
    try:
        start = value if isinstance(value, date) else date.fromisoformat(str(value))
    except ValueError:
        return Decision.REASK, "date_unparseable"
    if start < today:
        return Decision.REASK, "date_in_past"
    if start > today + timedelta(days=CONFIG["screening"]["max_start_days"]):
        return Decision.FLAG, "start_date_far"
    return Decision.ACCEPT, None


def _coerce(field: str, value: Any) -> Any:
    if field == "experience_years":
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if field == "start_date" and isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return value
    return value


# --- applying a classification ----------------------------------------------------


def apply(conv: Conversation, field: str, result: Classification, today: date | None = None) -> Outcome:
    """Run one field through the confidence gate and its business rule, update the conversation."""
    today = today or date.today()
    fv: FieldValue = getattr(conv.data, field)

    if field == "consent":
        rule, reason = _check_consent(result.value)
    elif field == "full_name":
        rule, reason = _check_name(result.value, fv.attempts)
    elif field == "has_license":
        rule, reason = _check_license(result.value)
    elif field == "location":
        rule, reason = _check_location(result.value)
    elif field == "availability":
        rule, reason = _check_options(result.value, AVAILABILITY_OPTIONS)
    elif field == "schedule":
        rule, reason = _check_options(result.value, SCHEDULE_OPTIONS)
    elif field == "experience_years":
        rule, reason = _check_years(result.value)
    elif field == "start_date":
        rule, reason = _check_start_date(result.value, today)
    elif field == "platforms":
        fv.value, fv.confidence, fv.confirmed = list(result.value or []), result.confidence, True
        return Outcome(field, Decision.ACCEPT)
    else:
        raise ValueError(f"unknown field {field!r}")

    decision = gate(result.confidence, rule)
    if decision is Decision.REASK:
        reason = reason or "low_confidence"

    if decision is not Decision.REASK:
        fv.value = _coerce(field, result.value)
        fv.confidence = result.confidence

    if decision in (Decision.REASK, Decision.CONFIRM):
        fv.attempts += 1
        if fv.attempts >= GATE["max_attempts"]:
            decision, reason = Decision.FLAG, f"{field}_unresolved_after_retries"
            if fv.value is None:
                fv.value = _coerce(field, result.value)
                fv.confidence = result.confidence

    if decision is Decision.ACCEPT:
        fv.confirmed = True
        fv.note = reason  # e.g. "license_needs_renewal": shown to the recruiter, not a blocker
    elif decision is Decision.FLAG:
        fv.flagged = True
        fv.note = reason
        if reason and reason not in conv.review_reasons:
            conv.review_reasons.append(reason)
    elif decision is Decision.DISQUALIFY:
        _disqualify(conv, fv, reason)
        return Outcome(field, decision, reason)

    conv.stage = next_stage(conv)
    return Outcome(field, decision, reason)


def _disqualify(conv: Conversation, fv: FieldValue, reason: str | None) -> None:
    fv.confirmed = True
    conv.disqualify_reason = reason
    conv.status = Status.DECLINED if reason == "declined_consent" else Status.DISQUALIFIED
    conv.stage = Stage.DONE


def confirm_pending(conv: Conversation, field: str) -> None:
    """The candidate said yes to a CONFIRM question: the stored value becomes final,
    and its business rule now applies at full strength."""
    fv: FieldValue = getattr(conv.data, field)
    if fv.value is None:
        return
    if field == "has_license" and fv.value in ("no", "in_progress"):
        _disqualify(conv, fv, "no_license" if fv.value == "no" else "license_in_progress")
        return
    if field == "consent" and fv.value == "no":
        _disqualify(conv, fv, "declined_consent")
        return
    fv.confirmed = True
    conv.stage = next_stage(conv)


def next_stage(conv: Conversation) -> Stage:
    if conv.status is not Status.IN_PROGRESS:
        return Stage.DONE
    for stage, field in STAGE_FIELDS.items():
        if not is_resolved(getattr(conv.data, field)):
            return stage
    return Stage.CONFIRMATION


def finish(conv: Conversation) -> Status:
    """Candidate confirmed the recap. Decide the final queue."""
    if conv.status is Status.IN_PROGRESS:
        conv.status = Status.NEEDS_REVIEW if (conv.review_reasons or "human_requested" in conv.flags) else Status.QUALIFIED
    conv.stage = Stage.DONE
    return conv.status


def missing_fields(conv: Conversation) -> list[str]:
    return [f for f in STAGE_FIELDS.values() if not is_resolved(getattr(conv.data, f))]
