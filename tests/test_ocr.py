"""
tests/test_ocr.py
Tests for OCR text parsing (mock mode).
"""
import pytest
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MOCK_MODE", "true")

from backend.services.ocr import _parse_route_cities, _match_city, CITY_MAP


# ── _match_city ───────────────────────────────────────────────────────────────

def test_match_city_devanagari_kathmandu():
    assert _match_city("काठमाडौं") == "Kathmandu"

def test_match_city_devanagari_pokhara():
    assert _match_city("पोखरा") == "Pokhara"

def test_match_city_roman_butwal():
    assert _match_city("Butwal") == "Butwal"

def test_match_city_roman_case_insensitive():
    assert _match_city("butwal") == "Butwal"

def test_match_city_no_match():
    assert _match_city("XYZ Unknown") == ""

def test_match_city_embedded_devanagari():
    assert _match_city("Route: काठमाडौं Express") == "Kathmandu"


# ── _parse_route_cities ───────────────────────────────────────────────────────

def test_parse_route_kathmandu_butwal():
    origin, dest = _parse_route_cities("काठमाडौं–बुटवल")
    assert origin == "Kathmandu"
    assert dest   == "Butwal"

def test_parse_route_dash_separator():
    origin, dest = _parse_route_cities("Pokhara-Kathmandu")
    assert origin == "Pokhara"
    assert dest   == "Kathmandu"

def test_parse_route_slash_separator():
    origin, dest = _parse_route_cities("Birgunj/Kathmandu")
    assert origin == "Birgunj"
    assert dest   == "Kathmandu"

def test_parse_route_single_city():
    origin, dest = _parse_route_cities("Pokhara")
    assert origin == "Pokhara"
    assert dest   == ""

def test_parse_route_empty():
    origin, dest = _parse_route_cities("")
    assert origin == ""
    assert dest   == ""

def test_parse_route_arrow_separator():
    origin, dest = _parse_route_cities("Dharan→Kathmandu")
    # arrow may not be in separator set but should still find first city
    assert origin == "Dharan"


# ── CITY_MAP coverage ─────────────────────────────────────────────────────────

def test_city_map_has_major_cities():
    dev_cities = list(CITY_MAP.keys())
    roman_cities = list(CITY_MAP.values())
    assert "Kathmandu" in roman_cities
    assert "Pokhara"   in roman_cities
    assert "Butwal"    in roman_cities
    assert "Birgunj"   in roman_cities

def test_city_map_devanagari_keys_are_unicode():
    for key in CITY_MAP.keys():
        assert any(0x0900 <= ord(c) <= 0x097F for c in key), \
            f"Key '{key}' doesn't appear to be Devanagari"
