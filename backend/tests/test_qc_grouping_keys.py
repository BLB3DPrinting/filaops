"""PR-4 (#784): grouping keys (printer / work-center / operator) are denormalized
onto the qc_inspections row at record time, so grouped metrics don't drop
order-level inspections that have no production_operation_id."""
from decimal import Decimal

from app.models.printer import Printer
from app.models.production_order import ProductionOrderOperation, QCInspection

QC = "/api/v1/production-orders/{id}/qc"


def _po(make_product, make_production_order):
    product = make_product()
    return make_production_order(
        product_id=product.id, status="complete",
        quantity=Decimal("3"), quantity_completed=Decimal("3"),
    )


def _printer(db, po_id):
    # po_id is autoincrement (never reused), so the code stays unique even though
    # the endpoint commits persist across test runs.
    p = Printer(code=f"PRN-{po_id}", name="Test Printer", model="X1C")
    db.add(p)
    db.flush()
    return p


def _op(db, po_id, printer_id, operator_id):
    op = ProductionOrderOperation(
        production_order_id=po_id, operation_code="QC", operation_name="Final QC",
        sequence=10, status="pending", work_center_id=1,  # conftest seeds WC id=1
        printer_id=printer_id, operator_id=operator_id, planned_run_minutes=1,
    )
    db.add(op)
    db.flush()
    return op


class TestQCGroupingKeys:
    def test_keys_copied_from_the_inspected_operation(self, client, db, make_product, make_production_order):
        po = _po(make_product, make_production_order)
        printer = _printer(db, po.id)
        op = _op(db, po.id, printer.id, 7)
        r = client.post(QC.format(id=po.id), json={"result": "passed", "operation_id": op.id})
        assert r.status_code == 200, r.text
        insp = db.query(QCInspection).filter(QCInspection.production_order_id == po.id).first()
        assert insp.printer_id == printer.id
        assert insp.work_center_id == 1
        assert insp.operator_id == 7

    def test_order_level_inspection_has_null_keys(self, client, db, make_product, make_production_order):
        po = _po(make_product, make_production_order)  # no operations
        r = client.post(QC.format(id=po.id), json={"result": "passed"})
        assert r.status_code == 200, r.text
        insp = db.query(QCInspection).filter(QCInspection.production_order_id == po.id).first()
        # no op -> keys are null (grouped as "unassigned", not dropped)
        assert insp.printer_id is None
        assert insp.work_center_id is None
        assert insp.operator_id is None
