"""The screening pipeline as a LangGraph graph. One run per candidate message.

    START ─┬─ new conversation ─→ open ──────────────────────────────→ END
           └─ message ─→ classify ─→ decide ─→ respond ─┬─ finished ─→ summarize ─→ END
                                                        └──────────────────────────→ END

classify  one Jev call: field answers, confirmations, signals
decide    rules.py applies them; code writes `next_step` (what to say next)
respond   Claude phrases the reply and records free-text answers via one tool
summarize short summary for the recruiter once the screening ends, run in the background
          after the reply is out (the graph pauses before it)

State is saved by the SQLite checkpointer after every step, keyed by thread_id
(the candidate's phone number on WhatsApp), so a conversation resumes hours later.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import date
from typing import Any, TypedDict

import anthropic
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from . import classifier, rules
from .config import ANTHROPIC_API_KEY, CONFIG, DATA_DIR
from .dates import spoken, today_line
from .geocoding import check_area
from .models import Channel, Conversation, Message, Stage, Status
from .prompts import OPENING, SYSTEM_PROMPT, TECHNICAL_ERROR
from .rules import Classification

log = logging.getLogger("pipeline")

CHOICE_FIELDS = ("consent", "has_license", "availability", "schedule")
CONFIRMED = 0.8                  # Jev probability to act on "yes, that's right" / "no, that's wrong"
SIGNAL = 0.8                     # threshold for acting on a signal (wants a human, abuse...)
FRUSTRATED = 1.0                 # frustration score runs 0 (calm) .. 2 (clearly frustrated)


class State(TypedDict, total=False):
    conversation: dict  # Conversation, as JSON
    message: str        # the candidate message being processed
    today: str          # ISO date, injectable for tests
    analysis: dict      # classify -> decide
    turn: dict          # decide -> respond: what happened this turn
    reply: str          # what we send back


# --- describing values in words (for Jev confirmations and Claude) -------------------

QUESTIONS = {
    Stage.CONSENT: "Ask whether they'd like to start the screening.",
    Stage.NAME: "Ask for their full name (name and surname).",
    Stage.LICENSE: "Ask whether they have a valid driver's license.",
    Stage.LOCATION: "Ask where they live (neighbourhood and city).",
    Stage.AVAILABILITY: "Ask their availability: full-time, part-time or weekends.",
    Stage.SCHEDULE: "Ask which shift they prefer: morning, afternoon, evening, or flexible.",
    Stage.EXPERIENCE: "Ask whether they have delivery experience: how many years and on which platforms (Glovo, Uber Eats...).",
    Stage.START_DATE: "Ask when they could start.",
}

REASK_HINTS = {
    "ask_surname": "Ask for their surname too.",
    "location_not_found": "Say you couldn't find that place and ask for their neighbourhood and city.",
    "date_in_past": "That date has already passed: ask again for when they could start.",
    "date_unparseable": "Ask for a specific day they could start.",
    "years_out_of_range": "Ask again how many years of delivery experience they have.",
}

DISQUALIFY_REASONS = {
    "no_license": "a valid driver's license is required for this role",
    "license_in_progress": "a valid driver's license is required to start; they're welcome to apply again once they have it",
    "out_of_area": "there's no Grupo Sazón restaurant close enough to where they live; they're welcome to apply again if that changes",
}


def describe(field: str, value: Any) -> str:
    """A field value in plain English, e.g. for 'Did you mean...?'."""
    if field == "has_license":
        return {"yes": "the candidate has a valid driver's license", "no": "the candidate has no driver's license",
                "expired": "the candidate's license is expired and only needs renewal",
                "in_progress": "the candidate is still getting their driver's license"}.get(value, str(value))
    if field == "availability":
        return "the candidate can work " + " and ".join(classifier.AVAILABILITY_TEXT[v] for v in value)
    if field == "schedule":
        return "the candidate prefers to work " + " and ".join(classifier.SCHEDULE_TEXT[v] for v in value)
    if field == "consent":
        return "the candidate wants to continue" if value == "yes" else "the candidate does not want to continue"
    return f"{field} is {value}"


def pending_confirmations(conv: Conversation) -> dict[str, str]:
    """Fields with a value we asked the candidate to confirm."""
    return {
        f: describe(f, fv.value)
        for f in CHOICE_FIELDS
        if (fv := getattr(conv.data, f)).value is not None and not fv.confirmed and not fv.flagged
    }


def recap_lines(conv: Conversation) -> list[str]:
    d, lang = conv.data, conv.language
    start = d.start_date.value
    return [
        f"name: {d.full_name.value}",
        f"driver's license: {d.has_license.value}",
        f"lives in: {(d.location.value or {}).get('place') or (d.location.value or {}).get('query')}",
        f"availability: {', '.join(d.availability.value or [])}",
        f"shift: {', '.join(d.schedule.value or [])}",
        f"delivery experience: {d.experience_years.value} years ({', '.join(d.platforms.value or []) or 'no platforms given'})",
        f"start date: {spoken(date.fromisoformat(str(start)), lang) if start else None}",
    ]


def next_step(conv: Conversation, turn: dict) -> str:
    """What the agent should say next. Code decides; Claude only phrases it."""
    if "deletion_requested" in turn.get("events", []):
        return "Confirm that their data will be deleted and say goodbye. Ask nothing else."
    if conv.status is Status.DISQUALIFIED:
        reason = DISQUALIFY_REASONS.get(conv.disqualify_reason or "", "the requirements for this role aren't met")
        return (f"Close the conversation kindly. Explain simply that {reason}. Tell them they can reply to ask "
                "for a human recruiter to review their application. Wish them luck. No emoji.")
    if conv.status is Status.DECLINED:
        if conv.disqualify_reason == "abusive":
            return "Close the conversation politely and neutrally."
        return "Say no problem, thank them for their time, and say goodbye."
    if conv.status in (Status.QUALIFIED, Status.NEEDS_REVIEW):
        return "Thank them. Say a recruiter will contact them within 48 hours. Say goodbye."
    if conv.status is Status.ABANDONED:
        later = "by writing again here" if conv.channel is Channel.WHATSAPP else "another time"
        return f"Say no problem, that they can finish the screening {later}, and goodbye. Ask nothing else."

    steps: list[str] = []
    if "resumed" in turn.get("events", []):
        steps.append("Welcome them back briefly.")
    if "manipulation" in turn.get("events", []) or "abusive_warning" in turn.get("events", []):
        steps.append("Don't engage with that; stay friendly and neutral and return to the screening.")
    if "human_requested" in turn.get("events", []):
        steps.append("Tell them a recruiter will contact them, and ask if they're happy to finish the last few questions first.")
    if turn.get("asks_question"):
        steps.append("First answer their question using only the FAQ.")
    if turn.get("date_read_back"):
        steps.append(f"Read their start date back to them: {turn['date_read_back']}.")

    to_confirm = pending_confirmations(conv)
    if conv.stage is Stage.CONFIRMATION:
        if turn.get("recap_rejected"):
            steps.append("Ask what needs correcting.")
        else:
            steps.append("Send a short summary of their answers as a list, then ask if everything is correct. "
                         "Summary data: " + "; ".join(recap_lines(conv)))
    elif to_confirm:
        field, text = next(iter(to_confirm.items()))
        steps.append(f"Ask them to confirm, as a yes/no question, that {text}.")
    else:
        hint = next((REASK_HINTS.get(o["reason"]) for o in turn.get("outcomes", [])
                     if o["decision"] == "reask" and o["reason"] in REASK_HINTS), None)
        location = conv.data.location.value or {}
        if conv.stage is Stage.LOCATION and location.get("status") == "ambiguous":
            hint = "Ask which of these places they mean: " + " / ".join(location["options"])
        steps.append(hint or QUESTIONS[conv.stage])
    return " ".join(steps)


def state_block(conv: Conversation, turn: dict, today: date) -> str:
    """The per-turn operator message Claude sees (as a mid-conversation system message)."""
    state = {
        "channel": conv.channel.value,
        "reply_language": conv.language,
        "stage": conv.stage.value,
        "frustrated": turn.get("frustrated", False),
        "collected": {k: v for k, v in conv.data.as_flat_dict().items() if v is not None},
        "next_step": next_step(conv, turn),
    }
    return f"<screening_state>\n{today_line(today)}\n{json.dumps(state, ensure_ascii=False, default=str)}\n</screening_state>"


# --- Claude ---------------------------------------------------------------------------

RECORD_DETAILS = {
    "name": "record_details",
    "description": "Record free-text answers the candidate just gave. Use null for anything they didn't say.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "full_name": {"type": ["string", "null"]},
            "location": {"type": ["string", "null"], "description": "Where they live, as they said it, plus city/country if given"},
            "experience_years": {"type": ["number", "null"], "description": "Years of delivery experience; 0 if none; 0.5 for a few months"},
            "platforms": {"type": ["array", "null"], "items": {"type": "string"}},
            "start_date": {"type": ["string", "null"], "description": "YYYY-MM-DD, worked out from today's date"},
        },
        "required": ["full_name", "location", "experience_years", "platforms", "start_date"],
        "additionalProperties": False,
    },
}

_claude: anthropic.Anthropic | None = None


def claude() -> anthropic.Anthropic:
    global _claude
    if _claude is None:
        _claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=30.0, max_retries=2)
    return _claude


def call_claude(messages: list[dict], tools: list[dict] | None = None, system: str = SYSTEM_PROMPT, max_tokens: int = 1024):
    model = CONFIG["llm"]["chat_model"]
    extra = {}
    if "haiku" not in model:  # Haiku has no server-side refusal fallback
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    return claude().beta.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        tools=tools or [],
        output_config={"effort": CONFIG["llm"]["chat_effort"]},
        cache_control={"type": "ephemeral"},
        **extra,
    )


def record_details(conv: Conversation, args: dict, today: date, turn: dict) -> dict:
    """Run Claude's extracted answers through the rules. Returns the tool result."""
    if conv.status is not Status.IN_PROGRESS:  # screening already over: nothing to record
        return {"results": [], "next_step": next_step(conv, turn)}
    results = []

    def run(field: str, value: Any) -> None:
        out = rules.apply(conv, field, Classification(value, 1.0), today=today)
        results.append({"field": field, "decision": out.decision.value, "reason": out.reason})
        turn.setdefault("outcomes", []).append(results[-1])

    if args.get("full_name"):
        run("full_name", args["full_name"])
    if args.get("location"):
        run("location", check_area(args["location"]))
    if args.get("experience_years") is not None:
        run("experience_years", args["experience_years"])
    if args.get("platforms"):
        run("platforms", args["platforms"])
    if args.get("start_date"):
        run("start_date", args["start_date"])
        if results[-1]["decision"] in ("accept", "flag"):
            turn["date_read_back"] = spoken(date.fromisoformat(args["start_date"]), conv.language)
    return {"results": results, "next_step": next_step(conv, turn)}


