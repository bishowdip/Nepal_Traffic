"""
tests/test_classifier.py
Tests for Nepal plate classification logic.
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.classifier import (
    classify, normalize_plate_text, _normalize_plate,
    _extract_district_code, _detect_ownership, DISTRICT_MAP
)


# ── normalize_plate_text ──────────────────────────────────────────────────────

def test_normalize_adds_spaces_between_letter_and_digit():
    assert normalize_plate_text("Ba2Kha4521") == "Ba 2 Kha 4521"

def test_normalize_collapses_extra_spaces():
    assert normalize_plate_text("Ba  2  Kha  4521") == "Ba 2 Kha 4521"

def test_normalize_strips_leading_trailing():
    assert normalize_plate_text("  Ba 2 Kha 4521  ") == "Ba 2 Kha 4521"

def test_normalize_no_change_when_already_spaced():
    assert normalize_plate_text("Ko 1 Ja 0033") == "Ko 1 Ja 0033"


# ── _extract_district_code ────────────────────────────────────────────────────

def test_district_code_ba():
    assert _extract_district_code("Ba 2 Kha 4521") == "Ba"

def test_district_code_ko():
    assert _extract_district_code("Ko 1 Ja 0033") == "Ko"

def test_district_code_bha_not_confused_with_ba():
    assert _extract_district_code("Bha 3 Ka 1234") == "Bha"

def test_district_code_unknown():
    assert _extract_district_code("ZZ 1 Ka 0001") is None

def test_district_code_case_insensitive():
    assert _extract_district_code("BA 2 KHA 4521") == "Ba"


# ── _detect_ownership ─────────────────────────────────────────────────────────

def test_ownership_police():
    assert _detect_ownership("Na Pra 2 Ga 0011") == "police"

def test_ownership_army():
    assert _detect_ownership("Na Se 1 Ka 0055") == "army"

def test_ownership_armed_police():
    assert _detect_ownership("Sa Pra 3 Ba 0099") == "armed_police"

def test_ownership_government():
    assert _detect_ownership("Na Ra Sa 4 Ka 0001") == "government"

def test_ownership_diplomatic():
    assert _detect_ownership("CD 82 1234") == "diplomatic"

def test_ownership_un():
    assert _detect_ownership("UN 12 5678") == "un"

def test_ownership_ngo():
    assert _detect_ownership("NGO Ba 1 Ka 0001") == "ngo"

def test_ownership_nospace_variant():
    assert _detect_ownership("NaPra2Ga0011") == "police"

def test_ownership_private_returns_none():
    assert _detect_ownership("Ba 2 Kha 4521") is None


# ── classify ──────────────────────────────────────────────────────────────────

def test_classify_private_car():
    result = classify("Ba 2 Kha 4521", "car", "white")
    assert result["vehicle_type"]        == "car"
    assert result["ownership_category"] == "private"
    assert result["district_code"]      == "Ba"
    assert result["district_city"]      == "Kathmandu"

def test_classify_public_bus_yellow():
    result = classify("La 3 Ga 1122", "bus", "yellow")
    assert result["vehicle_type"]        == "bus"
    assert result["ownership_category"] == "public"

def test_classify_police_plate():
    result = classify("Na Pra 2 Ga 0011", "car", "white")
    assert result["ownership_category"] == "police"

def test_classify_army_plate():
    result = classify("Na Se 1 Ka 0055", "car", "white")
    assert result["ownership_category"] == "army"

def test_classify_diplomatic():
    result = classify("CD 82 1234", "car", "white")
    assert result["ownership_category"] == "diplomatic"

def test_classify_unknown_district_returns_none():
    result = classify("ZZ 1 Ka 0001", "car", "white")
    assert result["district_code"] is None
    assert result["district_city"] is None

def test_classify_motorcycle():
    result = classify("Ko 1 Ja 0033", "motorcycle", "white")
    assert result["vehicle_type"] == "motorcycle"

def test_classify_district_map_contains_key_districts():
    for code in ["Ba", "Ko", "La", "Bha", "Ka"]:
        assert code in DISTRICT_MAP
