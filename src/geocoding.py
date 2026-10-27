"""Service-area check: find the candidate's place with Nominatim (OpenStreetMap),
measure the distance to the nearest restaurant, and decide in code.

Nominatim usage policy: max 1 request/second, identifying User-Agent, no bulk use.
https://operations.osmfoundation.org/policies/nominatim/  Data © OpenStreetMap contributors.
"""

from __future__ import annotations

import logging
import threading
import time

import httpx

from .config import CONFIG, NOMINATIM_CONTACT
from .locations import nearest

log = logging.getLogger("geocoding")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "fde-demo/0.1" + (f" ({NOMINATIM_CONTACT})" if NOMINATIM_CONTACT else "")
# Matches whose importance is within this many points of the best one count as likely.
IMPORTANCE_MARGIN = 0.1

_lock = threading.Lock()
_last_call = 0.0


def geocode(query: str) -> list[dict]:
    """Up to 3 matching places in Spain or Mexico: [{name, lat, lon, importance}]."""
    global _last_call
    with _lock:  # 1 request per second, as the usage policy requires
        wait = 1.0 - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = httpx.get(
                NOMINATIM_URL,
                params={"q": query, "format": "jsonv2", "countrycodes": "es,mx", "limit": 3, "accept-language": "es"},
                headers={"User-Agent": USER_AGENT},
                timeout=5.0,
            )
        finally:
            _last_call = time.monotonic()
    resp.raise_for_status()
    return [
        {"name": r["display_name"], "lat": float(r["lat"]), "lon": float(r["lon"]), "importance": float(r.get("importance") or 0)}
        for r in resp.json()
    ]


def area_status(distance_km: float) -> str:
    area = CONFIG["service_area"]
    if distance_km <= area["in_area_km"]:
        return "in_area"
    if distance_km <= area["review_km"]:
        return "review"
    return "out_of_area"


def check_area(query: str, search=geocode) -> dict:
    """Is the candidate's place inside the service area?

    status: in_area | review | out_of_area | ambiguous | not_found | unavailable.
    "ambiguous" only when likely places lead to different decisions;
    `options` then lists them so the agent can ask which one.
    """
    result = {"status": "not_found", "query": query, "place": None, "restaurant": None, "distance_km": None, "options": []}
    if not (query or "").strip():
        return result
    try:
        places = search(query)
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("geocode failed query=%r error=%s", query, exc)
        return {**result, "status": "unavailable"}
    if not places:
        log.info("geocode query=%r results=0", query)
        return result

    top = max(p["importance"] for p in places)
    likely = [p for p in places if p["importance"] >= top - IMPORTANCE_MARGIN]
    checked = []
    for p in likely:
        restaurant, km = nearest(p["lat"], p["lon"])
        checked.append((p, restaurant, km, area_status(km)))

    place, restaurant, km, status = checked[0]
    ambiguous = len({c[3] for c in checked}) > 1
    result.update(
        status="ambiguous" if ambiguous else status,
        place=place["name"],
        restaurant=f"{restaurant['name']}, {restaurant['city']}",
        distance_km=round(km, 1),
        options=[c[0]["name"] for c in checked] if ambiguous else [],
    )
    log.info("geocode query=%r place=%r nearest=%s km=%.1f status=%s", query, place["name"], restaurant["id"], km, result["status"])
    return result
