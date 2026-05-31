"""
Analytics & export endpoints.
"""
import io
import csv
import logging
from datetime import datetime, date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.vehicle import VehicleSighting, Alert
from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/reports/daily")
async def daily_report(
    report_date: Optional[str] = Query(None, alias="date"),
    checkpoint_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Return a full daily report as JSON."""
    if report_date:
        day = date.fromisoformat(report_date)
    else:
        day = date.today()

    day_start = datetime(day.year, day.month, day.day, 0, 0, 0)
    day_end   = datetime(day.year, day.month, day.day, 23, 59, 59)

    q = select(VehicleSighting).where(
        VehicleSighting.timestamp >= day_start,
        VehicleSighting.timestamp <= day_end,
    )
    if checkpoint_id:
        q = q.where(VehicleSighting.checkpoint_id == checkpoint_id)

    result = await db.execute(q)
    rows = result.scalars().all()

    by_type: dict = {}
    by_ownership: dict = {}
    by_origin: dict = {}
    hourly: dict = {str(h): 0 for h in range(24)}
    alert_count = 0

    for r in rows:
        by_type[r.vehicle_type] = by_type.get(r.vehicle_type, 0) + 1
        by_ownership[r.ownership_category] = by_ownership.get(r.ownership_category, 0) + 1
        if r.origin_city:
            by_origin[r.origin_city] = by_origin.get(r.origin_city, 0) + 1
        hour = str(r.timestamp.hour)
        hourly[hour] = hourly.get(hour, 0) + 1
        if r.flagged:
            alert_count += 1

    alert_res = await db.execute(
        select(func.count()).select_from(Alert).where(
            Alert.created_at >= day_start,
            Alert.created_at <= day_end,
        )
    )
    total_alerts = alert_res.scalar_one()

    return {
        "date": day.isoformat(),
        "checkpoint_id": checkpoint_id,
        "total_vehicles": len(rows),
        "by_type": by_type,
        "by_ownership": by_ownership,
        "top_origins": sorted(by_origin.items(), key=lambda x: x[1], reverse=True)[:10],
        "hourly_counts": hourly,
        "total_alerts": total_alerts,
        "flagged_vehicles": alert_count,
    }


@router.get("/reports/export/csv")
async def export_csv(
    checkpoint_id: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Export filtered vehicle sightings as CSV."""
    q = select(VehicleSighting)
    if checkpoint_id:
        q = q.where(VehicleSighting.checkpoint_id == checkpoint_id)
    if start:
        q = q.where(VehicleSighting.timestamp >= datetime.fromisoformat(start))
    if end:
        q = q.where(VehicleSighting.timestamp <= datetime.fromisoformat(end))
    q = q.order_by(VehicleSighting.timestamp.desc())

    result = await db.execute(q)
    rows = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "timestamp", "plate_text", "plate_confidence",
        "vehicle_type", "ownership_category", "district_code",
        "origin_city", "destination_city", "direction",
        "checkpoint_id", "dotm_registered", "fitness_valid",
        "insurance_valid", "owner_name", "flagged", "flag_reason",
    ])
    for r in rows:
        writer.writerow([
            r.id, r.timestamp.isoformat(), r.plate_text, r.plate_confidence,
            r.vehicle_type, r.ownership_category, r.district_code,
            r.origin_city, r.destination_city, r.direction,
            r.checkpoint_id, r.dotm_registered, r.fitness_valid,
            r.insurance_valid, r.owner_name, r.flagged, r.flag_reason,
        ])

    output.seek(0)
    filename = f"traffic_report_{date.today().isoformat()}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reports/export/pdf")
