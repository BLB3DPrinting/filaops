"""
Seed 4 printers (Alpha/Bravo/Charlie/Delta) + maintenance history.

Capability shapes are deliberately mixed:
- Alpha/Bravo/Delta: Vendor A Model X1 with AMS, camera, enclosure.
- Charlie: Vendor B Model S2 — camera only. The ams_slots key is
  OMITTED (not set to 0) so the UI's 'badge absent' render path is
  exercised, not just the 'badge shows 0' path.
- Delta: status='offline', overdue maintenance badge (last service
  > next_due_at).

12 maintenance logs spread across the 90-day window.
"""
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.maintenance import MaintenanceLog
from app.models.printer import Printer

from scripts.seed_data import _time


PRINTER_FIXTURES = [
    {
        "code": "P-001",
        "name": "Alpha",
        "brand": "vendor_a",
        "model": "Model X1",
        "status": "idle",
        "capabilities": {
            "ams_slots": 4,
            "camera": True,
            "enclosure": True,
            "bed_size": [256, 256, 256],
        },
    },
    {
        "code": "P-002",
        "name": "Bravo",
        "brand": "vendor_a",
        "model": "Model X1",
        "status": "printing",
        "capabilities": {
            "ams_slots": 4,
            "camera": True,
            "enclosure": True,
            "bed_size": [256, 256, 256],
        },
    },
    {
        "code": "P-003",
        "name": "Charlie",
        "brand": "vendor_b",
        "model": "Model S2",
        "status": "idle",
        "capabilities": {
            "camera": True,
            "enclosure": False,
            "bed_size": [220, 220, 250],
        },
    },
    {
        "code": "P-004",
        "name": "Delta",
        "brand": "vendor_a",
        "model": "Model X1",
        "status": "offline",
        "capabilities": {
            "ams_slots": 4,
            "camera": True,
            "enclosure": True,
            "bed_size": [256, 256, 256],
        },
    },
]


def seed(db: Session, context: dict[str, Any]) -> None:
    now = _time.now()
    rng = _time.rng()

    printers: list[Printer] = []
    for fx in PRINTER_FIXTURES:
        last_seen = now if fx["status"] != "offline" else now - timedelta(days=3)
        p = Printer(
            code=fx["code"],
            name=fx["name"],
            brand=fx["brand"],
            model=fx["model"],
            status=fx["status"],
            capabilities=fx["capabilities"],
            location="Main Shop",
            active=True,
            last_seen=last_seen,
            created_at=now - timedelta(days=540),
            updated_at=now,
        )
        db.add(p)
        printers.append(p)
    db.flush()

    maintenance_types = ["routine", "calibration", "cleaning", "repair"]
    logs_per_printer = {p.code: 0 for p in printers}

    for i in range(12):
        printer = printers[i % 4]
        days_back = rng.randint(5, 85)
        mtype = maintenance_types[i % len(maintenance_types)]
        performed_at = now - timedelta(days=days_back)

        if printer.code == "P-004" and logs_per_printer["P-004"] == 0:
            last_routine_days = 45
            performed_at = now - timedelta(days=last_routine_days)
            next_due = performed_at + timedelta(days=30)
        else:
            next_due = performed_at + timedelta(days=rng.randint(30, 60))

        db.add(
            MaintenanceLog(
                printer_id=printer.id,
                maintenance_type=mtype,
                description=f"{mtype.title()} service on {printer.name}",
                performed_by="Demo Operator",
                performed_at=performed_at,
                next_due_at=next_due,
                cost=Decimal(f"{rng.randint(15, 120)}.00"),
                downtime_minutes=rng.randint(10, 90),
                parts_used=None,
                notes=None,
                created_at=performed_at,
            )
        )
        logs_per_printer[printer.code] += 1

    db.flush()

    context["printer_ids"] = {p.code: p.id for p in printers}
    print(f"[seed]   {len(printers)} printers, 12 maintenance logs")
