"""WhatsApp channel: the Twilio webhook, plus the first outbound message to new candidates.

Each candidate message is one POST; the reply goes back as TwiML in the same response.
Only the opening is sent through Twilio's API, since the candidate hasn't written yet.

    python -m app.whatsapp              # serves http://localhost:8000/whatsapp
    ngrok http 8000                     # then set https://<tunnel>/whatsapp as "When a
                                        # message comes in" in the Twilio sandbox
    python -m app.whatsapp send         # message everyone in data/candidates.json not yet contacted

The conversation is keyed by the candidate's number ("whatsapp:+34..."), so a candidate who
replies hours later, or applies twice, continues the same conversation.
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
from collections import defaultdict

from flask import Flask, Response, abort, request
from twilio.base.exceptions import TwilioRestException
from twilio.request_validator import RequestValidator
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

from src.config import DATA_DIR, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WEBHOOK_URL, TWILIO_WHATSAPP_FROM
from src.models import Channel
from src.pipeline import Screening
from src.prompts import OPENING, TEXT_ONLY

CANDIDATES = DATA_DIR / "candidates.json"  # [{"phone": "+34...", "language": "es"}], not in git

log = logging.getLogger("whatsapp")

app = Flask(__name__)
screening = Screening()
validator = RequestValidator(TWILIO_AUTH_TOKEN) if TWILIO_AUTH_TOKEN else None
# Two quick messages from the same candidate are processed one after the other, never at once.
locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)


def from_twilio() -> bool:
    if validator is None:
        log.warning("TWILIO_AUTH_TOKEN not set: accepting unsigned requests (local testing only)")
        return True
    # Behind a tunnel Flask sees http://localhost; Twilio signed the public https URL.
    url = TWILIO_WEBHOOK_URL or request.url.replace("http://", "https://", 1)
    return validator.validate(url, request.form, request.headers.get("X-Twilio-Signature", ""))


@app.post("/whatsapp")
def whatsapp() -> Response:
    if not from_twilio():
        abort(403)
    sender = request.form.get("From", "")
    text = request.form.get("Body", "").strip()

    with locks[sender]:
        if screening.conversation(sender) is None:
            reply = screening.start(sender, Channel.WHATSAPP)  # first contact: the opening message
        elif not text:  # voice note, image or sticker
            reply = TEXT_ONLY[screening.conversation(sender).language]
        else:
            reply = screening.handle(sender, text)

    twiml = MessagingResponse()
    twiml.message(reply)
    return Response(str(twiml), mimetype="text/xml")  # Twilio rejects application/xml here (error 12300)


def send_openings() -> None:
    """Send the opening to every candidate in data/candidates.json who hasn't been contacted.

    Outside WhatsApp's 24h window a business-initiated message must be a Meta-approved
    template; the sandbox only delivers to numbers that joined it.
    """
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    for candidate in json.loads(CANDIDATES.read_text(encoding="utf-8")):
        to = f"whatsapp:{candidate['phone']}"
        if screening.conversation(to) is not None:
            print(f"{candidate['phone']}: already contacted, skipped")
            continue
        language = candidate.get("language", "es")
        try:
            msg = client.messages.create(from_=TWILIO_WHATSAPP_FROM, to=to, body=OPENING[language])
        except TwilioRestException as exc:
            print(f"{candidate['phone']}: not sent ({exc.msg})")
            continue
        # Only record the conversation once Twilio accepted the message, so a failed send is retried next run.
        screening.start(to, Channel.WHATSAPP, language)
        print(f"{candidate['phone']}: opening sent ({msg.sid}, {msg.status})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", choices=["serve", "send"], default="serve")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    if args.command == "send":
        send_openings()
    else:
        app.run(port=8000)
