"""Call worker: python -m worker

Watches Supabase for calls recruiters request in the web app, places them one at a time with
telephony/calls.py and writes each screening's outcome back. Needs Docker (LiveKit + SIP) and the
voice agent running natively (python -m voice.agent dev), which shares data/conversations.db.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from src.config import ROOT  # loads .env
from src.pipeline import Screening, sqlite_checkpointer

from .db import Db
from .mapping import parse_allowlist
from .process import POLL, process_call, utcnow

sys.path.insert(0, str(ROOT / "telephony"))  # its modules import each other by bare name
import calls as telephony  # noqa: E402

log = logging.getLogger("worker")
AGENT_NAME = os.getenv("AGENT_NAME") or "zadarma-agent"


async def main() -> None:
    db = Db.from_env()
    screening = Screening(sqlite_checkpointer())
    allowlist = parse_allowlist(os.getenv("CALL_ALLOWLIST"), os.getenv("MY_PHONE_NUMBER"))
    log.info("allowed numbers: %d; agent: %s", len(allowlist), AGENT_NAME)

    # A crash mid-call leaves rows that nobody will ever finish.
    for row in db.select("calls", {"status": "in.(dialling,in_call)", "select": "id"}):
        db.update("calls", {"id": row["id"]}, {"status": "failed", "error": "worker restarted",
                                                "ended_at": utcnow().isoformat()})

    async def dial(phone):
        return await telephony.start_call(phone, agent=AGENT_NAME)

    async def hang_up(call):
        await telephony.hang_up(call.room)

    def finish_summary(phone):
        screening.graph.invoke(None, {"configurable": {"thread_id": phone}})

    log.info("waiting for call requests (Ctrl-C to stop)")
    while True:
        try:
            rows = db.select("calls", {"status": "eq.requested", "order": "created_at.asc", "limit": "1",
                                       "select": "*,candidate:candidates(*)"})
        except Exception as e:  # network blip: try again on the next tick
            log.warning("could not read call requests: %s", e)
            rows = []
        if rows:
            call = rows[0]
            candidate = call.pop("candidate")
            log.info("call %s → candidate %s", call["id"], candidate["id"])
            try:
                status = await process_call(
                    call, candidate, db=db, dial=dial, still_on=telephony.is_active, hang_up=hang_up,
                    read_conv=screening.conversation, finish_summary=finish_summary, allowlist=allowlist,
                )
            except Exception as e:  # never let one bad call stop the worker
                log.exception("call %s crashed", call["id"])
                status = "failed"
                try:
                    db.update("calls", {"id": call["id"]}, {"status": "failed", "error": str(e)[:500],
                                                            "ended_at": utcnow().isoformat()})
                except Exception:
                    pass
            log.info("call %s finished: %s", call["id"], status)
        else:
            await asyncio.sleep(POLL)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
