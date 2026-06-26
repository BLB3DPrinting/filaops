"""PR-3 (#784): a QC inspection can target a specific production operation.

Today QC is attributed to the first op whose code matches '%QC%'. This lets a
caller name the exact operation (so a routing with >1 inspection step works),
while keeping the legacy heuristic as the fallback.
"""
from decimal import Decimal

from app.models.production_order import ProductionOrderOperation

QC = "/api/v1/production-orders/{id}/qc"
HIST = "/api/v1/production-orders/{id}/qc-inspections"


def _po(make_product, make_production_order):
    product = make_product()
    return make_production_order(
        product_id=product.id, status="complete",
        quantity=Decimal("5"), quantity_completed=Decimal("5"),
    )


def _add_op(db, po_id, code, seq):
    op = ProductionOrderOperation(
        production_order_id=po_id, operation_code=code,
        operation_name=code, sequence=seq, status="pending",
        work_center_id=1,  # conftest seeds WorkCenter id=1
        planned_run_minutes=1,  # NOT NULL, no default
    )
    db.add(op)
    db.flush()
    return op


class TestOperationTargetedQC:
    def test_targets_explicit_operation(self, client, db, make_product, make_production_order):
        po = _po(make_product, make_production_order)
        _add_op(db, po.id, "PRINT", 10)
        # A non-'%QC%' op — proves targeting isn't limited to QC-coded steps.
        final_op = _add_op(db, po.id, "FINAL-INSPECT", 20)
        r = client.post(QC.format(id=po.id), json={"result": "passed", "operation_id": final_op.id})
        assert r.status_code == 200, r.text
        rec = client.get(HIST.format(id=po.id)).json()["inspections"][0]
        assert rec["production_operation_id"] == final_op.id

    def test_rejects_operation_from_other_order(self, client, db, make_product, make_production_order):
        po = _po(make_product, make_production_order)
        other = _po(make_product, make_production_order)
        other_op = _add_op(db, other.id, "QC", 10)
        r = client.post(QC.format(id=po.id), json={"result": "passed", "operation_id": other_op.id})
        assert r.status_code == 400  # not an operation of this order

    def test_falls_back_to_qc_coded_op(self, client, db, make_product, make_production_order):
        po = _po(make_product, make_production_order)
        _add_op(db, po.id, "PRINT", 10)
        qc_op = _add_op(db, po.id, "QC-FINAL", 20)
        r = client.post(QC.format(id=po.id), json={"result": "passed"})  # no operation_id
        assert r.status_code == 200, r.text
        rec = client.get(HIST.format(id=po.id)).json()["inspections"][0]
        assert rec["production_operation_id"] == qc_op.id  # legacy ilike '%QC%'

    def test_no_op_id_and_no_qc_op_leaves_null(self, client, db, make_product, make_production_order):
        po = _po(make_product, make_production_order)
        _add_op(db, po.id, "PRINT", 10)  # nothing QC-coded
        r = client.post(QC.format(id=po.id), json={"result": "passed"})
        assert r.status_code == 200
        rec = client.get(HIST.format(id=po.id)).json()["inspections"][0]
        assert rec["production_operation_id"] is None
