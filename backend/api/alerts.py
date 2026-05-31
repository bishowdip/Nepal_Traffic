"""
Alert management endpoints.
"""
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.vehicle import Alert, AlertSeverity, AlertType
from backend.models.schemas import AlertOut

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/alerts", response_model=List[AlertOut])
async def list_alerts(
    resolved: Optional[bool] = None,
    severity: Optional[str] = None,
    alert_type: Optional[str] = None,
    checkpoint_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    q = select(Alert)
    if resolved is not None:
        q = q.where(Alert.resolved == resolved)
    if severity:
        q = q.where(Alert.severity == severity)
    if alert_type:
        q = q.where(Alert.alert_type == alert_type)
    q = q.order_by(Alert.created_at.desc())
    q = q.offset((page - 1) * limit).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/alerts/{alert_id}", response_model=AlertOut)
async def get_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.patch("/alerts/{alert_id}/resolve", response_model=AlertOut)
async def resolve_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.resolved = True
    alert.resolved_at = datetime.utcnow()
    await db.commit()
    await db.refresh(alert)
    return alert


@router.get("/alerts/count/active")
async def active_alert_count(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(func.count()).select_from(Alert).where(Alert.resolved == False)
    )
    return {"count": result.scalar_one()}
