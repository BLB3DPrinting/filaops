"""
Tests for #876 PR-3: op-type audit endpoint, human-gated classifier, and
hardened admin CRUD.

Covers:
- Non-staff-403 on every admin endpoint (PRO-leak-audit lesson)
- Dry-run writes nothing
- Apply is idempotent, NULL-only, never overwrites a human-set type
- Material-bearing safety rule (never auto-propose a no-consume type)
- Mixed-name priority flagging
- Audit shape + in-flight (non-terminal PO) exposure rollup
- is_system CRUD locks (consume_stages/is_qc locked; undeletable)
- 409 in-use guard on consume_stages edits referenced by a non-terminal PO
"""
from decimal import Decimal

import pytest

from app.models.manufacturing import (
    OperationType,
    Routing,
    RoutingOperation,
    RoutingOperationMaterial,
)
from app.models.production_order import (
    ProductionOrderOperation,
    ProductionOrderOperationMaterial,
)
from app.services.operation_type_classifier import (
    MANUAL_DECISION_REASON,
    MIXED_NAME_REASON,
    NO_MATCH_REASON,
    build_audit,
    classify_name,
    run_classifier,
)
from tests.services._operation_type_seed import seed_operation_types


@pytest.fixture(autouse=True)
def _seed(db):
    seed_operation_types(db)
    db.commit()


def _make_routing_op(db, make_product, make_work_center, operation_name, operation_code=None, operation_type=None):
    product = make_product(item_type="finished_good")
    routing = Routing(product_id=product.id, code=f"RTG-{operation_name}-{product.id}", is_template=False)
    db.add(routing)
    db.flush()
    wc = make_work_center()
    op = RoutingOperation(
        routing_id=routing.id,
        work_center_id=wc.id,
        sequence=10,
        operation_code=operation_code,
        operation_name=operation_name,
        operation_type=operation_type,
        run_time_minutes=Decimal("10"),
    )
    db.add(op)
    db.commit()
    db.refresh(op)
    return op


def _make_po_op(db, make_product, make_work_center, make_production_order, operation_name,
                 operation_code=None, operation_type=None, po_status="released"):
    product = make_product(item_type="finished_good")
    po = make_production_order(product_id=product.id, status=po_status)
    wc = make_work_center()
    op = ProductionOrderOperation(
        production_order_id=po.id,
        work_center_id=wc.id,
        sequence=10,
        operation_code=operation_code,
        operation_name=operation_name,
        operation_type=operation_type,
        planned_run_minutes=Decimal("10"),
    )
    db.add(op)
    db.commit()
    db.refresh(op)
    return op, po


# =============================================================================
# classify_name — pure name-rule unit tests
# =============================================================================

class TestClassifyName:
    def test_blank_name_no_proposal(self):
        result = classify_name("")
        assert result.proposed_type is None
        assert result.reason == NO_MATCH_REASON

    def test_none_name_no_proposal(self):
        result = classify_name(None)
        assert result.proposed_type is None
        assert result.reason == NO_MATCH_REASON

    def test_no_match_name(self):
        result = classify_name("Widget Frobnicate")
        assert result.proposed_type is None
        assert result.reason == NO_MATCH_REASON

    @pytest.mark.parametrize("name,expected", [
        ("Pack items", "PACK_SHIP"),
        ("Ship to customer", "PACK_SHIP"),
        ("Apply label", "PACK_SHIP"),
        ("Packaging step", "PACK_SHIP"),
        ("Box up", "PACK_SHIP"),
        ("Mail order", "PACK_SHIP"),
        ("QC inspection", "QUALITY_CONTROL"),
        ("Quality check", "QUALITY_CONTROL"),
        ("Inspect part", "QUALITY_CONTROL"),
        ("Assembly step", "ASSEMBLY"),
        ("3D Print base", "FDM_PRINT"),
        ("Sand the surface", "SANDING"),
        ("Paint finish", "PAINTING"),
        ("Support removal", "SUPPORT_REMOVAL"),
        ("Clean up", "SUPPORT_REMOVAL"),
        ("Post processing", "SUPPORT_REMOVAL"),
        ("Post-process", "SUPPORT_REMOVAL"),
    ])
    def test_single_rule_matches(self, name, expected):
        result = classify_name(name)
        assert result.proposed_type == expected
        assert result.reason is None
        assert result.mixed is False

    def test_mixed_name_priority_qc_plus_pack(self):
        """'QC + Pack' matches both the pack rule and the qc rule; PACK_SHIP
        (rule #1, higher priority) wins, flagged as mixed-name."""
        result = classify_name("QC + Pack")
        assert result.proposed_type == "PACK_SHIP"
        assert result.mixed is True
        assert result.reason == MIXED_NAME_REASON

    def test_case_insensitive(self):
        result = classify_name("PACK AND SHIP")
        assert result.proposed_type == "PACK_SHIP"


