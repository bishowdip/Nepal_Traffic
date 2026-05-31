"""
Vehicle CRUD, stats, and ingest endpoints.
"""
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.vehicle import VehicleSighting, Alert, Watchlist, Checkpoint
from backend.models.schemas import (
    VehicleSightingOut, VehicleSightingCreate, IngestPayload,
    SummaryStats, HourlyStats, OriginStats, DoTMRecord,
)
from backend.services import dotm, alert as alert_engine
from backend.api.stream import broadcast_sighting, broadcast_alert

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Ingest (from simulator / camera pipeline) ─────────────────────────────────

@router.post("/ingest", response_model=VehicleSightingOut, status_code=201)
async def ingest_sighting(payload: IngestPayload, db: AsyncSession = Depends(get_db)):
    """Receive a new vehicle detection and persist it."""
    # DoTM lookup
    dotm_record: Optional[DoTMRecord] = dotm.lookup(payload.plate_text)
    registered  = dotm_record is not None
    fitness_ok  = dotm.is_fitness_valid(dotm_record) if dotm_record else None
    insurance_ok = dotm.is_insurance_valid(dotm_record) if dotm_record else None
    owner_name  = dotm_record.owner_name if dotm_record else None

    sighting = VehicleSighting(
        id=str(uuid.uuid4()),
        plate_text=payload.plate_text,
        plate_confidence=payload.plate_confidence,
        vehicle_type=payload.vehicle_type,
        ownership_category=payload.ownership_category,
        district_code=payload.district_code,
        origin_text=payload.origin_text,
        origin_city=payload.origin_city,
        destination_city=payload.destination_city,
        direction=payload.direction,
        checkpoint_id=payload.checkpoint_id,
        camera_id=payload.camera_id,
        dotm_registered=registered,
        fitness_valid=fitness_ok,
        insurance_valid=insurance_ok,
        owner_name=owner_name,
        flagged=False,
        timestamp=payload.timestamp or datetime.utcnow(),
    )

    db.add(sighting)
    await db.flush()  # get the id

    # Check watchlist
    wl_result = await db.execute(
        select(Watchlist).where(
            Watchlist.active == True,
            func.lower(Watchlist.plate_text) == payload.plate_text.lower().strip()
        )
    )
    if wl_result.scalar_one_or_none():
        from backend.services.alert import _WATCHLIST_CACHE
        _WATCHLIST_CACHE[payload.plate_text.lower().strip()] = True

    # Run alert engine
    alerts = alert_engine.check(sighting)
    if alerts:
        sighting.flagged = True
        sighting.flag_reason = "; ".join(a.description or "" for a in alerts)
        for a in alerts:
            db.add(a)

    await db.commit()
    await db.refresh(sighting)

    # Broadcast to WebSocket clients
    try:
        out = VehicleSightingOut.model_validate(sighting)
        await broadcast_sighting(sighting.checkpoint_id, out.model_dump(mode="json"))
        for a in alerts:
            await broadcast_alert(sighting.checkpoint_id, {
                "id": a.id, "type": a.alert_type, "severity": a.severity,
                "plate": a.plate_text, "description": a.description,
            })
    except Exception as e:
        logger.warning(f"WebSocket broadcast failed: {e}")

    return sighting


# ── List / search sightings ───────────────────────────────────────────────────

