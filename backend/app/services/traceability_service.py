"""
Traceability Service -- lot tracking, serial numbers, and recall queries.

Extracted from admin/traceability.py and traceability.py (ARCHITECT-003).
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import Integer, cast, desc, func, or_
from sqlalchemy.orm import Session, joinedload

from app.logging_config import get_logger
from app.models.material_spool import MaterialSpool, ProductionOrderSpool
from app.models.product import Product
from app.models.production_order import ProductionOrder
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.sales_order import SalesOrder
from app.models.traceability import (
    CustomerTraceabilityProfile,
    MaterialLot,
    ProductionLotConsumption,
    SerialNumber,
)
from app.models.user import User
from app.models.vendor import Vendor
from app.schemas.traceability import (
    CustomerTraceabilityProfileCreate,
    CustomerTraceabilityProfileUpdate,
    MaterialLotCreate,
    MaterialLotListResponse,
    MaterialLotResponse,
    MaterialLotUpdate,
    MaterialLotUsed,
    ProductionLotConsumptionCreate,
    RecallAffectedProduct,
    RecallBackwardQueryResponse,
    RecallForwardQueryResponse,
    SerialNumberCreate,
    SerialNumberListResponse,
    SerialNumberUpdate,
)

logger = get_logger(__name__)

VALID_TRACEABILITY_LEVELS = ["none", "lot", "serial", "full"]


# ---- Helpers ----------------------------------------------------------------

def _build_material_lot_response(lot: MaterialLot) -> MaterialLotResponse:
    """Build a MaterialLotResponse from a MaterialLot ORM instance."""
    return MaterialLotResponse(
        id=lot.id,
        lot_number=lot.lot_number,
        product_id=lot.product_id,
        vendor_id=lot.vendor_id,
        purchase_order_id=lot.purchase_order_id,
        vendor_lot_number=lot.vendor_lot_number,
        quantity_received=lot.quantity_received,
        quantity_consumed=lot.quantity_consumed or Decimal(0),
        quantity_scrapped=lot.quantity_scrapped or Decimal(0),
        quantity_adjusted=lot.quantity_adjusted or Decimal(0),
        quantity_remaining=lot.quantity_remaining,
        status=lot.status,
        certificate_of_analysis=lot.certificate_of_analysis,
        coa_file_path=lot.coa_file_path,
        inspection_status=lot.inspection_status,
        manufactured_date=lot.manufactured_date,
        expiration_date=lot.expiration_date,
        received_date=lot.received_date,
        unit_cost=lot.unit_cost,
        location=lot.location,
        notes=lot.notes,
        created_at=lot.created_at,
        updated_at=lot.updated_at,
    )


def _get_purchase_info_for_spool(db: Session, spool: MaterialSpool) -> Optional[dict]:
    """Look up purchase order info for a spool based on its product."""
    if not spool.product:
        return None

    po_line = (
        db.query(PurchaseOrderLine)
        .filter(PurchaseOrderLine.product_id == spool.product.id)
        .order_by(desc(PurchaseOrderLine.created_at))
        .first()
    )
    if not po_line:
        return None

    po = (
        db.query(PurchaseOrder)
        .options(joinedload(PurchaseOrder.vendor))
        .filter(PurchaseOrder.id == po_line.purchase_order_id)
        .first()
    )
    if not po:
        return None

    return {
        "po_number": po.po_number,
        "vendor_name": po.vendor.name if po.vendor else None,
        "vendor_id": po.vendor_id,
        "order_date": po.order_date.isoformat() if po.order_date else None,
        "received_date": po.received_date.isoformat() if po.received_date else None,
    }


# ---- Customer Traceability Profiles ----------------------------------------

def list_traceability_profiles(
    db: Session,
    *,
    traceability_level: Optional[str] = None,
) -> list:
    """List all customer traceability profiles, optionally filtered by level."""
    query = db.query(CustomerTraceabilityProfile)

    if traceability_level:
        query = query.filter(
            CustomerTraceabilityProfile.traceability_level == traceability_level
        )

    return query.all()


def get_traceability_profile(db: Session, user_id: int) -> CustomerTraceabilityProfile:
    """Get the traceability profile for a specific customer."""
    profile = (
        db.query(CustomerTraceabilityProfile)
        .filter(CustomerTraceabilityProfile.user_id == user_id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Traceability profile not found")
    return profile


def create_traceability_profile(
    db: Session,
    data: CustomerTraceabilityProfileCreate,
) -> CustomerTraceabilityProfile:
    """Create a traceability profile for a customer."""
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    existing = (
        db.query(CustomerTraceabilityProfile)
        .filter(CustomerTraceabilityProfile.user_id == data.user_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Profile already exists for this user"
        )

    if data.traceability_level not in VALID_TRACEABILITY_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid traceability level. Must be one of: {VALID_TRACEABILITY_LEVELS}",
        )

    profile = CustomerTraceabilityProfile(**data.model_dump())
    db.add(profile)

    # Also update user's traceability_level for quick access
    user.traceability_level = data.traceability_level

    db.commit()
    db.refresh(profile)

    return profile


def update_traceability_profile(
    db: Session,
    user_id: int,
    data: CustomerTraceabilityProfileUpdate,
) -> CustomerTraceabilityProfile:
    """Update a customer's traceability profile."""
    profile = (
        db.query(CustomerTraceabilityProfile)
        .filter(CustomerTraceabilityProfile.user_id == user_id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    update_data = data.model_dump(exclude_unset=True)

    if "traceability_level" in update_data:
        if update_data["traceability_level"] not in VALID_TRACEABILITY_LEVELS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid traceability level. Must be one of: {VALID_TRACEABILITY_LEVELS}",
            )

    for field, value in update_data.items():
        setattr(profile, field, value)

    profile.updated_at = datetime.now(timezone.utc)

    # Update user's quick-access field
    if "traceability_level" in update_data:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.traceability_level = update_data["traceability_level"]

    db.commit()
    db.refresh(profile)

    return profile


# ---- Material Lots ----------------------------------------------------------

def list_material_lots(
    db: Session,
    *,
    product_id: Optional[int] = None,
    status: Optional[str] = None,
    vendor_id: Optional[int] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> MaterialLotListResponse:
    """List material lots with filtering and pagination."""
    query = db.query(MaterialLot)

    if product_id:
        query = query.filter(MaterialLot.product_id == product_id)
    if status:
        query = query.filter(MaterialLot.status == status)
    if vendor_id:
        query = query.filter(MaterialLot.vendor_id == vendor_id)
    if search:
        query = query.filter(
            or_(
                MaterialLot.lot_number.ilike(f"%{search}%"),
                MaterialLot.vendor_lot_number.ilike(f"%{search}%"),
            )
        )

    total = query.count()

    lots = (
        query.order_by(desc(MaterialLot.received_date))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [_build_material_lot_response(lot) for lot in lots]

    return MaterialLotListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


def get_material_lot(db: Session, lot_id: int) -> MaterialLotResponse:
    """Get a specific material lot by ID."""
    lot = db.query(MaterialLot).filter(MaterialLot.id == lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Material lot not found")
    return _build_material_lot_response(lot)


def create_material_lot(db: Session, data: MaterialLotCreate) -> MaterialLotResponse:
    """Create a new material lot (typically when receiving materials)."""
    product = db.query(Product).filter(Product.id == data.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    existing = (
        db.query(MaterialLot)
        .filter(MaterialLot.lot_number == data.lot_number)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Lot number already exists")

    lot_data = data.model_dump()
    if not lot_data.get("received_date"):
        lot_data["received_date"] = date.today()

    lot = MaterialLot(**lot_data)
    db.add(lot)
    db.commit()
    db.refresh(lot)

    return _build_material_lot_response(lot)


def update_material_lot(
    db: Session,
    lot_id: int,
    data: MaterialLotUpdate,
) -> MaterialLotResponse:
    """Update a material lot."""
    lot = db.query(MaterialLot).filter(MaterialLot.id == lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Material lot not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(lot, field, value)

    lot.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(lot)

    return _build_material_lot_response(lot)


def generate_lot_number(db: Session, material_code: str) -> dict:
    """Generate the next lot number for a material.

    Uses DB-side numeric extraction to avoid lexicographic ordering issues.
    """
    year = datetime.now(timezone.utc).year
    prefix = f"{material_code}-{year}-"

    max_seq = (
        db.query(
            func.max(
                cast(func.replace(MaterialLot.lot_number, prefix, ""), Integer)
            )
        )
        .filter(MaterialLot.lot_number.like(f"{prefix}%"))
        .scalar()
        or 0
    )

    return {"lot_number": f"{prefix}{max_seq + 1:04d}"}


# ---- Serial Numbers --------------------------------------------------------

def list_serial_numbers(
    db: Session,
    *,
    product_id: Optional[int] = None,
    production_order_id: Optional[int] = None,
    status: Optional[str] = None,
    sales_order_id: Optional[int] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> SerialNumberListResponse:
    """List serial numbers with filtering and pagination."""
    query = db.query(SerialNumber)

    if product_id:
        query = query.filter(SerialNumber.product_id == product_id)
    if production_order_id:
        query = query.filter(SerialNumber.production_order_id == production_order_id)
    if status:
        query = query.filter(SerialNumber.status == status)
    if sales_order_id:
        query = query.filter(SerialNumber.sales_order_id == sales_order_id)
    if search:
        query = query.filter(SerialNumber.serial_number.ilike(f"%{search}%"))

    total = query.count()

    serials = (
        query.order_by(desc(SerialNumber.manufactured_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return SerialNumberListResponse(
        items=serials,
        total=total,
        page=page,
        page_size=page_size,
    )


def get_serial_number(db: Session, serial_id: int) -> SerialNumber:
    """Get a specific serial number by ID."""
    serial = db.query(SerialNumber).filter(SerialNumber.id == serial_id).first()
    if not serial:
        raise HTTPException(status_code=404, detail="Serial number not found")
    return serial


def lookup_serial_number(db: Session, serial_number: str) -> SerialNumber:
    """Look up a serial number by the serial string."""
    serial = (
        db.query(SerialNumber)
        .filter(SerialNumber.serial_number == serial_number)
        .first()
    )
    if not serial:
        raise HTTPException(status_code=404, detail="Serial number not found")
    return serial


def create_serial_numbers(db: Session, data: SerialNumberCreate) -> list[SerialNumber]:
    """Generate serial numbers for a production order."""
    po = (
        db.query(ProductionOrder)
        .filter(ProductionOrder.id == data.production_order_id)
        .first()
    )
    if not po:
        raise HTTPException(status_code=404, detail="Production order not found")

    product = db.query(Product).filter(Product.id == data.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")
    prefix = f"BLB-{date_str}-"

    # DB-side numeric extraction to avoid lexicographic ordering issues
    seq = (
        db.query(
            func.max(
                cast(func.replace(SerialNumber.serial_number, prefix, ""), Integer)
            )
        )
        .filter(SerialNumber.serial_number.like(f"{prefix}%"))
        .scalar()
        or 0
    )

    created_serials = []
    for _ in range(data.quantity):
        seq += 1
        serial = SerialNumber(
            serial_number=f"{prefix}{seq:04d}",
            product_id=data.product_id,
            production_order_id=data.production_order_id,
            status="manufactured",
            qc_passed=data.qc_passed,
            qc_notes=data.qc_notes,
            manufactured_at=now,
        )
        db.add(serial)
        created_serials.append(serial)

    db.commit()
    for s in created_serials:
        db.refresh(s)

    return created_serials


def update_serial_number(
    db: Session,
    serial_id: int,
    data: SerialNumberUpdate,
) -> SerialNumber:
    """Update a serial number (e.g., mark as sold, shipped, returned)."""
    serial = db.query(SerialNumber).filter(SerialNumber.id == serial_id).first()
    if not serial:
        raise HTTPException(status_code=404, detail="Serial number not found")

    update_data = data.model_dump(exclude_unset=True)

    # Handle status-based timestamp updates
    if "status" in update_data:
        new_status = update_data["status"]
        if new_status == "sold" and not serial.sold_at:
            serial.sold_at = datetime.now(timezone.utc)
        elif new_status == "shipped" and not serial.shipped_at:
            serial.shipped_at = datetime.now(timezone.utc)
        elif new_status == "returned" and not serial.returned_at:
            serial.returned_at = datetime.now(timezone.utc)

    for field, value in update_data.items():
        setattr(serial, field, value)

    db.commit()
    db.refresh(serial)
    return serial


# ---- Lot Consumption -------------------------------------------------------

def record_lot_consumption(
    db: Session,
    data: ProductionLotConsumptionCreate,
) -> ProductionLotConsumption:
    """Record material lot consumption for a production order."""
    po = (
        db.query(ProductionOrder)
        .filter(ProductionOrder.id == data.production_order_id)
        .first()
    )
    if not po:
        raise HTTPException(status_code=404, detail="Production order not found")

    lot = db.query(MaterialLot).filter(MaterialLot.id == data.material_lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Material lot not found")

    if lot.quantity_remaining < data.quantity_consumed:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient quantity in lot. Available: {lot.quantity_remaining}",
        )

    consumption = ProductionLotConsumption(**data.model_dump())
    db.add(consumption)

    lot.quantity_consumed = lot.quantity_consumed + data.quantity_consumed

    if lot.quantity_remaining <= 0:
        lot.status = "depleted"

    lot.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(consumption)
    return consumption


def get_production_lot_consumptions(
    db: Session,
    production_order_id: int,
) -> list[ProductionLotConsumption]:
    """Get all lot consumptions for a production order."""
    return (
        db.query(ProductionLotConsumption)
        .filter(ProductionLotConsumption.production_order_id == production_order_id)
        .all()
    )


# ---- Recall Queries (MaterialLot-based, from admin/traceability.py) ---------

def recall_forward_query(db: Session, lot_number: str) -> RecallForwardQueryResponse:
    """
    Forward recall query: What did we make with this lot?

    Returns all products/serial numbers that used material from this lot.
    """
    lot = (
        db.query(MaterialLot)
        .filter(MaterialLot.lot_number == lot_number)
        .first()
    )
    if not lot:
        raise HTTPException(status_code=404, detail="Material lot not found")

    product = db.query(Product).filter(Product.id == lot.product_id).first()
    material_name = product.name if product else "Unknown"

    affected = (
        db.query(
            SerialNumber.serial_number,
            Product.name.label("product_name"),
            ProductionOrder.code.label("production_order_code"),
            SerialNumber.manufactured_at,
            SerialNumber.status,
            User.email.label("customer_email"),
            SalesOrder.order_number.label("sales_order_number"),
            SerialNumber.shipped_at,
        )
        .join(
            ProductionLotConsumption,
            ProductionLotConsumption.production_order_id
            == SerialNumber.production_order_id,
        )
        .join(Product, Product.id == SerialNumber.product_id)
        .join(
            ProductionOrder,
            ProductionOrder.id == SerialNumber.production_order_id,
        )
        .outerjoin(SalesOrder, SalesOrder.id == SerialNumber.sales_order_id)
        .outerjoin(User, User.id == SalesOrder.user_id)
        .filter(ProductionLotConsumption.material_lot_id == lot.id)
        .all()
    )

    affected_products = [
        RecallAffectedProduct(
            serial_number=row.serial_number,
            product_name=row.product_name,
            production_order_code=row.production_order_code,
            manufactured_at=row.manufactured_at,
            status=row.status,
            customer_email=row.customer_email,
            sales_order_number=row.sales_order_number,
            shipped_at=row.shipped_at,
        )
        for row in affected
    ]

    return RecallForwardQueryResponse(
        lot_number=lot.lot_number,
        material_name=material_name,
        quantity_received=lot.quantity_received,
        quantity_consumed=lot.quantity_consumed,
        affected_products=affected_products,
        total_affected=len(affected_products),
    )


def recall_backward_query(
    db: Session,
    serial_number: str,
) -> RecallBackwardQueryResponse:
    """
    Backward recall query: What material lots went into this serial number?

    Returns all material lots used to produce this unit.
    """
    serial = (
        db.query(SerialNumber)
        .filter(SerialNumber.serial_number == serial_number)
        .first()
    )
    if not serial:
        raise HTTPException(status_code=404, detail="Serial number not found")

    product = db.query(Product).filter(Product.id == serial.product_id).first()
    product_name = product.name if product else "Unknown"

    lots_used = (
        db.query(
            MaterialLot.lot_number,
            Product.name.label("material_name"),
            Vendor.name.label("vendor_name"),
            MaterialLot.vendor_lot_number,
            ProductionLotConsumption.quantity_consumed,
        )
        .join(
            ProductionLotConsumption,
            ProductionLotConsumption.material_lot_id == MaterialLot.id,
        )
        .join(Product, Product.id == MaterialLot.product_id)
        .outerjoin(Vendor, Vendor.id == MaterialLot.vendor_id)
        .filter(
            ProductionLotConsumption.production_order_id
            == serial.production_order_id
        )
        .all()
    )

    material_lots = [
        MaterialLotUsed(
            lot_number=row.lot_number,
            material_name=row.material_name,
            vendor_name=row.vendor_name,
            vendor_lot_number=row.vendor_lot_number,
            quantity_consumed=row.quantity_consumed,
        )
        for row in lots_used
    ]

    return RecallBackwardQueryResponse(
        serial_number=serial.serial_number,
        product_name=product_name,
        manufactured_at=serial.manufactured_at,
        material_lots_used=material_lots,
    )


# ---- Spool-based Traceability (from traceability.py) ------------------------

def trace_forward_from_spool(db: Session, spool_id: int) -> dict:
    """
    Trace a spool forward to all products and customers.

    Returns spool details, production orders that used this spool,
    linked sales orders, serial numbers produced, and customer info.
    """
    spool = (
        db.query(MaterialSpool)
        .options(
            joinedload(MaterialSpool.product),
            joinedload(MaterialSpool.location),
        )
        .filter(MaterialSpool.id == spool_id)
        .first()
    )
    if not spool:
        raise HTTPException(status_code=404, detail="Spool not found")

    spool_usage = (
        db.query(ProductionOrderSpool)
        .options(
            joinedload(ProductionOrderSpool.production_order).joinedload(
                ProductionOrder.product
            ),
            joinedload(ProductionOrderSpool.production_order).joinedload(
                ProductionOrder.sales_order
            ),
        )
        .filter(ProductionOrderSpool.spool_id == spool_id)
        .order_by(desc(ProductionOrderSpool.created_at))
        .all()
    )

    # Strip vendor_id from the purchase info (not used in forward trace)
    purchase_info = _get_purchase_info_for_spool(db, spool)
    if purchase_info:
        purchase_info.pop("vendor_id", None)

    usage_tree = []
    total_consumed_g = Decimal("0")
    affected_customers: set[str] = set()
    affected_sales_orders: set[str] = set()
    total_units_produced = 0

    for usage in spool_usage:
        po = usage.production_order
        if not po:
            continue

        serials = (
            db.query(SerialNumber)
            .filter(SerialNumber.production_order_id == po.id)
            .all()
        )

        sales_order_info = None
        if po.sales_order:
            sales_order_info = {
                "id": po.sales_order.id,
                "order_number": po.sales_order.order_number,
                "customer_name": po.sales_order.customer_name,
                "customer_email": po.sales_order.customer_email,
                "ship_date": (
                    po.sales_order.ship_date.isoformat()
                    if po.sales_order.ship_date
                    else None
                ),
                "status": po.sales_order.status,
            }
            affected_customers.add(
                po.sales_order.customer_name or po.sales_order.customer_email
            )
            affected_sales_orders.add(po.sales_order.order_number)

        consumed_g = float(usage.weight_consumed_kg or 0)  # Actually in grams
        total_consumed_g += Decimal(str(consumed_g))
        total_units_produced += int(po.quantity_completed or 0)

        usage_tree.append(
            {
                "production_order": {
                    "id": po.id,
                    "code": po.code,
                    "product_sku": po.product.sku if po.product else None,
                    "product_name": po.product.name if po.product else None,
                    "quantity_produced": float(po.quantity_completed or 0),
                    "completed_date": (
                        po.completed_date.isoformat()
                        if po.completed_date
                        else None
                    ),
                    "status": po.status,
                },
                "material_consumed_g": consumed_g,
                "sales_order": sales_order_info,
                "serial_numbers": [
                    {
                        "serial_number": sn.serial_number,
                        "status": sn.status,
                        "created_at": (
                            sn.created_at.isoformat() if sn.created_at else None
                        ),
                    }
                    for sn in serials
                ],
            }
        )

    return {
        "spool": {
            "id": spool.id,
            "spool_number": spool.spool_number,
            "material_sku": spool.product.sku if spool.product else None,
            "material_name": spool.product.name if spool.product else None,
            "initial_weight_g": float(spool.initial_weight_kg or 0),
            "current_weight_g": float(spool.current_weight_kg or 0),
            "consumed_g": float(total_consumed_g),
            "remaining_percent": (
                spool.weight_remaining_percent
                if hasattr(spool, "weight_remaining_percent")
                else 0
            ),
            "status": spool.status,
            "supplier_lot_number": spool.supplier_lot_number,
            "received_date": (
                spool.received_date.isoformat() if spool.received_date else None
            ),
            "expiry_date": (
                spool.expiry_date.isoformat() if spool.expiry_date else None
            ),
            "location": spool.location.name if spool.location else None,
        },
        "purchase_info": purchase_info,
        "usage": usage_tree,
        "summary": {
            "total_production_orders": len(usage_tree),
            "total_consumed_g": float(total_consumed_g),
            "total_units_produced": total_units_produced,
            "affected_sales_orders": len(affected_sales_orders),
            "affected_customers": len(affected_customers),
            "customers": list(affected_customers),
        },
    }


def trace_backward_from_serial(db: Session, serial_number: str) -> dict:
    """
    Trace a serial number back to source materials and vendor.

    Returns serial details, production order, product, all spools
    used in production, and purchase/vendor info for each spool.
    """
    serial = (
        db.query(SerialNumber)
        .options(
            joinedload(SerialNumber.production_order).joinedload(
                ProductionOrder.product
            ),
            joinedload(SerialNumber.production_order).joinedload(
                ProductionOrder.sales_order
            ),
        )
        .filter(SerialNumber.serial_number == serial_number)
        .first()
    )
    if not serial:
        raise HTTPException(
            status_code=404, detail=f"Serial number '{serial_number}' not found"
        )

    po = serial.production_order
    if not po:
        raise HTTPException(
            status_code=404, detail="Production order not found for this serial"
        )

    spools_used = (
        db.query(ProductionOrderSpool)
        .options(
            joinedload(ProductionOrderSpool.spool).joinedload(MaterialSpool.product),
            joinedload(ProductionOrderSpool.spool).joinedload(MaterialSpool.location),
        )
        .filter(ProductionOrderSpool.production_order_id == po.id)
        .all()
    )

    material_lineage = []
    for spool_usage in spools_used:
        spool = spool_usage.spool
        if not spool:
            continue

        purchase_info = _get_purchase_info_for_spool(db, spool)

        material_lineage.append(
            {
                "spool": {
                    "id": spool.id,
                    "spool_number": spool.spool_number,
                    "material_sku": spool.product.sku if spool.product else None,
                    "material_name": spool.product.name if spool.product else None,
                    "supplier_lot_number": spool.supplier_lot_number,
                    "received_date": (
                        spool.received_date.isoformat()
                        if spool.received_date
                        else None
                    ),
                    "expiry_date": (
                        spool.expiry_date.isoformat()
                        if spool.expiry_date
                        else None
                    ),
                },
                "weight_consumed_g": float(
                    spool_usage.weight_consumed_kg or 0
                ),  # Actually grams
                "purchase_order": purchase_info,
            }
        )

    sales_order_info = None
    if po.sales_order:
        sales_order_info = {
            "id": po.sales_order.id,
            "order_number": po.sales_order.order_number,
            "customer_name": po.sales_order.customer_name,
            "customer_email": po.sales_order.customer_email,
            "ship_date": (
                po.sales_order.ship_date.isoformat()
                if po.sales_order.ship_date
                else None
            ),
            "status": po.sales_order.status,
        }

    return {
        "serial_number": {
            "serial_number": serial.serial_number,
            "status": serial.status,
            "created_at": (
                serial.created_at.isoformat() if serial.created_at else None
            ),
        },
        "product": {
            "id": po.product.id if po.product else None,
            "sku": po.product.sku if po.product else None,
            "name": po.product.name if po.product else None,
        },
        "production_order": {
            "id": po.id,
            "code": po.code,
            "quantity_produced": float(po.quantity_completed or 0),
            "completed_date": (
                po.completed_date.isoformat() if po.completed_date else None
            ),
            "status": po.status,
        },
        "sales_order": sales_order_info,
        "material_lineage": material_lineage,
        "traceability_chain": {
            "complete": len(material_lineage) > 0,
            "spools_used": len(material_lineage),
            "vendors": len(
                set(
                    m["purchase_order"]["vendor_name"]
                    for m in material_lineage
                    if m["purchase_order"] and m["purchase_order"].get("vendor_name")
                )
            ),
        },
    }


def trace_backward_from_sales_order(db: Session, so_id: int) -> dict:
    """
    Trace a sales order back to all source materials.

    Useful for answering: "What materials went into this entire order?"
    """
    sales_order = db.query(SalesOrder).filter(SalesOrder.id == so_id).first()
    if not sales_order:
        raise HTTPException(status_code=404, detail="Sales order not found")

    production_orders = (
        db.query(ProductionOrder)
        .options(joinedload(ProductionOrder.product))
        .filter(ProductionOrder.sales_order_id == so_id)
        .all()
    )

    all_spools: dict[int, dict] = {}
    total_material_g = Decimal("0")

    for po in production_orders:
        spools_used = (
            db.query(ProductionOrderSpool)
            .options(
                joinedload(ProductionOrderSpool.spool).joinedload(
                    MaterialSpool.product
                )
            )
            .filter(ProductionOrderSpool.production_order_id == po.id)
            .all()
        )

        for spool_usage in spools_used:
            spool = spool_usage.spool
            if not spool:
                continue

            weight_g = Decimal(str(spool_usage.weight_consumed_kg or 0))
            total_material_g += weight_g

            if spool.id not in all_spools:
                all_spools[spool.id] = {
                    "spool_number": spool.spool_number,
                    "material_sku": spool.product.sku if spool.product else None,
                    "material_name": spool.product.name if spool.product else None,
                    "supplier_lot_number": spool.supplier_lot_number,
                    "total_consumed_g": 0,
                    "used_in_orders": [],
                }

            all_spools[spool.id]["total_consumed_g"] += float(weight_g)
            all_spools[spool.id]["used_in_orders"].append(
                {
                    "production_order_code": po.code,
                    "product_sku": po.product.sku if po.product else None,
                    "weight_consumed_g": float(weight_g),
                }
            )

    return {
        "sales_order": {
            "id": sales_order.id,
            "order_number": sales_order.order_number,
            "customer_name": sales_order.customer_name,
            "customer_email": sales_order.customer_email,
            "status": sales_order.status,
        },
        "production_orders": [
            {
                "code": po.code,
                "product_sku": po.product.sku if po.product else None,
                "product_name": po.product.name if po.product else None,
                "quantity": float(po.quantity_completed or 0),
            }
            for po in production_orders
        ],
        "materials_used": list(all_spools.values()),
        "summary": {
            "total_production_orders": len(production_orders),
            "unique_spools": len(all_spools),
            "total_material_g": float(total_material_g),
        },
    }


def calculate_recall_impact(db: Session, spool_ids: list[int]) -> dict:
    """
    Calculate the impact of recalling specific spools.

    Returns all affected production orders, sales orders, customers,
    and serial numbers, along with a severity rating.
    """
    if not spool_ids:
        raise HTTPException(status_code=400, detail="No spool IDs provided")

    affected_pos = (
        db.query(ProductionOrderSpool)
        .options(
            joinedload(ProductionOrderSpool.production_order).joinedload(
                ProductionOrder.product
            ),
            joinedload(ProductionOrderSpool.production_order).joinedload(
                ProductionOrder.sales_order
            ),
            joinedload(ProductionOrderSpool.spool),
        )
        .filter(ProductionOrderSpool.spool_id.in_(spool_ids))
        .all()
    )

    affected_sales_orders: dict[int, dict] = {}
    affected_customers: set[str] = set()
    affected_serials: list[dict] = []
    affected_products: set[str] = set()

    for po_spool in affected_pos:
        po = po_spool.production_order
        if not po:
            continue

        if po.product:
            affected_products.add(f"{po.product.sku} - {po.product.name}")

        if po.sales_order:
            so = po.sales_order
            if so.id not in affected_sales_orders:
                affected_sales_orders[so.id] = {
                    "order_number": so.order_number,
                    "customer_name": so.customer_name,
                    "customer_email": so.customer_email,
                    "ship_date": (
                        so.ship_date.isoformat() if so.ship_date else None
                    ),
                    "status": so.status,
                    "production_orders": [],
                }
            affected_sales_orders[so.id]["production_orders"].append(po.code)
            affected_customers.add(so.customer_name or so.customer_email)

        serials = (
            db.query(SerialNumber)
            .filter(SerialNumber.production_order_id == po.id)
            .all()
        )
        for serial in serials:
            affected_serials.append(
                {
                    "serial_number": serial.serial_number,
                    "production_order": po.code,
                    "product_sku": po.product.sku if po.product else None,
                    "status": serial.status,
                }
            )

    spools = (
        db.query(MaterialSpool)
        .options(joinedload(MaterialSpool.product))
        .filter(MaterialSpool.id.in_(spool_ids))
        .all()
    )

    spool_details = [
        {
            "id": spool.id,
            "spool_number": spool.spool_number,
            "material_sku": spool.product.sku if spool.product else None,
            "material_name": spool.product.name if spool.product else None,
            "supplier_lot_number": spool.supplier_lot_number,
        }
        for spool in spools
    ]

    customer_count = len(affected_customers)
    if customer_count > 10:
        severity = "HIGH"
    elif customer_count > 0:
        severity = "MEDIUM"
    else:
        severity = "LOW"

    return {
        "spools": spool_details,
        "impact": {
            "production_orders_affected": len(
                set(ps.production_order_id for ps in affected_pos)
            ),
            "sales_orders_affected": len(affected_sales_orders),
            "customers_affected": customer_count,
            "serial_numbers_affected": len(affected_serials),
            "products_affected": len(affected_products),
        },
        "sales_orders": list(affected_sales_orders.values()),
        "customers": list(affected_customers),
        "serial_numbers": affected_serials,
        "products": list(affected_products),
        "severity": severity,
    }
