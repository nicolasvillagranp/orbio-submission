"""Cuelga llamadas abiertas.

Uso:
    python telephony/hangup.py                                # cuelga todas
    python telephony/hangup.py --room call-34600111222-1700000000
"""

import argparse
import asyncio

from calls import hang_up

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--room", help="sala concreta a colgar (por defecto, todas)")
    rooms = asyncio.run(hang_up(parser.parse_args().room))
    print("\n".join(f"Colgada: {r}" for r in rooms) or "No había llamadas abiertas")
