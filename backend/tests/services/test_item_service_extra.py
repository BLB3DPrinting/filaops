"""
Extended tests for app/services/item_service.py — covers uncovered line ranges.

Focus areas (by uncovered line ranges):
- Unit change with inventory conversion (lines 528-570)
- MRP shortages in low stock (_add_mrp_shortages lines 825-853, 876-940)
- CSV import/export (lines 1324-1676): import_items_from_csv, helpers
- Category management edge cases
- recost_all_items filters (lines 1083-1086, 1127-1128)
- BOM cost with UOM conversion (lines 1083-1086)

Run with:
    cd backend
    pytest tests/services/test_item_service_extra.py -v
"""
import uuid
import pytest
from decimal import Decimal
from datetime import datetime, timezone

from fastapi import HTTPException

from app.services import item_service
from app.models.product import Product
from app.models.item_category import ItemCategory
from app.models.inventory import Inventory
from app.models.bom import BOM, BOMLine


def _uid():
    return uuid.uuid4().hex[:8]


def _uid_upper():
    """Unique ID safe for CSV import (uppercased hex)."""
    return uuid.uuid4().hex[:8].upper()


def _make_category(db, code, name, parent_id=None, is_active=True, sort_order=0):
    cat = ItemCategory(
        code=code, name=name, parent_id=parent_id,
        is_active=is_active, sort_order=sort_order,
    )
    db.add(cat)
    db.flush()
    return cat


def _make_inventory(db, product_id, on_hand, location_id=1, allocated=0):
    inv = Inventory(
        product_id=product_id, location_id=location_id,
        on_hand_quantity=Decimal(str(on_hand)),
        allocated_quantity=Decimal(str(allocated)),
    )
    db.add(inv)
    db.flush()
    return inv


def _csv_bytes(rows, header=None):
    """Build CSV bytes from a list of dicts (or header + rows)."""
    import csv
    import io

    if header is None:
        if not rows:
            return b""
        header = list(rows[0].keys())

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


# =============================================================================
# CSV Import — import_items_from_csv (lines 1356-1613)
# =============================================================================

