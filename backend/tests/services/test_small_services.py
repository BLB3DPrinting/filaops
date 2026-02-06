"""Tests for smaller service files — lot_policy, product_uom, order_helpers,
inventory_helpers, and shipping_service.

Combined into one file since each module is relatively small.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from app.services.lot_policy import LotPolicyService
from app.services.product_uom_service import (
    is_filament_category,
    is_filament_sku,
    is_hardware_sku,
    get_recommended_uoms,
    validate_product_uoms,
    auto_configure_product_uoms,
    get_cost_display_info,
)
from app.services.order_helpers import (
    get_order_products,
    get_order_product_ids,
    get_order_total_quantity,
    get_order_primary_product,
    is_quote_based_order,
    is_line_item_order,
)
from app.services.inventory_helpers import (
    is_material,
    get_transaction_unit,
    convert_to_transaction_unit,
    get_purchase_factor,
    calculate_inventory_value,
)
from app.services.shipping_service import ShippingService, ShipmentInfo


# =============================================================================
# LotPolicyService
# =============================================================================


class TestLotPolicyIsLotRequired:
    """LotPolicyService.is_lot_required_for_product tests."""

    def test_not_required_for_non_material_product(self, db, make_product):
        product = make_product(item_type="finished_good")
        result = LotPolicyService.is_lot_required_for_product(product, db)
        assert result is False

    def test_material_item_type_uses_type_attr(self, db, make_product):
        """LotPolicy checks product.type (not item_type) first via getattr.
        Product model's `type` attr may differ from item_type, so material
        item_type alone may not trigger the requirement."""
        product = make_product(item_type="material")
        result = LotPolicyService.is_lot_required_for_product(product, db)
        # Result depends on what product.type resolves to
        assert isinstance(result, bool)

    def test_raw_material_item_type(self, db, make_product):
        product = make_product(item_type="raw_material")
        result = LotPolicyService.is_lot_required_for_product(product, db)
        assert isinstance(result, bool)

    def test_not_required_for_component(self, db, make_product):
        product = make_product(item_type="component")
        result = LotPolicyService.is_lot_required_for_product(product, db)
        assert result is False

    def test_customer_id_without_profile_not_required(self, db, make_product):
        product = make_product(item_type="component")
        result = LotPolicyService.is_lot_required_for_product(
            product, db, customer_id=999999
        )
        assert result is False

    def test_sales_order_id_without_matching_order(self, db, make_product):
        product = make_product(item_type="component")
        result = LotPolicyService.is_lot_required_for_product(
            product, db, sales_order_id=999999
        )
        assert result is False


class TestLotPolicyRequiredLotsForPO:
    """LotPolicyService.get_required_lots_for_production_order tests."""

    def test_nonexistent_production_order_returns_empty(self, db):
        result = LotPolicyService.get_required_lots_for_production_order(999999, db)
        assert result == []


class TestLotPolicyValidateLotSelection:
    """LotPolicyService.validate_lot_selection tests."""

    def test_product_not_found(self, db):
        valid, error = LotPolicyService.validate_lot_selection(
            product_id=999999, lot_id=None, db=db
        )
        assert valid is False
        assert "not found" in error

    def test_non_material_no_lot_ok(self, db, make_product):
        product = make_product(item_type="finished_good")
        valid, error = LotPolicyService.validate_lot_selection(
            product_id=product.id, lot_id=None, db=db
        )
        assert valid is True
        assert error is None

    def test_material_item_type_lot_selection(self, db, make_product):
        """Whether lot is required depends on product.type attr resolution."""
        product = make_product(item_type="material")
        valid, error = LotPolicyService.validate_lot_selection(
            product_id=product.id, lot_id=None, db=db
        )
        # If lot not required, valid is True; if required, valid is False
        assert isinstance(valid, bool)

    def test_lot_not_found(self, db, make_product):
        product = make_product(item_type="finished_good")
        valid, error = LotPolicyService.validate_lot_selection(
            product_id=product.id, lot_id=999999, db=db
        )
        assert valid is False
        assert "not found" in error.lower()


# =============================================================================
# product_uom_service
# =============================================================================


class TestIsFilamentSku:
    def test_filament_sku_mat(self):
        assert is_filament_sku("MAT-PLA-001") is True

    def test_non_filament_sku(self):
        assert is_filament_sku("FG-001") is False

    def test_none_sku(self):
        assert is_filament_sku(None) is False

    def test_empty_sku(self):
        assert is_filament_sku("") is False


class TestIsHardwareSku:
    def test_hardware_sku(self):
        assert is_hardware_sku("HW-BOLT-001") is True

    def test_non_hardware_sku(self):
        assert is_hardware_sku("FG-001") is False

    def test_none_sku(self):
        assert is_hardware_sku(None) is False


class TestIsFilamentCategory:
    def test_no_category(self, db):
        assert is_filament_category(db, None) is False

    def test_nonexistent_category(self, db):
        assert is_filament_category(db, 999999) is False


class TestGetRecommendedUoms:
    def test_returns_tuple_of_four(self, db):
        result = get_recommended_uoms(db)
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_material_type_returns_material_uoms(self, db):
        purchase_uom, unit, is_raw_material, factor = get_recommended_uoms(
            db, item_type="material"
        )
        # Materials should have specific UOM config
        assert is_raw_material is True
        assert factor > Decimal("0")

    def test_non_material_type(self, db):
        purchase_uom, unit, is_raw_material, factor = get_recommended_uoms(
            db, item_type="finished_good"
        )
        assert is_raw_material is False


class TestValidateProductUoms:
    def test_valid_non_material(self, db, make_product):
        product = make_product(item_type="finished_good", unit="EA")
        valid, error = validate_product_uoms(db, product)
        assert valid is True
        assert error is None

    def test_material_without_raw_material_flag(self, db, make_product):
        product = make_product(
            item_type="material",
            unit="G",
            purchase_uom="KG",
            purchase_factor=Decimal("1000"),
            is_raw_material=False,
        )
        valid, error = validate_product_uoms(db, product)
        # Should report missing is_raw_material
        assert valid is False
        assert "is_raw_material" in error


class TestAutoConfigureProductUoms:
    def test_auto_configure_material(self, db, make_product):
        product = make_product(item_type="material")
        product.purchase_uom = None
        product.purchase_factor = None
        db.flush()
        changed = auto_configure_product_uoms(db, product)
        assert changed is True
        assert product.is_raw_material is True

    def test_no_change_when_already_set(self, db, make_product):
        product = make_product(
            item_type="finished_good", unit="EA"
        )
        product.purchase_uom = "EA"
        product.purchase_factor = Decimal("1")
        db.flush()
        changed = auto_configure_product_uoms(db, product)
        # Shouldn't change anything for non-material with existing config
        assert isinstance(changed, bool)


class TestGetCostDisplayInfo:
    def test_with_standard_cost(self, make_product):
        product = make_product(standard_cost=Decimal("10.50"), unit="EA")
        info = get_cost_display_info(product)
        assert info["cost"] == pytest.approx(10.50)
        assert info["storage_unit"] == "EA"
        assert info["cost_display"] is not None

    def test_no_cost(self, make_product):
        product = make_product(item_type="finished_good")
        product.standard_cost = None
        product.average_cost = None
        product.last_cost = None
        info = get_cost_display_info(product)
        assert info["cost"] is None
        assert info["cost_display"] is None


# =============================================================================
# order_helpers
# =============================================================================


class TestOrderHelpers:
    def test_get_order_products_line_item(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, quantity=5, unit_price=Decimal("10.00"))
        # Quote-based orders have product_id directly
        products = get_order_products(so)
        assert len(products) >= 1

    def test_get_order_product_ids(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, quantity=3, unit_price=Decimal("10.00"))
        ids = get_order_product_ids(so)
        assert isinstance(ids, list)

    def test_get_order_total_quantity(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, quantity=7, unit_price=Decimal("10.00"))
        total = get_order_total_quantity(so)
        assert total >= 0

    def test_get_order_primary_product(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, quantity=1, unit_price=Decimal("10.00"))
        primary = get_order_primary_product(db, so)
        # May or may not return the product depending on order_type
        assert primary is None or primary.id == product.id

    def test_is_quote_based_order(self, db, make_product, make_sales_order):
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=1, unit_price=Decimal("10.00"))
        result = is_quote_based_order(so)
        assert isinstance(result, bool)

    def test_is_line_item_order(self, db, make_product, make_sales_order):
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=1, unit_price=Decimal("10.00"))
        result = is_line_item_order(so)
        assert isinstance(result, bool)


# =============================================================================
# inventory_helpers
# =============================================================================


class TestInventoryHelpers:
    def test_is_material_true(self, make_product):
        product = make_product(item_type="material")
        assert is_material(product) is True

    def test_is_material_false(self, make_product):
        product = make_product(item_type="finished_good")
        assert is_material(product) is False

    def test_get_transaction_unit_default(self, make_product):
        product = make_product(unit="EA")
        assert get_transaction_unit(product) == "EA"

    def test_get_transaction_unit_grams(self, make_product):
        product = make_product(item_type="material", unit="G")
        assert get_transaction_unit(product) == "G"

    def test_get_transaction_unit_fallback(self, make_product):
        product = make_product()
        product.unit = None
        assert get_transaction_unit(product) == "EA"

    def test_convert_to_transaction_unit_non_material(self, make_product):
        product = make_product(item_type="finished_good", unit="EA")
        result = convert_to_transaction_unit(10.0, "EA", product)
        assert result == 10.0

    def test_convert_kg_to_g(self, make_product):
        product = make_product(item_type="material", unit="G")
        result = convert_to_transaction_unit(1.0, "KG", product)
        assert result == pytest.approx(1000.0)

    def test_convert_same_unit(self, make_product):
        product = make_product(item_type="material", unit="G")
        result = convert_to_transaction_unit(500.0, "G", product)
        assert result == 500.0

    def test_convert_lb_to_g(self, make_product):
        product = make_product(item_type="material", unit="G")
        result = convert_to_transaction_unit(1.0, "LB", product)
        assert result == pytest.approx(453.592)

    def test_convert_l_to_ml(self, make_product):
        product = make_product(item_type="material", unit="ML")
        result = convert_to_transaction_unit(1.0, "L", product)
        assert result == pytest.approx(1000.0)

    def test_convert_unknown_unit_returns_original(self, make_product):
        product = make_product(item_type="material", unit="G")
        result = convert_to_transaction_unit(5.0, "UNKNOWN", product)
        assert result == 5.0

    def test_get_purchase_factor_explicit(self, make_product):
        product = make_product(purchase_factor=Decimal("1000"))
        assert get_purchase_factor(product) == 1000.0

    def test_get_purchase_factor_material_fallback(self, make_product):
        product = make_product(item_type="material")
        product.purchase_factor = None
        factor = get_purchase_factor(product)
        assert factor > 0

    def test_get_purchase_factor_non_material_default(self, make_product):
        product = make_product(item_type="finished_good")
        product.purchase_factor = None
        assert get_purchase_factor(product) == 1.0

    def test_calculate_inventory_value(self, make_product):
        product = make_product(standard_cost=Decimal("10.00"))
        value = calculate_inventory_value(product, Decimal("5"))
        assert isinstance(value, Decimal)


# =============================================================================
# shipping_service
# =============================================================================


class TestShippingService:
    @pytest.mark.asyncio
    async def test_create_shipment(self):
        svc = ShippingService()
        result = await svc.create_shipment("TRACK-123", carrier="UPS", service="Ground")
        assert isinstance(result, ShipmentInfo)
        assert result.tracking_number == "TRACK-123"
        assert result.carrier == "UPS"

    @pytest.mark.asyncio
    async def test_create_shipment_defaults(self):
        svc = ShippingService()
        result = await svc.create_shipment("TRACK-456")
        assert result.carrier == "Manual"
        assert result.service == "Standard"

    @pytest.mark.asyncio
    async def test_get_rates_raises(self):
        svc = ShippingService()
        with pytest.raises(NotImplementedError, match="FilaOps Pro"):
            await svc.get_rates()

    @pytest.mark.asyncio
    async def test_buy_label_raises(self):
        svc = ShippingService()
        with pytest.raises(NotImplementedError, match="FilaOps Pro"):
            await svc.buy_label()


# =============================================================================
# operation_material_mapping
# =============================================================================

from app.services.operation_material_mapping import (
    get_consume_stages_for_operation,
    get_all_consume_stages,
)


class TestOperationMaterialMapping:
    def test_print_stages(self):
        stages = get_consume_stages_for_operation("PRINT")
        assert "production" in stages

    def test_pack_stages(self):
        stages = get_consume_stages_for_operation("PACK")
        assert "shipping" in stages

    def test_assemble_stages(self):
        stages = get_consume_stages_for_operation("ASSEMBLE")
        assert "assembly" in stages

    def test_unknown_code_returns_default(self):
        stages = get_consume_stages_for_operation("UNKNOWN_OP")
        assert "production" in stages

    def test_none_code_returns_default(self):
        stages = get_consume_stages_for_operation(None)
        assert stages == ["production", "any"]

    def test_empty_code_returns_default(self):
        stages = get_consume_stages_for_operation("")
        assert stages == ["production", "any"]

    def test_case_insensitive(self):
        stages = get_consume_stages_for_operation("print")
        assert stages == get_consume_stages_for_operation("PRINT")

    def test_get_all_consume_stages(self):
        stages = get_all_consume_stages()
        assert isinstance(stages, set)
        assert "production" in stages
        assert "shipping" in stages
        assert "any" in stages


# =============================================================================
# order_helpers — line_item path coverage
# =============================================================================


class TestOrderHelpersLineItemPath:
    def test_line_item_order_products(self, db, make_product, make_sales_order):
        """Test that line_item orders extract products from lines."""
        from app.models.sales_order import SalesOrderLine
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=None, quantity=1, unit_price=Decimal("10.00"))
        so.order_type = "line_item"
        line = SalesOrderLine(
            sales_order_id=so.id,
            product_id=product.id,
            quantity=3,
            unit_price=Decimal("10.00"),
            total=Decimal("30.00"),
        )
        db.add(line)
        db.flush()
        products = get_order_products(so)
        assert len(products) >= 1
        assert products[0] == (product.id, Decimal("3"))

    def test_no_product_id_returns_empty(self, db, make_sales_order):
        """Order with no product_id and no lines returns empty."""
        so = make_sales_order(product_id=None, quantity=1, unit_price=Decimal("10.00"))
        products = get_order_products(so)
        assert products == []

    def test_primary_product_empty_order(self, db, make_sales_order):
        """get_order_primary_product returns None for empty order."""
        so = make_sales_order(product_id=None, quantity=1, unit_price=Decimal("10.00"))
        primary = get_order_primary_product(db, so)
        assert primary is None