# --- graph nodes ----------------------------------------------------------------------


def _today(state: State) -> date:
    return date.fromisoformat(state["today"]) if state.get("today") else date.today()


def open_conversation(state: State) -> State:
    conv = Conversation.model_validate(state.get("conversation") or {})
    text = OPENING[conv.language]
    conv.messages.append(Message(role="agent", text=text))
    # Claude's history starts with the opening it "sent", so later turns read naturally.
    conv.llm_history = [
        {"role": "user", "content": "[A candidate applied for the delivery driver role. Send the opening message.]"},
        {"role": "assistant", "content": text},
    ]
    return {"conversation": conv.model_dump(mode="json"), "reply": text}


def classify(state: State) -> State:
    conv = Conversation.model_validate(state["conversation"])
    message = state["message"]
    conv.messages.append(Message(role="candidate", text=message))
    last_agent = next((m.text for m in reversed(conv.messages) if m.role == "agent"), "")

    open_fields = {f for f in CHOICE_FIELDS if not rules.is_resolved(getattr(conv.data, f))}
    if conv.stage is Stage.CONFIRMATION:
        open_fields = set(CHOICE_FIELDS) - {"consent"}  # corrections during the summary
    try:
        result = classifier.analyze(last_agent, message, open_fields, pending_confirmations(conv),
                                    recap_pending=conv.stage is Stage.CONFIRMATION)
        analysis = {
            "fields": {f: {"value": c.value, "confidence": c.confidence} for f, c in result["fields"].items()},
            "confirms": result["confirms"],
            "rejects": result["rejects"],
            "signals": result["signals"],
        }
    except Exception as exc:  # Jev down: carry on, Claude still talks; nothing gets classified
        log.warning("classifier failed: %s", exc)
        analysis = {"fields": {}, "confirms": {}, "rejects": {}, "signals": {}, "error": str(exc)}
    return {"conversation": conv.model_dump(mode="json"), "analysis": analysis}