# =============================================================================
# Audit
# =============================================================================

class TestAudit:
    def test_audit_shape_and_pair_grouping(self, db, make_product, make_work_center):
        _make_routing_op(db, make_product, make_work_center, "Print", operation_code="PRINT")
        rows = build_audit(db)
        assert len(rows) >= 1
        row = next(r for r in rows if r.operation_code == "PRINT" and r.operation_name == "Print")
        assert row.routing_op_count == 1
        assert row.po_op_count == 0
        assert row.match_source == "legacy-dict"
        assert row.current_consume_stages == ["production", "any"]

    def test_audit_match_source_stored_type(self, db, make_product, make_work_center):
        _make_routing_op(
            db, make_product, make_work_center, "Pack it up",
            operation_code=None, operation_type="PACK_SHIP",
        )
        rows = build_audit(db)
        row = next(r for r in rows if r.operation_name == "Pack it up")
        assert row.match_source == "stored-type"
        assert row.stored_operation_type == "PACK_SHIP"
        assert row.current_consume_stages == ["shipping", "any"]

    def test_audit_match_source_default(self, db, make_product, make_work_center):
        _make_routing_op(db, make_product, make_work_center, "Widget Frobnicate", operation_code=None)
        rows = build_audit(db)
        row = next(r for r in rows if r.operation_name == "Widget Frobnicate")
        assert row.match_source == "default"
        assert row.current_consume_stages == ["production", "any"]

    def test_audit_proposes_type_and_flags_behavior_changed(self, db, make_product, make_work_center):
        """An untyped op named 'Pack items' with legacy code None (so
        current resolution is the default ["production","any"]) proposes
        PACK_SHIP, whose stages differ -> behavior_changed True."""
        _make_routing_op(db, make_product, make_work_center, "Pack items", operation_code=None)
        rows = build_audit(db)
        row = next(r for r in rows if r.operation_name == "Pack items")
        assert row.proposed_type == "PACK_SHIP"
        assert row.proposed_consume_stages == ["shipping", "any"]
        assert row.behavior_changed is True

    def test_audit_in_flight_rollup_one_non_terminal_po(
        self, db, make_product, make_work_center, make_production_order
    ):
        """One non-terminal PO with a generic-coded op appears in the
        in-flight rollup; a terminal one does not."""
        _make_po_op(
            db, make_product, make_work_center, make_production_order,
            "3D Print", operation_code="PRINT", po_status="in_progress",
        )
        _make_po_op(
            db, make_product, make_work_center, make_production_order,
            "3D Print", operation_code="PRINT", po_status="complete",
        )
        rows = build_audit(db)
        row = next(r for r in rows if r.operation_code == "PRINT" and r.operation_name == "3D Print")
        assert row.in_flight_non_terminal_po_count == 1
        assert row.po_op_count == 2

    def test_audit_material_bearing_flag(self, db, make_product, make_work_center):
        op = _make_routing_op(db, make_product, make_work_center, "Sand surface", operation_code=None)
        component = make_product(item_type="supply")
        db.add(RoutingOperationMaterial(
            routing_operation_id=op.id,
            component_id=component.id,
            quantity=Decimal("1"),
            quantity_per="unit",
            unit="EA",
        ))
        db.commit()

        rows = build_audit(db)
        row = next(r for r in rows if r.operation_name == "Sand surface")
        assert row.material_bearing is True
        # SANDING is a no-consume type; material-bearing safety rule fires.
        assert row.proposed_type is None
        assert row.classification_reason == MANUAL_DECISION_REASON

    def test_audit_is_re_runnable_read_only(self, db, make_product, make_work_center):
        _make_routing_op(db, make_product, make_work_center, "Print", operation_code="PRINT")
        rows_first = build_audit(db)
        rows_second = build_audit(db)
        assert len(rows_first) == len(rows_second)
        # No operation_type rows were mutated by merely running the audit.
        untouched = db.query(RoutingOperation).filter(RoutingOperation.operation_code == "PRINT").first()
        assert untouched.operation_type is None

    def test_audit_match_source_unknown_stored_type_falls_through_to_legacy_dict(
        self, db, make_product, make_work_center
    ):
        """A stored operation_type that ISN'T in the catalog (unknown/
        inactive/stale hand-edited data) must not be reported as
        "stored-type" — resolve_consume_stages() actually falls through to
        the legacy dict for this row, so match_source must say
        "legacy-dict", matching runtime behavior exactly (CodeRabbit
        finding: _match_source must reflect the REAL resolution path)."""
        _make_routing_op(
            db, make_product, make_work_center, "3D Print",
            operation_code="PRINT", operation_type="NOT_A_REAL_TYPE_CODE",
        )
        rows = build_audit(db)
        row = next(r for r in rows if r.operation_name == "3D Print")
        assert row.stored_operation_type == "NOT_A_REAL_TYPE_CODE"
        assert row.match_source == "legacy-dict"
        assert row.current_consume_stages == ["production", "any"]

    def test_audit_match_source_unknown_stored_type_and_unknown_code_falls_through_to_default(
        self, db, make_product, make_work_center
    ):
        """Same as above, but with no legacy-dict code match either ->
        "default", not "stored-type"."""
        _make_routing_op(
            db, make_product, make_work_center, "Widget Frobnicate",
            operation_code=None, operation_type="NOT_A_REAL_TYPE_CODE",
        )
        rows = build_audit(db)
        row = next(r for r in rows if r.operation_name == "Widget Frobnicate")
        assert row.match_source == "default"
        assert row.current_consume_stages == ["production", "any"]

    def test_audit_stored_type_row_gets_no_proposed_type(self, db, make_product, make_work_center):
        """Proposals are for NULL-typed rows only — run_classifier() never
        touches a row that already carries a stored type, so build_audit()
        must not show an unactionable proposed_type (previously: a
        stored-type row's name could still match a rule and populate
        proposed_type with no proposed_consume_stages behind it)."""
        _make_routing_op(
            db, make_product, make_work_center, "Pack it up",
            operation_code=None, operation_type="QUALITY_CONTROL",
        )
        rows = build_audit(db)
        row = next(r for r in rows if r.operation_name == "Pack it up")
        assert row.stored_operation_type == "QUALITY_CONTROL"
        assert row.proposed_type is None
        assert row.proposed_consume_stages is None
        assert row.behavior_changed is False
        assert row.classification_reason is None

    def test_audit_conflicting_stored_types_across_rows_surfaced(
        self, db, make_product, make_work_center
    ):
        """Two rows sharing the same (operation_code, operation_name) pair
        but stored with DIFFERENT operation_type values is a genuine
        conflict, not just a NULL-vs-typed split — the representative
        stored_operation_type must be deterministic (sorted-first)
        regardless of DB row order, and the other type(s) must be exposed
        via conflicting_stored_types rather than silently dropped."""
        _make_routing_op(
            db, make_product, make_work_center, "Ambiguous Op",
            operation_code="AMBIG", operation_type="QUALITY_CONTROL",
        )
        _make_routing_op(
            db, make_product, make_work_center, "Ambiguous Op",
            operation_code="AMBIG", operation_type="ASSEMBLY",
        )
        rows = build_audit(db)
        row = next(r for r in rows if r.operation_name == "Ambiguous Op")
        # Deterministic representative: lexicographically first of the
        # distinct types ("ASSEMBLY" < "QUALITY_CONTROL").
        assert row.stored_operation_type == "ASSEMBLY"
        assert row.conflicting_stored_types == ["QUALITY_CONTROL"]
        assert row.routing_op_count == 2

    def test_audit_single_stored_type_has_no_conflict(self, db, make_product, make_work_center):
        """A pair with only one distinct non-NULL stored type (the common
        case) reports conflicting_stored_types = None, not an empty list
        or the type itself."""
        _make_routing_op(
            db, make_product, make_work_center, "Pack it up",
            operation_code=None, operation_type="PACK_SHIP",
        )
        rows = build_audit(db)
        row = next(r for r in rows if r.operation_name == "Pack it up")
        assert row.conflicting_stored_types is None