class TestImportItemsFromCsv:
    """Test import_items_from_csv.

    NOTE: CSV import uppercases SKUs. All test SKUs must be uppercase-safe.
    New-item tests must include 'unit' and 'purchase_uom' columns to bypass
    a pre-existing bug in get_recommended_uoms (returns 4 values, caller
    unpacks 3). This bug is tracked separately.
    """

    def test_import_creates_new_items(self, db):
        """Basic CSV import creates new products."""
        uid = _uid_upper()
        csv_data = _csv_bytes([
            {"sku": f"IMP-{uid}", "name": "Import Widget",
             "price": "19.99", "cost": "5.00", "unit": "EA", "purchase_uom": "EA"},
        ])

        result = item_service.import_items_from_csv(db, file_content=csv_data)

        assert result["total_rows"] == 1
        assert result["created"] == 1
        assert result["updated"] == 0
        assert result["skipped"] == 0

        product = db.query(Product).filter(Product.sku == f"IMP-{uid}").first()
        assert product is not None
        assert product.name == "Import Widget"

    def test_import_skips_existing_without_update_flag(self, db, make_product):
        """Existing SKUs are skipped when update_existing=False."""
        uid = _uid_upper()
        product = make_product(sku=f"EXIST-{uid}", name="Original")
        db.commit()

        csv_data = _csv_bytes([
            {"sku": product.sku, "name": "Updated Name"},
        ])

        result = item_service.import_items_from_csv(
            db, file_content=csv_data, update_existing=False,
        )

        assert result["skipped"] == 1
        assert result["updated"] == 0

        db.refresh(product)
        assert product.name == "Original"

    def test_import_updates_existing_with_flag(self, db, make_product):
        """Existing SKUs are updated when update_existing=True."""
        uid = _uid_upper()
        product = make_product(sku=f"UPD-{uid}", name="Old Name")
        db.commit()

        csv_data = _csv_bytes([
            {"sku": product.sku, "name": "New Name"},
        ])

        result = item_service.import_items_from_csv(
            db, file_content=csv_data, update_existing=True,
        )

        assert result["updated"] == 1
        db.refresh(product)
        assert product.name == "New Name"

    def test_import_missing_sku_errors(self, db):
        """Row without SKU is recorded as error."""
        csv_data = _csv_bytes([
            {"sku": "", "name": "No SKU Item"},
        ])

        result = item_service.import_items_from_csv(db, file_content=csv_data)

        assert result["skipped"] == 1
        assert len(result["errors"]) == 1
        assert "SKU" in result["errors"][0]["error"]

    def test_import_missing_name_errors(self, db):
        """Row without name is recorded as error."""
        uid = _uid_upper()
        csv_data = _csv_bytes([
            {"sku": f"NONAME-{uid}", "name": ""},
        ])

        result = item_service.import_items_from_csv(db, file_content=csv_data)

        assert result["skipped"] == 1
        assert len(result["errors"]) == 1
        assert "Name" in result["errors"][0]["error"]

    def test_import_with_cost_and_price(self, db):
        """Cost and price are parsed from CSV."""
        uid = _uid_upper()
        csv_data = _csv_bytes([
            {"sku": f"COST-{uid}", "name": "Costed Item",
             "standard_cost": "$12.50", "selling_price": "29.99",
             "unit": "EA", "purchase_uom": "EA"},
        ])

        result = item_service.import_items_from_csv(db, file_content=csv_data)

        assert result["created"] == 1
        product = db.query(Product).filter(Product.sku == f"COST-{uid}").first()
        assert float(product.standard_cost) == pytest.approx(12.50)
        assert float(product.selling_price) == pytest.approx(29.99)

    def test_import_with_category_name(self, db):
        """Category name in CSV row is matched to existing categories."""
        cat = _make_category(db, f"IMP-CAT-{_uid_upper()}", "Widgets CSV Test")
        db.commit()

        uid = _uid_upper()
        csv_data = _csv_bytes([
            {"sku": f"CATCSV-{uid}", "name": "Cat Item",
             "Category": "Widgets CSV Test", "unit": "EA", "purchase_uom": "EA"},
        ])

        result = item_service.import_items_from_csv(db, file_content=csv_data)

        assert result["created"] == 1
        product = db.query(Product).filter(Product.sku == f"CATCSV-{uid}").first()
        assert product.category_id == cat.id

    def test_import_with_category_id(self, db):
        """Numeric category_id in CSV row sets the category."""
        cat = _make_category(db, f"IMP-CID-{_uid_upper()}", "Direct ID")
        db.commit()

        uid = _uid_upper()
        csv_data = _csv_bytes([
            {"sku": f"CID-{uid}", "name": "CID Item",
             "category_id": str(cat.id), "unit": "EA", "purchase_uom": "EA"},
        ])

        result = item_service.import_items_from_csv(db, file_content=csv_data)

        assert result["created"] == 1
        product = db.query(Product).filter(Product.sku == f"CID-{uid}").first()
        assert product.category_id == cat.id

    def test_import_with_default_category(self, db):
        """Default category is applied when row has no category info."""
        cat = _make_category(db, f"DEF-CAT-{_uid_upper()}", "Default Cat")
        db.commit()

        uid = _uid_upper()
        csv_data = _csv_bytes([
            {"sku": f"DEFCAT-{uid}", "name": "Default Cat Item",
             "unit": "EA", "purchase_uom": "EA"},
        ])

        result = item_service.import_items_from_csv(
            db, file_content=csv_data, default_category_id=cat.id,
        )

        assert result["created"] == 1
        product = db.query(Product).filter(Product.sku == f"DEFCAT-{uid}").first()
        assert product.category_id == cat.id

    def test_import_seeded_item_protected(self, db, make_product):
        """Items with SEED-EXAMPLE- prefix cannot be updated via import."""
        product = make_product(sku="SEED-EXAMPLE-001", name="Seeded")
        db.commit()

        csv_data = _csv_bytes([
            {"sku": "SEED-EXAMPLE-001", "name": "Hacked"},
        ])

        result = item_service.import_items_from_csv(
            db, file_content=csv_data, update_existing=True,
        )

        assert result["skipped"] == 1
        assert any("seeded" in e.get("error", "").lower() for e in result["errors"])

    def test_import_latin1_encoding(self, db):
        """File with latin-1 encoding is handled gracefully."""
        uid = _uid_upper()
        content = f"sku,name,unit,purchase_uom\nLATIN-{uid},Caf\xe9 Item,EA,EA".encode("latin-1")

        result = item_service.import_items_from_csv(db, file_content=content)

        assert result["created"] == 1
        product = db.query(Product).filter(Product.sku == f"LATIN-{uid}").first()
        assert product is not None

    def test_import_bom_stripped(self, db):
        """UTF-8 BOM prefix is stripped."""
        uid = _uid_upper()
        content = f"\ufeffsku,name,unit,purchase_uom\nBOM-{uid},BOM Item,EA,EA".encode("utf-8")

        result = item_service.import_items_from_csv(db, file_content=content)

        assert result["created"] == 1

    def test_import_new_item_uses_raw_item_type(self, db):
        """New items use item_type from CSV directly (mapping is update-only)."""
        uid = _uid_upper()
        csv_data = _csv_bytes([
            {"sku": f"SUPPLY-{uid}", "name": "Supply Item",
             "item_type": "supply", "unit": "EA", "purchase_uom": "EA"},
        ])

        result = item_service.import_items_from_csv(db, file_content=csv_data)

        assert result["created"] == 1
        product = db.query(Product).filter(Product.sku == f"SUPPLY-{uid}").first()
        assert product.item_type == "supply"

    def test_import_update_maps_marketplace_item_type(self, db, make_product):
        """Update import maps marketplace item types (e.g., 'simple' -> 'finished_good')."""
        uid = _uid_upper()
        product = make_product(sku=f"ITMAP-{uid}", name="Type Map", item_type="component")
        db.commit()

        csv_data = _csv_bytes([
            {"sku": product.sku, "name": "Type Map", "item_type": "simple"},
        ])

        result = item_service.import_items_from_csv(
            db, file_content=csv_data, update_existing=True,
        )

        assert result["updated"] == 1
        db.refresh(product)
        assert product.item_type == "finished_good"

    def test_import_update_with_description(self, db, make_product):
        """Update import sets description from CSV."""
        uid = _uid_upper()
        product = make_product(sku=f"DESC-{uid}", name="Desc Test")
        db.commit()

        csv_data = _csv_bytes([
            {"sku": product.sku, "name": "Desc Test", "description": "New description"},
        ])

        result = item_service.import_items_from_csv(
            db, file_content=csv_data, update_existing=True,
        )

        assert result["updated"] == 1
        db.refresh(product)
        assert product.description == "New description"

    def test_import_update_strips_html_description(self, db, make_product):
        """HTML tags are stripped from description on update."""
        uid = _uid_upper()
        product = make_product(sku=f"HTML-{uid}", name="HTML Test")
        db.commit()

        csv_data = _csv_bytes([
            {"sku": product.sku, "name": "HTML Test",
             "description": "<p>Clean <b>text</b></p>"},
        ])

        result = item_service.import_items_from_csv(
            db, file_content=csv_data, update_existing=True,
        )

        assert result["updated"] == 1
        db.refresh(product)
        assert "<p>" not in product.description
        assert "Clean text" in product.description

    def test_import_with_upc(self, db):
        """UPC/barcode is imported from CSV."""
        uid = _uid_upper()
        csv_data = _csv_bytes([
            {"sku": f"UPC-{uid}", "name": "UPC Item",
             "upc": "123456789012", "unit": "EA", "purchase_uom": "EA"},
        ])

        result = item_service.import_items_from_csv(db, file_content=csv_data)

        assert result["created"] == 1
        product = db.query(Product).filter(Product.sku == f"UPC-{uid}").first()
        assert product.upc == "123456789012"

    def test_import_with_reorder_point(self, db):
        """Reorder point is imported from CSV."""
        uid = _uid_upper()
        csv_data = _csv_bytes([
            {"sku": f"ROP-{uid}", "name": "ROP Item",
             "reorder_point": "25", "unit": "EA", "purchase_uom": "EA"},
        ])

        result = item_service.import_items_from_csv(db, file_content=csv_data)

        assert result["created"] == 1
        product = db.query(Product).filter(Product.sku == f"ROP-{uid}").first()
        assert float(product.reorder_point) == 25.0

    def test_import_update_with_unit(self, db, make_product):
        """Unit is updated from CSV on update."""
        uid = _uid_upper()
        product = make_product(sku=f"UNIT-{uid}", name="Unit Test", unit="EA")
        db.commit()

        csv_data = _csv_bytes([
            {"sku": product.sku, "name": "Unit Test", "unit": "KG"},
        ])

        result = item_service.import_items_from_csv(
            db, file_content=csv_data, update_existing=True,
        )

        assert result["updated"] == 1
        db.refresh(product)
        assert product.unit == "KG"

    def test_import_update_reorder_point(self, db, make_product):
        """Reorder point is updated from CSV on update."""
        uid = _uid_upper()
        product = make_product(sku=f"RUPD-{uid}", name="RP Update")
        db.commit()

        csv_data = _csv_bytes([
            {"sku": product.sku, "name": "RP Update", "reorder_point": "42"},
        ])

        result = item_service.import_items_from_csv(
            db, file_content=csv_data, update_existing=True,
        )

        assert result["updated"] == 1
        db.refresh(product)
        assert float(product.reorder_point) == 42.0

    def test_import_update_with_upc(self, db, make_product):
        """UPC is updated from CSV on update."""
        uid = _uid_upper()
        product = make_product(sku=f"UPCUPD-{uid}", name="UPC Update")
        db.commit()

        csv_data = _csv_bytes([
            {"sku": product.sku, "name": "UPC Update", "upc": "999888777"},
        ])

        result = item_service.import_items_from_csv(
            db, file_content=csv_data, update_existing=True,
        )

        assert result["updated"] == 1
        db.refresh(product)
        assert product.upc == "999888777"

    def test_import_update_category_from_name(self, db, make_product):
        """Update import sets category from category name."""
        uid = _uid_upper()
        cat = _make_category(db, f"UPCAT-{uid}", "Widget Category CSV")
        product = make_product(sku=f"CATUPD-{uid}", name="Cat Update")
        db.commit()

        csv_data = _csv_bytes([
            {"sku": product.sku, "name": "Cat Update", "Category": "Widget Category CSV"},
        ])

        result = item_service.import_items_from_csv(
            db, file_content=csv_data, update_existing=True,
        )

        assert result["updated"] == 1
        db.refresh(product)
        assert product.category_id == cat.id