def decide(state: State) -> State:
    conv = Conversation.model_validate(state["conversation"])
    today = _today(state)
    a = state["analysis"]
    s = a.get("signals", {})
    turn: dict = {"events": [], "outcomes": [], "asks_question": s.get("asks_question", 0) >= 0.5,
                  "frustrated": s.get("frustration", 0) >= FRUSTRATED}

    if s.get("language") in ("es", "en"):
        conv.language = s["language"]
        conv.messages[-1].language = s["language"]

    if conv.status is Status.ABANDONED:  # they left earlier and wrote again: carry on where they stopped
        conv.status, conv.summary = Status.IN_PROGRESS, None
        turn["events"].append("resumed")

    # Signals that stop or redirect the conversation.
    if s.get("delete_data", 0) >= SIGNAL:
        conv.flags.append("deletion_requested")
        conv.status, conv.disqualify_reason, conv.stage = Status.DECLINED, "deletion_requested", Stage.DONE
        turn["events"].append("deletion_requested")
        return {"conversation": conv.model_dump(mode="json"), "turn": turn}
    if s.get("abusive", 0) >= SIGNAL:
        if "abusive" in conv.flags:  # second time: close
            conv.status, conv.disqualify_reason, conv.stage = Status.DECLINED, "abusive", Stage.DONE
            return {"conversation": conv.model_dump(mode="json"), "turn": turn}
        conv.flags.append("abusive")
        turn["events"].append("abusive_warning")
    if s.get("manipulation", 0) >= SIGNAL:
        conv.flags.append("manipulation")
        turn["events"].append("manipulation")
    if s.get("wants_human", 0) >= SIGNAL and "human_requested" not in conv.flags:
        conv.flags.append("human_requested")
        turn["events"].append("human_requested")

    # Confirmations of values we asked about. Only an explicit "that's wrong" discards the
    # value; if they talked about something else, it stays pending and we ask again.
    rejects = a.get("rejects", {})
    for field, p in a.get("confirms", {}).items():
        said_no = rejects.get(field, 0) >= CONFIRMED
        if field == "recap":
            if p >= CONFIRMED:
                rules.finish(conv)
            elif said_no:
                turn["recap_rejected"] = True
        elif p >= CONFIRMED:
            rules.confirm_pending(conv, field)
        elif said_no:
            getattr(conv.data, field).value = None

    # Field answers. Answers volunteered for fields we haven't asked about yet only count if
    # they're clear enough to keep; otherwise we just ask that question when we get to it
    # (so a vague guess never counts as a failed attempt).
    current = rules.STAGE_FIELDS.get(conv.stage)
    keep = CONFIG["confidence_gate"]["keep"]
    for field, c in a.get("fields", {}).items():
        if conv.status is not Status.IN_PROGRESS:
            break
        if field != current and c["confidence"] < keep:
            continue
        if turn["asks_question"] and c["confidence"] < keep:
            continue  # they asked something instead of answering: not a failed attempt
        out = rules.apply(conv, field, Classification(c["value"], c["confidence"]), today=today)
        turn["outcomes"].append({"field": field, "decision": out.decision.value, "reason": out.reason})

    # Leaving mid-screening, checked last so answers in the same message still count ("sí, todo
    # correcto, adiós" finishes it). Paused at the stage reached; writing again resumes it.
    if s.get("wants_to_leave", 0) >= SIGNAL and conv.status is Status.IN_PROGRESS:
        conv.status = Status.ABANDONED
        conv.flags.append("left_early")
        turn["events"].append("candidate_left")

    return {"conversation": conv.model_dump(mode="json"), "turn": turn}


