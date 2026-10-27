"""Data model for a screening conversation."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Stage(str, Enum):
    CONSENT = "consent"
    NAME = "name"
    LICENSE = "license"
    LOCATION = "location"
    AVAILABILITY = "availability"
    SCHEDULE = "schedule"
    EXPERIENCE = "experience"
    START_DATE = "start_date"
    CONFIRMATION = "confirmation"
    DONE = "done"


class Status(str, Enum):
    IN_PROGRESS = "in_progress"
    QUALIFIED = "qualified"
    NEEDS_REVIEW = "needs_review"
    DISQUALIFIED = "disqualified"
    ABANDONED = "abandoned"
    DECLINED = "declined"


class Channel(str, Enum):
    WHATSAPP = "whatsapp"
    VOICE = "voice"
    WEB = "web"


class Decision(str, Enum):
    """What the rules layer tells the conversation to do next with a field."""

    ACCEPT = "accept"          # value stored, move on
    CONFIRM = "confirm"        # value stored tentatively, ask the candidate to confirm
    REASK = "reask"            # nothing usable, ask again in other words
    FLAG = "flag"              # gave up asking; best guess stored, recruiter must review
    DISQUALIFY = "disqualify"  # knockout rule failed


class FieldValue(BaseModel):
    value: Any = None
    confidence: float | None = None
    attempts: int = 0
    confirmed: bool = False
    flagged: bool = False
    note: str | None = None


class ScreeningData(BaseModel):
    """The structured output the client asked for. One FieldValue per screening field."""

    consent: FieldValue = Field(default_factory=FieldValue)
    full_name: FieldValue = Field(default_factory=FieldValue)
    has_license: FieldValue = Field(default_factory=FieldValue)
    location: FieldValue = Field(default_factory=FieldValue)  # value: geocoding.check_area() result
    availability: FieldValue = Field(default_factory=FieldValue)
    schedule: FieldValue = Field(default_factory=FieldValue)
    experience_years: FieldValue = Field(default_factory=FieldValue)
    platforms: FieldValue = Field(default_factory=FieldValue)
    start_date: FieldValue = Field(default_factory=FieldValue)

    def as_flat_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, fv in self:
            v = fv.value
            out[name] = v.isoformat() if isinstance(v, date) else v
        return out


class Message(BaseModel):
    role: str  # "candidate" | "agent" | "system"
    text: str
    at: datetime = Field(default_factory=utcnow)
    language: str | None = None


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    channel: Channel = Channel.WEB
    contact: str | None = None  # phone number for WhatsApp
    stage: Stage = Stage.CONSENT
    status: Status = Status.IN_PROGRESS
    language: str = "es"
    data: ScreeningData = Field(default_factory=ScreeningData)
    messages: list[Message] = Field(default_factory=list)
    disqualify_reason: str | None = None
    review_reasons: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)  # human_requested, deletion_requested, abuse...
    summary: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    # LLM-side transcript (Anthropic message params) so tool use survives restarts.
    llm_history: list[dict[str, Any]] = Field(default_factory=list)
