"""
scripts/seed_database.py
Seed the database with realistic Nepal traffic data.

Creates:
  - 3 checkpoints: Thankot, Nagdhunga, Suryabinayak
  - 500 DoTM mock records (via dotm service)
  - 2000 historical vehicle sightings (last 7 days)
  - 5 watchlist entries
  - 12 resolved + 3 open alerts

Usage:
  cd nepal-traffic-ai
  python -m scripts.seed_database
"""
import asyncio
import random
import uuid
from datetime import datetime, timedelta, date

# Must set PYTHONPATH or run from project root
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def seed():
    # Init DB
    from backend.database import init_db, AsyncSessionLocal
    from backend.models.vehicle import (
        VehicleSighting, Alert, Checkpoint, Watchlist,
        VehicleType, OwnershipCategory, Direction, AlertType, AlertSeverity
    )
    from backend.services.dotm import lookup, get_all_plates, is_fitness_valid, is_insurance_valid
    from sqlalchemy import select

    await init_db()

    async with AsyncSessionLocal() as db:

        # ── Checkpoints ──────────────────────────────────────────────────────
        checkpoints_data = [
            {
                "id": "cp-thankot",
                "name": "Thankot Checkpoint",
                "location": "Thankot, Chandragiri Municipality",
                "lat": 27.6830, "lng": 85.2012,
                "camera_sources": "rtsp://cam1.thankot.traffic.gov.np/live",
            },
            {
                "id": "cp-nagdhunga",
                "name": "Nagdhunga Checkpoint",
                "location": "Nagdhunga, Tribhuvan Highway",
                "lat": 27.7123, "lng": 85.2456,
                "camera_sources": "rtsp://cam1.nagdhunga.traffic.gov.np/live",
            },
            {
                "id": "cp-suryabinayak",
                "name": "Suryabinayak Checkpoint",
                "location": "Suryabinayak, Araniko Highway",
                "lat": 27.6610, "lng": 85.4321,
                "camera_sources": "rtsp://cam1.suryabinayak.traffic.gov.np/live",
            },
        ]

        existing_cp = await db.execute(select(Checkpoint))
        if not existing_cp.scalars().first():
            for cp_data in checkpoints_data:
                cp = Checkpoint(**cp_data, active=True)
                db.add(cp)
            print(f"Added {len(checkpoints_data)} checkpoints")
        else:
            print("Checkpoints already exist, skipping")

        await db.flush()

        # ── Watchlist ────────────────────────────────────────────────────────
        watchlist_entries = [
            {"plate_text": "Ba 3 Ma 1234", "reason": "Stolen vehicle report", "added_by": "Insp. Sharma"},
            {"plate_text": "Ko 5 Ja 7891", "reason": "Outstanding traffic violations", "added_by": "Traffic HQ"},
            {"plate_text": "Na Se 2 Ga 0044", "reason": "Impersonating army vehicle", "added_by": "Insp. Thapa"},
            {"plate_text": "CD 15 9999", "reason": "Expired diplomatic status", "added_by": "DoTM Central"},
            {"plate_text": "La 1 Ka 4400", "reason": "Suspected smuggling involvement", "added_by": "Insp. Rai"},
        ]

        existing_wl = await db.execute(select(Watchlist))
        if not existing_wl.scalars().first():
            for wl_data in watchlist_entries:
                wl = Watchlist(id=str(uuid.uuid4()), **wl_data, active=True,
                               added_at=datetime.utcnow() - timedelta(days=random.randint(1, 30)))
                db.add(wl)
            print(f"Added {len(watchlist_entries)} watchlist entries")

        await db.flush()

        # ── Historical sightings ─────────────────────────────────────────────
        existing_sightings = await db.execute(select(Sighting := VehicleSighting).limit(1))
        if existing_sightings.scalars().first():
            print("Sightings already exist, skipping")
        else:
            all_plates = get_all_plates()[:200]  # Use first 200 DoTM plates for realistic data

            VEHICLE_TYPES   = [e.value for e in VehicleType]
            WEIGHT_TYPE     = [0.40, 0.28, 0.10, 0.12, 0.07, 0.02, 0.005, 0.005]
            OWNERSHIPS      = [e.value for e in OwnershipCategory]
            WEIGHT_OWN      = [0.72, 0.18, 0.05, 0.02, 0.01, 0.005, 0.005, 0.003, 0.002]
            CP_IDS          = ["cp-thankot", "cp-nagdhunga", "cp-suryabinayak"]
            ORIGIN_CITIES   = [
                "Pokhara", "Butwal", "Bhairahawa", "Narayanghat", "Bharatpur",
                "Biratnagar", "Birgunj", "Dharan", "Janakpur", "Chitwan",
                "Hetauda", "Nepalgunj", "Dhangadhi", "Surkhet", "Dang",
            ]
            ORIGIN_WEIGHTS  = [15, 12, 10, 14, 8, 7, 9, 5, 4, 6, 4, 3, 2, 2, 2]

            batch_size = 100
            count = 0

            for i in range(2000):
                # Random timestamp over the last 7 days with realistic traffic patterns
                day_offset = random.randint(0, 6)
                base_ts = datetime.utcnow() - timedelta(days=day_offset)

                # Traffic density: rush hours 7-10 AM, 4-7 PM
                hour = random.choices(
                    list(range(24)),
                    weights=[1,1,1,1,1,2,4,8,9,7,5,4,4,4,5,6,8,9,8,6,4,3,2,1]
                )[0]
                minute = random.randint(0, 59)
                ts = base_ts.replace(hour=hour, minute=minute, second=random.randint(0, 59), microsecond=0)

                vtype     = random.choices(VEHICLE_TYPES, weights=WEIGHT_TYPE)[0]
                ownership = random.choices(OWNERSHIPS,    weights=WEIGHT_OWN)[0]
                cp_id     = random.choice(CP_IDS)
                direction = random.choice(["inbound", "outbound"])

                # Pick plate (mix of DoTM-registered and unregistered)
                if random.random() < 0.78 and all_plates:
                    plate = random.choice(all_plates)
                    dotm_rec = lookup(plate)
                    registered   = dotm_rec is not None
                    fitness_ok   = is_fitness_valid(dotm_rec) if dotm_rec else None
                    insurance_ok = is_insurance_valid(dotm_rec) if dotm_rec else None
                    owner_name   = dotm_rec.owner_name if dotm_rec else None
                else:
                    from backend.services.classifier import DISTRICT_MAP, _LETTERS
                    dc  = random.choice(list(DISTRICT_MAP.keys()))
                    ser = random.randint(1, 9)
                    let = random.choice(_LETTERS)
                    num = random.randint(1, 9999)
                    plate = f"{dc} {ser} {let} {str(num).zfill(4)}"
                    registered   = False
                    fitness_ok   = None
                    insurance_ok = None
                    owner_name   = None

                # Origin city for buses/microbuses
                origin_city = destination_city = None
                origin_text = None
                if vtype in ("bus", "microbus") and random.random() < 0.7:
                    origin_city = random.choices(ORIGIN_CITIES, weights=ORIGIN_WEIGHTS)[0]
                    destination_city = "Kathmandu"
                    origin_text = f"{origin_city}–काठमाडौं"

                conf = round(random.uniform(0.55, 0.98), 3)
                flagged = not registered or (fitness_ok is False) or (insurance_ok is False)

                from backend.services.classifier import DISTRICT_MAP
                district_codes = list(DISTRICT_MAP.keys())
                dc = random.choice(district_codes)

                sighting = VehicleSighting(
                    id=str(uuid.uuid4()),
                    plate_text=plate,
                    plate_confidence=conf,
                    vehicle_type=vtype,
                    ownership_category=ownership,
                    district_code=dc,
                    origin_text=origin_text,
                    origin_city=origin_city,
                    destination_city=destination_city,
                    direction=direction,
                    checkpoint_id=cp_id,
                    camera_id="cam-01",
                    dotm_registered=registered,
                    fitness_valid=fitness_ok,
                    insurance_valid=insurance_ok,
                    owner_name=owner_name,
                    flagged=flagged,
                    flag_reason="Unregistered vehicle" if not registered else
                                ("Expired fitness" if fitness_ok is False else
                                 ("Expired insurance" if insurance_ok is False else None)),
                    timestamp=ts,
                )
                db.add(sighting)
                count += 1

                if count % batch_size == 0:
                    await db.flush()
                    print(f"  Inserted {count}/2000 sightings...", end="\r")

            await db.flush()
            print(f"\nAdded {count} historical sightings")

        # ── Alerts ───────────────────────────────────────────────────────────
        existing_alerts = await db.execute(select(Alert).limit(1))
        if existing_alerts.scalars().first():
            print("Alerts already exist, skipping")
        else:
            alert_types = [e.value for e in AlertType]
            severities  = [AlertSeverity.warning, AlertSeverity.critical, AlertSeverity.info]

            for i in range(15):
                resolved = i < 12  # first 12 resolved, last 3 open
                created = datetime.utcnow() - timedelta(hours=random.randint(1, 72))
                alert = Alert(
                    id=str(uuid.uuid4()),
                    alert_type=random.choice(alert_types),
                    plate_text=f"Ba {random.randint(1,9)} Ka {random.randint(1000,9999)}",
                    severity=random.choice(severities),
                    resolved=resolved,
                    created_at=created,
                    resolved_at=created + timedelta(minutes=random.randint(5, 120)) if resolved else None,
                    description="Seeded test alert",
                )
                db.add(alert)

            print("Added 15 alerts (12 resolved, 3 open)")

        await db.commit()
        print("\nDatabase seeding complete!")
        print(f"  Checkpoints: 3")
        print(f"  Watchlist:   5 entries")
        print(f"  Sightings:   2000 (last 7 days)")
        print(f"  Alerts:      15 (12 resolved, 3 open)")


if __name__ == "__main__":
    asyncio.run(seed())
