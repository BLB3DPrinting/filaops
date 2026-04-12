"""
Tests for app/services/compatibility_service.py

Covers:
- check_material_printer: unit-level checks (enclosure, nozzle temp, bed temp, diameter)
- check_operation_compatibility: operation with/without printer, with/without materials
- check_order_compatibility: full order aggregation
"""
import uuid
import pytest
from decimal import Decimal

from app.models.material import MaterialType
from app.models.printer import Printer
from app.models.manufacturing import Resource
from app.models.production_order import (
    ProductionOrderOperation,
    ProductionOrderOperationMaterial,
)
from app.services.compatibility_service import (
    check_material_printer,
    check_operation_compatibility,
    check_order_compatibility,
)


# =============================================================================
# Helpers
# =============================================================================

def _uid():
    return uuid.uuid4().hex[:8]


def _make_material_type(db, **kwargs):
    uid = _uid()
    mt = MaterialType(
        code=kwargs.pop("code", f"MT-{uid}"),
        name=kwargs.pop("name", f"Material {uid}"),
        base_material=kwargs.pop("base_material", "PLA"),
        density=kwargs.pop("density", Decimal("1.24")),
        base_price_per_kg=kwargs.pop("base_price_per_kg", Decimal("20.00")),
        requires_enclosure=kwargs.pop("requires_enclosure", False),
        active=True,
        is_customer_visible=True,
        **kwargs,
    )
    db.add(mt)
    db.flush()
    return mt


def _make_printer(db, work_center_id=None, **kwargs):
    uid = _uid()
    p = Printer(
        code=kwargs.pop("code", f"P-{uid}"),
        name=kwargs.pop("name", f"Printer {uid}"),
        model=kwargs.pop("model", "Generic"),
        brand=kwargs.pop("brand", "generic"),
        capabilities=kwargs.pop("capabilities", None),
        work_center_id=work_center_id,
        active=True,
    )
    db.add(p)
    db.flush()
    return p


def _make_resource(db, work_center_id, **kwargs):
    uid = _uid()
    r = Resource(
        work_center_id=work_center_id,
        code=kwargs.pop("code", f"R-{uid}"),
        name=kwargs.pop("name", f"Resource {uid}"),
        printer_class=kwargs.pop("printer_class", "open"),
        status="available",
        is_active=True,
    )
    db.add(r)
    db.flush()
    return r


# =============================================================================
# check_material_printer — unit-level checks
# =============================================================================