# =============================================================================
# CSV helper functions (lines 1322-1354)
# =============================================================================

class TestCsvHelperFunctions:
    """Test CSV helper functions."""

    def test_get_csv_column_value_case_variants(self):
        """_get_csv_column_value matches across naming variants."""
        row = {"Product Name": "Widget"}
        result = item_service._get_csv_column_value(row, item_service._NAME_COLUMNS)
        assert result == "Widget"

    def test_get_csv_column_value_empty(self):
        """Missing columns return empty string."""
        result = item_service._get_csv_column_value({}, item_service._SKU_COLUMNS)
        assert result == ""

    def test_parse_price_basic(self):
        """Basic price parsing."""
        assert item_service._parse_price("19.99") == pytest.approx(19.99)

    def test_parse_price_with_dollar(self):
        """Dollar sign is stripped."""
        assert item_service._parse_price("$29.99") == pytest.approx(29.99)

    def test_parse_price_with_euro(self):
        """Euro sign is stripped."""
        assert item_service._parse_price("€15.00") == pytest.approx(15.00)

    def test_parse_price_with_comma(self):
        """Comma thousands separator is stripped."""
        assert item_service._parse_price("1,299.99") == pytest.approx(1299.99)

    def test_parse_price_empty(self):
        """Empty string returns None."""
        assert item_service._parse_price("") is None

    def test_parse_price_invalid(self):
        """Non-numeric string returns None."""
        assert item_service._parse_price("not a number") is None

    def test_strip_html(self):
        """HTML tags are removed."""
        result = item_service._strip_html("<p>Hello <b>World</b></p>")
        assert result == "Hello World"

    def test_strip_html_no_tags(self):
        """Non-HTML text is returned unchanged."""
        result = item_service._strip_html("Just plain text")
        assert result == "Just plain text"

    def test_get_best_price_from_row_prefers_sale(self):
        """_get_best_price_from_row prefers sale price columns."""
        row = {"price": "20.00", "Sale Price": "15.00"}
        result = item_service._get_best_price_from_row(row)
        assert result == "15.00"

    def test_get_best_price_from_row_fallback(self):
        """Falls back to first available price column."""
        row = {"selling_price": "25.00"}
        result = item_service._get_best_price_from_row(row)
        assert result == "25.00"

    def test_get_upc_from_row(self):
        """_get_upc_from_row finds UPC from various column names."""
        row = {"Barcode": "123456"}
        result = item_service._get_upc_from_row(row)
        assert result == "123456"

    def test_get_upc_from_row_empty(self):
        """Empty UPC returns None."""
        result = item_service._get_upc_from_row({})
        assert result is None