def respond(state: State) -> State:
    conv = Conversation.model_validate(state["conversation"])
    today = _today(state)
    turn = dict(state.get("turn") or {})
    history_before = list(conv.llm_history)

    conv.llm_history.append({"role": "user", "content": state["message"]})
    conv.llm_history.append({"role": "system", "content": state_block(conv, turn, today)})

    try:
        for _ in range(3):  # at most a couple of tool rounds per message
            # Always the same tool list: changing it mid-conversation invalidates earlier
            # thinking blocks (and the prompt cache).
            resp = call_claude(conv.llm_history, [RECORD_DETAILS])
            if resp.stop_reason == "refusal":
                raise RuntimeError("refusal")
            conv.llm_history.append({"role": "assistant", "content": [b.to_dict() for b in resp.content]})
            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            if not tool_uses:
                break
            results = []
            for tu in tool_uses:
                out = record_details(conv, dict(tu.input), today, turn) if tu.name == "record_details" else {"error": "unknown tool"}
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": json.dumps(out, ensure_ascii=False)})
            conv.llm_history.append({"role": "user", "content": results})
        reply = "".join(b.text for b in resp.content if b.type == "text").strip()
        if not reply:
            raise RuntimeError(f"empty reply (stop_reason={resp.stop_reason})")
    except Exception as exc:  # never crash on the candidate: apologise and let them repeat
        log.warning("respond failed: %s", exc)
        conv.llm_history = history_before  # keep Claude's history valid for the next turn
        reply = TECHNICAL_ERROR[conv.language]

    conv.messages.append(Message(role="agent", text=reply, language=conv.language))
    return {"conversation": conv.model_dump(mode="json"), "reply": reply, "turn": turn}