# =============================================================================
# Classifier: dry-run / apply / idempotency / safety rules
# =============================================================================

class TestClassifierDryRun:
    def test_dry_run_writes_nothing(self, db, make_product, make_work_center):
        op = _make_routing_op(db, make_product, make_work_center, "Pack items", operation_code=None)
        result = run_classifier(db, dry_run=True)
        assert result.dry_run is True
        assert result.applied_count == 0

        db.refresh(op)
        assert op.operation_type is None

        proposal = next(p for p in result.proposals if p.row_id == op.id)
        assert proposal.proposed_type == "PACK_SHIP"

    def test_dry_run_reports_before_after_stages(self, db, make_product, make_work_center):
        op = _make_routing_op(db, make_product, make_work_center, "Assembly step", operation_code=None)
        result = run_classifier(db, dry_run=True)
        proposal = next(p for p in result.proposals if p.row_id == op.id)
        assert proposal.before_stages == ["production", "any"]
        assert proposal.after_stages == ["assembly", "production", "any"]


class TestClassifierApply:
    def test_apply_sets_null_to_type(self, db, make_product, make_work_center):
        op = _make_routing_op(db, make_product, make_work_center, "Pack items", operation_code=None)
        result = run_classifier(db, dry_run=False)
        assert result.applied_count == 1

        db.refresh(op)
        assert op.operation_type == "PACK_SHIP"

    def test_apply_is_idempotent(self, db, make_product, make_work_center):
        op = _make_routing_op(db, make_product, make_work_center, "Pack items", operation_code=None)
        first = run_classifier(db, dry_run=False)
        assert first.applied_count == 1

        db.refresh(op)
        assert op.operation_type == "PACK_SHIP"

        second = run_classifier(db, dry_run=False)
        assert second.applied_count == 0, "re-running apply must find zero NULL rows left"

        db.refresh(op)
        assert op.operation_type == "PACK_SHIP"

    def test_apply_never_overwrites_a_human_set_type(self, db, make_product, make_work_center):
        op = _make_routing_op(
            db, make_product, make_work_center, "Pack items",
            operation_code=None, operation_type="QUALITY_CONTROL",
        )
        run_classifier(db, dry_run=False)
        db.refresh(op)
        assert op.operation_type == "QUALITY_CONTROL", "apply must never touch a non-NULL operation_type"

    def test_apply_writes_via_conditional_update_not_orm_mutate(
        self, db, make_product, make_work_center
    ):
        """The apply path must be a conditional UPDATE ... WHERE
        operation_type IS NULL (re-checked at write time), not an ORM
        read-then-mutate-then-commit — closing the TOCTOU window where a
        concurrent request could type the row between the initial SELECT
        and this function's write. Simulated in-process by setting the
        row's operation_type to non-NULL AFTER the row objects have
        already been read via _iter_null_typed_routing_ops (which
        run_classifier calls internally): if the write were still
        row.operation_type = proposed_type; db.add(row), the stale ORM
        object would silently clobber the concurrent value on commit.
        With the conditional UPDATE, the write matches zero rows for this
        id and the concurrently-set value survives."""
        op = _make_routing_op(db, make_product, make_work_center, "Pack items", operation_code=None)

        from app.services import operation_type_classifier as classifier_module

        real_iter = classifier_module._iter_null_typed_routing_ops

        def _iter_then_concurrently_type(db_):
            rows = real_iter(db_)
            # Simulate a concurrent request setting operation_type between
            # our read and our write, via a raw UPDATE so it doesn't go
            # through this same ORM session's identity map trickery.
            db_.execute(
                classifier_module.RoutingOperation.__table__.update()
                .where(classifier_module.RoutingOperation.id == op.id)
                .values(operation_type="QUALITY_CONTROL")
            )
            db_.commit()
            return rows

        original = classifier_module._iter_null_typed_routing_ops
        classifier_module._iter_null_typed_routing_ops = _iter_then_concurrently_type
        try:
            result = run_classifier(db, dry_run=False)
        finally:
            classifier_module._iter_null_typed_routing_ops = original

        # Our conditional UPDATE matched zero rows for this id (the
        # concurrent write already changed operation_type away from NULL),
        # so applied_count reflects that -- not a stale in-memory count.
        assert result.applied_count == 0
        db.refresh(op)
        assert op.operation_type == "QUALITY_CONTROL", (
            "the concurrently-set value must survive; the classifier's "
            "conditional UPDATE must not clobber it"
        )

    def test_apply_second_run_reports_zero_from_rowcount(self, db, make_product, make_work_center):
        """applied_count on a second run must come from actual UPDATE
        rowcount (zero matching rows), not from re-counting proposals."""
        _make_routing_op(db, make_product, make_work_center, "Pack items", operation_code=None)
        first = run_classifier(db, dry_run=False)
        assert first.applied_count == 1

        second = run_classifier(db, dry_run=False)
        assert second.applied_count == 0

    def test_apply_only_touches_null_rows_both_tables(
        self, db, make_product, make_work_center, make_production_order
    ):
        routing_op = _make_routing_op(db, make_product, make_work_center, "Pack items", operation_code=None)
        po_op, _po = _make_po_op(
            db, make_product, make_work_center, make_production_order,
            "Assembly", operation_code=None,
        )
        result = run_classifier(db, dry_run=False)
        assert result.applied_count == 2

        db.refresh(routing_op)
        db.refresh(po_op)
        assert routing_op.operation_type == "PACK_SHIP"
        assert po_op.operation_type == "ASSEMBLY"

    def test_material_bearing_refused_no_consume_needs_manual(self, db, make_product, make_work_center):
        """An op named 'Sand and inspect' matching a no-consume rule but
        carrying material rows must never be auto-applied — surfaced as
        needs-manual-decision, left NULL."""
        op = _make_routing_op(db, make_product, make_work_center, "Sanding", operation_code=None)
        component = make_product(item_type="supply")
        db.add(RoutingOperationMaterial(
            routing_operation_id=op.id,
            component_id=component.id,
            quantity=Decimal("1"),
            quantity_per="unit",
            unit="EA",
        ))
        db.commit()

        result = run_classifier(db, dry_run=False)
        assert result.applied_count == 0
        assert result.skipped_manual_decision_count == 1

        db.refresh(op)
        assert op.operation_type is None

        proposal = next(p for p in result.proposals if p.row_id == op.id)
        assert proposal.proposed_type is None
        assert proposal.reason == MANUAL_DECISION_REASON
        assert proposal.material_bearing is True

    def test_material_bearing_po_op_material_also_refused(
        self, db, make_product, make_work_center, make_production_order
    ):
        po_op, _po = _make_po_op(
            db, make_product, make_work_center, make_production_order,
            "Quality Control", operation_code=None,
        )
        component = make_product(item_type="supply")
        db.add(ProductionOrderOperationMaterial(
            production_order_operation_id=po_op.id,
            component_id=component.id,
            quantity_required=Decimal("1"),
            unit="EA",
            status="pending",
        ))
        db.commit()

        result = run_classifier(db, dry_run=False)
        assert result.applied_count == 0
        assert result.skipped_manual_decision_count == 1
        db.refresh(po_op)
        assert po_op.operation_type is None

    def test_blank_name_no_proposal_not_applied(self, db, make_product, make_work_center):
        op = _make_routing_op(db, make_product, make_work_center, "", operation_code=None)
        result = run_classifier(db, dry_run=False)
        assert result.applied_count == 0
        assert result.skipped_no_match_count >= 1
        db.refresh(op)
        assert op.operation_type is None

    def test_mixed_name_flagged_qc_plus_pack(self, db, make_product, make_work_center):
        op = _make_routing_op(db, make_product, make_work_center, "QC + Pack", operation_code=None)
        result = run_classifier(db, dry_run=False)
        proposal = next(p for p in result.proposals if p.row_id == op.id)
        assert proposal.proposed_type == "PACK_SHIP"
        assert proposal.reason == MIXED_NAME_REASON

        db.refresh(op)
        assert op.operation_type == "PACK_SHIP"

    def test_non_terminal_exposure_count(
        self, db, make_product, make_work_center, make_production_order
    ):
        _make_po_op(
            db, make_product, make_work_center, make_production_order,
            "Pack items", operation_code=None, po_status="in_progress",
        )
        result = run_classifier(db, dry_run=True)
        assert result.non_terminal_exposure_count >= 1