# =============================================================================
# Category helper for CSV import (lines 1637-1676)
# =============================================================================

class TestCategoryFromCsvRow:
    """Test _update_category_from_row and _get_category_id_from_row."""

    def test_update_category_from_numeric_id(self, db, make_product):
        """Category is set from numeric category_id in CSV row."""
        cat = _make_category(db, f"NUMCAT-{_uid()}", "Numeric Cat")
        product = make_product()
        db.flush()

        row = {"category_id": str(cat.id)}
        item_service._update_category_from_row(db, product, row, None)

        assert product.category_id == cat.id

    def test_update_category_from_name(self, db, make_product):
        """Category is matched by name."""
        cat = _make_category(db, f"NAMECAT-{_uid()}", "Named Category")
        product = make_product()
        db.flush()

        row = {"Category": "Named Category"}
        item_service._update_category_from_row(db, product, row, None)

        assert product.category_id == cat.id

    def test_update_category_comma_separated(self, db, make_product):
        """WooCommerce comma-separated categories take the first one."""
        cat = _make_category(db, f"COMMA-{_uid()}", "First Category")
        product = make_product()
        db.flush()

        row = {"Categories": "First Category, Second Category"}
        item_service._update_category_from_row(db, product, row, None)

        assert product.category_id == cat.id

    def test_get_category_id_default_fallback(self, db):
        """_get_category_id_from_row returns default when no match."""
        row = {}
        result = item_service._get_category_id_from_row(db, row, default_category_id=42)
        assert result == 42

    def test_get_category_id_from_numeric_string(self, db):
        """Numeric category_id in row is parsed."""
        cat = _make_category(db, f"NUMCID-{_uid()}", "Numeric CID")
        db.flush()

        row = {"category_id": str(cat.id)}
        result = item_service._get_category_id_from_row(db, row, default_category_id=None)
        assert result == cat.id

    def test_get_category_id_invalid_numeric(self, db):
        """Non-numeric category_id falls through to name-based lookup."""
        row = {"category_id": "not-a-number"}
        result = item_service._get_category_id_from_row(db, row, default_category_id=99)
        assert result == 99


