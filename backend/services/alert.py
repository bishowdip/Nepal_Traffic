"""
Alert engine for Nepal Traffic AI.
Evaluates a new VehicleSighting against all alert rules and returns
a list of Alert objects to be persisted.
"""
import logging
from datetime import datetime, timedelta
from typing import List

from backend.models.vehicle import Alert, AlertType, AlertSeverity, VehicleSighting

logger = logging.getLogger(__name__)

# In-memory cache: plate → watchlist active flag (refreshed on demand)
_WATCHLIST_CACHE: dict[str, bool] = {}

# In-memory hourly counters: (checkpoint_id, hour_bucket) → count
_HOURLY_COUNTS: dict[tuple[str, str], list[datetime]] = {}

# How many standard deviations above the rolling mean triggers a high-volume alert
_HIGH_VOLUME_STD_THRESHOLD = 2.0
_HIGH_VOLUME_HISTORY_HOURS = 24


def refresh_watchlist(watchlist: dict[str, bool]) -> None:
    """Called by startup / background task to keep the watchlist cache current."""
    global _WATCHLIST_CACHE
    _WATCHLIST_CACHE = watchlist


def check(sighting: VehicleSighting) -> List[Alert]:
    """
    Evaluate a new sighting against all alert rules.
    Returns a (possibly empty) list of Alert objects ready for DB insertion.
    """
    alerts: List[Alert] = []
    now = datetime.utcnow()

    plate = (sighting.plate_text or "").strip().upper()

    # ── Rule 1: Watchlist match ────────────────────────────────────────────
    if plate and _WATCHLIST_CACHE.get(plate.lower(), False):
        alerts.append(Alert(
            alert_type=AlertType.watchlist_match,
            plate_text=sighting.plate_text,
            sighting_id=sighting.id,
            severity=AlertSeverity.critical,
            description=f"Plate {plate} matched active watchlist entry.",
        ))

    # ── Rule 2: Unregistered ──────────────────────────────────────────────
    if not sighting.dotm_registered:
        alerts.append(Alert(
            alert_type=AlertType.unregistered,
            plate_text=sighting.plate_text,
            sighting_id=sighting.id,
            severity=AlertSeverity.warning,
            description=f"Plate {plate} not found in DoTM registry.",
        ))

    # ── Rule 3: Expired fitness ───────────────────────────────────────────
    if sighting.fitness_valid is False:
        alerts.append(Alert(
            alert_type=AlertType.expired_fitness,
            plate_text=sighting.plate_text,
            sighting_id=sighting.id,
            severity=AlertSeverity.warning,
            description=f"Vehicle fitness certificate expired for {plate}.",
        ))

    # ── Rule 4: Expired insurance ─────────────────────────────────────────
    if sighting.insurance_valid is False:
        alerts.append(Alert(
            alert_type=AlertType.expired_insurance,
            plate_text=sighting.plate_text,
            sighting_id=sighting.id,
            severity=AlertSeverity.warning,
            description=f"Vehicle insurance expired for {plate}.",
        ))

    # ── Rule 5: Low OCR confidence (obscured plate) ───────────────────────
    if sighting.plate_confidence < 0.4:
        alerts.append(Alert(
            alert_type=AlertType.obscured_plate,
            plate_text=sighting.plate_text,
            sighting_id=sighting.id,
            severity=AlertSeverity.info,
            description=f"Low OCR confidence ({sighting.plate_confidence:.2f}) — possible obscured plate.",
        ))

    # ── Rule 6: Unreadable plate (too short) ──────────────────────────────
    stripped = re.sub(r"\s+", "", plate)
    if 0 < len(stripped) < 4:
        alerts.append(Alert(
            alert_type=AlertType.unreadable_plate,
            plate_text=sighting.plate_text,
            sighting_id=sighting.id,
            severity=AlertSeverity.warning,
            description=f"Plate text '{sighting.plate_text}' appears unreadable (only {len(stripped)} chars).",
        ))

    # ── Rule 7: High volume per hour per checkpoint ───────────────────────
    high_vol_alert = _check_high_volume(sighting.checkpoint_id, now)
    if high_vol_alert:
        alerts.append(high_vol_alert)

    return alerts


# ── High-volume helper ────────────────────────────────────────────────────────

import re
import statistics


def _check_high_volume(checkpoint_id: str, now: datetime) -> Alert | None:
    """
    Maintain a sliding window of per-hour counts.
    If current hour count is more than _HIGH_VOLUME_STD_THRESHOLD std devs
    above the mean of the last 24 hours, return a high_volume alert.
    """
    # Current hour bucket
    bucket = now.strftime("%Y-%m-%dT%H")
    key = (checkpoint_id, bucket)

    # Append to current hour's list
    _HOURLY_COUNTS.setdefault(key, []).append(now)

    # Collect counts for the last _HIGH_VOLUME_HISTORY_HOURS
    hourly_totals = []
    for h in range(_HIGH_VOLUME_HISTORY_HOURS):
        past = now - timedelta(hours=h)
        past_bucket = past.strftime("%Y-%m-%dT%H")
        past_key = (checkpoint_id, past_bucket)
        count = len(_HOURLY_COUNTS.get(past_key, []))
        hourly_totals.append(count)

    if len(hourly_totals) < 3:
        return None

    current = hourly_totals[0]
    historical = hourly_totals[1:]

    if len(historical) < 2:
        return None

    mean = statistics.mean(historical)
    try:
        stdev = statistics.stdev(historical)
    except statistics.StatisticsError:
        return None

    if stdev == 0:
        return None

    z_score = (current - mean) / stdev
    if z_score > _HIGH_VOLUME_STD_THRESHOLD:
        return Alert(
            alert_type=AlertType.high_volume,
            plate_text="",
            sighting_id=None,
            severity=AlertSeverity.info,
            description=(
                f"High traffic volume at checkpoint {checkpoint_id}: "
                f"{current} vehicles this hour (mean={mean:.1f}, stdev={stdev:.1f}, z={z_score:.2f})."
            ),
        )
    return None
