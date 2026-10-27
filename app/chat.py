"""Talk to the screening agent in the terminal.

    python -m app.chat                 # new conversation
    python -m app.chat --id demo-1     # resume (state is in data/conversations.db)
    python -m app.chat --debug         # also print the extracted data after each turn
"""

from __future__ import annotations

import argparse
import json
import logging
import uuid

from src.models import Status
from src.pipeline import Screening


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", default=None, help="conversation id to start or resume")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.debug else logging.WARNING, format="  · %(name)s: %(message)s")

    screening = Screening()
    thread_id = args.id or f"cli-{uuid.uuid4().hex[:6]}"
    if screening.conversation(thread_id) is None:
        print(f"[conversation {thread_id}]\nSofía: {screening.start(thread_id)}")
    else:
        print(f"[resuming {thread_id}]")

    while True:
        try:
            text = input("\nTú: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        print(f"\nSofía: {screening.handle(thread_id, text)}")
        conv = screening.conversation(thread_id)
        if args.debug:
            print(f"  [stage={conv.stage.value} status={conv.status.value}] {json.dumps(conv.data.as_flat_dict(), ensure_ascii=False, default=str)}")
        if conv.status is not Status.IN_PROGRESS:
            print(f"\n[{conv.status.value.upper()}] {screening.summary(thread_id)}")
            break


if __name__ == "__main__":
    main()
