"""
Tests for #876 PR-1: operation-type catalog schema, seed, resolver.

This PR is INERT — it ships schema + seed + a dormant resolver that no
consumer calls yet. The load-bearing proof is predicate-equivalence: for
every one of the 18 legacy operation_code dict keys, the seeded catalog
type's consume_stages must produce IDENTICAL results through both live
consumer predicate shapes as the legacy code path does, so the migration's
exact-code backfill (migration 101) is provably behavior-neutral.

Covers:
- Predicate-equivalence proof (all 18 legacy keys x both predicate shapes)
- Resolver precedence (type beats code; unknown/inactive type falls
  through to code; NULL/unknown -> default)
- Seed idempotency (running the seed helper twice = no change)
- Backfill idempotency + exact-match-only scoping (OP10/FINISH stay NULL)
- GET /api/v1/operation-types auth + shape
"""
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.manufacturing import OperationType, Routing, RoutingOperation
from app.models.bom import BOMLine
from app.services.operation_material_mapping import (
    OPERATION_CONSUME_STAGES,
    DEFAULT_CONSUME_STAGES,
    get_consume_stages_for_operation,
    load_operation_type_stage_map,
    resolve_consume_stages,
)

# Mirrors migrations/versions/101_operation_types.py::SEED_OPERATION_TYPES /
# BACKFILL_ALIAS_MAP verbatim, so a drift between the migration and this test
# fails loudly rather than silently.
SEED_OPERATION_TYPES = [
    ("FDM_PRINT", ["production", "any"], False),
    ("RESIN_PRINT", ["production", "any"], False),
    ("ASSEMBLY", ["assembly", "production", "any"], False),
    ("QUALITY_CONTROL", ["any"], True),
    ("SUPPORT_REMOVAL", ["any"], False),
    ("SANDING", ["any"], False),
    ("PAINTING", ["finishing", "any"], False),
    ("PACK_SHIP", ["shipping", "any"], False),
    ("GENERAL", ["production", "any"], False),
]

BACKFILL_ALIAS_MAP = {
    "PRINT": "FDM_PRINT",
    "EXTRUDE": "GENERAL",
    "MOLD": "GENERAL",
    "CUT": "GENERAL",
    "MACHINE": "GENERAL",
    "ASSEMBLE": "ASSEMBLY",
    "BUILD": "ASSEMBLY",
    "WELD": "ASSEMBLY",
    "QC": "QUALITY_CONTROL",
    "INSPECT": "QUALITY_CONTROL",
    "TEST": "QUALITY_CONTROL",
    "CLEAN": "SUPPORT_REMOVAL",
    "SAND": "SANDING",
    "PAINT": "PAINTING",
    "COAT": "PAINTING",
    "PACK": "PACK_SHIP",
    "SHIP": "PACK_SHIP",
    "LABEL": "PACK_SHIP",
}


def _seed_operation_types(db):
    """Idempotent INSERT-if-missing seed helper, mirroring migration 101
    step 2, for use directly against the test DB (no alembic run in tests)."""
    existing_codes = {code for (code,) in db.query(OperationType.code).all()}
    seed_source = {
        "FDM_PRINT": ("FDM Print", "print", ["production", "any"], False, 10),
        "RESIN_PRINT": ("Resin Print", "print", ["production", "any"], False, 20),
        "ASSEMBLY": ("Assembly", "assembly", ["assembly", "production", "any"], False, 30),
        "QUALITY_CONTROL": ("Quality Control", "quality", ["any"], True, 40),
        "SUPPORT_REMOVAL": ("Support Removal / Cleanup", "finishing", ["any"], False, 50),
        "SANDING": ("Sanding", "finishing", ["any"], False, 60),
        "PAINTING": ("Painting", "finishing", ["finishing", "any"], False, 70),
        "PACK_SHIP": ("Pack / Ship", "shipping", ["shipping", "any"], False, 80),
        "GENERAL": ("Other (consumes at production)", "other", ["production", "any"], False, 90),
    }
    created = []
    for code, (label, category, stages, is_qc, sort_order) in seed_source.items():
        if code in existing_codes:
            continue
        row = OperationType(
            code=code,
            label=label,
            category=category,
            consume_stages=stages,
            is_qc=is_qc,
            is_system=True,
            is_active=True,
            sort_order=sort_order,
        )
        db.add(row)
        created.append(code)
    db.flush()
    return created


