"""#784 step 5 — SPC measurements captured with a QC inspection are persisted
and surfaced (with computed in/out-of-spec) in the inspection history."""
from decimal import Decimal

QC = "/api/v1/production-orders/{id}/qc"
HIST = "/api/v1/production-orders/{id}/qc-inspections"
PLANS = "/api/v1/quality-plans"


def _make_po(make_product, make_production_order):
    product = make_product()
    return make_production_order(
        product_id=product.id, status="complete",
        quantity=Decimal("5"), quantity_completed=Decimal("5"),
    )


class TestQCMeasurements:
    def test_measurements_recorded_with_spec_flags(self, client, db, make_product, make_production_order):
        po = _make_po(make_product, make_production_order)
        r = client.post(QC.format(id=po.id), json={
            "result": "passed",
            "measurements": [
                {"characteristic": "bore_dia", "nominal": "10.0", "lower_limit": "9.95",
                 "upper_limit": "10.05", "measured_value": "10.012", "unit": "mm"},
                {"characteristic": "height", "lower_limit": "20", "upper_limit": "21",
                 "measured_value": "21.5", "unit": "mm"},
                {"characteristic": "note_only", "measured_value": "5"},  # no limits
            ],
        })
        assert r.status_code == 200, r.text

        ms = client.get(HIST.format(id=po.id)).json()["inspections"][0]["measurements"]
        assert len(ms) == 3
        # default ordering follows input order
        assert [m["characteristic"] for m in ms] == ["bore_dia", "height", "note_only"]
        assert ms[0]["is_within_spec"] is True    # 10.012 within [9.95, 10.05]
        assert ms[1]["is_within_spec"] is False   # 21.5 > 21
        assert ms[2]["is_within_spec"] is None     # no limits -> not determinable
        assert abs(float(ms[0]["measured_value"]) - 10.012) < 1e-6  # exact Numeric round-trip

    def test_inspection_without_measurements(self, client, db, make_product, make_production_order):
        po = _make_po(make_product, make_production_order)
        client.post(QC.format(id=po.id), json={"result": "passed"})
        rec = client.get(HIST.format(id=po.id)).json()["inspections"][0]
        assert rec["measurements"] == []

    def test_explicit_sequence_orders_output(self, client, db, make_product, make_production_order):
        po = _make_po(make_product, make_production_order)
        client.post(QC.format(id=po.id), json={
            "result": "passed",
            "measurements": [
                {"characteristic": "b", "sequence": 2, "measured_value": "1"},
                {"characteristic": "a", "sequence": 1, "measured_value": "2"},
            ],
        })
        ms = client.get(HIST.format(id=po.id)).json()["inspections"][0]["measurements"]
        assert [m["characteristic"] for m in ms] == ["a", "b"]

    def test_value_at_limit_is_in_spec(self, client, db, make_product, make_production_order):
        po = _make_po(make_product, make_production_order)
        client.post(QC.format(id=po.id), json={
            "result": "passed",
            "measurements": [
                {"characteristic": "edge", "lower_limit": "1.0", "upper_limit": "2.0", "measured_value": "2.0"},
            ],
        })
        ms = client.get(HIST.format(id=po.id)).json()["inspections"][0]["measurements"]
        assert ms[0]["is_within_spec"] is True  # boundary is inclusive

    def test_inverted_limits_rejected(self, client, db, make_product, make_production_order):
        po = _make_po(make_product, make_production_order)
        r = client.post(QC.format(id=po.id), json={
            "result": "passed",
            "measurements": [
                {"characteristic": "x", "lower_limit": "10", "upper_limit": "5", "measured_value": "7"},
            ],
        })
        assert r.status_code == 422  # transposed LSL/USL rejected at the boundary

    def test_measurement_persists_plan_link_and_conformance(self, client, db, make_product, make_production_order):
        po = _make_po(make_product, make_production_order)
        plan = client.post(PLANS, json={
            "product_id": po.product_id, "code": "QP-LINK", "name": "Link plan",
            "characteristics": [
                {"characteristic": "bore", "code": "BORE", "nominal": "10",
                 "lower_limit": "9.9", "upper_limit": "10.1"},
                {"characteristic": "Surface", "code": "SURF", "characteristic_type": "attribute"},
            ],
        }).json()
        var_id = plan["characteristics"][0]["id"]
        attr_id = plan["characteristics"][1]["id"]
        r = client.post(QC.format(id=po.id), json={
            "result": "passed",
            "measurements": [
                {"characteristic": "bore", "quality_plan_characteristic_id": var_id,
                 "characteristic_code": "BORE", "nominal": "10", "lower_limit": "9.9",
                 "upper_limit": "10.1", "measured_value": "10.0", "unit": "mm"},
                {"characteristic": "Surface", "quality_plan_characteristic_id": attr_id,
                 "characteristic_code": "SURF", "conforms": True},
            ],
        })
        assert r.status_code == 200, r.text
        ms = client.get(HIST.format(id=po.id)).json()["inspections"][0]["measurements"]
        # variable row: FK + denormalized code round-trip; conforms stays NULL
        assert ms[0]["quality_plan_characteristic_id"] == var_id
        assert ms[0]["characteristic_code"] == "BORE"
        assert ms[0]["conforms"] is None
        assert ms[0]["is_within_spec"] is True
        # attribute row: pass/fail stored; no limits so is_within_spec is None
        assert ms[1]["quality_plan_characteristic_id"] == attr_id
        assert ms[1]["characteristic_code"] == "SURF"
        assert ms[1]["conforms"] is True
        assert ms[1]["is_within_spec"] is None

    def test_unknown_plan_characteristic_id_is_rejected(self, client, db, make_product, make_production_order):
        po = _make_po(make_product, make_production_order)
        r = client.post(QC.format(id=po.id), json={
            "result": "passed",
            "measurements": [
                {"characteristic": "bore", "quality_plan_characteristic_id": 999999,
                 "measured_value": "1"},
            ],
        })
        # A bogus FK is a clean 400, not a 500 FK IntegrityError.
        assert r.status_code == 400, r.text
        assert "not found in this product" in r.json()["detail"]

    def test_characteristic_code_is_authoritative_from_plan(self, client, db, make_product, make_production_order):
        po = _make_po(make_product, make_production_order)
        plan = client.post(PLANS, json={
            "product_id": po.product_id, "code": "QP-AUTH", "name": "Auth plan",
            "characteristics": [{"characteristic": "bore", "code": "REAL_CODE", "nominal": "10"}],
        }).json()
        cid = plan["characteristics"][0]["id"]
        client.post(QC.format(id=po.id), json={
            "result": "passed",
            "measurements": [
                {"characteristic": "bore", "quality_plan_characteristic_id": cid,
                 "characteristic_code": "CLIENT_LIE", "measured_value": "10"},
            ],
        })
        ms = client.get(HIST.format(id=po.id)).json()["inspections"][0]["measurements"]
        # The server overrides a wrong client code with the plan's real code.
        assert ms[0]["characteristic_code"] == "REAL_CODE"

    def test_characteristic_from_another_product_is_rejected(self, client, db, make_product, make_production_order):
        po = _make_po(make_product, make_production_order)  # product A
        other = make_product()                              # product B
        other_plan = client.post(PLANS, json={
            "product_id": other.id, "code": "QP-OTHER", "name": "Other plan",
            "characteristics": [{"characteristic": "x", "code": "X"}],
        }).json()
        other_cid = other_plan["characteristics"][0]["id"]
        r = client.post(QC.format(id=po.id), json={
            "result": "passed",
            "measurements": [
                {"characteristic": "x", "quality_plan_characteristic_id": other_cid,
                 "measured_value": "1"},
            ],
        })
        # The characteristic exists but belongs to a different product's plan.
        assert r.status_code == 400, r.text
        assert "not found in this product" in r.json()["detail"]

    def test_deleting_linked_characteristic_nulls_fk_keeps_code(self, client, db, make_product, make_production_order):
        po = _make_po(make_product, make_production_order)
        plan = client.post(PLANS, json={
            "product_id": po.product_id, "code": "QP-DEL", "name": "Del plan",
            "characteristics": [{"characteristic": "bore", "code": "BORE", "nominal": "10"}],
        }).json()
        cid = plan["characteristics"][0]["id"]
        pid = plan["id"]
        client.post(QC.format(id=po.id), json={
            "result": "passed",
            "measurements": [
                {"characteristic": "bore", "quality_plan_characteristic_id": cid,
                 "characteristic_code": "BORE", "measured_value": "10"},
            ],
        })
        # Replacing the plan's characteristics delete-orphans the old row; its
        # ON DELETE SET NULL nulls the measurement FK, but the denormalized code
        # is preserved for historical SPC grouping.
        r = client.patch(f"{PLANS}/{pid}", json={"characteristics": [{"characteristic": "new"}]})
        assert r.status_code == 200, r.text
        ms = client.get(HIST.format(id=po.id)).json()["inspections"][0]["measurements"]
        assert ms[0]["quality_plan_characteristic_id"] is None  # FK SET NULL
        assert ms[0]["characteristic_code"] == "BORE"           # code preserved

    def test_equal_sequence_keeps_insertion_order(self, client, db, make_product, make_production_order):
        po = _make_po(make_product, make_production_order)
        client.post(QC.format(id=po.id), json={
            "result": "passed",
            "measurements": [
                {"characteristic": "first", "sequence": 1, "measured_value": "1"},
                {"characteristic": "second", "sequence": 1, "measured_value": "2"},
            ],
        })
        ms = client.get(HIST.format(id=po.id)).json()["inspections"][0]["measurements"]
        # equal sequence -> id tie-breaker preserves insertion order
        assert [m["characteristic"] for m in ms] == ["first", "second"]
