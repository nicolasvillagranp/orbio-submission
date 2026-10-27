"""Carga la configuración desde .env (raíz del repo)."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TRUNK_NAME = "zadarma-outbound"


def require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        sys.exit(f"Falta la variable {name} en .env (mira .env.example)")
    return value


LIVEKIT_URL = require("LIVEKIT_URL")
LIVEKIT_API_KEY = require("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = require("LIVEKIT_API_SECRET")
ROOM = os.getenv("LIVEKIT_ROOM", "prueba")