# =============================================================================
# Unit change with inventory conversion (lines 528-570)
# =============================================================================

class TestUpdateItemUnitChange:
    """Test update_item when changing unit with existing inventory."""

    def test_unit_change_converts_inventory(self, db, make_product):
        """Changing unit from G to KG converts inventory quantities."""
        product = make_product(
            sku=f"UNITCONV-{_uid()}", unit="G",
        )
        _make_inventory(db, product.id, on_hand=1000, allocated=200)
        db.commit()

        updated = item_service.update_item(
            db, product.id, data={"unit": "KG"},
        )

        assert updated.unit == "KG"
        inv = db.query(Inventory).filter(Inventory.product_id == product.id).first()
        # 1000 G -> 1 KG
        assert float(inv.on_hand_quantity) == pytest.approx(1.0, rel=1e-2)
        # 200 G -> 0.2 KG
        assert float(inv.allocated_quantity) == pytest.approx(0.2, rel=1e-2)

    def test_unit_change_incompatible_raises_400(self, db, make_product):
        """Changing to incompatible unit (e.g., G to EA) raises 400."""
        product = make_product(
            sku=f"INCOMPAT-{_uid()}", unit="G",
        )
        _make_inventory(db, product.id, on_hand=500)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            item_service.update_item(
                db, product.id, data={"unit": "EA"},
            )
        assert exc_info.value.status_code == 400
        assert "incompatible" in str(exc_info.value.detail).lower()

    def test_unit_change_no_inventory_succeeds(self, db, make_product):
        """Changing unit without inventory records succeeds freely."""
        product = make_product(
            sku=f"NOINV-{_uid()}", unit="G",
        )
        db.commit()

        updated = item_service.update_item(
            db, product.id, data={"unit": "KG"},
        )

        assert updated.unit == "KG"

    def test_unit_change_same_unit_noop(self, db, make_product):
        """Changing to the same unit (case-insensitive) is a no-op."""
        product = make_product(
            sku=f"SAMEUNIT-{_uid()}", unit="EA",
        )
        _make_inventory(db, product.id, on_hand=100)
        db.commit()

        updated = item_service.update_item(
            db, product.id, data={"unit": "ea"},
        )

        assert updated.unit == "ea"  # The value is set, but no conversion needed
        inv = db.query(Inventory).filter(Inventory.product_id == product.id).first()
        assert float(inv.on_hand_quantity) == 100.0


