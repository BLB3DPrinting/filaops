"""#784 step 4 — defect-reason taxonomy endpoints + QC inspection wiring.

Covers the defect-reasons CRUD endpoints and the waive-end-to-end + defect
dimension on POST /production-orders/{id}/qc.
"""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.services import production_order_service

BASE = "/api/v1/production-orders/defect-reasons"


def _make_po(make_product, make_production_order):
    product = make_product()
    # 'complete' is the canonical runtime ProductionOrder status (not 'completed').
    return make_production_order(
        product_id=product.id, status="complete",
        quantity=Decimal("5"), quantity_completed=Decimal("5"),
    )


class TestDefectReasonCRUD:
    def test_empty_list(self, client):
        resp = client.get(BASE)
        assert resp.status_code == 200
        assert resp.json()["details"] == []

    def test_create_and_list(self, client):
        r = client.post(BASE, json={
            "code": "layer_shift", "name": "Layer Shift",
            "category": "dimensional", "severity": "major",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == "layer_shift"
        assert body["severity"] == "major"
        assert body["active"] is True

        listing = client.get(BASE).json()
        assert "layer_shift" in listing["reasons"]

    def test_duplicate_code_rejected(self, client):
        client.post(BASE, json={"code": "dup", "name": "A"})
        r = client.post(BASE, json={"code": "dup", "name": "B"})
        assert r.status_code == 400

    def test_invalid_severity_rejected(self, client):
        r = client.post(BASE, json={"code": "bad", "name": "Bad", "severity": "catastrophic"})
        assert r.status_code == 400

    def test_deactivate_hides_from_active_list(self, client):
        created = client.post(BASE, json={"code": "old", "name": "Old"}).json()
        patched = client.patch(f"{BASE}/{created['id']}", json={"active": False})
        assert patched.status_code == 200
        assert patched.json()["active"] is False

        assert "old" not in client.get(BASE).json()["reasons"]
        all_codes = [d["code"] for d in client.get(f"{BASE}/all").json()]
        assert "old" in all_codes  # still present when including inactive


class TestQCInspectionDefectAndWaive:
    QC = "/api/v1/production-orders/{id}/qc"
    HIST = "/api/v1/production-orders/{id}/qc-inspections"

    def test_record_inspection_with_defect_reason(self, client, db, make_product, make_production_order):
        reason = client.post(BASE, json={"code": "warp", "name": "Warping", "severity": "minor"}).json()
        po = _make_po(make_product, make_production_order)

        r = client.post(self.QC.format(id=po.id), json={
            "result": "failed", "quantity_failed": 1,
            "defect_reason_id": reason["id"], "failure_reason": "warped corner",
        })
        assert r.status_code == 200, r.text
        assert r.json()["defect_reason_id"] == reason["id"]

        rec = client.get(self.HIST.format(id=po.id)).json()["inspections"][0]
        assert rec["defect_reason_id"] == reason["id"]
        assert rec["defect_reason"]["code"] == "warp"
        assert rec["defect_reason"]["severity"] == "minor"

    def test_unknown_defect_reason_rejected(self, client, db, make_product, make_production_order):
        po = _make_po(make_product, make_production_order)
        r = client.post(self.QC.format(id=po.id), json={"result": "failed", "defect_reason_id": 999999})
        assert r.status_code == 400

    def test_inactive_defect_reason_rejected(self, client, db, make_product, make_production_order):
        reason = client.post(BASE, json={"code": "retired", "name": "Retired"}).json()
        client.patch(f"{BASE}/{reason['id']}", json={"active": False})
        po = _make_po(make_product, make_production_order)
        r = client.post(self.QC.format(id=po.id), json={"result": "failed", "defect_reason_id": reason["id"]})
        assert r.status_code == 400

    def test_defect_reason_on_passed_rejected(self, client, db, make_product, make_production_order):
        reason = client.post(BASE, json={"code": "p_def", "name": "P Defect"}).json()
        po = _make_po(make_product, make_production_order)
        # a clean pass carries no defect
        r = client.post(self.QC.format(id=po.id), json={"result": "passed", "defect_reason_id": reason["id"]})
        assert r.status_code == 400

    def test_defect_reason_allowed_on_waive(self, client, db, make_product, make_production_order):
        reason = client.post(BASE, json={"code": "w_def", "name": "Waived Defect", "severity": "minor"}).json()
        po = _make_po(make_product, make_production_order)
        # a waive records the defect being accepted
        r = client.post(self.QC.format(id=po.id), json={"result": "waived", "defect_reason_id": reason["id"]})
        assert r.status_code == 200, r.text
        rec = client.get(self.HIST.format(id=po.id)).json()["inspections"][0]
        assert rec["defect_reason"]["code"] == "w_def"
        assert rec["waiver_user_id"] is not None

    def test_waive_attributes_to_current_user(self, client, db, make_product, make_production_order):
        po = _make_po(make_product, make_production_order)
        r = client.post(self.QC.format(id=po.id), json={"result": "waived", "notes": "accepted as-is"})
        assert r.status_code == 200, r.text

        rec = client.get(self.HIST.format(id=po.id)).json()["inspections"][0]
        assert rec["result"] == "waived"
        assert rec["waiver_user_id"] is not None  # attributed to the operator

    def test_pass_has_no_waiver(self, client, db, make_product, make_production_order):
        po = _make_po(make_product, make_production_order)
        client.post(self.QC.format(id=po.id), json={"result": "passed"})
        rec = client.get(self.HIST.format(id=po.id)).json()["inspections"][0]
        assert rec["waiver_user_id"] is None
        assert rec["defect_reason"] is None


class TestWaiverServiceGuard:
    """The /qc endpoint only sets waiver_user_id on a waived result, but the
    service guards a direct caller too (symmetric to defect_reason)."""

    def test_waiver_rejected_on_non_waived_result(self, db, make_product, make_production_order):
        from app.models.user import User
        user = db.query(User).first()
        po = _make_po(make_product, make_production_order)
        with pytest.raises(HTTPException) as exc:
            production_order_service.record_qc_inspection(
                db, po.id, inspector="x", qc_status="failed", waiver_user_id=user.id,
            )
        assert exc.value.status_code == 400

    def test_waiver_rejected_for_unknown_user(self, db, make_product, make_production_order):
        po = _make_po(make_product, make_production_order)
        with pytest.raises(HTTPException) as exc:
            production_order_service.record_qc_inspection(
                db, po.id, inspector="x", qc_status="waived", waiver_user_id=999999,
            )
        assert exc.value.status_code == 400
