"""Genera un token para entrar en una sala desde el navegador y oír la llamada.

Uso:
    python telephony/join_token.py --room call-34600111222-1700000000
Pega servidor y token en https://meet.livekit.io -> pestaña "Custom".
"""

import argparse
from datetime import timedelta

from livekit import api

from config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL, ROOM

WS_URL = LIVEKIT_URL.replace("https://", "wss://").replace("http://", "ws://")


def browser_token(room: str) -> str:
    return (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity("yo-navegador")
        .with_name("Yo (navegador)")
        .with_ttl(timedelta(hours=24))
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .to_jwt()
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--room", default=ROOM, help="sala a la que unirse")
    room = parser.parse_args().room
    print(f"Servidor: {WS_URL}")
    print(f"Sala:     {room}")
    print(f"Token:    {browser_token(room)}")