class TestCheckMaterialPrinter:
    """Tests for the core check_material_printer function."""

    def test_fully_compatible_returns_no_issues(self, db):
        mt = _make_material_type(
            db,
            base_material="PLA",
            requires_enclosure=False,
            nozzle_temp_max=220,
            bed_temp_max=60,
            filament_diameter=Decimal("1.75"),
        )
        caps = {
            "enclosure": False,
            "max_temp_hotend": 300,
            "max_temp_bed": 110,
            "filament_diameters": [1.75],
        }
        issues = check_material_printer(mt, "TestPrinter", caps)
        assert issues == []

    def test_enclosure_required_but_open(self, db):
        mt = _make_material_type(
            db,
            base_material="ABS",
            requires_enclosure=True,
        )
        caps = {"enclosure": False}
        issues = check_material_printer(mt, "OpenPrinter", caps)
        assert len(issues) == 1
        assert issues[0].check == "enclosure"
        assert issues[0].severity == "error"
        assert "requires an enclosure" in issues[0].message

    def test_enclosure_required_and_enclosed_ok(self, db):
        mt = _make_material_type(
            db,
            base_material="ABS",
            requires_enclosure=True,
        )
        caps = {"enclosure": True}
        issues = check_material_printer(mt, "EnclosedPrinter", caps)
        # No enclosure issue
        assert not any(i.check == "enclosure" for i in issues)

    def test_enclosure_required_but_unknown_is_warning(self, db):
        """When enclosure capability is absent from caps, downgrade to warning
        so unconfigured printers don't hard-block scheduling."""
        mt = _make_material_type(
            db,
            base_material="ABS",
            requires_enclosure=True,
        )
        caps = {}  # no enclosure key at all
        issues = check_material_printer(mt, "UnknownPrinter", caps)
        enclosure_issues = [i for i in issues if i.check == "enclosure"]
        assert len(enclosure_issues) == 1
        assert enclosure_issues[0].severity == "warning"
        assert "unknown" in enclosure_issues[0].message.lower()

    def test_nozzle_temp_too_high(self, db):
        mt = _make_material_type(
            db,
            nozzle_temp_max=320,
        )
        caps = {"max_temp_hotend": 300}
        issues = check_material_printer(mt, "TestPrinter", caps)
        assert len(issues) == 1
        assert issues[0].check == "nozzle_temp"
        assert issues[0].severity == "error"
        assert "320°C" in issues[0].message
        assert "300°C" in issues[0].message

    def test_nozzle_temp_within_range(self, db):
        mt = _make_material_type(db, nozzle_temp_max=250)
        caps = {"max_temp_hotend": 300}
        issues = check_material_printer(mt, "TestPrinter", caps)
        assert not any(i.check == "nozzle_temp" for i in issues)

    def test_bed_temp_too_high(self, db):
        mt = _make_material_type(db, bed_temp_max=120)
        caps = {"max_temp_bed": 100}
        issues = check_material_printer(mt, "TestPrinter", caps)
        assert len(issues) == 1
        assert issues[0].check == "bed_temp"
        assert issues[0].severity == "warning"
        assert "120°C" in issues[0].message

    def test_warnings_only_still_compatible(self, db):
        """Warnings (e.g. bed temp) should not mark an operation incompatible."""
        from app.services.compatibility_service import OperationCompatibility, CompatibilityIssue
        op_compat = OperationCompatibility(
            operation_id=1,
            operation_name="Print",
            printer_name="TestPrinter",
            issues=[CompatibilityIssue(
                severity="warning", check="bed_temp",
                message="bed temp warning", material_name="PLA", printer_name="TestPrinter",
            )],
        )
        assert op_compat.compatible is True

    def test_bed_temp_within_range(self, db):
        mt = _make_material_type(db, bed_temp_max=80)
        caps = {"max_temp_bed": 110}
        issues = check_material_printer(mt, "TestPrinter", caps)
        assert not any(i.check == "bed_temp" for i in issues)

    def test_diameter_mismatch(self, db):
        mt = _make_material_type(
            db,
            filament_diameter=Decimal("2.85"),
        )
        caps = {"filament_diameters": [1.75]}
        issues = check_material_printer(mt, "TestPrinter", caps)
        assert len(issues) == 1
        assert issues[0].check == "diameter"
        assert issues[0].severity == "error"
        assert "2.85" in issues[0].message

    def test_diameter_match(self, db):
        mt = _make_material_type(
            db,
            filament_diameter=Decimal("1.75"),
        )
        caps = {"filament_diameters": [1.75, 2.85]}
        issues = check_material_printer(mt, "TestPrinter", caps)
        assert not any(i.check == "diameter" for i in issues)

    def test_no_diameter_in_caps_skips_check(self, db):
        mt = _make_material_type(
            db,
            filament_diameter=Decimal("1.75"),
        )
        caps = {}  # no filament_diameters key
        issues = check_material_printer(mt, "TestPrinter", caps)
        assert not any(i.check == "diameter" for i in issues)

    def test_no_temps_in_caps_skips_temp_checks(self, db):
        mt = _make_material_type(
            db,
            nozzle_temp_max=300,
            bed_temp_max=110,
        )
        caps = {}  # no max_temp_hotend or max_temp_bed
        issues = check_material_printer(mt, "TestPrinter", caps)
        assert issues == []

    def test_multiple_issues_at_once(self, db):
        mt = _make_material_type(
            db,
            base_material="ABS",
            requires_enclosure=True,
            nozzle_temp_max=320,
            bed_temp_max=120,
            filament_diameter=Decimal("2.85"),
        )
        caps = {
            "enclosure": False,
            "max_temp_hotend": 260,
            "max_temp_bed": 100,
            "filament_diameters": [1.75],
        }
        issues = check_material_printer(mt, "BadPrinter", caps)
        checks_found = {i.check for i in issues}
        assert checks_found == {"enclosure", "nozzle_temp", "bed_temp", "diameter"}
        assert all(i.material_name == mt.name for i in issues)
        assert all(i.printer_name == "BadPrinter" for i in issues)


# =============================================================================
# check_operation_compatibility — operation-level
# =============================================================================

