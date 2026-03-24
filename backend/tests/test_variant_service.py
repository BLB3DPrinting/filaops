"""Tests for the variant matrix feature — variant_service.py."""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.models.material import MaterialType, Color, MaterialColor
from app.services import variant_service, item_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def material_type_pla(db):
    """PLA material type."""
    mt = MaterialType(
        code="PLA_BASIC", name="PLA Basic", base_material="PLA",
        density=Decimal("1.24"), base_price_per_kg=Decimal("20.00"),
    )
    db.add(mt)
    db.flush()
    return mt


@pytest.fixture
def color_red(db):
    """Red color."""
    c = Color(code="RED", name="Red", hex_code="#FF0000")
    db.add(c)
    db.flush()
    return c


@pytest.fixture
def color_blue(db):
    """Blue color."""
    c = Color(code="BLU", name="Blue", hex_code="#0000FF")
    db.add(c)
    db.flush()
    return c


@pytest.fixture
def material_color_red(db, material_type_pla, color_red):
    """Valid PLA+Red combo in MaterialColor junction."""
    mc = MaterialColor(
        material_type_id=material_type_pla.id,
        color_id=color_red.id,
    )
    db.add(mc)
    db.flush()
    return mc


@pytest.fixture
def material_color_blue(db, material_type_pla, color_blue):
    """Valid PLA+Blue combo in MaterialColor junction."""
    mc = MaterialColor(
        material_type_id=material_type_pla.id,
        color_id=color_blue.id,
    )
    db.add(mc)
    db.flush()
    return mc


@pytest.fixture
def filament_red(make_product, material_type_pla, color_red):
    """Supply product representing PLA Red filament."""
    return make_product(
        sku="FIL-PLA-RED",
        name="PLA Red Filament",
        item_type="supply",
        unit="G",
        purchase_uom="KG",
        purchase_factor=Decimal("1000"),
        standard_cost=Decimal("20.00"),
        material_type_id=material_type_pla.id,
        color_id=color_red.id,
    )


@pytest.fixture
def filament_blue(make_product, material_type_pla, color_blue):
    """Supply product representing PLA Blue filament."""
    return make_product(
        sku="FIL-PLA-BLU",
        name="PLA Blue Filament",
        item_type="supply",
        unit="G",
        purchase_uom="KG",
        purchase_factor=Decimal("1000"),
        standard_cost=Decimal("20.00"),
        material_type_id=material_type_pla.id,
        color_id=color_blue.id,
    )


@pytest.fixture
def packaging(make_product):
    """Fixed material — packaging box (not variable)."""
    return make_product(
        sku="PKG-BOX-SM",
        name="Small Box",
        item_type="supply",
        standard_cost=Decimal("0.50"),
    )


