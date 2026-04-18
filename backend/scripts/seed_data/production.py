"""
Seed 40 production orders + 14 scrap reasons + QC inspection records.

Count scaled from the spec's ~80 down to 40 (same reasoning as
sales_orders.py -- service-layer inserts are the bottleneck and we
want to stay under the 30s seed budget). Status mix preserved:

    completed (closed/passed QC)  15
    in_progress                   10
    accepted_short                 5   (completed qty < ordered qty)
    scrapped                       5   (with ScrapRecord + reason)
    released                       5
    --------------------------------
    Total                         40

ScrapReason: the alembic migration seeds 14 standard reasons but
wipe_all_tables clears them. This module re-seeds the same 14 so
ScrapRecord.scrap_reason_id FKs resolve and the admin UI renders.

Linkage to sales orders:
- All 4 in_production sales orders get a linked in-progress PO.
- 6 additional PO rows are linked to shipped sales orders.
- The remaining 30 are source='manual' (MTS replenishment).

Design note: this module bypasses create_production_order() because
that service calls reserve_production_materials() which would try
to consume actual inventory -- our raw-material stock is intentionally
low (2 items below reorder point per spec). Direct ORM inserts skip
the reservation and keep the module fast.

QC inspection records: per spec-author instruction, record_qc_inspection
fires for 5 of the 15 completed orders even if the Quality Dashboard
UI isn't wired in v4.0.0 -- pre-populates the data for when it lands.
"""
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.production_order import ProductionOrder, ScrapRecord
from app.models.scrap_reason import ScrapReason
from app.services import inventory_service, production_order_service

from scripts.seed_data import _time


SCRAP_REASONS = [
    ("adhesion",        "Bed Adhesion Failure",    "Print failed to adhere to build plate"),
    ("layer_shift",     "Layer Shift",             "Layer shift during print"),
    ("stringing",       "Stringing",               "Excessive stringing / hairs between parts"),
    ("warping",         "Warping",                 "Part warped away from bed"),
    ("nozzle_clog",     "Nozzle Clog",             "Nozzle clogged mid-print"),
    ("damage",          "Post-Print Damage",       "Part damaged during handling or post-processing"),
    ("quality_fail",    "Quality Inspection Fail", "Did not pass QC inspection"),
    ("dimensional",     "Dimensional Tolerance",   "Part out of dimensional spec"),
    ("surface_defect",  "Surface Defect",          "Visible surface quality issue"),
    ("material_defect", "Material Defect",         "Filament defect (moisture, contamination)"),
    ("wrong_material",  "Wrong Material",          "Printed in incorrect material"),
    ("operator_error",  "Operator Error",          "Operator mistake"),
    ("machine_failure", "Machine Failure",         "Printer hardware failure during print"),
    ("other",           "Other",                   "Other reason -- see notes"),
]


def _seed_scrap_reasons(db: Session, now) -> dict[str, int]:
    out: dict[str, int] = {}
    for idx, (code, name, description) in enumerate(SCRAP_REASONS):
        sr = ScrapReason(
            code=code,
            name=name,
            description=description,
            active=True,
            sequence=idx,
            created_at=now,
            updated_at=now,
        )
        db.add(sr)
        db.flush()
        out[code] = sr.id
    return out


