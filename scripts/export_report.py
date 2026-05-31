"""
scripts/export_report.py
CLI to export CSV or PDF reports from the Nepal Traffic AI system.

Usage:
  python -m scripts.export_report --format csv --date 2024-01-15
  python -m scripts.export_report --format pdf --checkpoint cp-thankot
  python -m scripts.export_report --format csv --start 2024-01-01 --end 2024-01-31
"""
import argparse
import asyncio
import sys
import os
from pathlib import Path
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def export_csv(checkpoint_id=None, start=None, end=None, output_path=None):
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.vehicle import VehicleSighting
    from sqlalchemy import select
    from datetime import datetime
    import csv

    await init_db()

    async with AsyncSessionLocal() as db:
        q = select(VehicleSighting)
        if checkpoint_id:
            q = q.where(VehicleSighting.checkpoint_id == checkpoint_id)
        if start:
            q = q.where(VehicleSighting.timestamp >= datetime.fromisoformat(start))
        if end:
            q = q.where(VehicleSighting.timestamp <= datetime.fromisoformat(end + "T23:59:59"))
        q = q.order_by(VehicleSighting.timestamp.desc())

        result = await db.execute(q)
        rows = result.scalars().all()

    if not output_path:
        output_path = f"traffic_export_{date.today().isoformat()}.csv"

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
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

    print(f"CSV exported: {output_path} ({len(rows)} records)")
    return output_path


async def export_pdf(checkpoint_id=None, report_date=None, output_path=None):
    from backend.database import AsyncSessionLocal, init_db
    from backend.models.vehicle import VehicleSighting, Alert
    from sqlalchemy import select, func
    from datetime import datetime, date as date_type
    import io

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.units import cm
    except ImportError:
        print("reportlab not installed. Run: pip install reportlab")
        return

    await init_db()

    day = date_type.fromisoformat(report_date) if report_date else date_type.today()
    day_start = datetime(day.year, day.month, day.day, 0, 0, 0)
    day_end   = datetime(day.year, day.month, day.day, 23, 59, 59)

    async with AsyncSessionLocal() as db:
        q = select(VehicleSighting).where(
            VehicleSighting.timestamp >= day_start,
            VehicleSighting.timestamp <= day_end,
        )
        if checkpoint_id:
            q = q.where(VehicleSighting.checkpoint_id == checkpoint_id)
        result = await db.execute(q)
        rows = result.scalars().all()

        alert_res = await db.execute(
            select(func.count()).select_from(Alert).where(
                Alert.created_at >= day_start,
                Alert.created_at <= day_end,
            )
        )
        total_alerts = alert_res.scalar_one()

    # Aggregate
    by_type:  dict = {}
    by_own:   dict = {}
    by_origin: dict = {}
    hourly:   dict = {h: 0 for h in range(24)}
    for r in rows:
        by_type[r.vehicle_type] = by_type.get(r.vehicle_type, 0) + 1
        by_own[r.ownership_category] = by_own.get(r.ownership_category, 0) + 1
        if r.origin_city:
            by_origin[r.origin_city] = by_origin.get(r.origin_city, 0) + 1
        hourly[r.timestamp.hour] = hourly.get(r.timestamp.hour, 0) + 1

    if not output_path:
        output_path = f"traffic_report_{day.isoformat()}.pdf"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm,
                             topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story  = []

    story.append(Paragraph("Government of Nepal — Department of Transport Management", styles["Normal"]))
    story.append(Paragraph("Nepal Traffic AI — Daily Checkpoint Report", styles["Title"]))
    story.append(Paragraph(f"Date: {day.strftime('%B %d, %Y')} | Checkpoint: {checkpoint_id or 'All'}", styles["Normal"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1D9E75")))
    story.append(Spacer(1, 0.4*cm))

    summary_data = [
        ["Metric", "Value"],
        ["Total Vehicles",   str(len(rows))],
        ["Total Alerts",     str(total_alerts)],
        ["Flagged",          str(sum(1 for r in rows if r.flagged))],
        ["DoTM Registered",  str(sum(1 for r in rows if r.dotm_registered))],
        ["Unregistered",     str(sum(1 for r in rows if not r.dotm_registered))],
    ]
    t = Table(summary_data, colWidths=[8*cm, 5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1D9E75")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.grey),
    ]))
    story.append(Paragraph("Summary", styles["Heading2"]))
    story.append(t)
    story.append(Spacer(1, 0.4*cm))

    type_data = [["Vehicle Type", "Count"]] + [
        [k, str(v)] for k, v in sorted(by_type.items(), key=lambda x: x[1], reverse=True)
    ]
    t2 = Table(type_data, colWidths=[6*cm, 4*cm])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0F6E56")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.grey),
    ]))
    story.append(Paragraph("Vehicle Types", styles["Heading2"]))
    story.append(t2)

    doc.build(story)
    buf.seek(0)
    with open(output_path, "wb") as f:
        f.write(buf.read())

    print(f"PDF exported: {output_path} ({len(rows)} records)")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Nepal Traffic AI reports")
    parser.add_argument("--format",     choices=["csv", "pdf"], default="csv")
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--date",       default=None, help="YYYY-MM-DD (for PDF)")
    parser.add_argument("--start",      default=None, help="YYYY-MM-DD (for CSV)")
    parser.add_argument("--end",        default=None, help="YYYY-MM-DD (for CSV)")
    parser.add_argument("--output",     default=None, help="Output file path")
    args = parser.parse_args()

    if args.format == "csv":
        asyncio.run(export_csv(args.checkpoint, args.start, args.end, args.output))
    else:
        asyncio.run(export_pdf(args.checkpoint, args.date, args.output))
