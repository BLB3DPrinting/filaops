"""
Item Import Service — CSV bulk import of items with marketplace column mapping.

Extracted verbatim from item_service.py (DEBT-1 D1-B mechanical split).
item_service re-exports these names for backward compatibility.
"""
import csv
import io
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import Product, ItemCategory

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# CSV Import Column Mappings
# ---------------------------------------------------------------------------

# Marketplace column mappings for SKU
_SKU_COLUMNS = [
    "sku", "SKU", "Sku", "product_sku", "Product SKU", "product-sku",
    "Variant SKU", "variant_sku", "variant-sku", "VariantSKU",
    "SKU Code", "sku_code", "sku-code", "SKUCode",
    "ASIN", "asin", "Amazon ASIN",
    "Product Code", "product_code", "product-code",
    "Item SKU", "item_sku", "item-sku",
    "Product ID", "product_id", "product-id",
]

# Marketplace column mappings for Name
_NAME_COLUMNS = [
    "name", "Name", "product_name", "Product Name", "product-name",
    "title", "Title", "Product Title", "product-title",
    "Variant Title", "variant_title", "variant-title", "VariantTitle",
    "Product Title", "product_title", "product-title", "ProductTitle",
    "Item Name", "item_name", "item-name",
]

# Marketplace column mappings for Description
_DESCRIPTION_COLUMNS = [
    "description", "Description", "product_description", "Product Description",
    "Body (HTML)", "body_html", "Body", "body", "Body HTML",
    "Short Description", "short_description", "short-description", "Short description",
    "Long Description", "long_description", "long-description",
    "Product Description", "product-description",
    "Item Description", "item_description",
]

# Marketplace column mappings for Price
_PRICE_COLUMNS = [
    "selling_price", "Selling Price", "selling-price",
    "price", "Price",
    "Variant Price", "variant_price", "variant-price", "VariantPrice",
    "Variant Compare At Price", "variant_compare_at_price", "variant-compare-at-price",
    "Sale price", "sale_price", "sale-price", "Sale Price",
    "Regular price", "regular_price", "regular-price", "Regular Price",
    "Unit Price", "unit_price", "unit-price", "UnitPrice",
    "Retail Price", "retail_price", "retail-price",
    "List Price", "list_price", "list-price",
]

# Marketplace column mappings for Cost
_COST_COLUMNS = [
    "standard_cost", "Standard Cost", "standard-cost",
    "cost", "Cost",
    "Variant Cost", "variant_cost", "variant-cost", "VariantCost",
    "Wholesale Price", "wholesale_price", "wholesale-price",
    "Cost Price", "cost_price", "cost-price", "CostPrice",
    "Purchase PPU", "purchase_ppu", "purchase-ppu",
    "Item Subtotal", "item_subtotal",
    "Purchase Cost", "purchase_cost", "purchase-cost",
    "Unit Cost", "unit_cost", "unit-cost",
    "Wholesale Cost", "wholesale_cost",
]

# UOM column mappings
_UNIT_COLUMNS = [
    "unit", "Unit", "UOM", "uom", "Unit of Measure", "unit_of_measure",
]

_PURCHASE_UOM_COLUMNS = [
    "purchase_uom", "Purchase UOM", "purchase_unit", "Purchase Unit",
    "buying_unit", "Buying Unit", "order_unit", "Order Unit",
]


def _get_csv_column_value(row: dict, possible_names: list[str]) -> str:
    """Get value from CSV row using case-insensitive column name matching."""
    for col in possible_names:
        if row.get(col, "").strip():
            return row.get(col, "").strip()
    return ""


def _parse_price(price_str: str) -> float | None:
    """Parse price string, removing currency symbols."""
    if not price_str:
        return None
    price_clean = (
        price_str.replace("$", "")
        .replace(",", "")
        .replace("€", "")
        .replace("£", "")
        .strip()
    )
    try:
        return float(price_clean)
    except ValueError:
        return None


def _strip_html(text: str) -> str:
    """Strip HTML tags from text."""
    import re

    if "<" in text and ">" in text:
        return re.sub(r"<[^>]+>", "", text).strip()
    return text


def _normalize_import_item_type(value: str | None, default: str) -> str:
    """Normalize item type names from CSV exports and shop-owner shorthand."""
    item_type_raw = (value or "").strip().lower()
    if not item_type_raw:
        return default

    item_type_map = {
        "simple": "finished_good",
        "variable": "finished_good",
        "finished_good": "finished_good",
        "component": "component",
        "packaging": "packaging",
        "box": "packaging",
        "mailers": "packaging",
        "mailer": "packaging",
        "supply": "supply",
        "service": "service",
        "material": "material",
        "filament": "material",
        "raw_material": "material",
    }
    return item_type_map.get(item_type_raw, default)


