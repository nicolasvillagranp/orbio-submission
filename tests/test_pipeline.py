"""The decide step with fake Jev analyses, so tests never call an API."""

from src import pipeline
from src.models import Channel, Conversation, Message, Stage, Status


def run_decide(conv: Conversation, signals=None, confirms=None, text="..."):
    conv.messages.append(Message(role="candidate", text=text))
    analysis = {"fields": {}, "confirms": confirms or {}, "rejects": {}, "signals": {"language": "es", **(signals or {})}}
    out = pipeline.decide({"conversation": conv.model_dump(mode="json"), "analysis": analysis, "today": "2026-10-20"})
    return Conversation.model_validate(out["conversation"]), out["turn"]


def test_goodbye_mid_screening_pauses_at_the_stage_reached():
    conv, turn = run_decide(Conversation(stage=Stage.LOCATION), {"wants_to_leave": 0.95}, text="tengo que irme")
    assert conv.status is Status.ABANDONED and conv.stage is Stage.LOCATION
    assert "left_early" in conv.flags and "candidate_left" in turn["events"]


def test_unclear_goodbye_is_ignored():
    conv, _ = run_decide(Conversation(stage=Stage.LOCATION), {"wants_to_leave": 0.4})
    assert conv.status is Status.IN_PROGRESS


def test_writing_again_resumes_where_they_left():
    left, _ = run_decide(Conversation(stage=Stage.LOCATION), {"wants_to_leave": 0.95})
    conv, turn = run_decide(left, text="hola, sigo")
    assert conv.status is Status.IN_PROGRESS and conv.stage is Stage.LOCATION and "resumed" in turn["events"]


def test_confirming_the_recap_and_saying_goodbye_finishes_instead_of_abandoning():
    conv, _ = run_decide(Conversation(stage=Stage.CONFIRMATION), {"wants_to_leave": 0.95}, {"recap": 0.95},
                         text="sí, todo correcto, adiós")
    assert conv.status in (Status.QUALIFIED, Status.NEEDS_REVIEW)


def test_recruiter_override_moves_a_knockout_to_review_and_keeps_the_reason():
    from langgraph.checkpoint.memory import MemorySaver

    screening = pipeline.Screening(MemorySaver())
    out = Conversation(id="t1", status=Status.DISQUALIFIED, stage=Stage.DONE, disqualify_reason="out_of_area")
    screening.graph.update_state({"configurable": {"thread_id": "t1"}},
                                 {"conversation": out.model_dump(mode="json")}, as_node="summarize")

    conv = screening.override("t1", "vive a 21 km pero tiene coche")
    assert conv.status is Status.NEEDS_REVIEW and conv.disqualify_reason == "out_of_area"
    assert "recruiter_override" in conv.flags and "override_out_of_area" in conv.review_reasons
    assert screening.conversation("t1").status is Status.NEEDS_REVIEW  # saved
    assert [c.id for c in screening.conversations()] == ["t1"]


def test_abandoned_reply_says_goodbye_and_how_to_continue():
    whatsapp = Conversation(channel=Channel.WHATSAPP, status=Status.ABANDONED)
    voice = Conversation(channel=Channel.VOICE, status=Status.ABANDONED)
    assert "writing again" in pipeline.next_step(whatsapp, {})
    assert "another time" in pipeline.next_step(voice, {})