# =============================================================================
# Admin endpoints: auth
# =============================================================================

ADMIN_ENDPOINTS = [
    ("get", "/api/v1/admin/operation-types/audit"),
    ("post", "/api/v1/admin/operation-types/classify"),
    ("post", "/api/v1/admin/operation-types"),
    ("put", "/api/v1/admin/operation-types/GENERAL"),
    ("post", "/api/v1/admin/operation-types/GENERAL/deactivate"),
]


@pytest.fixture
def customer_client(db):
    """TestClient authenticated as a NON-STAFF (account_type='customer')
    user — mirrors tests/endpoints/test_inventory_auth.py's fixture."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import get_db
    from app.models.user import User
    from app.core.security import create_access_token

    customer = User(
        email=f"buyer-{id(db)}@example.com",
        password_hash="not-a-real-hash",
        account_type="customer",
        status="active",
    )
    db.add(customer)
    db.flush()
    token = create_access_token(user_id=customer.id)

    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c

    app.dependency_overrides.clear()


class TestAdminEndpointsUnauthenticated:
    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
    def test_requires_auth(self, unauthed_client, method, path):
        kwargs = {"json": {}} if method in ("post", "put") else {}
        resp = getattr(unauthed_client, method)(path, **kwargs)
        assert resp.status_code == 401


class TestAdminEndpointsNonStaffForbidden:
    """PRO-leak-audit lesson: every admin endpoint must reject an
    authenticated non-staff (customer) account with 403."""

    @pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
    def test_non_staff_forbidden(self, customer_client, method, path):
        kwargs = {}
        if method in ("post", "put"):
            kwargs["json"] = {}
        resp = getattr(customer_client, method)(path, **kwargs)
        assert resp.status_code == 403


# =============================================================================
# Admin endpoints: audit + classify (via HTTP, staff-authed `client`)
# =============================================================================

class TestAuditEndpoint:
    def test_audit_endpoint_shape(self, client, db, make_product, make_work_center):
        _make_routing_op(db, make_product, make_work_center, "Print", operation_code="PRINT")
        response = client.get("/api/v1/admin/operation-types/audit")
        assert response.status_code == 200
        body = response.json()
        assert "rows" in body
        assert "total_pairs" in body
        assert "total_in_flight_exposure" in body
        assert body["total_pairs"] >= 1


class TestClassifyEndpoint:
    def test_classify_dry_run_default_writes_nothing(self, client, db, make_product, make_work_center):
        op = _make_routing_op(db, make_product, make_work_center, "Pack items", operation_code=None)
        response = client.post("/api/v1/admin/operation-types/classify", json={})
        assert response.status_code == 200
        body = response.json()
        assert body["dry_run"] is True
        assert body["applied_count"] == 0

        db.refresh(op)
        assert op.operation_type is None

    def test_classify_apply_sets_type_and_stamps_applied_by(self, client, db, make_product, make_work_center):
        op = _make_routing_op(db, make_product, make_work_center, "Pack items", operation_code=None)
        response = client.post("/api/v1/admin/operation-types/classify", json={"dry_run": False})
        assert response.status_code == 200
        body = response.json()
        assert body["applied_count"] == 1
        assert body["applied_by"] is not None
        assert body["applied_at"] is not None

        db.refresh(op)
        assert op.operation_type == "PACK_SHIP"


# =============================================================================
# Admin CRUD: is_system locks + 409 in-use guard
# =============================================================================

class TestAdminCRUD:
    def test_create_custom_type(self, client, db):
        response = client.post(
            "/api/v1/admin/operation-types",
            json={
                "code": "CUSTOM_TEST",
                "label": "Custom Test Type",
                "consume_stages": ["production", "any"],
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["code"] == "CUSTOM_TEST"
        assert body["is_system"] is False

    def test_create_duplicate_code_rejected(self, client, db):
        client.post(
            "/api/v1/admin/operation-types",
            json={"code": "DUPE_TEST", "label": "Dupe", "consume_stages": ["any"]},
        )
        response = client.post(
            "/api/v1/admin/operation-types",
            json={"code": "DUPE_TEST", "label": "Dupe Again", "consume_stages": ["any"]},
        )
        assert response.status_code == 400

    def test_system_row_label_and_sort_order_editable(self, client, db):
        response = client.put(
            "/api/v1/admin/operation-types/GENERAL",
            json={"label": "Other (renamed)", "sort_order": 95},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["label"] == "Other (renamed)"
        assert body["sort_order"] == 95

    def test_system_row_consume_stages_locked(self, client, db):
        response = client.put(
            "/api/v1/admin/operation-types/GENERAL",
            json={"consume_stages": ["shipping"]},
        )
        assert response.status_code == 400

    def test_system_row_is_qc_locked(self, client, db):
        response = client.put(
            "/api/v1/admin/operation-types/QUALITY_CONTROL",
            json={"is_qc": False},
        )
        assert response.status_code == 400

    def test_system_row_same_value_consume_stages_not_locked(self, client, db):
        """Submitting the SAME consume_stages value as already stored is not
        a change and must not be rejected as a lock violation."""
        response = client.put(
            "/api/v1/admin/operation-types/GENERAL",
            json={"consume_stages": ["production", "any"]},
        )
        assert response.status_code == 200

    @pytest.mark.parametrize("field,value", [
        ("label", None),
        ("consume_stages", None),
        ("is_qc", None),
        ("sort_order", None),
        ("is_active", None),
    ])
    def test_explicit_null_rejected_for_not_nullable_fields(self, client, db, field, value):
        """An explicit JSON null for a NOT NULL-backed column (label,
        consume_stages, is_qc, sort_order, is_active) is rejected with 422
        rather than reaching the ORM as a null write (e.g. list(None) on
        consume_stages). Omitting the field entirely remains fine (covered
        by test_system_row_label_and_sort_order_editable etc., which never
        sends the other fields)."""
        response = client.put(
            "/api/v1/admin/operation-types/GENERAL",
            json={field: value},
        )
        assert response.status_code == 422

    def test_explicit_null_still_accepted_for_nullable_fields(self, client, db):
        """description/category are genuinely nullable columns — explicit
        null must still be accepted for these (only the NOT NULL-backed
        fields are rejected)."""
        response = client.put(
            "/api/v1/admin/operation-types/GENERAL",
            json={"description": None, "category": None},
        )
        assert response.status_code == 200

    def test_deactivate_is_system_row_soft_only(self, client, db):
        response = client.post("/api/v1/admin/operation-types/SANDING/deactivate")
        assert response.status_code == 200
        body = response.json()
        assert body["is_active"] is False

        op_type = db.query(OperationType).filter(OperationType.code == "SANDING").first()
        assert op_type is not None, "is_system row must never be hard-deleted"

    def test_consume_stages_edit_referenced_by_non_terminal_po_returns_409(
        self, client, db, make_product, make_work_center, make_production_order
    ):
        # consume_stages is LOCKED on system types (asserted separately
        # above), so the in-use 409 guard is exercised via a custom type.
        create_resp = client.post(
            "/api/v1/admin/operation-types",
            json={"code": "CUSTOM_INUSE", "label": "Custom In Use", "consume_stages": ["production", "any"]},
        )
        assert create_resp.status_code == 201

        _make_po_op(
            db, make_product, make_work_center, make_production_order,
            "Custom op", operation_code=None, operation_type="CUSTOM_INUSE", po_status="in_progress",
        )
        response = client.put(
            "/api/v1/admin/operation-types/CUSTOM_INUSE",
            json={"consume_stages": ["shipping"]},
        )
        assert response.status_code == 409

    def test_consume_stages_edit_referenced_only_by_terminal_po_allowed(
        self, client, db, make_product, make_work_center, make_production_order
    ):
        create_resp = client.post(
            "/api/v1/admin/operation-types",
            json={"code": "CUSTOM_TERMINAL", "label": "Custom Terminal", "consume_stages": ["production", "any"]},
        )
        assert create_resp.status_code == 201

        _make_po_op(
            db, make_product, make_work_center, make_production_order,
            "Custom op", operation_code=None, operation_type="CUSTOM_TERMINAL", po_status="complete",
        )
        response = client.put(
            "/api/v1/admin/operation-types/CUSTOM_TERMINAL",
            json={"consume_stages": ["shipping", "any", "production"]},
        )
        assert response.status_code == 200
