"""Grupo Sazón's 45 restaurants (data/restaurants.json), which define the service area.

The client is fictional: these are invented locations spread over the 10 largest metro
areas of Spain and Mexico. Coordinates are approximate neighbourhood centres.
"""

from __future__ import annotations

import json
from math import asin, cos, radians, sin, sqrt

from .config import DATA_DIR

RESTAURANTS: list[dict] = json.loads((DATA_DIR / "restaurants.json").read_text(encoding="utf-8"))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km. Straight line, not driving distance."""
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))


def nearest(lat: float, lon: float) -> tuple[dict, float]:
    """The closest restaurant and its distance in km."""
    best = min(RESTAURANTS, key=lambda r: haversine_km(lat, lon, r["lat"], r["lon"]))
    return best, haversine_km(lat, lon, best["lat"], best["lon"])