def _backfill_operation_types(db):
    """Idempotent exact-match-only backfill helper, mirroring migration 101
    step 4, for use directly against the test DB."""
    total_updated = 0
    for table in ("routing_operations", "production_order_operations"):
        for legacy_code, type_code in BACKFILL_ALIAS_MAP.items():
            result = db.execute(
                text(
                    f"""
                    UPDATE {table}
                    SET operation_type = :type_code
                    WHERE operation_type IS NULL
                      AND UPPER(operation_code) = :legacy_code
                    """
                ),
                {"type_code": type_code, "legacy_code": legacy_code},
            )
            total_updated += result.rowcount or 0
    db.commit()
    return total_updated


# =============================================================================
# Predicate-equivalence proof — the load-bearing test
# =============================================================================

class TestPredicateEquivalence:
    """
    For every one of the 18 legacy OPERATION_CONSUME_STAGES keys, the seeded
    type's consume_stages must be IDENTICAL to the legacy dict's stage list,
    and must produce identical results through BOTH live consumer predicate
    shapes:
      - `stage in stages` (inventory_service._get_stage_op_materials /
        _stage_has_consumed_op_materials / _get_stage_component_ids pattern)
      - `BOMLine.consume_stage.in_(stages)` (operation_blocking
        .get_bom_lines_for_operation pattern) for both 'production' and
        'shipping' consume_stage values (the two live BOMLine values).

    This proves the migration's exact-code backfill is behavior-neutral:
    a row typed by exact-code match resolves identically to how it resolves
    today via the untouched legacy code path.
    """

    @pytest.fixture(autouse=True)
    def _seed(self, db):
        _seed_operation_types(db)
        db.commit()

    def _type_for_code(self, db, legacy_code):
        type_code = BACKFILL_ALIAS_MAP[legacy_code]
        return db.query(OperationType).filter(OperationType.code == type_code).first()

    @pytest.mark.parametrize("legacy_code", list(OPERATION_CONSUME_STAGES.keys()))
    def test_seeded_type_stages_match_legacy_dict_exactly(self, db, legacy_code):
        """alias(code) -> type.consume_stages == OPERATION_CONSUME_STAGES[code]."""
        op_type = self._type_for_code(db, legacy_code)
        assert op_type is not None, f"no seeded type for legacy code {legacy_code}"
        assert list(op_type.consume_stages) == OPERATION_CONSUME_STAGES[legacy_code]

    @pytest.mark.parametrize("legacy_code", list(OPERATION_CONSUME_STAGES.keys()))
    @pytest.mark.parametrize("stage", ["production", "shipping", "assembly", "finishing", "any"])
    def test_membership_predicate_equivalence(self, db, legacy_code, stage):
        """`stage in stages` (inventory_service pattern) must agree between
        the legacy code path and the seeded type's stored stages."""
        op_type = self._type_for_code(db, legacy_code)
        legacy_stages = get_consume_stages_for_operation(legacy_code)
        typed_stages = list(op_type.consume_stages)

        legacy_result = stage in legacy_stages
        typed_result = stage in typed_stages
        assert legacy_result == typed_result, (
            f"stage={stage!r} legacy_code={legacy_code!r}: "
            f"legacy={legacy_result} typed={typed_result}"
        )

    @pytest.mark.parametrize("legacy_code", list(OPERATION_CONSUME_STAGES.keys()))
    @pytest.mark.parametrize("bom_consume_stage", ["production", "shipping"])
    def test_bomline_predicate_equivalence(self, db, legacy_code, bom_consume_stage, make_product, make_bom):
        """`BOMLine.consume_stage.in_(stages)` (operation_blocking pattern)
        must agree between the legacy code path and the seeded type's
        stored stages, for both live BOMLine.consume_stage values."""
        op_type = self._type_for_code(db, legacy_code)
        legacy_stages = get_consume_stages_for_operation(legacy_code)
        typed_stages = list(op_type.consume_stages)

        fg = make_product(item_type="finished_good")
        raw = make_product(item_type="supply", is_raw_material=True)
        bom = make_bom(
            product_id=fg.id,
            lines=[{"component_id": raw.id, "quantity": Decimal("1"), "unit": "EA"}],
        )
        line = bom.lines[0] if hasattr(bom, "lines") else db.query(BOMLine).filter(BOMLine.bom_id == bom.id).first()
        line.consume_stage = bom_consume_stage
        db.flush()

        legacy_match = (
            db.query(BOMLine)
            .filter(BOMLine.id == line.id, BOMLine.consume_stage.in_(legacy_stages))
            .first()
            is not None
        )
        typed_match = (
            db.query(BOMLine)
            .filter(BOMLine.id == line.id, BOMLine.consume_stage.in_(typed_stages))
            .first()
            is not None
        )
        assert legacy_match == typed_match, (
            f"bom_consume_stage={bom_consume_stage!r} legacy_code={legacy_code!r}: "
            f"legacy={legacy_match} typed={typed_match}"
        )