def seed(db: Session, context: dict[str, Any]) -> None:
    rng = _time.rng()
    now = _time.now()
    admin_email = context["admin_email"]
    finished_good_ids = context["finished_good_ids"]
    fg_id_list = list(finished_good_ids.values())
    in_production_so_ids = list(context.get("in_production_order_ids", []))
    shipped_so_ids = list(context.get("shipped_order_ids", []))

    scrap_reason_ids = _seed_scrap_reasons(db, now)

    from app.models.bom import BOM
    from app.models.manufacturing import Routing
    from app.models.product import Product
    fg_products = {p.id: p for p in db.query(Product).filter(Product.id.in_(fg_id_list)).all()}
    boms_by_product = {
        b.product_id: b
        for b in db.query(BOM).filter(BOM.product_id.in_(fg_id_list), BOM.active.is_(True)).all()
    }
    routings_by_product = {
        r.product_id: r
        for r in db.query(Routing).filter(Routing.product_id.in_(fg_id_list), Routing.is_active.is_(True)).all()
    }

    linked_so_ids = list(in_production_so_ids)
    if shipped_so_ids:
        linked_so_ids.extend(rng.sample(shipped_so_ids, k=min(6, len(shipped_so_ids))))
    linked_iter = iter(linked_so_ids)

    def _next_linked_so_id() -> int | None:
        return next(linked_iter, None)

    def _new_po(status: str, qty: int, product_id: int, sales_order_id: int | None, days_back: int) -> ProductionOrder:
        created = now - timedelta(days=days_back)
        routing_id = routings_by_product[product_id].id if product_id in routings_by_product else None
        po = ProductionOrder(
            code=production_order_service.generate_production_order_code(db),
            product_id=product_id,
            bom_id=boms_by_product[product_id].id if product_id in boms_by_product else None,
            routing_id=routing_id,
            sales_order_id=sales_order_id,
            quantity_ordered=Decimal(str(qty)),
            quantity_completed=Decimal("0"),
            quantity_scrapped=Decimal("0"),
            source="sales_order" if sales_order_id else "manual",
            order_type="MAKE_TO_ORDER" if sales_order_id else "MAKE_TO_STOCK",
            status=status,
            qc_status="not_required",
            priority=rng.choice([2, 3, 3, 3, 4]),
            due_date=(created + timedelta(days=rng.randint(7, 30))).date(),
            created_by=admin_email,
            created_at=created,
            updated_at=created,
        )
        db.add(po)
        db.flush()

        # Copy routing operations to production_order_operations (+ their
        # materials via routing_operation_materials). Without this the PO
        # detail page shows 'No operations' because we bypassed
        # create_production_order() for inventory-reservation reasons.
        if routing_id:
            production_order_service.copy_routing_to_operations(db, po, routing_id)
            db.flush()

        return po

    def _schedule_ops(po: ProductionOrder, anchor) -> None:
        """Forward-schedule ops: first starts at anchor, each next follows."""
        cursor = anchor
        for op in sorted(po.operations, key=lambda o: o.sequence):
            duration_min = float(op.planned_run_minutes or 0) + float(op.planned_setup_minutes or 0)
            op.scheduled_start = cursor
            op.scheduled_end = cursor + timedelta(minutes=duration_min)
            cursor = op.scheduled_end

    def _mark_ops_complete(po: ProductionOrder, qty_completed: Decimal) -> None:
        """All ops done -- completed / accepted_short buckets."""
        _schedule_ops(po, po.actual_start or po.created_at)
        for op in sorted(po.operations, key=lambda o: o.sequence):
            op.status = "complete"
            op.quantity_completed = qty_completed
            op.actual_setup_minutes = op.planned_setup_minutes
            op.actual_run_minutes = op.planned_run_minutes
            op.actual_start = op.scheduled_start
            op.actual_end = op.scheduled_end
            op.operator_name = "Demo Operator"

    def _mark_ops_in_progress(po: ProductionOrder) -> None:
        """First op complete, second op running, rest pending (scheduled)."""
        ops = sorted(po.operations, key=lambda o: o.sequence)
        if not ops:
            return
        _schedule_ops(po, po.actual_start or po.created_at)
        first = ops[0]
        first.status = "complete"
        first.quantity_completed = po.quantity_ordered
        first.actual_setup_minutes = first.planned_setup_minutes
        first.actual_run_minutes = first.planned_run_minutes
        first.actual_start = first.scheduled_start
        first.actual_end = first.scheduled_end
        first.operator_name = "Demo Operator"
        if len(ops) > 1:
            second = ops[1]
            second.status = "running"
            second.actual_start = second.scheduled_start
            second.operator_name = "Demo Operator"

    def _mark_ops_released(po: ProductionOrder) -> None:
        """All ops pending but scheduled forward from released_at."""
        _schedule_ops(po, po.released_at or po.created_at)

    def _mark_ops_scrapped(po: ProductionOrder, scrap_code: str) -> None:
        """First op complete, second op skipped with scrap_reason."""
        _schedule_ops(po, po.created_at)
        ops = sorted(po.operations, key=lambda o: o.sequence)
        if not ops:
            return
        ops[0].status = "complete"
        ops[0].quantity_completed = Decimal("0")
        ops[0].quantity_scrapped = po.quantity_scrapped
        ops[0].actual_start = ops[0].scheduled_start
        ops[0].actual_end = po.scrapped_at
        ops[0].scrap_reason = scrap_code
        ops[0].operator_name = "Demo Operator"
        for op in ops[1:]:
            op.status = "skipped"

    completed_po_ids: list[int] = []

    for _ in range(15):
        po = _new_po(
            status="completed",
            qty=rng.randint(5, 50),
            product_id=rng.choice(fg_id_list),
            sales_order_id=_next_linked_so_id(),
            days_back=rng.randint(10, 80),
        )
        po.quantity_completed = po.quantity_ordered
        po.qc_status = "passed"
        po.completed_at = po.created_at + timedelta(days=rng.randint(1, 5))
        po.actual_start = po.created_at + timedelta(hours=2)
        po.actual_end = po.completed_at
        _mark_ops_complete(po, po.quantity_ordered)
        db.add(po)
        completed_po_ids.append(po.id)

    for _ in range(10):
        po = _new_po(
            status="in_progress",
            qty=rng.randint(5, 40),
            product_id=rng.choice(fg_id_list),
            sales_order_id=_next_linked_so_id(),
            days_back=rng.randint(1, 6),
        )
        po.quantity_completed = Decimal(str(int(po.quantity_ordered) * rng.randint(10, 70) // 100))
        po.actual_start = po.created_at + timedelta(hours=1)
        po.released_at = po.created_at
        _mark_ops_in_progress(po)
        db.add(po)

    for _ in range(5):
        qty = rng.randint(10, 30)
        po = _new_po(
            status="completed",
            qty=qty,
            product_id=rng.choice(fg_id_list),
            sales_order_id=_next_linked_so_id(),
            days_back=rng.randint(15, 60),
        )
        short_by = rng.randint(1, max(2, qty // 4))
        po.quantity_completed = Decimal(str(qty - short_by))
        po.quantity_scrapped = Decimal(str(short_by))
        po.qc_status = "waived"
        po.qc_notes = "Accepted short -- customer approved reduced quantity"
        po.completed_at = po.created_at + timedelta(days=rng.randint(2, 8))
        po.actual_start = po.created_at + timedelta(hours=2)
        po.actual_end = po.completed_at
        _mark_ops_complete(po, po.quantity_completed)
        db.add(po)

    scrap_codes = rng.sample(list(scrap_reason_ids.keys()), k=5)
    for scrap_code in scrap_codes:
        qty = rng.randint(5, 20)
        product_id = rng.choice(fg_id_list)
        product = fg_products[product_id]
        po = _new_po(
            status="scrapped",
            qty=qty,
            product_id=product_id,
            sales_order_id=None,
            days_back=rng.randint(5, 85),
        )
        po.quantity_scrapped = po.quantity_ordered
        po.qc_status = "failed"
        po.scrapped_at = po.created_at + timedelta(days=rng.randint(1, 3))
        po.scrap_reason = scrap_code
        _mark_ops_scrapped(po, scrap_code)
        db.add(po)

        unit_cost = Decimal(str(product.standard_cost or 5))
        db.add(ScrapRecord(
            production_order_id=po.id,
            product_id=product_id,
            quantity=po.quantity_scrapped,
            unit_cost=unit_cost,
            total_cost=unit_cost * po.quantity_scrapped,
            scrap_reason_id=scrap_reason_ids[scrap_code],
            scrap_reason_code=scrap_code,
            notes=f"Demo scrap event: {scrap_code}",
            created_at=po.scrapped_at,
        ))

    for _ in range(5):
        po = _new_po(
            status="released",
            qty=rng.randint(5, 30),
            product_id=rng.choice(fg_id_list),
            sales_order_id=_next_linked_so_id(),
            days_back=rng.randint(0, 3),
        )
        po.released_at = po.created_at
        _mark_ops_released(po)
        db.add(po)

    db.flush()

    # Allocate materials for every PO that reached the released stage or
    # beyond. reserve_production_materials bumps inventory.allocated_quantity
    # and writes 'reservation' InventoryTransaction rows. It does NOT raise
    # on insufficient stock -- it warns and lets available_quantity go
    # negative, which is realistic for demo data showing the Low Stock
    # alert badge on PLA Black / PLA White.
    for po in db.query(ProductionOrder).filter(ProductionOrder.status != "scrapped").all():
        inventory_service.reserve_production_materials(
            db=db, production_order=po, created_by=admin_email,
        )
    db.flush()

    for po_id in rng.sample(completed_po_ids, k=5):
        production_order_service.record_qc_inspection(
            db,
            order_id=po_id,
            inspector="Demo QA Tech",
            qc_status="passed",
            quantity_passed=int(db.get(ProductionOrder, po_id).quantity_completed),
            quantity_failed=0,
            notes="Visual inspection passed. No dimensional issues.",
        )

    context["scrap_reason_ids"] = scrap_reason_ids
    total = 15 + 10 + 5 + 5 + 5
    print(
        f"[seed]   {total} production orders "
        f"(15 completed / 10 in_progress / 5 accepted_short / 5 scrapped / 5 released), "
        f"{len(SCRAP_REASONS)} scrap reasons, 5 QC inspections"
    )