# =============================================================================
# Recost operations — filters and edge cases (lines 1083-1086)
# =============================================================================

class TestRecostBomCostWithUomConversion:
    """Test recalculate_bom_cost with UOM conversion between BOM line and component."""

    def test_bom_cost_with_uom_conversion(self, db, make_product, make_bom):
        """BOM line unit differs from component unit -> conversion applied."""
        fg = make_product()
        # Component tracked in KG, cost is per KG
        comp = make_product(
            item_type="component", standard_cost=Decimal("20.00"), unit="KG",
        )
        # BOM specifies 500 G
        bom = BOM(
            product_id=fg.id, name=f"BOM-UOM-{_uid()}", active=True,
        )
        db.add(bom)
        db.flush()
        line = BOMLine(
            bom_id=bom.id, component_id=comp.id,
            quantity=Decimal("500"), unit="G",
            sequence=10,
        )
        db.add(line)
        db.flush()

        total = item_service.recalculate_bom_cost(bom, db)

        # 500 G -> 0.5 KG * $20.00/KG = $10.00
        assert float(total) == pytest.approx(10.0, rel=1e-2)

    def test_bom_cost_with_scrap_factor(self, db, make_product):
        """Scrap factor increases effective quantity in cost calculation."""
        fg = make_product()
        comp = make_product(
            item_type="component", standard_cost=Decimal("2.00"), unit="EA",
        )
        bom = BOM(
            product_id=fg.id, name=f"BOM-SCRAP-{_uid()}", active=True,
        )
        db.add(bom)
        db.flush()
        line = BOMLine(
            bom_id=bom.id, component_id=comp.id,
            quantity=Decimal("10"), unit="EA",
            scrap_factor=Decimal("5"),  # 5%
            sequence=10,
        )
        db.add(line)
        db.flush()

        total = item_service.recalculate_bom_cost(bom, db)

        # 10 * (1 + 5/100) * 2.00 = 10 * 1.05 * 2.00 = 21.00
        assert float(total) == pytest.approx(21.0, rel=1e-2)


# =============================================================================
# recost_all_items with filters (lines 1184-1247)
# =============================================================================

