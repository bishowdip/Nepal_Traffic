"""
OCR service for Nepal license plates and Devanagari bus route text.

Engines (selected via settings.OCR_ENGINE / $OCR_ENGINE):
  • "easyocr" — real OCR via EasyOCR (reuses PyTorch + Apple MPS / CUDA).
  • "paddle"  — real OCR via PaddleOCR (optional, only if installed).
  • "mock"    — synthetic plates / routes (no models required).
  • ""        — auto: "mock" when MOCK_MODE is on, otherwise "easyocr".

Real OCR runs whenever a genuine image is supplied, independent of MOCK_MODE
(which only governs whether *detections* are synthetic). If the chosen engine
fails to load, the service degrades gracefully to mock output.
"""
import logging
import os
import re
from typing import Optional
import numpy as np

from backend.config import settings
from backend.services.classifier import normalize_plate_text

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


# ── Engine selection ──────────────────────────────────────────────────────────

def _resolve_engine() -> str:
    """Resolve the active OCR engine, honouring $OCR_ENGINE then settings."""
    engine = (os.getenv("OCR_ENGINE") or settings.OCR_ENGINE or "").strip().lower()
    if engine in ("easyocr", "paddle", "mock"):
        return engine
    return "mock" if settings.MOCK_MODE else "easyocr"


# ── EasyOCR backend ───────────────────────────────────────────────────────────

_easyocr_plate = None
_easyocr_route = None
_easyocr_failed = False


def _get_easyocr(langs: list[str]):
    """Build an EasyOCR reader for the given languages (raises on failure)."""
    import easyocr
    return easyocr.Reader(langs, gpu=settings.OCR_GPU)


def _get_easyocr_plate():
    global _easyocr_plate, _easyocr_failed
    if _easyocr_plate is None and not _easyocr_failed:
        try:
            langs = settings.ocr_plate_lang_list
            _easyocr_plate = _get_easyocr(langs)
            logger.info(f"EasyOCR plate reader loaded (langs={langs}, gpu={settings.OCR_GPU}).")
        except Exception as e:
            logger.warning(f"EasyOCR plate init failed: {e}. Falling back to mock plates.")
            _easyocr_failed = True
    return _easyocr_plate


def _get_easyocr_route():
    global _easyocr_route, _easyocr_failed
    if _easyocr_route is None and not _easyocr_failed:
        try:
            langs = settings.ocr_route_lang_list
            _easyocr_route = _get_easyocr(langs)
            logger.info(f"EasyOCR route reader loaded (langs={langs}, gpu={settings.OCR_GPU}).")
        except Exception as e:
            logger.warning(f"EasyOCR route init failed: {e}. Falling back to mock routes.")
            _easyocr_failed = True
    return _easyocr_route


# ── PaddleOCR backend (optional) ──────────────────────────────────────────────

_paddle_en = None
_paddle_dev = None


def _get_paddle(lang: str):
    global _paddle_en, _paddle_dev
    cache = "_paddle_en" if lang == "en" else "_paddle_dev"
    reader = globals()[cache]
    if reader is None:
        try:
            from paddleocr import PaddleOCR
            reader = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
            globals()[cache] = reader
        except Exception as e:
            logger.warning(f"PaddleOCR ({lang}) init failed: {e}")
    return reader


# ── Plate image preprocessing ─────────────────────────────────────────────────

def _preprocess_plate(image: np.ndarray) -> np.ndarray:
    """
    Boost a (usually small) plate crop for OCR: upscale, grayscale, CLAHE.
    Returns a single-channel image; falls back to the original on any error.
    """
    try:
        import cv2
    except Exception:
        return image
    if image is None or image.size == 0:
        return image

    img = image
    h, w = img.shape[:2]
    longest = max(h, w)
    # Upscale small crops so glyphs are tall enough for the recognizer.
    if longest < 400:
        scale = min(4.0, 400.0 / max(longest, 1))
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
    except Exception:
        pass
    return gray


def _clean_token(text: str) -> str:
    """Uppercase and strip stray punctuation from a recognized plate token."""
    return re.sub(r"[^A-Za-z0-9]", "", text).upper()


# ── Public API ────────────────────────────────────────────────────────────────

def parse_plate(image: np.ndarray) -> dict:
    """
    Run OCR on a plate image.
    Returns: { text: str, confidence: float, bounding_box: list }
    """
    engine = _resolve_engine()
    if engine == "mock" or image is None:
        return _mock_plate()

    if engine == "easyocr":
        return _parse_plate_easyocr(image)
    if engine == "paddle":
        return _parse_plate_paddle(image)
    return _mock_plate()


def _parse_plate_easyocr(image: np.ndarray) -> dict:
    reader = _get_easyocr_plate()
    if reader is None:
        return _mock_plate()
    empty = {"text": "", "confidence": 0.0, "bounding_box": []}
    try:
        proc = _preprocess_plate(image)
        results = reader.readtext(proc, detail=1, paragraph=False)
        # results: list of (bbox, text, conf)
        toks = []
        for bbox, text, conf in results:
            cleaned = _clean_token(text)
            if cleaned and float(conf) >= settings.OCR_MIN_CONF:
                # left edge x of the token box, for reading order
                left_x = min(p[0] for p in bbox)
                toks.append((left_x, cleaned, float(conf), bbox))
        if not toks:
            return empty
        toks.sort(key=lambda t: t[0])  # left → right
        raw_text = " ".join(t[1] for t in toks)
        text = normalize_plate_text(raw_text)
        conf = round(sum(t[2] for t in toks) / len(toks), 3)
        return {"text": text, "confidence": conf, "bounding_box": toks[0][3]}
    except Exception as e:
        logger.error(f"EasyOCR plate error: {e}")
        return empty


def _parse_plate_paddle(image: np.ndarray) -> dict:
    ocr = _get_paddle("en")
    if ocr is None:
        return _mock_plate()
    try:
        result = ocr.ocr(image, cls=True)
        if not result or not result[0]:
            return {"text": "", "confidence": 0.0, "bounding_box": []}
        best = max(result[0], key=lambda r: r[1][1] if r and r[1] else 0)
        return {"text": best[1][0], "confidence": float(best[1][1]), "bounding_box": best[0]}
    except Exception as e:
        logger.error(f"Paddle plate OCR error: {e}")
        return {"text": "", "confidence": 0.0, "bounding_box": []}


def parse_route_text(image: np.ndarray) -> dict:
    """
    Run Devanagari OCR on the front panel of a bus.
    Returns: { raw_text: str, origin: str, destination: str }
    """
    engine = _resolve_engine()
    if engine == "mock" or image is None:
        return _mock_route()

    empty = {"raw_text": "", "origin": "", "destination": ""}
    try:
        if engine == "easyocr":
            reader = _get_easyocr_route()
            if reader is None:
                return _mock_route()
            results = reader.readtext(_preprocess_plate(image), detail=1, paragraph=False)
            lines = [text for _, text, conf in results if float(conf) >= settings.OCR_MIN_CONF]
        elif engine == "paddle":
            ocr = _get_paddle("en")
            if ocr is None:
                return _mock_route()
            result = ocr.ocr(image, cls=True)
            if not result or not result[0]:
                return empty
            lines = [r[1][0] for r in result[0] if r and r[1]]
        else:
            return _mock_route()

        raw_text = " ".join(lines)
        origin, destination = _parse_route_cities(raw_text)
        return {"raw_text": raw_text, "origin": origin, "destination": destination}
    except Exception as e:
        logger.error(f"Route OCR error: {e}")
        return empty


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
