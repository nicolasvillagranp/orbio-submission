"""Service-area decisions, with a fake geocoder so tests never call Nominatim."""

import httpx
import pytest

from src.geocoding import area_status, check_area
from src.locations import haversine_km, nearest

# Sol, Madrid restaurant is at 40.4168, -3.7038. One degree of latitude is ~111 km.
SOL = (40.4168, -3.7038)


def place(name, lat, lon, importance=0.5):
    return {"name": name, "lat": lat, "lon": lon, "importance": importance}


def fake(*places):
    return lambda query: list(places)


def km_north_of_sol(km):
    return SOL[0] + km / 111.2, SOL[1]


@pytest.mark.parametrize("km,status", [(14, "in_area"), (15, "in_area"), (17, "review"), (20, "review"), (25, "out_of_area")])
def test_area_status_thresholds(km, status):
    assert area_status(km) == status


def test_haversine_matches_known_distance():
    # Madrid Sol -> Barcelona Eixample is ~505 km in a straight line
    assert 495 < haversine_km(*SOL, 41.3910, 2.1650) < 515


def test_nearest_restaurant():
    restaurant, km = nearest(*SOL)
    assert restaurant["id"] == "mad-sol" and km < 0.01


def test_place_near_a_restaurant_is_in_area():
    r = check_area("Lavapiés", fake(place("Lavapiés, Madrid", 40.4087, -3.7010)))
    assert r["status"] == "in_area"
    assert r["restaurant"] == "Sol, Madrid"


def test_far_place_is_out_of_area():
    r = check_area("Oviedo", fake(place("Oviedo, Asturias", 43.3619, -5.8494)))
    assert r["status"] == "out_of_area"


def test_ambiguous_only_when_decisions_differ():
    near, far = place("Guadalupe, Nuevo León", 25.6767, -100.2560, 0.5), place("Guadalupe, Zacatecas", 22.7470, -102.5180, 0.45)
    r = check_area("Guadalupe", fake(near, far))
    assert r["status"] == "ambiguous"
    assert r["options"] == ["Guadalupe, Nuevo León", "Guadalupe, Zacatecas"]


def test_same_decision_different_restaurants_is_not_ambiguous():
    # Both places are in area, near different Madrid restaurants: no need to ask.
    a, b = place("A", *km_north_of_sol(2), 0.5), place("B", 40.3100, -3.7300, 0.48)
    assert check_area("X", fake(a, b))["status"] == "in_area"


def test_unlikely_matches_are_ignored():
    # Second match is >0.1 below the top importance, so its different decision doesn't matter.
    near, far = place("Near", *km_north_of_sol(1), 0.6), place("Far", 22.7470, -102.5180, 0.3)
    assert check_area("X", fake(near, far))["status"] == "in_area"


def test_no_results_is_not_found():
    assert check_area("asdfgh", fake())["status"] == "not_found"


def test_empty_query_skips_lookup():
    def boom(_):
        raise AssertionError("should not call the geocoder")
    assert check_area("  ", boom)["status"] == "not_found"


def test_geocoder_error_is_unavailable():
    def down(_):
        raise httpx.ConnectError("no network")
    assert check_area("Madrid", down)["status"] == "unavailable"
