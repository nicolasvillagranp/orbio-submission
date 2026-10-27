"""Loads config/config.yaml (business settings) and .env (secrets)."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"

load_dotenv(ROOT / ".env")

with open(CONFIG_DIR / "config.yaml", encoding="utf-8") as f:
    CONFIG: dict = yaml.safe_load(f)


def secret(*names: str) -> str | None:
    """First non-empty environment variable among `names`."""
    return next((v for n in names if (v := os.getenv(n))), None)


ANTHROPIC_API_KEY = secret("ANTHROPIC_API_KEY", "CLAUDE")
JEV_API_KEY = secret("TYPESAFE_API_KEY", "JEV")
NOMINATIM_CONTACT = secret("NOMINATIM_CONTACT")
TWILIO_ACCOUNT_SID = secret("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = secret("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = secret("TWILIO_WHATSAPP_FROM") or "whatsapp:+14155238886"  # Twilio sandbox
TWILIO_WEBHOOK_URL = secret("TWILIO_WEBHOOK_URL")  # public URL Twilio posts to, if the tunnel rewrites it
