from datetime import date

from src.dates import spoken, today_line


def test_spoken_spanish_and_english():
    d = date(2026, 10, 19)
    assert spoken(d) == "lunes 19 de octubre"
    assert spoken(d, "en") == "Monday, October 19"


def test_today_line():
    assert today_line(date(2026, 10, 18)) == "Hoy es domingo 18 de octubre de 2026 (2026-10-18)."