SUMMARY_PROMPT = """\
You write short notes for recruiters about a delivery-driver screening. In Spanish, at most \
4 lines, no greeting: outcome and why, key facts (license, where they live and nearest \
restaurant, availability, shift, experience, start date), and anything the recruiter must check."""


def summarize(state: State) -> State:
    conv = Conversation.model_validate(state["conversation"])
    facts = {
        "status": conv.status.value,
        "disqualify_reason": conv.disqualify_reason,
        "review_reasons": conv.review_reasons,
        "flags": conv.flags,
        "data": conv.data.as_flat_dict(),
        "notes": {f: fv.note for f, fv in conv.data if fv.note},
    }
    try:
        resp = call_claude([{"role": "user", "content": json.dumps(facts, ensure_ascii=False, default=str)}],
                           system=SUMMARY_PROMPT, max_tokens=512)
        conv.summary = "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as exc:
        log.warning("summary failed: %s", exc)
        conv.summary = f"[Resumen no disponible] Estado: {conv.status.value}. Motivos: {conv.review_reasons or conv.disqualify_reason}"
    return {"conversation": conv.model_dump(mode="json")}


# --- wiring ---------------------------------------------------------------------------


def _route_start(state: State) -> str:
    return "classify" if state.get("conversation") and state.get("message") else "open"


def _route_after_respond(state: State) -> str:
    conv = state["conversation"]
    return "summarize" if conv["status"] != Status.IN_PROGRESS.value and not conv.get("summary") else END


def build_graph(checkpointer=None):
    g = StateGraph(State)
    g.add_node("open", open_conversation)
    g.add_node("classify", classify)
    g.add_node("decide", decide)
    g.add_node("respond", respond)
    g.add_node("summarize", summarize)
    g.add_conditional_edges(START, _route_start, ["open", "classify"])
    g.add_edge("open", END)
    g.add_edge("classify", "decide")
    g.add_edge("decide", "respond")
    g.add_conditional_edges("respond", _route_after_respond, ["summarize", END])
    g.add_edge("summarize", END)
    # Pause before the recruiter summary so the candidate gets their reply first;
    # Screening resumes the run in the background.
    return g.compile(checkpointer=checkpointer, interrupt_before=["summarize"])


