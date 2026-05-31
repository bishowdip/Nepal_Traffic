"""
Mock Department of Transport Management (DoTM) registry.
Provides lookup by plate text with fuzzy normalization.
Seeded with 500 realistic Nepal vehicle records.
"""
import re
import random
from datetime import date, timedelta
from typing import Optional

from backend.models.schemas import DoTMRecord

# ── Seed data parameters ──────────────────────────────────────────────────────

_MAKES_MODELS = [
    ("Suzuki", ["Alto", "Swift", "Baleno", "Ertiga", "Jimny"]),
    ("Toyota", ["Hilux", "Land Cruiser", "Fortuner", "Corolla", "Hiace"]),
    ("Hyundai", ["i10", "i20", "Tucson", "Creta", "Accent"]),
    ("Honda", ["City", "Civic", "CRV", "Brio", "Jazz"]),
    ("Mahindra", ["Scorpio", "Bolero", "XUV300", "Thar", "TUV300"]),
    ("Tata", ["Nano", "Nexon", "Punch", "Harrier", "Safari"]),
    ("Bajaj", ["Pulsar", "Discover", "Platina", "CT100", "Dominar"]),
    ("Hero", ["Splendor", "Passion", "HF Deluxe", "Xtreme", "Glamour"]),
    ("Yamaha", ["FZS", "R15", "Ray-ZR", "FZ-S", "MT-15"]),
    ("Eicher", ["Pro 3015", "Pro 3018", "Skyline", "Starline"]),
    ("Ashok Leyland", ["Viking", "Lynx", "Falcon", "Partner"]),
    ("TATA Bus", ["Starbus", "Ultra", "Cityride", "LPO", "LP"]),
    ("Hino", ["FC", "FG", "SG", "AK", "FB"]),
    ("Swaraj Mazda", ["T3500", "T4500", "Minibus"]),
]

_OWNER_FIRST = ["Ram", "Shyam", "Hari", "Sita", "Gita", "Bishnu", "Krishna",
                "Durga", "Laxmi", "Prem", "Raju", "Anita", "Sunita", "Bikash",
                "Nabin", "Pratik", "Deepak", "Suman", "Binod", "Saroj",
                "Manoj", "Rajesh", "Suresh", "Ramesh", "Ganesh", "Santosh",
                "Kamal", "Dinesh", "Umesh", "Lokesh", "Mahesh", "Yogesh"]

_OWNER_LAST = ["Sharma", "Thapa", "Karki", "Rai", "Tamang", "Gurung",
               "Magar", "Limbu", "Shrestha", "Pradhan", "Joshi", "Panta",
               "Bhatta", "Koirala", "Adhikari", "Bhandari", "Regmi",
               "Poudel", "Giri", "Khatri", "Chaudhary", "Yadav", "Shah",
               "Basnet", "Bogati", "Dahal", "Kafle", "Gautam", "Pandit"]

_DISTRICTS = ["Kathmandu", "Lalitpur", "Bhaktapur", "Pokhara", "Bharatpur",
               "Biratnagar", "Birgunj", "Butwal", "Dharan", "Janakpur"]

_COLORS = ["White", "Black", "Silver", "Red", "Blue", "Grey",
           "Green", "Yellow", "Maroon", "Orange"]

_DISTRICT_CODES = ["Ba", "Ko", "Me", "La", "Bha", "Ka", "Chi", "Mo", "Pa", "Ra",
                   "Su", "Dha", "Sy", "Ta", "Ru"]

_LETTERS = ["Ka", "Kha", "Ga", "Gha", "Cha", "Chha", "Ja", "Jha",
            "Ta", "Tha", "Da", "Dha", "Na", "Pa", "Pha", "Ba", "Ma",
            "Ya", "Ra", "La", "Wa", "Sa", "Ha"]

_VEHICLE_TYPES = ["car", "motorcycle", "bus", "microbus", "truck", "van"]
_WEIGHTS_TYPE  = [0.40, 0.28, 0.10, 0.12, 0.07, 0.03]


def _random_date_future(min_days: int, max_days: int) -> date:
    return date.today() + timedelta(days=random.randint(min_days, max_days))


def _random_date_past(min_days: int, max_days: int) -> date:
    return date.today() - timedelta(days=random.randint(min_days, max_days))


def _gen_plate(district_code: str, series: int, letter: str, number: int) -> str:
    return f"{district_code} {series} {letter} {str(number).zfill(4)}"


def _build_registry(count: int = 500) -> dict[str, DoTMRecord]:
    random.seed(42)
    registry: dict[str, DoTMRecord] = {}

    for _ in range(count):
        dc   = random.choice(_DISTRICT_CODES)
        ser  = random.randint(1, 9)
        let  = random.choice(_LETTERS)
        num  = random.randint(1, 9999)
        plate = _gen_plate(dc, ser, let, num)

        make, models = random.choice(_MAKES_MODELS)
        model = random.choice(models)
        vtype = random.choices(_VEHICLE_TYPES, weights=_WEIGHTS_TYPE)[0]

        # 15% of vehicles have expired fitness
        if random.random() < 0.15:
            fitness_expiry = _random_date_past(10, 365)
        else:
            fitness_expiry = _random_date_future(30, 730)

        # 10% of vehicles have expired insurance
        if random.random() < 0.10:
            insurance_expiry = _random_date_past(5, 180)
        else:
            insurance_expiry = _random_date_future(30, 365)

        owner = f"{random.choice(_OWNER_FIRST)} {random.choice(_OWNER_LAST)}"
        engine_cc = random.choice([100, 125, 150, 200, 350, 800, 1000,
                                    1300, 1500, 1800, 2000, 2500, 3000, 3500])

        record = DoTMRecord(
            plate_text=plate,
            owner_name=owner,
            vehicle_make=make,
            vehicle_model=model,
            registered_year=random.randint(2005, 2023),
            fitness_expiry=fitness_expiry.isoformat(),
            insurance_expiry=insurance_expiry.isoformat(),
            registered_district=random.choice(_DISTRICTS),
            vehicle_type=vtype,
            engine_cc=engine_cc,
            color=random.choice(_COLORS),
            registered=True,
        )
        key = _normalize_key(plate)
        registry[key] = record

    return registry


def _normalize_key(plate: str) -> str:
    """Normalize plate text for fuzzy matching."""
    return re.sub(r"\s+", "", plate).lower()


# Build the registry once at module import
_REGISTRY: dict[str, DoTMRecord] = _build_registry(500)


def lookup(plate_text: str) -> Optional[DoTMRecord]:
    """
    Look up a plate in the mock DoTM registry.
    Uses fuzzy normalization (strip spaces, case-insensitive).
    Auto-flags if fitness or insurance is expired.
    """
    key = _normalize_key(plate_text)
    record = _REGISTRY.get(key)

    if record is None:
        return None

    # Validate expiry dates
    today = date.today()
    fitness_valid  = date.fromisoformat(record.fitness_expiry) >= today
    insurance_valid = date.fromisoformat(record.insurance_expiry) >= today

    # Return a copy with up-to-date validity flags embedded
    # (we use the record as-is; callers check expiry themselves)
    return record


def get_all_plates() -> list[str]:
    return [r.plate_text for r in _REGISTRY.values()]


def is_fitness_valid(record: DoTMRecord) -> bool:
    return date.fromisoformat(record.fitness_expiry) >= date.today()


def is_insurance_valid(record: DoTMRecord) -> bool:
    return date.fromisoformat(record.insurance_expiry) >= date.today()
