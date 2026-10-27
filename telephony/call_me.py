"""Llama a un número desde Zadarma; la llamada vive en una sala de LiveKit.

Uso:
    python telephony/call_me.py                          # llama a MY_PHONE_NUMBER
    python telephony/call_me.py --to +34611222333        # llama a otro número
    python telephony/call_me.py --to 4444                # test de eco gratuito de Zadarma
    python telephony/call_me.py --agent zadarma-agent    # además despacha el agente
    python telephony/call_me.py --record                 # graba el audio de la llamada
    python telephony/call_me.py --caller-id auto         # número de salida libre al azar
    python telephony/call_me.py --listen                 # espera a que entres desde el navegador

Para colgar: Ctrl+C aquí, colgar desde el teléfono, o python telephony/hangup.py
"""

import argparse
import asyncio
import os
import sys

from calls import CallError, hang_up, is_active, room_name_for, start_call, wait_for_listener
from join_token import WS_URL, browser_token


async def main(
    to: str,
    room: str,
    agent: str | None = None,
    listen: bool = False,
    record: bool = False,
    caller_id: str | None = None,
) -> None:
    print(f"Sala: {room}")
    print("Para escucharla, entra en https://meet.livekit.io (pestaña Custom) con:")
    print(f"  Servidor: {WS_URL}")
    print(f"  Token:    {browser_token(room)}\n")

    if listen:
        print("Esperando a que entres en la sala desde el navegador...")
        await wait_for_listener(room)
        print("Conectado.")

    print(f"Llamando a {to}" + (f" con el agente '{agent}'" if agent else "") + "...")
    try:
        call = await start_call(to, agent=agent, room=room, record=record, caller_id=caller_id)
    except CallError as e:
        sys.exit(f"La llamada falló: {e}")
    except OSError:
        sys.exit(f"No se puede conectar con LiveKit en {WS_URL}. ¿Está levantado docker compose?")

    print(f"Llamada contestada. Participante: {call.participant_identity}")
    print("Pulsa Ctrl+C para colgar (o cuelga desde el teléfono).")
    while await is_active(call):
        await asyncio.sleep(2)
    await hang_up(room)
    print("El teléfono ha colgado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--to", default=os.getenv("MY_PHONE_NUMBER"), help="número de destino")
    parser.add_argument("--agent", default=os.getenv("AGENT_NAME") or None, help="agente a despachar")
    parser.add_argument("--listen", action="store_true", help="no marcar hasta que entres desde el navegador")
    parser.add_argument("--caller-id", help="número de salida, o 'auto' para uno libre al azar")
    parser.add_argument("--record", action="store_true", help="grabar el audio de la llamada")
    args = parser.parse_args()
    if not args.to:
        sys.exit("Indica --to o define MY_PHONE_NUMBER en .env")
    room = room_name_for(args.to)
    try:
        asyncio.run(main(args.to, room, args.agent, args.listen, args.record, args.caller_id))
    except KeyboardInterrupt:
        asyncio.run(hang_up(room))
        print("\nLlamada colgada.")