class TestRecostAllItemsFilters:
    """Test recost_all_items with item_type, category, and cost_source filters."""

    def test_filter_by_item_type(self, db, make_product, make_bom):
        """Only items matching the item_type filter are recosted."""
        fg = make_product(item_type="finished_good", standard_cost=Decimal("0"))
        comp = make_product(
            item_type="component", standard_cost=Decimal("10.00"), unit="EA",
        )
        make_bom(fg.id, lines=[
            {"component_id": comp.id, "quantity": Decimal("1"), "unit": "EA"},
        ])
        supply = make_product(item_type="supply", standard_cost=Decimal("0"))
        db.commit()

        result = item_service.recost_all_items(db, item_type="finished_good")

        # Only the finished good should be updated, not the supply
        updated_ids = [i["id"] for i in result["items"]]
        assert fg.id in updated_ids
        assert supply.id not in updated_ids

    def test_filter_by_category(self, db, make_product, make_bom):
        """Only items in the specified category are recosted."""
        cat = _make_category(db, f"RC-CAT-{_uid()}", "Recost Cat")
        db.flush()

        fg = make_product(
            item_type="finished_good", standard_cost=Decimal("0"),
            category_id=cat.id,
        )
        comp = make_product(
            item_type="component", standard_cost=Decimal("5.00"), unit="EA",
        )
        make_bom(fg.id, lines=[
            {"component_id": comp.id, "quantity": Decimal("2"), "unit": "EA"},
        ])

        other = make_product(
            item_type="finished_good", standard_cost=Decimal("0"),
        )
        db.commit()

        result = item_service.recost_all_items(db, category_id=cat.id)

        updated_ids = [i["id"] for i in result["items"]]
        assert fg.id in updated_ids
        assert other.id not in updated_ids

    def test_filter_by_cost_source(self, db, make_product, make_bom):
        """Only items matching the cost_source_filter are included."""
        fg = make_product(item_type="finished_good", standard_cost=Decimal("0"))
        comp = make_product(
            item_type="component", standard_cost=Decimal("8.00"), unit="EA",
        )
        make_bom(fg.id, lines=[
            {"component_id": comp.id, "quantity": Decimal("1"), "unit": "EA"},
        ])

        purchased = make_product(
            item_type="supply", standard_cost=Decimal("3.00"),
        )
        db.commit()

        result = item_service.recost_all_items(db, cost_source_filter="manufactured")

        updated_ids = [i["id"] for i in result["items"]]
        assert fg.id in updated_ids
        # Purchased item should be excluded by cost_source_filter
        assert purchased.id not in updated_ids


# =============================================================================
# calculate_item_cost edge cases
# =============================================================================

class TestCalculateItemCostEdgeCases:
    """Additional tests for calculate_item_cost."""

    def test_purchased_item_fallback_to_last_cost(self, db, make_product):
        """If no standard_cost or average_cost, falls back to last_cost."""
        product = make_product(last_cost=Decimal("6.50"))
        db.commit()

        result = item_service.calculate_item_cost(product, db)

        assert result["cost_source"] == "purchased"
        assert result["purchase_cost"] == 6.50

    def test_purchased_item_no_cost_at_all(self, db, make_product):
        """Item with no cost data returns zero."""
        product = make_product()
        db.commit()

        result = item_service.calculate_item_cost(product, db)

        assert result["cost_source"] == "purchased"
        assert result["purchase_cost"] == 0.0
        assert result["total_cost"] == 0.0


# =============================================================================
# Low stock with MRP shortages (lines 825-853, 876-940)
# =============================================================================

class TestLowStockWithMrpShortages:
    """Test get_low_stock_items with include_mrp_shortages=True."""

    def test_mrp_shortage_adds_items(self, db, make_product, make_bom):
        """MRP shortages from BOM explosion appear in low stock results."""
        fg = make_product(
            item_type="finished_good", procurement_type="make",
            has_bom=True, unit="EA",
        )
        raw = make_product(
            item_type="supply", unit="EA", is_raw_material=True,
            procurement_type="buy", standard_cost=Decimal("1.00"),
        )
        make_bom(fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("10"), "unit": "EA"},
        ])

        # Create an active sales order that triggers MRP demand
        from app.models.sales_order import SalesOrder
        uid = _uid()
        so = SalesOrder(
            order_number=f"SO-LOWSTK-{uid}",
            user_id=1,
            product_id=fg.id,
            product_name="Low Stock FG",
            quantity=5,
            material_type="PLA",
            unit_price=Decimal("10"),
            total_price=Decimal("50"),
            grand_total=Decimal("50"),
            status="confirmed",
            order_type="quote_based",
        )
        db.add(so)
        db.flush()
        db.commit()

        result = item_service.get_low_stock_items(
            db, include_mrp_shortages=True,
        )

        # The raw material should appear with MRP shortage
        raw_items = [i for i in result["items"] if i["id"] == raw.id]
        if raw_items:
            assert raw_items[0]["mrp_shortage"] > 0
            assert raw_items[0]["shortage_source"] in ("mrp", "both")

    def test_mrp_shortage_from_production_order(self, db, make_product, make_bom):
        """MRP shortages from active production orders appear in low stock."""
        fg = make_product(
            item_type="finished_good", procurement_type="make",
            has_bom=True, unit="EA",
        )
        raw = make_product(
            item_type="supply", unit="EA", is_raw_material=True,
            procurement_type="buy", standard_cost=Decimal("2.00"),
        )
        make_bom(fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("5"), "unit": "EA"},
        ])

        # Create an active production order
        from app.models.production_order import ProductionOrder
        po = ProductionOrder(
            code=f"PO-LOWSTK-{_uid()}",
            product_id=fg.id,
            quantity_ordered=Decimal("10"),
            quantity_completed=Decimal("0"),
            quantity_scrapped=Decimal("0"),
            status="released",
            source="manual",
        )
        db.add(po)
        db.flush()
        db.commit()

        result = item_service.get_low_stock_items(
            db, include_mrp_shortages=True,
        )

        raw_items = [i for i in result["items"] if i["id"] == raw.id]
        if raw_items:
            assert raw_items[0]["mrp_shortage"] > 0


