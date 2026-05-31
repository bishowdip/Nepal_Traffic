"""
Nepal vehicle plate classification service.

Nepal plate format: [District Code] [Series] [Letter] [Number]
  e.g. "Ba 2 Kha 4521"  →  Kathmandu, private car
       "Na Pra 3 Ga 0011" → Nepal Police
       "CD 82 1234"        → Diplomatic
"""
import re
from typing import Optional


# ── District code → city mapping ──────────────────────────────────────────────

_LETTERS = ["Ka", "Kha", "Ga", "Gha", "Cha", "Chha", "Ja", "Jha",
            "Ta", "Tha", "Da", "Dha", "Na", "Pa", "Pha", "Ba", "Ma",
            "Ya", "Ra", "La", "Wa", "Sa", "Ha"]

DISTRICT_MAP: dict[str, str] = {
    "Ba":  "Kathmandu",
    "Ko":  "Kathmandu",       # old Kathmandu
    "Me":  "Kathmandu Metro",
    "La":  "Lalitpur",
    "Bha": "Bhaktapur",
    "Ka":  "Pokhara",
    "Ga":  "Gandaki",
    "Ra":  "Rupandehi",
    "Chi": "Bharatpur",
    "Su":  "Sunsari",
    "Mo":  "Biratnagar",
    "Pa":  "Birgunj",
    "Dha": "Janakpur",
    "Ru":  "Rupandehi",
    "Sy":  "Syangja",
    "Ta":  "Tanahun",
    "Pal": "Palpa",
    "Ar":  "Arghakhanchi",
    "Gu":  "Gulmi",
    "Dang": "Dang",
    "Sur": "Surkhet",
    "Kav": "Kavrepalanchok",
    "Sin": "Sindhupalchok",
    "Dol": "Dolakha",
    "Ram": "Ramechhap",
    "Mak": "Makwanpur",
    "Sar": "Sarlahi",
    "Mah": "Mahottari",
    "Dha2": "Dhanusha",
    "Sir": "Siraha",
    "Udh": "Udayapur",
    "Kho": "Khotang",
    "Bho": "Bhojpur",
    "Ter": "Terhathum",
    "San": "Sankhuwasabha",
    "Sol": "Solukhumbu",
    "Oka": "Okhaldhunga",
    "Ach": "Achham",
    "Baj": "Bajhang",
    "Bai": "Bajura",
    "Hum": "Humla",
    "Jum": "Jumla",
    "Mug": "Mugu",
    "Kali": "Kalikot",
    "Dail": "Dailekh",
    "Jaj": "Jajarkot",
    "Ruk": "Rukum",
    "Rol": "Rolpa",
    "Pyu": "Pyuthan",
    "Sal": "Salyan",
    "Bans": "Banke",
    "Bar": "Bardiya",
    "Kail": "Kailali",
    "Kan": "Kanchanpur",
}

# ── Special ownership prefixes ────────────────────────────────────────────────

OWNERSHIP_PREFIXES: list[tuple[list[str], str]] = [
    (["Na Pra", "NaPra", "NAPRA"],          "police"),
    (["Na Se", "NaSe", "NASE"],             "army"),
    (["Sa Pra", "SaPra", "SAPRA"],          "armed_police"),
    (["Na Ra Sa", "NaRaSa", "NARASA"],      "government"),
    (["Yo Pra", "YoPra", "YOPRA"],          "government"),
    (["CD"],                                "diplomatic"),
    (["UN"],                                "un"),
    (["INGO", "NGO"],                       "ngo"),
]

# YOLO class → vehicle type override rules
_YOLO_TYPE_MAP = {
    "car":        "car",
    "motorcycle": "motorcycle",
    "bus":        "bus",
    "truck":      "truck",
    "van":        "van",
    "bicycle":    "other",
    "rickshaw":   "other",
    "tractor":    "tractor",
    "microbus":   "microbus",
}


def _normalize_plate(text: str) -> str:
    """Strip extra whitespace; uppercase leading code."""
    return re.sub(r"\s+", " ", text.strip())


def _extract_district_code(plate: str) -> Optional[str]:
    """Try to match longest known district prefix first."""
    plate_upper = plate.upper()
    # Sort by length descending so "Bha" matches before "Ba"
    for code in sorted(DISTRICT_MAP.keys(), key=len, reverse=True):
        if plate_upper.startswith(code.upper()):
            return code
    return None


def _detect_ownership(plate: str) -> Optional[str]:
    """Return ownership category if plate starts with a special prefix."""
    plate_upper = plate.upper().replace(" ", "")
    for variants, category in OWNERSHIP_PREFIXES:
        for v in variants:
            if plate_upper.startswith(v.upper().replace(" ", "")):
                return category
    return None


def classify(
    plate_text: str,
    yolo_class: str = "car",
    plate_color: str = "white",
) -> dict:
    """
    Classify a Nepal vehicle based on plate text, YOLO class, and plate color.

    Returns:
        {
            vehicle_type: str,
            ownership_category: str,
            district_code: str | None,
            district_city: str | None,
        }
    """
    normalized = _normalize_plate(plate_text)

    # 1. Check special ownership prefixes
    ownership = _detect_ownership(normalized)

    # 2. Determine vehicle type from YOLO + plate color
    vehicle_type = _YOLO_TYPE_MAP.get(yolo_class.lower(), "other")

    # Plate color overrides for public/electric
    if plate_color.lower() == "yellow":
        if vehicle_type in ("bus", "microbus", "van"):
            ownership = ownership or "public"
        elif vehicle_type == "car":
            ownership = ownership or "public"  # taxi
    elif plate_color.lower() == "green":
        pass  # electric — keep ownership from prefix or private

    # 3. Bus ownership based on plate color
    if vehicle_type == "bus":
        if plate_color.lower() == "yellow":
            ownership = ownership or "public"
        else:
            ownership = ownership or "private"

    # 4. Extract district code
    district_code = _extract_district_code(normalized)
    district_city = DISTRICT_MAP.get(district_code) if district_code else None

    # 5. Fall back to private if no special ownership found
    ownership = ownership or "private"

    return {
        "vehicle_type": vehicle_type,
        "ownership_category": ownership,
        "district_code": district_code,
        "district_city": district_city,
    }


def normalize_plate_text(text: str) -> str:
    """
    Normalize plate text: handle no-space variants, fix common OCR errors.
    e.g. "Ba2Kha4521" → "Ba 2 Kha 4521"
    """
    text = text.strip()
    # Insert space between letters and digits
    text = re.sub(r"([A-Za-z])(\d)", r"\1 \2", text)
    text = re.sub(r"(\d)([A-Za-z])", r"\1 \2", text)
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text)
    return text.strip()
