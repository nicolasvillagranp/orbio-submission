"""Dates in words. The agent is told today's date every turn, Claude writes the
candidate's start date as YYYY-MM-DD, rules.py validates it, and the agent reads it
back with the weekday computed here so the candidate can catch any mistake."""

from __future__ import annotations

from datetime import date

WEEKDAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MONTHS_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def spoken(d: date, language: str = "es") -> str:
    """'lunes 19 de octubre' / 'Monday, October 19'."""
    if language == "en":
        return f"{d:%A, %B} {d.day}"
    return f"{WEEKDAYS_ES[d.weekday()]} {d.day} de {MONTHS_ES[d.month - 1]}"


def today_line(today: date) -> str:
    """Told to the agent every turn: 'Hoy es domingo 18 de octubre de 2026 (2026-10-18).'"""
    return f"Hoy es {spoken(today)} de {today.year} ({today.isoformat()})."
