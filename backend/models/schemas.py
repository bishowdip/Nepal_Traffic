from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from backend.models.vehicle import VehicleType, OwnershipCategory, Direction, AlertType, AlertSeverity


# ── VehicleSighting ───────────────────────────────────────────────────────────

class VehicleSightingBase(BaseModel):
    plate_text: str
    plate_confidence: float = 0.0
    vehicle_type: VehicleType = VehicleType.other
    ownership_category: OwnershipCategory = OwnershipCategory.private
    district_code: Optional[str] = None
    origin_text: Optional[str] = None
    origin_city: Optional[str] = None
    destination_city: Optional[str] = None
    direction: Direction = Direction.inbound
    checkpoint_id: str
    camera_id: Optional[str] = None
    image_path: Optional[str] = None
    dotm_registered: bool = False
    fitness_valid: Optional[bool] = None
    insurance_valid: Optional[bool] = None
    owner_name: Optional[str] = None
    flagged: bool = False
    flag_reason: Optional[str] = None


class VehicleSightingCreate(VehicleSightingBase):
    timestamp: Optional[datetime] = None


class VehicleSightingOut(VehicleSightingBase):
    id: str
    timestamp: datetime

    class Config:
        from_attributes = True


# ── Alert ─────────────────────────────────────────────────────────────────────

class AlertBase(BaseModel):
    alert_type: AlertType
    plate_text: str
    sighting_id: Optional[str] = None
    severity: AlertSeverity = AlertSeverity.info
    description: Optional[str] = None


class AlertCreate(AlertBase):
    pass


class AlertOut(AlertBase):
    id: str
    resolved: bool
    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Checkpoint ────────────────────────────────────────────────────────────────

class CheckpointBase(BaseModel):
    name: str
    location: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    active: bool = True
    camera_sources: Optional[str] = None


class CheckpointCreate(CheckpointBase):
    pass


class CheckpointOut(CheckpointBase):
    id: str

    class Config:
        from_attributes = True


# ── Watchlist ─────────────────────────────────────────────────────────────────

class WatchlistBase(BaseModel):
    plate_text: str
    reason: Optional[str] = None
    added_by: Optional[str] = None
    active: bool = True


class WatchlistCreate(WatchlistBase):
    pass


class WatchlistOut(WatchlistBase):
    id: str
    added_at: datetime

    class Config:
        from_attributes = True


# ── Stats / Reports ───────────────────────────────────────────────────────────

class SummaryStats(BaseModel):
    total_today: int
    by_type: dict
    by_ownership: dict
    plate_accuracy_pct: float
    active_alerts: int


class HourlyStats(BaseModel):
    hour: str  # ISO datetime string
    count: int
    inbound: int
    outbound: int


class OriginStats(BaseModel):
    city: str
    count: int
    percentage: float


# ── Ingest (from simulator / camera) ─────────────────────────────────────────

class IngestPayload(BaseModel):
    plate_text: str
    plate_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    vehicle_type: VehicleType = VehicleType.other
    ownership_category: OwnershipCategory = OwnershipCategory.private
    district_code: Optional[str] = None
    origin_text: Optional[str] = None
    origin_city: Optional[str] = None
    destination_city: Optional[str] = None
    direction: Direction = Direction.inbound
    checkpoint_id: str
    camera_id: Optional[str] = "cam-01"
    yolo_confidence: Optional[float] = None
    plate_image_b64: Optional[str] = None
    timestamp: Optional[datetime] = None


class DoTMRecord(BaseModel):
    plate_text: str
    owner_name: str
    vehicle_make: str
    vehicle_model: str
    registered_year: int
    fitness_expiry: str      # ISO date string
    insurance_expiry: str    # ISO date string
    registered_district: str
    vehicle_type: str
    engine_cc: int
    color: str
    registered: bool = True