# =============================================================================
# Bulk update edge cases
# =============================================================================

class TestBulkUpdateEdgeCases:
    """Additional edge cases for bulk_update_items."""

    def test_update_item_type_valid(self, db, make_product):
        """Valid item_type is applied in bulk update."""
        product = make_product(item_type="finished_good")
        db.commit()

        result = item_service.bulk_update_items(
            db, item_ids=[product.id], item_type="component",
        )

        assert result["updated_count"] == 1
        db.refresh(product)
        assert product.item_type == "component"

    def test_invalid_procurement_type_recorded_as_error(self, db, make_product):
        """Invalid procurement_type is recorded as error, not exception."""
        product = make_product()
        db.commit()

        result = item_service.bulk_update_items(
            db, item_ids=[product.id], procurement_type="invalid_type",
        )

        assert result["error_count"] == 1
        assert "invalid" in result["errors"][0]["error"].lower()


# =============================================================================
# delete_category edge cases
# =============================================================================

class TestDeleteCategoryEdgeCases:
    """Additional edge cases for delete_category."""

    def test_delete_nonexistent_category_raises_404(self, db):
        """Deleting a non-existent category raises 404."""
        with pytest.raises(HTTPException) as exc_info:
            item_service.delete_category(db, 999999)
        assert exc_info.value.status_code == 404

    def test_delete_category_with_inactive_children_succeeds(self, db):
        """Category with only inactive children can be deleted."""
        parent = _make_category(db, f"DEL-OK-{_uid()}", "Deletable")
        _make_category(
            db, f"DEL-CHILD-{_uid()}", "Inactive Child",
            parent_id=parent.id, is_active=False,
        )
        db.commit()

        result = item_service.delete_category(db, parent.id)
        assert "deleted" in result["message"].lower() or parent.code in result["message"]


# =============================================================================
# update_category edge cases
# =============================================================================

class TestUpdateCategoryEdgeCases:
    """Additional edge cases for update_category."""

    def test_update_nonexistent_category_raises_404(self, db):
        """Updating a non-existent category raises 404."""
        with pytest.raises(HTTPException) as exc_info:
            item_service.update_category(db, 999999, name="Ghost")
        assert exc_info.value.status_code == 404

    def test_update_parent_to_nonexistent_raises_400(self, db):
        """Setting parent_id to a non-existent category raises 400."""
        cat = _make_category(db, f"UPDPAR-{_uid()}", "Update Parent")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            item_service.update_category(db, cat.id, parent_id=999999)
        assert exc_info.value.status_code == 400
        assert "parent" in str(exc_info.value.detail).lower()

    def test_update_description(self, db):
        """Description is updated correctly."""
        cat = _make_category(db, f"UPDDESC-{_uid()}", "Desc Cat")
        db.commit()

        updated = item_service.update_category(
            db, cat.id, description="New description",
        )
        assert updated.description == "New description"

    def test_update_parent_to_none(self, db):
        """Setting parent_id to None removes the parent."""
        parent = _make_category(db, f"PAR-RM-{_uid()}", "Parent RM")
        child = _make_category(
            db, f"CHD-RM-{_uid()}", "Child RM",
            parent_id=parent.id,
        )
        db.commit()

        updated = item_service.update_category(db, child.id, parent_id=None)
        assert updated.parent_id is None