# =============================================================================
# Resolver precedence
# =============================================================================

class TestResolverPrecedence:
    @pytest.fixture(autouse=True)
    def _seed(self, db):
        _seed_operation_types(db)
        db.commit()

    def test_type_beats_code(self, db):
        """A typed op resolves via its type even when operation_code would
        resolve to something different through the legacy map."""
        type_map = load_operation_type_stage_map(db)
        # PACK_SHIP type vs. a code ("PRINT") that would legacy-resolve to
        # production-only — the stored type must win.
        stages = resolve_consume_stages(type_map, "PACK_SHIP", "PRINT")
        assert stages == ["shipping", "any"]

    def test_unknown_type_falls_through_to_code(self, db):
        """An operation_type not present in the catalog (stale/hand-edited
        data) falls through to the legacy code resolution rather than
        raising or silently defaulting."""
        type_map = load_operation_type_stage_map(db)
        stages = resolve_consume_stages(type_map, "NOT_A_REAL_TYPE", "PACK")
        assert stages == get_consume_stages_for_operation("PACK")
        assert "shipping" in stages

    def test_inactive_type_falls_through_to_code(self, db):
        """A deactivated type is excluded from the active-only map load
        used elsewhere, but load_operation_type_stage_map includes inactive
        rows so history never breaks. This test proves the fallback path
        for when a type code isn't in the map at all (simulating a type
        deleted outright, which the design forbids for system rows, but is
        the fallback contract nonetheless)."""
        type_map = {}  # simulates the type genuinely absent from the map
        stages = resolve_consume_stages(type_map, "PACK_SHIP", "PACK")
        assert stages == get_consume_stages_for_operation("PACK")

    def test_null_type_uses_code(self, db):
        type_map = load_operation_type_stage_map(db)
        stages = resolve_consume_stages(type_map, None, "ASSEMBLE")
        assert stages == get_consume_stages_for_operation("ASSEMBLE")
        assert "assembly" in stages

    def test_null_type_and_null_code_returns_default(self, db):
        type_map = load_operation_type_stage_map(db)
        stages = resolve_consume_stages(type_map, None, None)
        assert stages == DEFAULT_CONSUME_STAGES
        assert stages == ["production", "any"]

    def test_null_type_and_unknown_code_returns_default(self, db):
        type_map = load_operation_type_stage_map(db)
        stages = resolve_consume_stages(type_map, None, "SOME_UNKNOWN_CODE")
        assert stages == DEFAULT_CONSUME_STAGES

    def test_empty_type_string_uses_code(self, db):
        """Empty-string operation_type (falsy) must not attempt a type-map
        lookup — falls straight through to code resolution."""
        type_map = load_operation_type_stage_map(db)
        stages = resolve_consume_stages(type_map, "", "PRINT")
        assert stages == get_consume_stages_for_operation("PRINT")

    def test_load_operation_type_stage_map_includes_inactive(self, db):
        """load_operation_type_stage_map must include inactive rows so a
        routing operation typed before its type was deactivated still
        resolves — history must never break because a type was retired."""
        op_type = db.query(OperationType).filter(OperationType.code == "PACK_SHIP").first()
        op_type.is_active = False
        db.flush()

        type_map = load_operation_type_stage_map(db)
        assert "PACK_SHIP" in type_map
        assert type_map["PACK_SHIP"] == ["shipping", "any"]

    def test_load_operation_type_stage_map_empty_when_table_missing(self, db, monkeypatch):
        """If the OperationType query fails (e.g. table not migrated on an
        older DB), the loader degrades to an empty map rather than raising,
        so resolve_consume_stages falls through to the legacy code path for
        every call."""
        def _boom(*args, **kwargs):
            raise Exception("relation \"operation_types\" does not exist")

        monkeypatch.setattr(db, "query", _boom)
        type_map = load_operation_type_stage_map(db)
        assert type_map == {}