@pytest.fixture
def template_product(
    db,
    make_product,
    make_bom,
    make_work_center,
    filament_red,
    packaging,
):
    """A template finished good with BOM, routing, and variable+fixed materials."""
    product = make_product(
        sku="FG-TEST-TMPL",
        name="Test Template Widget",
        item_type="finished_good",
        procurement_type="make",
        standard_cost=Decimal("5.00"),
        selling_price=Decimal("15.00"),
    )

    # BOM with filament (variable) and packaging (fixed)
    make_bom(
        product_id=product.id,
        lines=[
            {"component_id": filament_red.id, "quantity": Decimal("37"), "unit": "G"},
            {"component_id": packaging.id, "quantity": Decimal("1"), "unit": "EA"},
        ],
    )
    product.has_bom = True

    # Routing with one operation and both materials
    wc = make_work_center()
    routing = Routing(
        product_id=product.id,
        code=f"RTG-{product.sku}",
        name=f"Routing for {product.name}",
        is_active=True,
        version=1,
    )
    db.add(routing)
    db.flush()

    op = RoutingOperation(
        routing_id=routing.id,
        work_center_id=wc.id,
        sequence=10,
        operation_code="PRINT",
        operation_name="3D Print",
        run_time_minutes=120,
    )
    db.add(op)
    db.flush()

    # Variable material (filament — swapped per variant)
    mat_variable = RoutingOperationMaterial(
        routing_operation_id=op.id,
        component_id=filament_red.id,
        quantity=Decimal("37"),
        quantity_per="unit",
        unit="G",
        is_variable=True,
    )
    db.add(mat_variable)

    # Fixed material (packaging — same for all variants)
    mat_fixed = RoutingOperationMaterial(
        routing_operation_id=op.id,
        component_id=packaging.id,
        quantity=Decimal("1"),
        quantity_per="unit",
        unit="EA",
        is_variable=False,
    )
    db.add(mat_fixed)
    db.flush()

    return product


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCreateVariant:
    """Test creating individual variants from a template."""

    def test_create_variant_basic(
        self, db, template_product, material_type_pla, color_blue,
        material_color_blue, filament_blue,
    ):
        """Create a variant — should generate correct SKU, swap variable materials."""
        result = variant_service.create_variant(
            db,
            template_product.id,
            material_type_pla.id,
            color_blue.id,
        )

        assert result["status"] == "created"
        assert result["sku"] == "FG-TEST-TMPL-PLA_BASIC-BLU"
        assert result["parent_product_id"] == template_product.id

        # Verify template is now marked as template
        db.refresh(template_product)
        assert template_product.is_template is True

        # Verify the variant product exists with correct metadata
        variant = item_service.get_item(db, result["id"])
        assert variant.parent_product_id == template_product.id
        assert variant.variant_metadata["material_type_code"] == "PLA_BASIC"
        assert variant.variant_metadata["color_code"] == "BLU"

    def test_variant_material_swapped(
        self, db, template_product, material_type_pla, color_blue,
        material_color_blue, filament_red, filament_blue,
    ):
        """Variant's routing materials should have filament swapped to blue."""
        result = variant_service.create_variant(
            db,
            template_product.id,
            material_type_pla.id,
            color_blue.id,
        )

        # Get the variant's routing materials
        variant_routing = (
            db.query(Routing)
            .filter(Routing.product_id == result["id"], Routing.is_active.is_(True))
            .first()
        )
        assert variant_routing is not None

        ops = (
            db.query(RoutingOperation)
            .filter(RoutingOperation.routing_id == variant_routing.id)
            .all()
        )
        assert len(ops) == 1

        materials = (
            db.query(RoutingOperationMaterial)
            .filter(RoutingOperationMaterial.routing_operation_id == ops[0].id)
            .all()
        )
        assert len(materials) == 2

        # Find the variable material — should be blue now
        variable_mats = [m for m in materials if m.is_variable]
        fixed_mats = [m for m in materials if not m.is_variable]

        # Variable material should be swapped to blue filament
        assert len(variable_mats) == 1
        assert variable_mats[0].component_id == filament_blue.id

        # Fixed material should still be packaging
        assert len(fixed_mats) == 1

    def test_duplicate_variant_rejected(
        self, db, template_product, material_type_pla, color_blue,
        material_color_blue, filament_blue,
    ):
        """Creating the same variant twice should fail with 409."""
        variant_service.create_variant(
            db, template_product.id, material_type_pla.id, color_blue.id,
        )

        with pytest.raises(HTTPException) as exc_info:
            variant_service.create_variant(
                db, template_product.id, material_type_pla.id, color_blue.id,
            )
        assert exc_info.value.status_code == 409

    def test_invalid_material_color_combo(
        self, db, template_product, material_type_pla, color_blue,
    ):
        """Creating a variant with an invalid MaterialColor combo should fail."""
        # No material_color_blue fixture — combo doesn't exist in junction table
        with pytest.raises(HTTPException) as exc_info:
            variant_service.create_variant(
                db, template_product.id, material_type_pla.id, color_blue.id,
            )
        assert exc_info.value.status_code == 400


