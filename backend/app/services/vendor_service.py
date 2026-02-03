"""
Vendor Service — CRUD and metrics for vendors.

Extracted from vendors.py (ARCHITECT-003).
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models.vendor import Vendor
from app.models.purchase_order import PurchaseOrder
from app.core.utils import get_or_404, check_unique_or_400

logger = get_logger(__name__)


def generate_vendor_code(db: Session) -> str:
    """Generate next vendor code (VND-001, VND-002, etc.)."""
    last = db.query(Vendor).order_by(desc(Vendor.code)).first()
    if last and last.code.startswith("VND-"):
        try:
            num = int(last.code.split("-")[1])
            return f"VND-{num + 1:03d}"
        except (IndexError, ValueError):
            pass
    return "VND-001"


def list_vendors(
    db: Session,
    *,
    search: str | None = None,
    active_only: bool = True,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[Vendor], int, dict[int, int]]:
    """
    List vendors with pagination.

    Returns:
        (vendors, total_count, po_counts_by_vendor_id)
    """
    query = db.query(Vendor)

    if active_only:
        query = query.filter(Vendor.is_active.is_(True))

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (Vendor.name.ilike(search_filter))
            | (Vendor.code.ilike(search_filter))
            | (Vendor.contact_name.ilike(search_filter))
            | (Vendor.email.ilike(search_filter))
        )

    total = query.count()
    vendors = query.order_by(Vendor.name).offset(offset).limit(limit).all()

    po_counts = dict(
        db.query(PurchaseOrder.vendor_id, func.count(PurchaseOrder.id))
        .group_by(PurchaseOrder.vendor_id)
        .all()
    )

    return vendors, total, po_counts


def get_vendor(db: Session, vendor_id: int) -> Vendor:
    """Get vendor by ID or raise 404."""
    return get_or_404(db, Vendor, vendor_id, "Vendor not found")


def create_vendor(db: Session, *, data: dict, _max_retries: int = 3) -> Vendor:
    """
    Create a new vendor.

    Retries with a new auto-generated code on IntegrityError (race condition).
    """
    explicit_code = data.pop("code", None)
    code = explicit_code or generate_vendor_code(db)
    check_unique_or_400(db, Vendor, "code", code)

    now = datetime.now(timezone.utc)
    for attempt in range(_max_retries):
        try:
            vendor = Vendor(
                code=code,
                **data,
                created_at=now,
                updated_at=now,
            )
            db.add(vendor)
            db.commit()
            db.refresh(vendor)
            logger.info(f"Created vendor {vendor.code}: {vendor.name}")
            return vendor
        except IntegrityError:
            db.rollback()
            if explicit_code:
                raise  # User-provided code conflict — don't retry
            code = generate_vendor_code(db)
            logger.warning(f"Vendor code collision, retrying with {code} (attempt {attempt + 2})")

    raise HTTPException(status_code=409, detail="Failed to generate unique vendor code")


def update_vendor(db: Session, vendor_id: int, *, data: dict) -> Vendor:
    """
    Update a vendor.

    Args:
        db: Database session
        vendor_id: Vendor ID
        data: Fields to update (from VendorUpdate schema model_dump(exclude_unset=True))
    """
    vendor = get_or_404(db, Vendor, vendor_id, "Vendor not found")

    if "code" in data and data["code"] != vendor.code:
        check_unique_or_400(db, Vendor, "code", data["code"], exclude_id=vendor.id)

    for field, value in data.items():
        setattr(vendor, field, value)

    vendor.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(vendor)

    logger.info(f"Updated vendor {vendor.code}")
    return vendor


def get_vendor_metrics(db: Session, vendor_id: int) -> dict:
    """Get vendor performance metrics (PO count, spend, lead time, on-time %)."""
    vendor = get_or_404(db, Vendor, vendor_id, "Vendor not found")

    pos = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.vendor_id == vendor_id)
        .order_by(desc(PurchaseOrder.created_at))
        .all()
    )

    total_spend = sum(float(po.total_amount or 0) for po in pos)

    lead_times = []
    on_time_count = 0
    received_count = 0

    for po in pos:
        if po.order_date and po.received_date:
            days = (po.received_date - po.order_date).days
            lead_times.append(days)
            received_count += 1
            if po.expected_date and po.received_date <= po.expected_date:
                on_time_count += 1

    avg_lead_time = sum(lead_times) / len(lead_times) if lead_times else None
    on_time_pct = (on_time_count / received_count * 100) if received_count > 0 else None

    recent_pos = [
        {
            "id": po.id,
            "po_number": po.po_number,
            "status": po.status,
            "order_date": po.order_date.isoformat() if po.order_date else None,
            "total_amount": float(po.total_amount or 0),
        }
        for po in pos[:10]
    ]

    return {
        "vendor_id": vendor_id,
        "vendor_name": vendor.name,
        "total_pos": len(pos),
        "total_spend": round(total_spend, 2),
        "avg_lead_time_days": round(avg_lead_time, 1) if avg_lead_time else None,
        "on_time_delivery_pct": round(on_time_pct, 1) if on_time_pct else None,
        "recent_pos": recent_pos,
    }


def delete_vendor(db: Session, vendor_id: int) -> dict:
    """Delete a vendor (soft if has POs, hard if no POs)."""
    vendor = get_or_404(db, Vendor, vendor_id, "Vendor not found")

    po_count = (
        db.query(func.count(PurchaseOrder.id))
        .filter(PurchaseOrder.vendor_id == vendor_id)
        .scalar()
    )

    if po_count > 0:
        vendor.is_active = False
        vendor.updated_at = datetime.now(timezone.utc)
        db.commit()
        return {"message": f"Vendor {vendor.code} deactivated (has {po_count} POs)"}
    else:
        db.delete(vendor)
        db.commit()
        return {"message": f"Vendor {vendor.code} deleted"}