# =============================================================================
# Seed + backfill idempotency
# =============================================================================

class TestSeedIdempotency:
    def test_seed_creates_nine_system_rows(self, db):
        created = _seed_operation_types(db)
        db.commit()
        assert len(created) == 9
        assert set(created) == {code for code, _, _ in SEED_OPERATION_TYPES}

        rows = db.query(OperationType).filter(OperationType.is_system.is_(True)).all()
        assert len(rows) == 9

    def test_seed_running_twice_creates_nothing_new(self, db):
        first_created = _seed_operation_types(db)
        db.commit()
        assert len(first_created) == 9

        count_after_first = db.query(OperationType).count()

        second_created = _seed_operation_types(db)
        db.commit()
        assert second_created == []

        count_after_second = db.query(OperationType).count()
        assert count_after_first == count_after_second

    def test_seed_is_unique_on_code(self, db):
        _seed_operation_types(db)
        db.commit()
        codes = [c for (c,) in db.query(OperationType.code).all()]
        assert len(codes) == len(set(codes))


class TestBackfillIdempotency:
    def test_backfill_types_exact_matches_only(self, db, make_product):
        """An OP10 row (no exact legacy-code match — routing editor
        autofill) and a FINISH row (deliberately excluded) both stay NULL.
        A PRINT row (exact match) gets typed FDM_PRINT."""
        _seed_operation_types(db)
        db.commit()

        product = make_product(item_type="finished_good")
        routing = Routing(product_id=product.id, code="RTG-TEST", is_template=False)
        db.add(routing)
        db.flush()

        from app.models.work_center import WorkCenter
        wc = db.query(WorkCenter).first()

        op_op10 = RoutingOperation(
            routing_id=routing.id, work_center_id=wc.id, sequence=10,
            operation_code="OP10", operation_name="3D Print",
            run_time_minutes=Decimal("60"),
        )
        op_finish = RoutingOperation(
            routing_id=routing.id, work_center_id=wc.id, sequence=20,
            operation_code="FINISH", operation_name="Pack/Ship",
            run_time_minutes=Decimal("2"),
        )
        op_print = RoutingOperation(
            routing_id=routing.id, work_center_id=wc.id, sequence=30,
            operation_code="PRINT", operation_name="Print",
            run_time_minutes=Decimal("60"),
        )
        db.add_all([op_op10, op_finish, op_print])
        db.commit()

        _backfill_operation_types(db)

        db.refresh(op_op10)
        db.refresh(op_finish)
        db.refresh(op_print)

        assert op_op10.operation_type is None, "OP10 has no exact legacy-code match — must stay NULL"
        assert op_finish.operation_type is None, "FINISH is deliberately excluded — must stay NULL"
        assert op_print.operation_type == "FDM_PRINT", "PRINT is an exact legacy-code match"

    def test_backfill_running_twice_is_a_no_op(self, db, make_product):
        _seed_operation_types(db)
        db.commit()

        product = make_product(item_type="finished_good")
        routing = Routing(product_id=product.id, code="RTG-TEST2", is_template=False)
        db.add(routing)
        db.flush()

        from app.models.work_center import WorkCenter
        wc = db.query(WorkCenter).first()

        op = RoutingOperation(
            routing_id=routing.id, work_center_id=wc.id, sequence=10,
            operation_code="ASSEMBLE", operation_name="Assembly",
            run_time_minutes=Decimal("10"),
        )
        db.add(op)
        db.commit()

        first_updated = _backfill_operation_types(db)
        db.refresh(op)
        assert op.operation_type == "ASSEMBLY"
        assert first_updated >= 1

        second_updated = _backfill_operation_types(db)
        db.refresh(op)
        assert op.operation_type == "ASSEMBLY", "re-running must not change an already-typed row"
        # WHERE operation_type IS NULL excludes every row typed by the first
        # pass, so the second pass must be a complete no-op.
        assert second_updated == 0, "second backfill pass must update zero rows"

    def test_backfill_never_overwrites_a_human_set_type(self, db, make_product):
        """A row a human already typed (even to something unexpected) must
        never be overwritten — the WHERE operation_type IS NULL guard is
        what makes this true; assert it holds."""
        _seed_operation_types(db)
        db.commit()

        product = make_product(item_type="finished_good")
        routing = Routing(product_id=product.id, code="RTG-TEST3", is_template=False)
        db.add(routing)
        db.flush()

        from app.models.work_center import WorkCenter
        wc = db.query(WorkCenter).first()

        op = RoutingOperation(
            routing_id=routing.id, work_center_id=wc.id, sequence=10,
            operation_code="PRINT", operation_name="Print",
            operation_type="QUALITY_CONTROL",  # deliberately "wrong" / human-set
            run_time_minutes=Decimal("60"),
        )
        db.add(op)
        db.commit()

        _backfill_operation_types(db)
        db.refresh(op)
        assert op.operation_type == "QUALITY_CONTROL", "backfill must never overwrite a non-NULL type"