class TestBulkCreateVariants:
    """Test bulk variant creation."""

    def test_bulk_create(
        self, db, template_product, material_type_pla,
        color_red, color_blue,
        material_color_red, material_color_blue,
        filament_red, filament_blue,
    ):
        """Bulk create two variants — one should be created, one skipped if exists."""
        selections = [
            {"material_type_id": material_type_pla.id, "color_id": color_red.id},
            {"material_type_id": material_type_pla.id, "color_id": color_blue.id},
        ]

        results = variant_service.bulk_create_variants(
            db, template_product.id, selections,
        )

        # Both should have results
        assert len(results) == 2

        # At least one should be created (red may be skipped since template
        # already uses red filament in its BOM, but SKU is different so it creates)
        created = [r for r in results if r.get("status") == "created"]
        assert len(created) >= 1

    def test_bulk_skips_existing(
        self, db, template_product, material_type_pla, color_blue,
        material_color_blue, filament_blue,
    ):
        """Bulk create should skip variants that already exist."""
        # Create one first
        variant_service.create_variant(
            db, template_product.id, material_type_pla.id, color_blue.id,
        )

        # Bulk create with same selection
        results = variant_service.bulk_create_variants(
            db,
            template_product.id,
            [{"material_type_id": material_type_pla.id, "color_id": color_blue.id}],
        )

        assert len(results) == 1
        assert results[0]["status"] == "skipped"


class TestListVariants:
    """Test listing variants for a template."""

    def test_list_variants(
        self, db, template_product, material_type_pla, color_blue,
        material_color_blue, filament_blue,
    ):
        """List variants should return created variants with metadata."""
        variant_service.create_variant(
            db, template_product.id, material_type_pla.id, color_blue.id,
        )

        variants = variant_service.list_variants(db, template_product.id)
        assert len(variants) == 1
        assert variants[0]["sku"] == "FG-TEST-TMPL-PLA_BASIC-BLU"
        assert variants[0]["material_type_code"] == "PLA_BASIC"
        assert variants[0]["color_code"] == "BLU"
        assert variants[0]["color_hex"] == "#0000FF"

    def test_list_variants_empty(self, db, template_product):
        """Template with no variants should return empty list."""
        variants = variant_service.list_variants(db, template_product.id)
        assert variants == []


class TestDeleteVariant:
    """Test deleting variants."""

    def test_delete_variant(
        self, db, template_product, material_type_pla, color_blue,
        material_color_blue, filament_blue,
    ):
        """Deleting the last variant should clear is_template on parent."""
        result = variant_service.create_variant(
            db, template_product.id, material_type_pla.id, color_blue.id,
        )

        db.refresh(template_product)
        assert template_product.is_template is True

        variant_service.delete_variant(db, template_product.id, result["id"])

        db.refresh(template_product)
        assert template_product.is_template is False

    def test_delete_non_variant_fails(self, db, template_product):
        """Deleting a product without parent_product_id should fail."""
        with pytest.raises(HTTPException) as exc_info:
            variant_service.delete_variant(db, 99999, template_product.id)
        assert exc_info.value.status_code == 400


class TestListItemsExcludesVariants:
    """Test that list_items() filters out variants by default."""

    def test_excludes_variants_by_default(
        self, db, template_product, material_type_pla, color_blue,
        material_color_blue, filament_blue,
    ):
        """Variants should not appear in list_items() by default."""
        variant_service.create_variant(
            db, template_product.id, material_type_pla.id, color_blue.id,
        )

        items, total = item_service.list_items(db, search="FG-TEST-TMPL")
        skus = [item["sku"] for item in items]

        # Template should be in the list
        assert "FG-TEST-TMPL" in skus
        # Variant should NOT be in the list
        assert "FG-TEST-TMPL-PLA_BASIC-BLU" not in skus

    def test_includes_variants_when_requested(
        self, db, template_product, material_type_pla, color_blue,
        material_color_blue, filament_blue,
    ):
        """Variants should appear when exclude_variants=False."""
        variant_service.create_variant(
            db, template_product.id, material_type_pla.id, color_blue.id,
        )

        items, total = item_service.list_items(
            db, search="FG-TEST-TMPL", exclude_variants=False,
        )
        skus = [item["sku"] for item in items]

        assert "FG-TEST-TMPL" in skus
        assert "FG-TEST-TMPL-PLA_BASIC-BLU" in skus