class TestCheckOperationCompatibility:
    """Tests for check_operation_compatibility."""

    def test_no_printer_assigned_returns_empty(self, db, make_work_center, make_production_order, make_product):
        wc = make_work_center()
        product = make_product()
        order = make_production_order(product_id=product.id)

        op = ProductionOrderOperation(
            production_order_id=order.id,
            work_center_id=wc.id,
            sequence=10,
            operation_code="PRINT",
            operation_name="Print",
            planned_setup_minutes=0,
            planned_run_minutes=60,
            status="pending",
            printer_id=None,
            resource_id=None,
        )
        db.add(op)
        db.flush()

        result = check_operation_compatibility(db, op)
        assert result.compatible is True
        assert result.issues == []
        assert result.printer_name is None

    def test_printer_assigned_compatible_material(self, db, make_work_center, make_production_order, make_product):
        wc = make_work_center()
        mt = _make_material_type(
            db, base_material="PLA", requires_enclosure=False,
            nozzle_temp_max=220, bed_temp_max=60,
        )
        component = make_product(
            item_type="supply", unit="G", is_raw_material=True,
            material_type_id=mt.id,
        )
        product = make_product()
        order = make_production_order(product_id=product.id)

        printer = _make_printer(db, work_center_id=wc.id, capabilities={
            "enclosure": True, "max_temp_hotend": 300, "max_temp_bed": 110,
        })

        op = ProductionOrderOperation(
            production_order_id=order.id,
            work_center_id=wc.id,
            sequence=10,
            operation_code="PRINT",
            operation_name="Print",
            planned_setup_minutes=0,
            planned_run_minutes=60,
            status="pending",
            printer_id=printer.id,
        )
        db.add(op)
        db.flush()

        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("500"),
            unit="G",
            quantity_allocated=Decimal("0"),
            quantity_consumed=Decimal("0"),
            status="pending",
        )
        db.add(mat)
        db.flush()

        result = check_operation_compatibility(db, op)
        assert result.compatible is True
        assert result.printer_name == printer.name

    def test_printer_assigned_incompatible_material(self, db, make_work_center, make_production_order, make_product):
        wc = make_work_center()
        mt = _make_material_type(
            db, base_material="ABS", requires_enclosure=True,
            nozzle_temp_max=260, bed_temp_max=100,
        )
        component = make_product(
            item_type="supply", unit="G", is_raw_material=True,
            material_type_id=mt.id,
        )
        product = make_product()
        order = make_production_order(product_id=product.id)

        # Open-frame printer — will fail enclosure check
        printer = _make_printer(db, work_center_id=wc.id, capabilities={
            "enclosure": False, "max_temp_hotend": 300, "max_temp_bed": 110,
        })

        op = ProductionOrderOperation(
            production_order_id=order.id,
            work_center_id=wc.id,
            sequence=10,
            operation_code="PRINT",
            operation_name="Print",
            planned_setup_minutes=0,
            planned_run_minutes=60,
            status="pending",
            printer_id=printer.id,
        )
        db.add(op)
        db.flush()

        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("500"),
            unit="G",
            quantity_allocated=Decimal("0"),
            quantity_consumed=Decimal("0"),
            status="pending",
        )
        db.add(mat)
        db.flush()

        result = check_operation_compatibility(db, op)
        assert result.compatible is False
        assert any(i.check == "enclosure" for i in result.issues)

    def test_resource_only_no_printer(self, db, make_work_center, make_production_order, make_product):
        """When only a Resource is assigned (no Printer row), use printer_class."""
        wc = make_work_center()
        mt = _make_material_type(
            db, base_material="ABS", requires_enclosure=True,
        )
        component = make_product(
            item_type="supply", unit="G", is_raw_material=True,
            material_type_id=mt.id,
        )
        product = make_product()
        order = make_production_order(product_id=product.id)

        resource = _make_resource(db, work_center_id=wc.id, printer_class="enclosed")

        op = ProductionOrderOperation(
            production_order_id=order.id,
            work_center_id=wc.id,
            sequence=10,
            operation_code="PRINT",
            operation_name="Print",
            planned_setup_minutes=0,
            planned_run_minutes=60,
            status="pending",
            resource_id=resource.id,
        )
        db.add(op)
        db.flush()

        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("500"),
            unit="G",
            quantity_allocated=Decimal("0"),
            quantity_consumed=Decimal("0"),
            status="pending",
        )
        db.add(mat)
        db.flush()

        result = check_operation_compatibility(db, op)
        # Enclosed resource satisfies ABS enclosure requirement
        assert not any(i.check == "enclosure" for i in result.issues)

    def test_material_without_material_type_skipped(self, db, make_work_center, make_production_order, make_product):
        """Products with no material_type_id should be silently skipped."""
        wc = make_work_center()
        component = make_product(item_type="supply", unit="G", is_raw_material=True)
        # No material_type_id set
        product = make_product()
        order = make_production_order(product_id=product.id)

        printer = _make_printer(db, work_center_id=wc.id, capabilities={
            "enclosure": False, "max_temp_hotend": 200,
        })

        op = ProductionOrderOperation(
            production_order_id=order.id,
            work_center_id=wc.id,
            sequence=10,
            operation_code="PRINT",
            operation_name="Print",
            planned_setup_minutes=0,
            planned_run_minutes=60,
            status="pending",
            printer_id=printer.id,
        )
        db.add(op)
        db.flush()

        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("500"),
            unit="G",
            quantity_allocated=Decimal("0"),
            quantity_consumed=Decimal("0"),
            status="pending",
        )
        db.add(mat)
        db.flush()

        result = check_operation_compatibility(db, op)
        assert result.compatible is True
        assert result.issues == []