# =============================================================================
# GET /api/v1/operation-types
# =============================================================================

class TestOperationTypesEndpoint:
    @pytest.fixture(autouse=True)
    def _seed(self, db):
        _seed_operation_types(db)
        db.commit()

    def test_requires_auth(self, unauthed_client):
        response = unauthed_client.get("/api/v1/operation-types")
        assert response.status_code == 401

    def test_lists_active_types_ordered_by_sort_order(self, client, db):
        response = client.get("/api/v1/operation-types")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 9

        codes_in_order = [row["code"] for row in body]
        sort_orders = [row["sort_order"] for row in body]
        assert sort_orders == sorted(sort_orders)
        assert "FDM_PRINT" in codes_in_order
        assert "PACK_SHIP" in codes_in_order

        pack_ship = next(row for row in body if row["code"] == "PACK_SHIP")
        assert pack_ship["consume_stages"] == ["shipping", "any"]
        assert pack_ship["is_qc"] is False

        qc = next(row for row in body if row["code"] == "QUALITY_CONTROL")
        assert qc["is_qc"] is True

    def test_excludes_inactive_types(self, client, db):
        op_type = db.query(OperationType).filter(OperationType.code == "SANDING").first()
        op_type.is_active = False
        db.commit()

        response = client.get("/api/v1/operation-types")
        assert response.status_code == 200
        codes = [row["code"] for row in response.json()]
        assert "SANDING" not in codes
        assert len(codes) == 8
