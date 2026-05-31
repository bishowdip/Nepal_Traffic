import uuid
from datetime import datetime
from sqlalchemy import (
    String, Float, Boolean, DateTime, ForeignKey,
    Enum as SAEnum, Text, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base
import enum


class VehicleType(str, enum.Enum):
    car = "car"
    motorcycle = "motorcycle"
    bus = "bus"
    microbus = "microbus"
    truck = "truck"
    van = "van"
    tractor = "tractor"
    other = "other"


class OwnershipCategory(str, enum.Enum):
    private = "private"
    public = "public"
    government = "government"
    police = "police"
    army = "army"
    armed_police = "armed_police"
    diplomatic = "diplomatic"
    un = "un"
    ngo = "ngo"


class Direction(str, enum.Enum):
    inbound = "inbound"
    outbound = "outbound"


class AlertType(str, enum.Enum):
    expired_fitness = "expired_fitness"
    obscured_plate = "obscured_plate"
    watchlist_match = "watchlist_match"
    unregistered = "unregistered"
    high_volume = "high_volume"
    expired_insurance = "expired_insurance"
    unreadable_plate = "unreadable_plate"


class AlertSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


def _new_uuid() -> str:
    return str(uuid.uuid4())


class VehicleSighting(Base):
    __tablename__ = "vehicle_sightings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    plate_text: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    plate_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    vehicle_type: Mapped[VehicleType] = mapped_column(
        SAEnum(VehicleType), default=VehicleType.other
    )
    ownership_category: Mapped[OwnershipCategory] = mapped_column(
        SAEnum(OwnershipCategory), default=OwnershipCategory.private
    )
    district_code: Mapped[str] = mapped_column(String(16), nullable=True)
    origin_text: Mapped[str] = mapped_column(Text, nullable=True)
    origin_city: Mapped[str] = mapped_column(String(64), nullable=True)
    destination_city: Mapped[str] = mapped_column(String(64), nullable=True)
    direction: Mapped[Direction] = mapped_column(
        SAEnum(Direction), default=Direction.inbound
    )
    checkpoint_id: Mapped[str] = mapped_column(String(36), nullable=False)
    camera_id: Mapped[str] = mapped_column(String(64), nullable=True)
    image_path: Mapped[str] = mapped_column(String(256), nullable=True)
    dotm_registered: Mapped[bool] = mapped_column(Boolean, default=False)
    fitness_valid: Mapped[bool] = mapped_column(Boolean, nullable=True)
    insurance_valid: Mapped[bool] = mapped_column(Boolean, nullable=True)
    owner_name: Mapped[str] = mapped_column(String(128), nullable=True)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reason: Mapped[str] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    alerts: Mapped[list["Alert"]] = relationship("Alert", back_populates="sighting")

    __table_args__ = (
        Index("ix_sighting_checkpoint_ts", "checkpoint_id", "timestamp"),
        Index("ix_sighting_plate_ts", "plate_text", "timestamp"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    alert_type: Mapped[AlertType] = mapped_column(SAEnum(AlertType), nullable=False)
    plate_text: Mapped[str] = mapped_column(String(32), nullable=False)
    sighting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vehicle_sightings.id"), nullable=True
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        SAEnum(AlertSeverity), default=AlertSeverity.info
    )
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    sighting: Mapped["VehicleSighting"] = relationship("VehicleSighting", back_populates="alerts")


class Checkpoint(Base):
    __tablename__ = "checkpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    location: Mapped[str] = mapped_column(String(256), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=True)
    lng: Mapped[float] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    camera_sources: Mapped[str] = mapped_column(Text, nullable=True)


class Watchlist(Base):
    __tablename__ = "watchlist"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    plate_text: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    added_by: Mapped[str] = mapped_column(String(128), nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
