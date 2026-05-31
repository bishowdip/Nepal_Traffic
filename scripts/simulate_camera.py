"""
scripts/simulate_camera.py
Simulate a live camera feed for development/testing.

Generates realistic Nepal vehicle detections and POSTs them to the API
every 2–8 seconds (randomized), mimicking a real checkpoint camera.

Usage:
  cd nepal-traffic-ai
  python -m scripts.simulate_camera [--checkpoint cp-thankot] [--rate 4]
"""
import asyncio
import argparse
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from datetime import datetime

API_BASE = "http://localhost:8000/api"


# ── Plate generation ──────────────────────────────────────────────────────────

DISTRICT_CODES = ["Ba", "Ko", "Me", "La", "Bha", "Ka", "Chi", "Ra", "Su", "Mo", "Pa", "Sy", "Ta"]
LETTERS        = ["Ka", "Kha", "Ga", "Gha", "Cha", "Ja", "Ta", "Da", "Pa", "Ba", "Ma", "Ra", "Sa"]

VEHICLE_TYPES   = ["car", "motorcycle", "bus", "microbus", "truck", "van", "tractor", "other"]
WEIGHT_TYPE     = [0.40, 0.28, 0.10, 0.12, 0.07, 0.02, 0.005, 0.005]

OWNERSHIPS      = ["private", "public", "government", "police", "army",
                   "armed_police", "diplomatic", "un", "ngo"]
WEIGHT_OWN      = [0.72, 0.18, 0.05, 0.02, 0.01, 0.005, 0.005, 0.003, 0.002]

ORIGIN_CITIES   = [
    ("Pokhara",     "काठमाडौं–पोखरा",    15),
    ("Butwal",      "काठमाडौं–बुटवल",    12),
    ("Bhairahawa",  "काठमाडौं–भैरहवा",   10),
    ("Narayanghat", "नारायणघाट–काठमाडौं", 14),
    ("Biratnagar",  "काठमाडौं–विराटनगर",  7),
    ("Birgunj",     "काठमाडौं–वीरगंज",    9),
    ("Dharan",      "धरान–काठमाडौं",      5),
    ("Janakpur",    "जनकपुर–काठमाडौं",    4),
    ("Hetauda",     "हेटौंडा–काठमाडौं",   6),
    ("Nepalgunj",   "काठमाडौं–नेपालगन्ज", 3),
]
ORIGIN_WEIGHTS  = [c[2] for c in ORIGIN_CITIES]


def make_plate(ownership: str) -> str:
    dc  = random.choice(DISTRICT_CODES)
    ser = random.randint(1, 9)
    let = random.choice(LETTERS)
    num = random.randint(1, 9999)

    if ownership == "police":
        return f"Na Pra {ser} {let} {str(num).zfill(4)}"
    elif ownership == "army":
        return f"Na Se {ser} {let} {str(num).zfill(4)}"
    elif ownership == "armed_police":
        return f"Sa Pra {ser} {let} {str(num).zfill(4)}"
    elif ownership == "government":
        return f"Na Ra Sa {ser} {let} {str(num).zfill(4)}"
    elif ownership == "diplomatic":
        return f"CD {random.randint(10, 99)} {random.randint(1000, 9999)}"
    elif ownership == "un":
        return f"UN {random.randint(10, 99)} {random.randint(1000, 9999)}"
    elif ownership == "ngo":
        return f"NGO {dc} {ser} {let} {str(num).zfill(4)}"
    else:
        return f"{dc} {ser} {let} {str(num).zfill(4)}"


def make_detection(checkpoint_id: str) -> dict:
    vtype     = random.choices(VEHICLE_TYPES, weights=WEIGHT_TYPE)[0]
    ownership = random.choices(OWNERSHIPS,    weights=WEIGHT_OWN)[0]
    plate     = make_plate(ownership)
    conf      = round(random.uniform(0.55, 0.98), 3)
    direction = random.choice(["inbound", "outbound"])

    origin_text = origin_city = destination_city = None
    if vtype in ("bus", "microbus") and random.random() < 0.70:
        city_data = random.choices(ORIGIN_CITIES, weights=ORIGIN_WEIGHTS)[0]
        origin_city, origin_text, _ = city_data
        destination_city = "Kathmandu"
        if direction == "outbound":
            origin_city, destination_city = destination_city, origin_city

    dc_used = None
    if not any(ownership == s for s in ["police", "army", "armed_police", "government", "diplomatic", "un", "ngo"]):
        dc_used = plate.split(" ")[0]

    return {
        "plate_text":         plate,
        "plate_confidence":   conf,
        "vehicle_type":       vtype,
        "ownership_category": ownership,
        "district_code":      dc_used,
        "origin_text":        origin_text,
        "origin_city":        origin_city,
        "destination_city":   destination_city,
        "direction":          direction,
        "checkpoint_id":      checkpoint_id,
        "camera_id":          "sim-cam-01",
        "yolo_confidence":    round(random.uniform(0.70, 0.99), 3),
        "timestamp":          datetime.utcnow().isoformat(),
    }


async def simulate(checkpoint_id: str, rate_seconds: float, count: int = 0):
    """
    Continuously generate detections and POST to the API.

    Args:
        checkpoint_id: Target checkpoint ID
        rate_seconds:  Average interval between detections
        count:         Number of detections to send (0 = infinite)
    """
    print(f"Starting camera simulator")
    print(f"  Checkpoint: {checkpoint_id}")
    print(f"  API:        {API_BASE}")
    print(f"  Rate:       ~{rate_seconds}s between detections")
    print(f"  Count:      {'∞' if count == 0 else count}")
    print("─" * 50)

    sent = 0
    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            detection = make_detection(checkpoint_id)
            try:
                resp = await client.post(f"{API_BASE}/ingest", json=detection)
                sent += 1
                status = "✓" if resp.status_code == 201 else f"✗ {resp.status_code}"
                plate  = detection['plate_text']
                vtype  = detection['vehicle_type']
                own    = detection['ownership_category']
                origin = detection.get('origin_city') or '—'
                print(f"  [{sent:04d}] {status} {plate:<22} {vtype:<12} {own:<12} from {origin}")
            except httpx.ConnectError:
                print(f"  [ERR] Cannot connect to {API_BASE}. Is the server running?")
                print(f"        Retrying in 5s...")
                await asyncio.sleep(5)
                continue
            except Exception as e:
                print(f"  [ERR] {e}")

            if count and sent >= count:
                print(f"\nCompleted {sent} detections.")
                break

            # Randomize interval: ±50% around the target rate
            delay = rate_seconds * random.uniform(0.5, 1.5)
            await asyncio.sleep(delay)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate camera feed for Nepal Traffic AI")
    parser.add_argument("--checkpoint", default="cp-thankot", help="Checkpoint ID")
    parser.add_argument("--rate",  type=float, default=4.0, help="Average seconds between detections")
    parser.add_argument("--count", type=int,   default=0,   help="Number of detections to send (0=infinite)")
    args = parser.parse_args()

    asyncio.run(simulate(args.checkpoint, args.rate, args.count))
