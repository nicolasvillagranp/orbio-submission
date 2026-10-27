"""Elige qué número de Zadarma se usa como CallerID en cada llamada.

Candidatos: los números virtuales activos de la cuenta (API de Zadarma), o solo
los de ZADARMA_CALLER_IDS (lista separada por comas) si se define.
"Libre" = ninguna llamada abierta en LiveKit lo está usando: cada sala `call-*`
guarda en su metadata el `caller_id` con el que se marcó.

Uso:
    python telephony/number_pool.py     # muestra candidatos, ocupados y libres
"""

import asyncio
import json
import os
import random

from livekit import api

import zadarma_api


def _digits(number: str) -> str:
    return "".join(c for c in number if c.isdigit())


def candidates() -> list[str]:
    """Números activos que se pueden usar como CallerID (solo dígitos)."""
    allowed = {_digits(n) for n in os.getenv("ZADARMA_CALLER_IDS", "").split(",") if n.strip()}
    active = [_digits(n["number"]) for n in zadarma_api.numbers() if n.get("status") == "on"]
    return [n for n in active if not allowed or n in allowed]


async def in_use(lkapi: api.LiveKitAPI) -> set[str]:
    """CallerIDs de las llamadas que siguen abiertas."""
    resp = await lkapi.room.list_rooms(api.ListRoomsRequest())
    used = set()
    for room in resp.rooms:
        if not room.name.startswith("call-"):
            continue
        try:
            caller_id = json.loads(room.metadata or "{}").get("caller_id")
        except json.JSONDecodeError:
            continue
        if caller_id:
            used.add(_digits(caller_id))
    return used


async def pick(lkapi: api.LiveKitAPI) -> str:
    """Un número libre al azar. ZadarmaError si no hay candidatos o están todos ocupados."""
    pool = await asyncio.to_thread(candidates)
    if not pool:
        raise zadarma_api.ZadarmaError("No hay números activos que usar como CallerID")
    free = [n for n in pool if n not in await in_use(lkapi)]
    if not free:
        raise zadarma_api.ZadarmaError(f"Los {len(pool)} números están ocupados en otras llamadas")
    return random.choice(free)


async def _main() -> None:
    from config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL

    async with api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET) as lkapi:
        pool, used = await asyncio.to_thread(candidates), await in_use(lkapi)
    for n in pool:
        print(f"  {n}  {'OCUPADO' if n in used else 'libre'}")
    print("(ninguno)" if not pool else "")


if __name__ == "__main__":
    import sys

    try:
        asyncio.run(_main())
    except zadarma_api.ZadarmaError as e:
        sys.exit(f"Error: {e}")
