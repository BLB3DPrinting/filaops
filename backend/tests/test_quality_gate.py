"""#784 PR-7 — the configurable QC inspection-result gate (off | warn | block)."""
from decimal import Decimal

from app.models.system_setting import SystemSetting
from app.services.quality_gate_service import evaluate_inspection
from app.services.quality_policy import GateAction, get_quality_policy

QC = "/api/v1/production-orders/{id}/qc"
HIST = "/api/v1/production-orders/{id}/qc-inspections"
PLANS = "/api/v1/quality-plans"


def _set(db, key, value):
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, value=value))
    db.flush()


def _make_po(make_product, make_production_order):
    product = make_product()
    po = make_production_order(
        product_id=product.id, status="complete",
        quantity=Decimal("5"), quantity_completed=Decimal("5"),
    )
    return product, po


# --- pure evaluation (no DB) -------------------------------------------------

class _Char:
    def __init__(self, id, name, ctype="variable", lo=None, hi=None):
        self.id = id
        self.characteristic = name
        self.characteristic_type = ctype
        self.lower_limit = lo
        self.upper_limit = hi


class _Plan:
    code = "QP"

    def __init__(self, chars):
        self.characteristics = chars


class TestGateEvaluation:
    def test_complete_and_passing_is_clean(self):
        plan = _Plan([
            _Char(1, "bore", "variable", Decimal("9.9"), Decimal("10.1")),
            _Char(2, "finish", "attribute"),
        ])
        ev = evaluate_inspection(plan, [
            {"quality_plan_characteristic_id": 1, "measured_value": "10.0"},
            {"quality_plan_characteristic_id": 2, "conforms": True},
        ])
        assert ev.is_clean

    def test_unmeasured_characteristic_is_missing(self):
        plan = _Plan([
            _Char(1, "bore", "variable", Decimal("9.9"), Decimal("10.1")),
            _Char(2, "finish", "attribute"),
        ])
        ev = evaluate_inspection(plan, [{"quality_plan_characteristic_id": 1, "measured_value": "10.0"}])
        assert ev.missing == ["finish"]
        assert not ev.is_clean

    def test_out_of_spec_variable_is_failing(self):
        plan = _Plan([_Char(1, "bore", "variable", Decimal("9.9"), Decimal("10.1"))])
        ev = evaluate_inspection(plan, [{"quality_plan_characteristic_id": 1, "measured_value": "10.5"}])
        assert ev.failing == ["bore"]

    def test_attribute_fail_is_failing(self):
        plan = _Plan([_Char(1, "finish", "attribute")])
        ev = evaluate_inspection(plan, [{"quality_plan_characteristic_id": 1, "conforms": False}])
        assert ev.failing == ["finish"]

    def test_variable_with_value_no_limits_is_clean(self):
        plan = _Plan([_Char(1, "weight", "variable")])  # no spec limits
        ev = evaluate_inspection(plan, [{"quality_plan_characteristic_id": 1, "measured_value": "5"}])
        assert ev.is_clean  # a recorded value with no spec to violate

    def test_variable_no_value_is_missing(self):
        plan = _Plan([_Char(1, "bore", "variable", Decimal("9.9"), Decimal("10.1"))])
        ev = evaluate_inspection(plan, [{"quality_plan_characteristic_id": 1, "measured_value": None}])
        assert ev.missing == ["bore"]

    def test_client_conforms_ignored_for_variable(self):
        # A client lying conforms=true can't pass an out-of-spec variable reading.
        plan = _Plan([_Char(1, "bore", "variable", Decimal("9.9"), Decimal("10.1"))])
        ev = evaluate_inspection(plan, [
            {"quality_plan_characteristic_id": 1, "measured_value": "20", "conforms": True},
        ])
        assert ev.failing == ["bore"]

    def test_client_measurement_limits_ignored_for_variable(self):
        # A client can't widen the spec: an out-of-spec value with its own wide
        # limits must still fail against the PLAN's authoritative limits.
        plan = _Plan([_Char(1, "bore", "variable", Decimal("9.9"), Decimal("10.1"))])
        ev = evaluate_inspection(plan, [
            {"quality_plan_characteristic_id": 1, "measured_value": "50",
             "lower_limit": "0", "upper_limit": "100"},
        ])
        assert ev.failing == ["bore"]

    def test_attribute_unanswered_is_missing(self):
        plan = _Plan([_Char(1, "finish", "attribute")])
        ev = evaluate_inspection(plan, [{"quality_plan_characteristic_id": 1, "conforms": None}])
        assert ev.missing == ["finish"]
        assert ev.failing == []

    def test_duplicate_rows_cannot_hide_a_failure(self):
        # Two rows for the same characteristic — a later passing row must not
        # hide an earlier out-of-spec one.
        plan = _Plan([_Char(1, "bore", "variable", Decimal("9.9"), Decimal("10.1"))])
        ev = evaluate_inspection(plan, [
            {"quality_plan_characteristic_id": 1, "measured_value": "50"},    # fail
            {"quality_plan_characteristic_id": 1, "measured_value": "10.0"},  # pass
        ])
        assert ev.failing == ["bore"]


# --- policy resolution -------------------------------------------------------

