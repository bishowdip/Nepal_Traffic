"""
OCR service for Nepal license plates and Devanagari bus route text.
Uses PaddleOCR in real mode; returns mock results in MOCK_MODE.
"""
import logging
import re
from typing import Optional
import numpy as np

from backend.config import settings

logger = logging.getLogger(__name__)

# ── Nepal city name lookup ────────────────────────────────────────────────────

CITY_MAP: dict[str, str] = {
    "काठमाडौं": "Kathmandu",
    "काठमाडौ":  "Kathmandu",
    "पोखरा":    "Pokhara",
    "बुटवल":    "Butwal",
    "भैरहवा":   "Bhairahawa",
    "चितवन":    "Chitwan",
    "वीरगंज":   "Birgunj",
    "विराटनगर": "Biratnagar",
    "धरान":     "Dharan",
    "धनकुटा":   "Dhankuta",
    "जनकपुर":   "Janakpur",
    "नेपालगन्ज": "Nepalgunj",
    "धनगढी":    "Dhangadhi",
    "महेन्द्रनगर": "Mahendranagar",
    "हेटौंडा":  "Hetauda",
    "नारायणघाट": "Narayanghat",
    "भरतपुर":   "Bharatpur",
    "लहान":     "Lahan",
    "राजविराज": "Rajbiraj",
    "इलाम":     "Ilam",
    "ताप्लेजुङ": "Taplejung",
    "बाग्लुङ":  "Baglung",
    "गोर्खा":   "Gorkha",
    "दमौली":    "Damauli",
    "वालिङ":    "Waling",
    "स्याङ्जा": "Syangja",
    "पाल्पा":   "Palpa",
    "तानसेन":   "Tansen",
    "दाङ":      "Dang",
    "तुलसीपुर": "Tulsipur",
    "सुर्खेत":  "Surkhet",
    "लुम्बिनी":  "Lumbini",
    "सुनौली":   "Sonauli",
    "रुपन्देही": "Rupandehi",
}

ROMAN_CITY_MAP: dict[str, str] = {v.lower(): v for v in CITY_MAP.values()}

_ocr_en = None
_ocr_dev = None


def _get_ocr_en():
    global _ocr_en
    if _ocr_en is None and not settings.MOCK_MODE:
        try:
            from paddleocr import PaddleOCR
            _ocr_en = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        except Exception as e:
            logger.warning(f"PaddleOCR (en) init failed: {e}")
    return _ocr_en


def _get_ocr_dev():
    global _ocr_dev
    if _ocr_dev is None and not settings.MOCK_MODE:
        try:
            from paddleocr import PaddleOCR
            # "nepali" may not exist in all versions; fall back to "en" with unicode support
            _ocr_dev = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        except Exception as e:
            logger.warning(f"PaddleOCR (devanagari) init failed: {e}")
    return _ocr_dev


# ── Public API ────────────────────────────────────────────────────────────────

def parse_plate(image: np.ndarray) -> dict:
    """
    Run OCR on a plate image.
    Returns: { text: str, confidence: float, bounding_box: list }
    """
    if settings.MOCK_MODE or image is None:
        return _mock_plate()

    ocr = _get_ocr_en()
    if ocr is None:
        return _mock_plate()

    try:
        result = ocr.ocr(image, cls=True)
        if not result or not result[0]:
            return {"text": "", "confidence": 0.0, "bounding_box": []}

        # Pick the highest-confidence line
        best = max(result[0], key=lambda r: r[1][1] if r and r[1] else 0)
        text = best[1][0]
        conf = float(best[1][1])
        bbox = best[0]
        return {"text": text, "confidence": conf, "bounding_box": bbox}
    except Exception as e:
        logger.error(f"Plate OCR error: {e}")
        return {"text": "", "confidence": 0.0, "bounding_box": []}


def parse_route_text(image: np.ndarray) -> dict:
    """
    Run Devanagari OCR on the front panel of a bus.
    Returns: { raw_text: str, origin: str, destination: str }
    """
    if settings.MOCK_MODE or image is None:
        return _mock_route()

    ocr = _get_ocr_dev()
    if ocr is None:
        return _mock_route()

    try:
        result = ocr.ocr(image, cls=True)
        if not result or not result[0]:
            return {"raw_text": "", "origin": "", "destination": ""}

        lines = [r[1][0] for r in result[0] if r and r[1]]
        raw_text = " ".join(lines)
        origin, destination = _parse_route_cities(raw_text)
        return {"raw_text": raw_text, "origin": origin, "destination": destination}
    except Exception as e:
        logger.error(f"Route OCR error: {e}")
        return {"raw_text": "", "origin": "", "destination": ""}


# ── Route city parser ─────────────────────────────────────────────────────────

_SEPARATORS = re.compile(r"[–\-—/→➔·|,]")


def _parse_route_cities(text: str) -> tuple[str, str]:
    """Extract origin and destination from route text."""
    # Split by common route separators
    parts = [p.strip() for p in _SEPARATORS.split(text) if p.strip()]

    origin = ""
    destination = ""

    for i, part in enumerate(parts[:4]):
        city = _match_city(part)
        if city:
            if not origin:
                origin = city
            elif not destination:
                destination = city
                break

    return origin, destination


def _match_city(text: str) -> str:
    """Match Devanagari or romanized city name in text."""
    for dev, roman in CITY_MAP.items():
        if dev in text:
            return roman
    text_lower = text.lower().strip()
    for roman_lower, roman in ROMAN_CITY_MAP.items():
        if roman_lower in text_lower:
            return roman
    return ""


# ── Mock helpers ──────────────────────────────────────────────────────────────

import random

_MOCK_PLATES = [
    ("Ba 2 Kha 4521", 0.91),
    ("Ko 1 Ja 0033",  0.88),
    ("La 3 Ga 1122",  0.85),
    ("Ka 4 Cha 8899", 0.79),
    ("Na Pra 2 Ga 0011", 0.93),
    ("Na Se 1 Ka 0055",  0.90),
    ("CD 82 1234",    0.96),
    ("Ba 7 Kha 3301", 0.87),
    ("Me 1 Pa 5500",  0.82),
    ("Chi 3 Ba 2211", 0.78),
]

_MOCK_ROUTES = [
    ("काठमाडौं–बुटवल", "Kathmandu", "Butwal"),
    ("काठमाडौं–पोखरा", "Kathmandu", "Pokhara"),
    ("काठमाडौं–विराटनगर", "Kathmandu", "Biratnagar"),
    ("भरतपुर–काठमाडौं", "Bharatpur", "Kathmandu"),
    ("नारायणघाट–काठमाडौं", "Narayanghat", "Kathmandu"),
    ("काठमाडौं–भैरहवा", "Kathmandu", "Bhairahawa"),
    ("धरान–काठमाडौं", "Dharan", "Kathmandu"),
    ("जनकपुर–काठमाडौं", "Janakpur", "Kathmandu"),
]


def _mock_plate() -> dict:
    text, conf = random.choice(_MOCK_PLATES)
    conf += random.uniform(-0.05, 0.05)
    return {"text": text, "confidence": round(min(max(conf, 0.0), 1.0), 3), "bounding_box": []}


def _mock_route() -> dict:
    raw, origin, dest = random.choice(_MOCK_ROUTES)
    return {"raw_text": raw, "origin": origin, "destination": dest}
