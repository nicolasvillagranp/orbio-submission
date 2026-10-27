"""Voice channel: a thin LiveKit Agents adapter over the same screening graph as WhatsApp.

LiveKit does the audio: turn detection and interruptions. Speech-to-text is Deepgram and
text-to-speech is Cartesia, called directly with DEEPGRAM_API_KEY and CARTESIA_API_KEY, so
it runs against the self-hosted LiveKit server (LiveKit Inference only exists on LiveKit Cloud).
Each finished candidate turn goes to Screening.handle(); nothing here knows the screening rules.

    python -m voice.agent           # talk from the terminal with the laptop's microphone (= console)
    python -m voice.agent dev       # register as AGENT_NAME and wait for phone calls:
                                    #   python telephony/call_me.py --to +34... --agent zadarma-agent
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    AudioConfig,
    BackgroundAudioPlayer,
    BuiltinAudioClip,
    JobContext,
    cli,
    room_io,
)
from livekit.plugins import cartesia, deepgram, silero

from src.config import CONFIG
from src.models import Channel, Status
from src.pipeline import Screening
from src.prompts import ACKNOWLEDGEMENTS

VOICE = CONFIG["voice"]
AGENT_NAME = os.getenv("AGENT_NAME") or "zadarma-agent"  # what telephony/calls.py dispatches
screening = Screening()


class ScreeningAgent(Agent):
    """No LLM in the session: the screening graph writes every reply.

    LiveKit skips its reply step when no LLM is set, so each finished candidate turn is
    handled here, where the hook still runs, and the reply is spoken with say().
    """

    def __init__(self, thread_id: str):
        super().__init__(instructions="")
        self.thread_id = thread_id
        self.last_ack: str | None = None

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        language = screening.conversation(self.thread_id).language
        pending = asyncio.ensure_future(
            asyncio.to_thread(screening.handle, self.thread_id, new_message.text_content or ""))
        # Reply not ready almost at once: acknowledge first, so the candidate isn't left in silence.
        done, _ = await asyncio.wait({pending}, timeout=VOICE["ack_after"])
        if not done:
            self.session.say(self.acknowledgement(language), add_to_chat_ctx=False)
        reply = await pending
        conv = screening.conversation(self.thread_id)
        # The graph replies in the language of the candidate's latest message: speak it in that language.
        self.session.tts.update_options(language=conv.language)
        try:
            self.session.say(reply)  # queued: plays right after the acknowledgement
        except RuntimeError:  # the candidate hung up while the graph was answering
            return
        if conv.status is not Status.IN_PROGRESS:  # finished, disqualified, declined or they said goodbye
            # Hang up once the goodbye has been spoken: closing the session deletes the room
            # (delete_room_on_close), which drops the phone leg so the call stops costing.
            self.session.shutdown(drain=True)

    def acknowledgement(self, language: str) -> str:
        """A short filler, never the same one twice in a row."""
        self.last_ack = random.choice([a for a in ACKNOWLEDGEMENTS[language] if a != self.last_ack])
        return self.last_ack


async def wait_until_answered(room: rtc.Room, participant: rtc.RemoteParticipant) -> None:
    """The SIP participant joins the room when dialling starts, not when the phone is picked
    up: wait for `sip.callStatus` to reach "active" (dialing -> ringing -> active)."""
    answered = asyncio.Event()

    def check(*_) -> None:
        if participant.attributes.get("sip.callStatus") == "active":
            answered.set()

    room.on("participant_attributes_changed", check)
    check()
    try:
        await answered.wait()
    finally:
        room.off("participant_attributes_changed", check)


server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    # Phone calls (telephony/calls.py) carry the dialled number in the job metadata; it keys the
    # conversation, so the recruiter sees whom it was with. Console and playground sessions have
    # none and get one conversation per session (console reuses the same room name on every run).
    phone_number = json.loads(ctx.job.metadata or "{}").get("phone_number")
    thread_id = phone_number or f"voice-{ctx.job.id}"

    room_options = room_io.RoomOptions(delete_room_on_close=True)
    if phone_number:
        # Otherwise the opening (with the AI disclosure) would be spoken to a ringing phone.
        phone = await ctx.wait_for_participant(kind=rtc.ParticipantKind.PARTICIPANT_KIND_SIP)
        await wait_until_answered(ctx.room, phone)
        await asyncio.sleep(0.7)  # let the phone's audio path settle before speaking
        # Listen to the phone, not to someone listening in from the browser (call_me.py --listen).
        room_options = room_io.RoomOptions(participant_identity=phone.identity, delete_room_on_close=True)

    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),  # Spanish and English, switching mid-call
        # The opening is Spanish; on_user_turn_completed then follows the candidate's language.
        tts=cartesia.TTS(model="sonic-3", voice=VOICE["tts_voice"], language="es"),
        vad=silero.VAD.load(),
        turn_handling={"endpointing": {"min_delay": VOICE["min_delay"], "max_delay": VOICE["max_delay"]}},
    )
    await session.start(room=ctx.room, agent=ScreeningAgent(thread_id), room_options=room_options)

    # Typing sound while the graph works, so the pause doesn't read as a dropped call.
    thinking = BackgroundAudioPlayer(thinking_sound=AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.5))
    await thinking.start(room=ctx.room, agent_session=session)

    opening = await asyncio.to_thread(screening.start, thread_id, Channel.VOICE)
    session.say(opening, allow_interruptions=False)  # carries the AI disclosure: always heard in full


if __name__ == "__main__":
    if len(sys.argv) == 1:  # no command: just talk to it
        sys.argv.append("console")
    cli.run_app(server)