async def export_pdf(
    checkpoint_id: Optional[str] = None,
    report_date: Optional[str] = Query(None, alias="date"),
    db: AsyncSession = Depends(get_db),
):
    """Generate and return a PDF traffic report."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        )
        from reportlab.lib.units import cm
    except ImportError:
        return {"error": "reportlab not installed"}

    if report_date:
        day = date.fromisoformat(report_date)
    else:
        day = date.today()

    day_start = datetime(day.year, day.month, day.day, 0, 0, 0)
    day_end   = datetime(day.year, day.month, day.day, 23, 59, 59)

    q = select(VehicleSighting).where(
        VehicleSighting.timestamp >= day_start,
        VehicleSighting.timestamp <= day_end,
    )
    if checkpoint_id:
        q = q.where(VehicleSighting.checkpoint_id == checkpoint_id)
    result = await db.execute(q)
    rows = result.scalars().all()

    by_type: dict = {}
    by_ownership: dict = {}
    by_origin: dict = {}
    hourly: dict = {h: 0 for h in range(24)}

    for r in rows:
        by_type[r.vehicle_type] = by_type.get(r.vehicle_type, 0) + 1
        by_ownership[r.ownership_category] = by_ownership.get(r.ownership_category, 0) + 1
        if r.origin_city:
            by_origin[r.origin_city] = by_origin.get(r.origin_city, 0) + 1
        hourly[r.timestamp.hour] = hourly.get(r.timestamp.hour, 0) + 1

    alert_res = await db.execute(
        select(func.count()).select_from(Alert).where(
            Alert.created_at >= day_start,
            Alert.created_at <= day_end,
        )
    )
    total_alerts = alert_res.scalar_one()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm,
                             topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    # ── Header ─────────────────────────────────────────────────────────────
    title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=18,
                                  spaceAfter=6)
    story.append(Paragraph("Government of Nepal", styles["Normal"]))
    story.append(Paragraph("Department of Transport Management", styles["Normal"]))
    story.append(Paragraph("Nepal Traffic AI — Vehicle Checkpoint Report", title_style))
    story.append(Paragraph(
        f"Checkpoint: {settings.CHECKPOINT_NAME} | Date: {day.strftime('%B %d, %Y')}",
        styles["Normal"]
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1D9E75")))
    story.append(Spacer(1, 0.5*cm))

    # ── Summary table ───────────────────────────────────────────────────────
    story.append(Paragraph("Summary", styles["Heading2"]))
    summary_data = [
        ["Metric", "Value"],
        ["Total Vehicles", str(len(rows))],
        ["Total Alerts", str(total_alerts)],
        ["Flagged Vehicles", str(sum(1 for r in rows if r.flagged))],
        ["DoTM Registered", str(sum(1 for r in rows if r.dotm_registered))],
        ["Unregistered", str(sum(1 for r in rows if not r.dotm_registered))],
    ]
    t = Table(summary_data, colWidths=[8*cm, 6*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1D9E75")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))

    # ── Vehicle type breakdown ──────────────────────────────────────────────
    story.append(Paragraph("Vehicle Type Breakdown", styles["Heading2"]))
    type_data = [["Type", "Count", "%"]] + [
        [k, str(v), f"{v/max(len(rows),1)*100:.1f}%"]
        for k, v in sorted(by_type.items(), key=lambda x: x[1], reverse=True)
    ]
    t2 = Table(type_data, colWidths=[6*cm, 4*cm, 4*cm])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F6E56")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
    ]))
    story.append(t2)
    story.append(Spacer(1, 0.5*cm))

    # ── Top 10 origin cities ────────────────────────────────────────────────
    story.append(Paragraph("Top Origin Cities", styles["Heading2"]))
    top_origins = sorted(by_origin.items(), key=lambda x: x[1], reverse=True)[:10]
    if top_origins:
        origin_data = [["City", "Count"]] + [[c, str(n)] for c, n in top_origins]
        t3 = Table(origin_data, colWidths=[8*cm, 4*cm])
        t3.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#185FA5")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
        ]))
        story.append(t3)
        story.append(Spacer(1, 0.5*cm))

    # ── Hourly traffic table ────────────────────────────────────────────────
    story.append(Paragraph("Hourly Traffic Count", styles["Heading2"]))
    hourly_data = [["Hour", "Count"]] + [
        [f"{h:02d}:00", str(hourly.get(h, 0))] for h in range(24)
    ]
    # Split into two columns
    half = 12
    left  = hourly_data[:half+1]
    right = hourly_data[half+1:]
    combined = [["Hour", "Count", "Hour", "Count"]]
    for i in range(half):
        l = left[i+1] if i+1 < len(left)  else ["", ""]
        r = right[i]  if i   < len(right) else ["", ""]
        combined.append(l + r)
    t4 = Table(combined, colWidths=[3*cm, 2.5*cm, 3*cm, 2.5*cm])
    t4.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#378ADD")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
    ]))
    story.append(t4)

    doc.build(story)
    buf.seek(0)
    filename = f"traffic_report_{day.isoformat()}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