def import_items_from_csv(
    db: Session,
    *,
    file_content: bytes,
    update_existing: bool = False,
    default_item_type: str = "finished_good",
    default_category_id: int | None = None,
) -> dict:
    """
    Import items from CSV file content.

    Returns dict with keys: total_rows, created, updated, skipped, errors, warnings.
    """
    from app.services.product_uom_service import get_recommended_uoms, validate_product_uoms

    try:
        text = file_content.decode("utf-8")
    except UnicodeDecodeError:
        text = file_content.decode("latin-1")

    if text.startswith("\ufeff"):
        text = text[1:]

    reader = csv.DictReader(io.StringIO(text))

    result = {
        "total_rows": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "warnings": [],
    }

    for row_num, row in enumerate(reader, start=2):
        result["total_rows"] += 1

        try:
            # Find SKU
            sku = _get_csv_column_value(row, _SKU_COLUMNS).upper()
            if not sku:
                result["errors"].append({
                    "row": row_num,
                    "error": "SKU is required",
                })
                result["skipped"] += 1
                continue

            # Find name
            name = _get_csv_column_value(row, _NAME_COLUMNS)
            if not name:
                result["errors"].append({
                    "row": row_num,
                    "error": "Name is required",
                    "sku": sku,
                })
                result["skipped"] += 1
                continue

            # Check if exists
            existing = db.query(Product).filter(Product.sku == sku).first()

            if existing:
                # Protect seeded example items
                if existing.sku.startswith("SEED-EXAMPLE-"):
                    result["errors"].append({
                        "row": row_num,
                        "error": f"SKU '{sku}' is a seeded example item",
                        "sku": sku,
                    })
                    result["skipped"] += 1
                    continue

                if not update_existing:
                    result["skipped"] += 1
                    continue

                # Update existing
                existing.name = name

                # Update description
                desc = _get_csv_column_value(row, _DESCRIPTION_COLUMNS)
                if desc:
                    existing.description = _strip_html(desc)

                # Update unit
                unit_value = _get_csv_column_value(row, _UNIT_COLUMNS).upper()
                if unit_value:
                    existing.unit = unit_value

                # Update purchase_uom
                purchase_uom_value = _get_csv_column_value(
                    row, _PURCHASE_UOM_COLUMNS
                ).upper()
                if purchase_uom_value:
                    existing.purchase_uom = purchase_uom_value

                # Update item type
                item_type_raw = (
                    row.get("item_type", "")
                    or row.get("Item Type", "")
                    or row.get("Type", "")
                ).strip()
                if item_type_raw:
                    existing.item_type = _normalize_import_item_type(
                        item_type_raw, existing.item_type
                    )

                # Update category
                _update_category_from_row(db, existing, row, default_category_id)

                # Update cost
                cost_str = _get_csv_column_value(row, _COST_COLUMNS)
                cost = _parse_price(cost_str)
                if cost is not None:
                    existing.standard_cost = cost

                # Update price
                price_str = _get_best_price_from_row(row)
                price = _parse_price(price_str)
                if price is not None:
                    existing.selling_price = price

                # Update reorder point
                if row.get("reorder_point"):
                    try:
                        existing.reorder_point = float(row["reorder_point"])
                    except ValueError:
                        pass

                # Update UPC
                upc = _get_upc_from_row(row)
                if upc:
                    existing.upc = upc

                existing.updated_at = datetime.now(timezone.utc)

                # Validate UOM configuration
                is_valid, warning_msg = validate_product_uoms(db, existing)
                if not is_valid:
                    result["warnings"].append({
                        "row": row_num,
                        "sku": sku,
                        "warning": warning_msg,
                    })

                result["updated"] += 1

            else:
                # Create new item
                desc = _get_csv_column_value(row, _DESCRIPTION_COLUMNS)
                description = _strip_html(desc) if desc else None

                price_str = _get_best_price_from_row(row)
                selling_price = _parse_price(price_str)

                cost_str = _get_csv_column_value(row, _COST_COLUMNS)
                standard_cost = _parse_price(cost_str)

                # Handle category
                final_category_id = _get_category_id_from_row(
                    db, row, default_category_id
                )

                # Get item type
                item_type_str = (
                    row.get("item_type", "")
                    or row.get("Item Type", "")
                    or row.get("Type", "")
                    or ""
                ).strip() or default_item_type
                item_type_str = _normalize_import_item_type(
                    item_type_str, default_item_type
                )

                # Get unit from CSV
                unit_value = _get_csv_column_value(row, _UNIT_COLUMNS).upper()
                purchase_uom_value = _get_csv_column_value(
                    row, _PURCHASE_UOM_COLUMNS
                ).upper()
                purchase_factor = None
                is_raw_material = False

                # Auto-detect UOMs based on item type, SKU, and category if not provided.
                if not purchase_uom_value or not unit_value:
                    (
                        recommended_purchase,
                        recommended_unit,
                        is_raw_material,
                        purchase_factor,
                    ) = get_recommended_uoms(
                        db,
                        sku=sku,
                        category_id=final_category_id,
                        item_type=item_type_str,
                    )
                    if not purchase_uom_value:
                        purchase_uom_value = recommended_purchase
                    if not unit_value and is_raw_material:
                        unit_value = recommended_unit

                final_unit = unit_value or "EA"
                final_purchase_uom = purchase_uom_value or final_unit
                if purchase_factor is None:
                    purchase_factor = 1

                # Get reorder point
                reorder_point = None
                if row.get("reorder_point"):
                    try:
                        reorder_point = float(row["reorder_point"])
                    except ValueError:
                        pass

                # Get UPC
                upc = _get_upc_from_row(row)

                item = Product(
                    sku=sku,
                    name=name,
                    description=description,
                    unit=final_unit,
                    purchase_uom=final_purchase_uom,
                    item_type=item_type_str,
                    category_id=final_category_id,
                    standard_cost=standard_cost,
                    selling_price=selling_price,
                    purchase_factor=purchase_factor,
                    is_raw_material=is_raw_material,
                    reorder_point=reorder_point,
                    upc=upc,
                    active=True,
                )
                db.add(item)
                db.flush()

                # Validate UOM configuration
                is_valid, warning_msg = validate_product_uoms(db, item)
                if not is_valid:
                    result["warnings"].append({
                        "row": row_num,
                        "sku": sku,
                        "warning": warning_msg,
                    })

                result["created"] += 1

        except Exception as e:
            result["errors"].append({
                "row": row_num,
                "error": str(e),
                "sku": row.get("sku", ""),
            })
            result["skipped"] += 1

    db.commit()

    logger.info(
        f"CSV import complete: {result['created']} created, "
        f"{result['updated']} updated, {result['skipped']} skipped, "
        f"{len(result['warnings'])} UOM warnings"
    )

    return result