@router.get("/vehicles", response_model=List[VehicleSightingOut])
async def list_vehicles(
    checkpoint_id: Optional[str] = None,
    type: Optional[str] = None,
    ownership: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    direction: Optional[str] = None,
    flagged: Optional[bool] = None,
    plate: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    q = select(VehicleSighting)
    if checkpoint_id:
        q = q.where(VehicleSighting.checkpoint_id == checkpoint_id)
    if type:
        q = q.where(VehicleSighting.vehicle_type == type)
    if ownership:
        q = q.where(VehicleSighting.ownership_category == ownership)
    if start:
        q = q.where(VehicleSighting.timestamp >= start)
    if end:
        q = q.where(VehicleSighting.timestamp <= end)
    if direction:
        q = q.where(VehicleSighting.direction == direction)
    if flagged is not None:
        q = q.where(VehicleSighting.flagged == flagged)
    if plate:
        q = q.where(VehicleSighting.plate_text.ilike(f"%{plate}%"))

    q = q.order_by(VehicleSighting.timestamp.desc())
    q = q.offset((page - 1) * limit).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/vehicles/search", response_model=List[VehicleSightingOut])
async def search_vehicles(
    plate: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(VehicleSighting)
        .where(VehicleSighting.plate_text.ilike(f"%{plate}%"))
        .order_by(VehicleSighting.timestamp.desc())
        .limit(100)
    )
    return result.scalars().all()


@router.get("/vehicles/{vehicle_id}", response_model=VehicleSightingOut)
async def get_vehicle(vehicle_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(VehicleSighting).where(VehicleSighting.id == vehicle_id)
    )
    sighting = result.scalar_one_or_none()
    if not sighting:
        raise HTTPException(status_code=404, detail="Sighting not found")
    return sighting


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats/summary", response_model=SummaryStats)
async def stats_summary(
    checkpoint_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    base_q = select(VehicleSighting).where(VehicleSighting.timestamp >= today_start)
    if checkpoint_id:
        base_q = base_q.where(VehicleSighting.checkpoint_id == checkpoint_id)

    result = await db.execute(base_q)
    rows = result.scalars().all()

    by_type: dict = {}
    by_ownership: dict = {}
    total_conf: float = 0.0
    conf_count: int = 0

    for r in rows:
        by_type[r.vehicle_type] = by_type.get(r.vehicle_type, 0) + 1
        by_ownership[r.ownership_category] = by_ownership.get(r.ownership_category, 0) + 1
        if r.plate_confidence > 0:
            total_conf += r.plate_confidence
            conf_count += 1

    alert_count_res = await db.execute(
        select(func.count()).select_from(Alert).where(Alert.resolved == False)
    )
    active_alerts = alert_count_res.scalar_one()

    return SummaryStats(
        total_today=len(rows),
        by_type={k: v for k, v in by_type.items()},
        by_ownership={k: v for k, v in by_ownership.items()},
        plate_accuracy_pct=round((total_conf / conf_count * 100) if conf_count else 0.0, 1),
        active_alerts=active_alerts,
    )


@router.get("/stats/hourly", response_model=List[HourlyStats])
async def stats_hourly(
    checkpoint_id: Optional[str] = None,
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(hours=hours)
    q = select(VehicleSighting).where(VehicleSighting.timestamp >= since)
    if checkpoint_id:
        q = q.where(VehicleSighting.checkpoint_id == checkpoint_id)
    result = await db.execute(q)
    rows = result.scalars().all()

    # Bucket by hour
    buckets: dict = {}
    for r in rows:
        bucket = r.timestamp.strftime("%Y-%m-%dT%H:00:00")
        if bucket not in buckets:
            buckets[bucket] = {"count": 0, "inbound": 0, "outbound": 0}
        buckets[bucket]["count"] += 1
        if r.direction == "inbound":
            buckets[bucket]["inbound"] += 1
        else:
            buckets[bucket]["outbound"] += 1

    return [
        HourlyStats(hour=h, count=v["count"], inbound=v["inbound"], outbound=v["outbound"])
        for h, v in sorted(buckets.items())
    ]


@router.get("/stats/origin", response_model=List[OriginStats])
async def stats_origin(
    checkpoint_id: Optional[str] = None,
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)
    q = select(VehicleSighting).where(
        VehicleSighting.timestamp >= since,
        VehicleSighting.origin_city != None,
        VehicleSighting.origin_city != "",
    )
    if checkpoint_id:
        q = q.where(VehicleSighting.checkpoint_id == checkpoint_id)
    result = await db.execute(q)
    rows = result.scalars().all()

    counts: dict = {}
    for r in rows:
        city = r.origin_city or ""
        if city:
            counts[city] = counts.get(city, 0) + 1

    total = sum(counts.values()) or 1
    sorted_cities = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:15]

    return [
        OriginStats(city=city, count=cnt, percentage=round(cnt / total * 100, 1))
        for city, cnt in sorted_cities
    ]


# ── DoTM lookup endpoint ──────────────────────────────────────────────────────

@router.get("/dotm/{plate_text}")
async def dotm_lookup(plate_text: str):
    record = dotm.lookup(plate_text)
    if record is None:
        raise HTTPException(status_code=404, detail="Plate not found in DoTM registry")
    return record


# ── Checkpoint endpoints ──────────────────────────────────────────────────────

@router.get("/checkpoints")
async def list_checkpoints(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Checkpoint).where(Checkpoint.active == True))
    return result.scalars().all()


@router.post("/checkpoints", status_code=201)
async def create_checkpoint(data: dict, db: AsyncSession = Depends(get_db)):
    cp = Checkpoint(
        id=str(uuid.uuid4()),
        name=data.get("name", "New Checkpoint"),
        location=data.get("location"),
        lat=data.get("lat"),
        lng=data.get("lng"),
        active=True,
        camera_sources=data.get("camera_sources"),
    )
    db.add(cp)
    await db.commit()
    await db.refresh(cp)
    return cp


# ── Watchlist endpoints ───────────────────────────────────────────────────────

@router.get("/watchlist")
async def list_watchlist(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Watchlist).where(Watchlist.active == True))
    return result.scalars().all()


@router.post("/watchlist", status_code=201)
async def add_watchlist(data: dict, db: AsyncSession = Depends(get_db)):
    wl = Watchlist(
        id=str(uuid.uuid4()),
        plate_text=data.get("plate_text", ""),
        reason=data.get("reason"),
        added_by=data.get("added_by", "operator"),
        active=True,
    )
    db.add(wl)
    await db.commit()
    await db.refresh(wl)
    return wl


@router.delete("/watchlist/{plate_text}", status_code=204)
async def remove_watchlist(plate_text: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Watchlist).where(func.lower(Watchlist.plate_text) == plate_text.lower())
    )
    wl = result.scalar_one_or_none()
    if wl:
        wl.active = False
        await db.commit()