class TestGatePolicy:
    def test_default_action_is_warn(self, db):
        db.query(SystemSetting).filter(
            SystemSetting.key.in_(["quality_gate_action", "quality_gate_close"])
        ).delete(synchronize_session=False)
        db.flush()
        assert get_quality_policy(db).gate_action is GateAction.WARN

    def test_legacy_bool_true_maps_to_block(self, db):
        db.query(SystemSetting).filter(SystemSetting.key == "quality_gate_action").delete()
        _set(db, "quality_gate_close", True)
        assert get_quality_policy(db).gate_action is GateAction.BLOCK

    def test_explicit_action_wins_over_legacy(self, db):
        _set(db, "quality_gate_close", True)
        _set(db, "quality_gate_action", "off")
        assert get_quality_policy(db).gate_action is GateAction.OFF

    def test_policy_endpoint_returns_action_and_legacy_close(self, client, db):
        # Setting the NEW key alone must keep the legacy gate_close field in sync
        # (derived from the action), so older UI toggles don't drift.
        _set(db, "quality_mode", "full")
        _set(db, "quality_gate_action", "block")
        body = client.get("/api/v1/quality/policy").json()
        assert body["gate_action"] == "block"
        assert body["gate_close"] is True   # derived from action, not the raw row
        assert body["gates_close"] is True  # block + full


# --- end-to-end via /qc ------------------------------------------------------

class TestGateEndpoint:
    def _plan(self, client, product_id):
        return client.post(PLANS, json={
            "product_id": product_id, "code": "QP-GATE", "name": "Gate plan",
            "characteristics": [
                {"characteristic": "bore", "code": "BORE", "characteristic_type": "variable",
                 "nominal": "10", "lower_limit": "9.9", "upper_limit": "10.1"},
                {"characteristic": "finish", "code": "FIN", "characteristic_type": "attribute"},
            ],
        }).json()

    def test_block_rejects_incomplete_pass(self, client, db, make_product, make_production_order):
        product, po = _make_po(make_product, make_production_order)
        plan = self._plan(client, product.id)
        _set(db, "quality_mode", "full")
        _set(db, "quality_gate_action", "block")
        bore_id = plan["characteristics"][0]["id"]
        r = client.post(QC.format(id=po.id), json={
            "result": "passed",
            "measurements": [
                {"characteristic": "bore", "quality_plan_characteristic_id": bore_id,
                 "characteristic_code": "BORE", "measured_value": "10.0"},
            ],  # 'finish' attribute unmeasured
        })
        assert r.status_code == 400, r.text
        assert "does not satisfy plan" in r.json()["detail"]
        # Block runs before any side effect: no inspection row was written.
        assert client.get(HIST.format(id=po.id)).json()["inspections"] == []

    def test_warn_allows_incomplete_pass_with_warning(self, client, db, make_product, make_production_order):
        product, po = _make_po(make_product, make_production_order)
        plan = self._plan(client, product.id)
        _set(db, "quality_mode", "full")
        _set(db, "quality_gate_action", "warn")
        bore_id = plan["characteristics"][0]["id"]
        r = client.post(QC.format(id=po.id), json={
            "result": "passed",
            "measurements": [
                {"characteristic": "bore", "quality_plan_characteristic_id": bore_id,
                 "characteristic_code": "BORE", "measured_value": "10.0"},
            ],
        })
        assert r.status_code == 200, r.text
        assert any("does not satisfy" in w for w in r.json()["warnings"])

    def test_off_records_without_gate(self, client, db, make_product, make_production_order):
        product, po = _make_po(make_product, make_production_order)
        self._plan(client, product.id)
        _set(db, "quality_mode", "full")
        _set(db, "quality_gate_action", "off")
        r = client.post(QC.format(id=po.id), json={"result": "passed"})
        assert r.status_code == 200, r.text
        assert r.json()["warnings"] == []

    def test_complete_passing_clears_block(self, client, db, make_product, make_production_order):
        product, po = _make_po(make_product, make_production_order)
        plan = self._plan(client, product.id)
        _set(db, "quality_mode", "full")
        _set(db, "quality_gate_action", "block")
        bore_id = plan["characteristics"][0]["id"]
        fin_id = plan["characteristics"][1]["id"]
        r = client.post(QC.format(id=po.id), json={
            "result": "passed",
            "measurements": [
                {"characteristic": "bore", "quality_plan_characteristic_id": bore_id,
                 "characteristic_code": "BORE", "measured_value": "10.0"},
                {"characteristic": "finish", "quality_plan_characteristic_id": fin_id,
                 "characteristic_code": "FIN", "conforms": True},
            ],
        })
        assert r.status_code == 200, r.text
        assert r.json()["warnings"] == []

    def test_basic_mode_does_not_gate(self, client, db, make_product, make_production_order):
        product, po = _make_po(make_product, make_production_order)
        self._plan(client, product.id)
        _set(db, "quality_mode", "basic")  # not full -> no gate even with block
        _set(db, "quality_gate_action", "block")
        r = client.post(QC.format(id=po.id), json={"result": "passed"})
        assert r.status_code == 200, r.text
        assert r.json()["warnings"] == []

    def test_failed_result_is_not_gated(self, client, db, make_product, make_production_order):
        product, po = _make_po(make_product, make_production_order)
        self._plan(client, product.id)
        _set(db, "quality_mode", "full")
        _set(db, "quality_gate_action", "block")
        # A 'failed' result never needs a complete inspection — it's a fail.
        r = client.post(QC.format(id=po.id), json={"result": "failed"})
        assert r.status_code == 200, r.text