def _get_best_price_from_row(row: dict) -> str:
    """Get the best price from CSV row, preferring sale price."""
    for col in _PRICE_COLUMNS:
        value = row.get(col, "").strip()
        if value:
            # Prefer sale price if available (WooCommerce)
            if "sale" in col.lower():
                return value
    # Return first found as fallback
    return _get_csv_column_value(row, _PRICE_COLUMNS)


def _get_upc_from_row(row: dict) -> str | None:
    """Get UPC/barcode from CSV row."""
    upc_cols = [
        "upc", "UPC", "barcode", "Barcode", "EAN", "GTIN",
        "Product Code", "product_code", "ASIN", "asin",
    ]
    value = _get_csv_column_value(row, upc_cols)
    return value if value else None


def _update_category_from_row(
    db: Session, product: Product, row: dict, default_category_id: int | None
) -> None:
    """Update product category from CSV row data."""
    # Try category_id first (numeric)
    category_id_raw = (
        row.get("category_id", "")
        or row.get("Category ID", "")
        or row.get("category-id", "")
    ).strip()
    if category_id_raw:
        try:
            product.category_id = int(category_id_raw)
            return
        except ValueError:
            pass

    # Try category name
    category_name_raw = (
        row.get("Category", "")
        or row.get("category", "")
        or row.get("Categories", "")
        or row.get("Product Category", "")
        or row.get("Type", "")
        or row.get("Product Type", "")
    ).strip()

    if category_name_raw:
        # Handle WooCommerce comma-separated categories (take first)
        if "," in category_name_raw:
            category_name_raw = category_name_raw.split(",")[0].strip()

        # Try to find category by name
        category = (
            db.query(ItemCategory)
            .filter(ItemCategory.name.ilike(f"%{category_name_raw}%"))
            .first()
        )
        if category:
            product.category_id = category.id


def _get_category_id_from_row(
    db: Session, row: dict, default_category_id: int | None
) -> int | None:
    """Get category ID from CSV row data."""
    # Try category_id first (numeric)
    category_id_raw = (
        row.get("category_id", "")
        or row.get("Category ID", "")
        or row.get("category-id", "")
    ).strip()
    if category_id_raw:
        try:
            return int(category_id_raw)
        except ValueError:
            pass

    # Try category name
    category_name_raw = (
        row.get("Category", "")
        or row.get("category", "")
        or row.get("Categories", "")
        or row.get("Product Category", "")
        or row.get("Type", "")
        or row.get("Product Type", "")
    ).strip()

    if category_name_raw:
        if "," in category_name_raw:
            category_name_raw = category_name_raw.split(",")[0].strip()

        category = (
            db.query(ItemCategory)
            .filter(ItemCategory.name.ilike(f"%{category_name_raw}%"))
            .first()
        )
        if category:
            return category.id

    return default_category_id