def sqlite_checkpointer(path=DATA_DIR / "conversations.db") -> SqliteSaver:
    return SqliteSaver(sqlite3.connect(str(path), check_same_thread=False))


# --- the one function every channel calls --------------------------------------------


class Screening:
    """Entry point for WhatsApp, voice and the local chat: one instance per process."""

    def __init__(self, checkpointer=None):
        self.graph = build_graph(checkpointer if checkpointer is not None else sqlite_checkpointer())
        self._summaries: dict[str, threading.Thread] = {}

    def _config(self, thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def conversation(self, thread_id: str) -> Conversation | None:
        values = self.graph.get_state(self._config(thread_id)).values
        return Conversation.model_validate(values["conversation"]) if values.get("conversation") else None

    def start(self, thread_id: str, channel: Channel = Channel.WEB, language: str = "es") -> str:
        conv = Conversation(id=thread_id, channel=channel, contact=thread_id, language=language)
        out = self.graph.invoke({"conversation": conv.model_dump(mode="json"), "message": ""}, self._config(thread_id))
        return out["reply"]

    def handle(self, thread_id: str, message: str, today: date | None = None) -> str:
        """Process one candidate message and return the reply."""
        if self.conversation(thread_id) is None:  # first contact without an opening (e.g. inbound WhatsApp)
            return self.start(thread_id)
        state: State = {"message": message}
        if today:
            state["today"] = today.isoformat()
        config = self._config(thread_id)
        out = self.graph.invoke(state, config)
        if "summarize" in self.graph.get_state(config).next:
            # Screening over: write the recruiter summary without making the candidate wait.
            worker = threading.Thread(target=self.graph.invoke, args=(None, config), daemon=True)
            worker.start()
            self._summaries[thread_id] = worker
        return out["reply"]

    def summary(self, thread_id: str, timeout: float = 30.0) -> str | None:
        """The recruiter summary, waiting for it if it's still being written."""
        if worker := self._summaries.pop(thread_id, None):
            worker.join(timeout)
        conv = self.conversation(thread_id)
        return conv.summary if conv else None

    # --- recruiter view ----------------------------------------------------------------

    def conversations(self) -> list[Conversation]:
        """Every saved conversation, most recently updated first."""
        saver = self.graph.checkpointer
        if isinstance(saver, SqliteSaver):  # one query instead of loading every checkpoint
            threads = [r[0] for r in saver.conn.execute("SELECT DISTINCT thread_id FROM checkpoints")]
        else:
            threads = list(dict.fromkeys(c.config["configurable"]["thread_id"] for c in saver.list(None)))
        convs = [c for t in threads if (c := self.conversation(t))]
        return sorted(convs, key=lambda c: c.messages[-1].at if c.messages else c.created_at, reverse=True)

    def override(self, thread_id: str, recruiter_note: str = "") -> Conversation:
        """A recruiter overrides a knockout (technical decision 12): the candidate moves to
        Needs review. The original reason stays on the record and in the transcript."""
        conv = self.conversation(thread_id)
        if conv is None or conv.status is not Status.DISQUALIFIED:
            raise ValueError(f"{thread_id} is not a disqualified conversation")
        conv.status = Status.NEEDS_REVIEW
        conv.flags.append("recruiter_override")
        conv.review_reasons.append(f"override_{conv.disqualify_reason}")
        note = f": {recruiter_note.strip()}" if recruiter_note.strip() else ""
        conv.messages.append(Message(role="system", text=f"Recruiter override of {conv.disqualify_reason}{note}"))
        # As if written by the last node, so the graph doesn't (re)run the summary.
        self.graph.update_state(self._config(thread_id), {"conversation": conv.model_dump(mode="json")}, as_node="summarize")
        return conv