# =============================================================================
# check_order_compatibility — order-level aggregation
# =============================================================================

class TestCheckOrderCompatibility:
    """Tests for check_order_compatibility."""

    def test_order_with_no_operations(self, db, make_production_order, make_product):
        product = make_product()
        order = make_production_order(product_id=product.id)

        result = check_order_compatibility(db, order)
        assert result.compatible is True
        assert result.total_issues == 0
        assert result.operations == []

    def test_order_aggregates_all_operations(self, db, make_work_center, make_production_order, make_product):
        wc = make_work_center()
        mt_ok = _make_material_type(db, base_material="PLA", requires_enclosure=False)
        mt_bad = _make_material_type(db, base_material="ABS", requires_enclosure=True)
        comp_ok = make_product(item_type="supply", unit="G", is_raw_material=True, material_type_id=mt_ok.id)
        comp_bad = make_product(item_type="supply", unit="G", is_raw_material=True, material_type_id=mt_bad.id)
        product = make_product()
        order = make_production_order(product_id=product.id)

        # Open printer — PLA fine, ABS not fine
        printer = _make_printer(db, work_center_id=wc.id, capabilities={"enclosure": False})

        # Operation 1: PLA — compatible
        op1 = ProductionOrderOperation(
            production_order_id=order.id, work_center_id=wc.id, sequence=10,
            operation_code="PRINT1", operation_name="Print PLA",
            planned_setup_minutes=0, planned_run_minutes=60, status="pending",
            printer_id=printer.id,
        )
        db.add(op1)
        db.flush()
        db.add(ProductionOrderOperationMaterial(
            production_order_operation_id=op1.id, component_id=comp_ok.id,
            quantity_required=Decimal("500"), unit="G",
            quantity_allocated=Decimal("0"), quantity_consumed=Decimal("0"), status="pending",
        ))
        db.flush()

        # Operation 2: ABS — incompatible (needs enclosure)
        op2 = ProductionOrderOperation(
            production_order_id=order.id, work_center_id=wc.id, sequence=20,
            operation_code="PRINT2", operation_name="Print ABS",
            planned_setup_minutes=0, planned_run_minutes=60, status="pending",
            printer_id=printer.id,
        )
        db.add(op2)
        db.flush()
        db.add(ProductionOrderOperationMaterial(
            production_order_operation_id=op2.id, component_id=comp_bad.id,
            quantity_required=Decimal("500"), unit="G",
            quantity_allocated=Decimal("0"), quantity_consumed=Decimal("0"), status="pending",
        ))
        db.flush()

        result = check_order_compatibility(db, order)
        assert result.compatible is False
        assert result.total_issues == 1
        assert result.production_order_id == order.id
        assert result.production_order_code == order.code
        assert len(result.operations) == 2

        # First operation should be compatible
        op1_result = next(o for o in result.operations if o.operation_id == op1.id)
        assert op1_result.compatible is True

        # Second operation should have enclosure issue
        op2_result = next(o for o in result.operations if o.operation_id == op2.id)
        assert op2_result.compatible is False
        assert op2_result.issues[0].check == "enclosure"
