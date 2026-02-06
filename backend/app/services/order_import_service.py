"""
Order CSV Import Service

Handles importing sales orders from CSV files:
- Parse CSV with flexible column mapping
- Find or create customers
- Validate products and pricing
- Create sales orders with line items

Business logic extracted from ``admin/orders.py``.
"""
import csv
import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.user import User


# ============================================================================
# HELPERS
# ============================================================================

def clean_price(price_str: str) -> Optional[Decimal]:
    """Remove currency symbols and commas from price string."""
    if not price_str:
        return None
    try:
        cleaned = price_str.replace("$", "").replace(",", "").strip()
        if not cleaned:
            return None
        return Decimal(cleaned)
    except (ValueError, TypeError, InvalidOperation):
        return None


def find_product_by_sku(db: Session, sku: str) -> Optional[Product]:
    """Find product by SKU (case-insensitive)."""
    return db.query(Product).filter(Product.sku.ilike(sku.strip())).first()


def find_or_create_customer(
    db: Session,
    email: str,
    name: str = None,
    shipping_address: dict = None,
) -> Optional[User]:
    """Find existing customer by email or create new one."""
    if not email or "@" not in email:
        return None

    email_lower = email.lower().strip()

    customer = db.query(User).filter(User.email.ilike(email_lower)).first()
    if customer:
        return customer

    first_name = ""
    last_name = ""
    if name:
        name_parts = name.strip().split(maxsplit=1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

    year = datetime.now(timezone.utc).year
    last_customer = db.query(User).filter(
        User.customer_number.like(f"CUST-{year}-%")
    ).order_by(User.customer_number.desc()).first()

    if last_customer:
        try:
            last_num = int(last_customer.customer_number.split("-")[2])
            customer_number = f"CUST-{year}-{last_num + 1:06d}"
        except (ValueError, IndexError):
            customer_number = f"CUST-{year}-000001"
    else:
        customer_number = f"CUST-{year}-000001"

    now = datetime.now(timezone.utc)
    customer = User(
        customer_number=customer_number,
        email=email_lower,
        password_hash="!import-created-no-password",  # unusable hash; customer must reset password
        first_name=first_name or None,
        last_name=last_name or None,
        company_name=shipping_address.get("company") if shipping_address else None,
        phone=shipping_address.get("phone") if shipping_address else None,
        status="active",
        account_type="customer",
        email_verified=False,
        shipping_address_line1=shipping_address.get("line1") if shipping_address else None,
        shipping_address_line2=shipping_address.get("line2") if shipping_address else None,
        shipping_city=shipping_address.get("city") if shipping_address else None,
        shipping_state=shipping_address.get("state") if shipping_address else None,
        shipping_zip=shipping_address.get("zip") if shipping_address else None,
        shipping_country=shipping_address.get("country") or "USA",
        billing_address_line1=shipping_address.get("line1") if shipping_address else None,
        billing_address_line2=shipping_address.get("line2") if shipping_address else None,
        billing_city=shipping_address.get("city") if shipping_address else None,
        billing_state=shipping_address.get("state") if shipping_address else None,
        billing_zip=shipping_address.get("zip") if shipping_address else None,
        billing_country=shipping_address.get("country") or "USA",
        created_at=now,
        updated_at=now,
    )
    db.add(customer)
    db.flush()
    return customer


# ============================================================================
# COLUMN NAME VARIATIONS
# ============================================================================

ORDER_ID_COLS = ["order id", "Order ID", "order_id", "Order_ID", "Order Number", "order_number", "Order #", "Order#"]
ORDER_DATE_COLS = ["order date", "Order Date", "order_date", "Date", "date", "Order Date/Time"]
CUSTOMER_EMAIL_COLS = ["customer email", "Customer Email", "customer_email", "Email", "email", "Buyer Email", "buyer_email"]
CUSTOMER_NAME_COLS = ["customer name", "Customer Name", "customer_name", "Name", "name", "Buyer Name", "buyer_name", "Shipping Name", "shipping name"]
PRODUCT_SKU_COLS = ["product sku", "Product SKU", "product_sku", "SKU", "sku", "Variant SKU", "variant_sku", "Item SKU", "item_sku"]
QUANTITY_COLS = ["quantity", "Quantity", "Qty", "qty", "QTY"]
UNIT_PRICE_COLS = ["unit price", "Unit Price", "unit_price", "Price", "price", "Item Price", "item_price"]
SHIPPING_COST_COLS = ["shipping cost", "Shipping Cost", "shipping_cost", "Shipping", "shipping"]
TAX_COLS = ["tax amount", "Tax Amount", "tax_amount", "Tax", "tax"]
SHIP_LINE1_COLS = ["shipping address line 1", "Shipping Address Line 1", "shipping_address_line1", "Shipping Address", "shipping address"]
SHIP_CITY_COLS = ["shipping city", "Shipping City", "shipping_city", "City", "city"]
SHIP_STATE_COLS = ["shipping state", "Shipping State", "shipping_state", "State", "state"]
SHIP_ZIP_COLS = ["shipping zip", "Shipping Zip", "shipping_zip", "Zip", "zip", "Postal Code", "postal_code"]
SHIP_COUNTRY_COLS = ["shipping country", "Shipping Country", "shipping_country", "Country", "country"]
NOTES_COLS = ["customer notes", "Customer Notes", "customer_notes", "Notes", "notes", "Order Notes"]


def _find_col(row: dict, candidates: list) -> str:
    """Find the first matching column value from a list of candidates."""
    for col in candidates:
        val = row.get(col, "").strip()
        if val:
            return val
    return ""


# ============================================================================
# MAIN IMPORT FUNCTION
# ============================================================================

def import_orders_from_csv(
    db: Session,
    csv_text: str,
    *,
    create_customers: bool = True,
    source: str = "manual",
    current_user_id: int,
) -> Dict[str, Any]:
    """Import orders from CSV text content.

    Args:
        db: Database session
        csv_text: Decoded CSV text content (BOM already stripped)
        create_customers: Whether to auto-create missing customers
        source: Order source label (manual, squarespace, shopify, etc.)
        current_user_id: ID of the admin performing the import

    Returns:
        Dict with total_rows, created, skipped, errors
    """
    reader = csv.DictReader(io.StringIO(csv_text))

    total_rows = 0
    created = 0
    skipped = 0
    errors: List[dict] = []

    # Group rows by Order ID for multi-line orders
    orders_dict: Dict[str, Dict[str, Any]] = {}

    for row_num, row in enumerate(reader, start=2):
        total_rows += 1
        order_id = ""

        try:
            order_id = _find_col(row, ORDER_ID_COLS) or f"IMPORT-{row_num}"
            customer_email = _find_col(row, CUSTOMER_EMAIL_COLS).lower()
            if not customer_email or "@" not in customer_email:
                customer_email = f"import-{order_id.lower().replace(' ', '-')}@placeholder.local"

            product_sku = _find_col(row, PRODUCT_SKU_COLS)
            if not product_sku:
                errors.append({"row": row_num, "error": "Product SKU missing - line item skipped", "order_id": order_id})
                continue

            # Parse quantity
            quantity = 1
            qty_str = _find_col(row, QUANTITY_COLS)
            if qty_str:
                try:
                    quantity = int(float(qty_str.replace(",", "")))
                    if quantity <= 0:
                        quantity = 1
                except (ValueError, TypeError):
                    pass

            unit_price = None
            up_str = _find_col(row, UNIT_PRICE_COLS)
            if up_str:
                unit_price = clean_price(up_str)

            shipping_cost = Decimal("0.00")
            sc_str = _find_col(row, SHIPPING_COST_COLS)
            if sc_str:
                shipping_cost = clean_price(sc_str) or Decimal("0.00")

            tax_amount = Decimal("0.00")
            tax_str = _find_col(row, TAX_COLS)
            if tax_str:
                tax_amount = clean_price(tax_str) or Decimal("0.00")

            customer_name = _find_col(row, CUSTOMER_NAME_COLS)

            shipping_address = {}
            for key, cols in [
                ("line1", SHIP_LINE1_COLS),
                ("city", SHIP_CITY_COLS),
                ("state", SHIP_STATE_COLS),
                ("zip", SHIP_ZIP_COLS),
                ("country", SHIP_COUNTRY_COLS),
            ]:
                val = _find_col(row, cols)
                if val:
                    shipping_address[key] = val

            notes = _find_col(row, NOTES_COLS)

            if order_id not in orders_dict:
                orders_dict[order_id] = {
                    "customer_email": customer_email,
                    "customer_name": customer_name,
                    "shipping_address": shipping_address,
                    "shipping_cost": shipping_cost,
                    "tax_amount": tax_amount,
                    "notes": notes,
                    "lines": [],
                }

            orders_dict[order_id]["lines"].append({
                "sku": product_sku,
                "quantity": quantity,
                "unit_price": unit_price,
            })

        except Exception as e:
            errors.append({"row": row_num, "error": str(e), "order_id": order_id})
            skipped += 1

    # Process each order
    for order_id, order_data in orders_dict.items():
        try:
            customer = None
            if create_customers:
                customer = find_or_create_customer(
                    db,
                    order_data["customer_email"],
                    order_data["customer_name"],
                    order_data["shipping_address"],
                )
            else:
                customer = db.query(User).filter(
                    User.email.ilike(order_data["customer_email"])
                ).first()

            if not customer:
                if "@placeholder.local" in order_data["customer_email"] and not create_customers:
                    errors.append({"order_id": order_id, "error": "Customer email missing and create_customers=false - order skipped"})
                else:
                    errors.append({"order_id": order_id, "error": f"Customer not found: {order_data['customer_email']} (set create_customers=true to auto-create)"})
                skipped += 1
                continue

            # Process order lines
            line_products = []
            total_price = Decimal("0.00")
            total_quantity = 0

            for line in order_data["lines"]:
                product = find_product_by_sku(db, line["sku"])
                if not product:
                    errors.append({"order_id": order_id, "error": f"Product not found: {line['sku']}"})
                    continue
                if not product.active:
                    errors.append({"order_id": order_id, "error": f"Product '{line['sku']}' is inactive"})
                    continue

                up = line["unit_price"] or product.selling_price or Decimal("0.00")
                if up <= 0:
                    errors.append({"order_id": order_id, "error": f"Product '{line['sku']}' has no price"})
                    continue

                line_total = up * line["quantity"]
                line_products.append({"product": product, "quantity": line["quantity"], "unit_price": up, "line_total": line_total})
                total_price += line_total
                total_quantity += line["quantity"]

            if not line_products:
                errors.append({"order_id": order_id, "error": "No valid products found for order"})
                skipped += 1
                continue

            # Check duplicate
            existing = db.query(SalesOrder).filter(SalesOrder.source_order_id == order_id).first()
            if existing:
                errors.append({"order_id": order_id, "error": f"Order already exists: {existing.order_number}"})
                skipped += 1
                continue

            # Generate order number
            year = datetime.now(timezone.utc).year
            last_order = db.query(SalesOrder).filter(
                SalesOrder.order_number.like(f"SO-{year}-%")
            ).order_by(SalesOrder.order_number.desc()).first()

            if last_order:
                try:
                    last_num = int(last_order.order_number.split("-")[2])
                    order_number = f"SO-{year}-{last_num + 1:06d}"
                except (ValueError, IndexError):
                    order_number = f"SO-{year}-000001"
            else:
                order_number = f"SO-{year}-000001"

            shipping_cost = order_data["shipping_cost"]
            tax_amount = order_data["tax_amount"]
            grand_total = total_price + shipping_cost + tax_amount

            ship_addr = order_data["shipping_address"]
            shipping_line1 = ship_addr.get("line1") or customer.shipping_address_line1
            shipping_city = ship_addr.get("city") or customer.shipping_city
            shipping_state = ship_addr.get("state") or customer.shipping_state
            shipping_zip = ship_addr.get("zip") or customer.shipping_zip
            shipping_country = ship_addr.get("country") or customer.shipping_country or "USA"

            sales_order = SalesOrder(
                user_id=customer.id,
                order_number=order_number,
                order_type="line_item",
                source=source,
                source_order_id=order_id,
                product_name=line_products[0]["product"].name if line_products else "Imported Order",
                quantity=total_quantity,
                material_type="PLA",
                finish="standard",
                unit_price=total_price / total_quantity if total_quantity > 0 else Decimal("0.00"),
                total_price=total_price,
                tax_amount=tax_amount,
                shipping_cost=shipping_cost,
                grand_total=grand_total,
                status="pending",
                payment_status="pending",
                rush_level="standard",
                shipping_address_line1=shipping_line1,
                shipping_address_line2=None,
                shipping_city=shipping_city,
                shipping_state=shipping_state,
                shipping_zip=shipping_zip,
                shipping_country=shipping_country,
                customer_notes=order_data["notes"],
                internal_notes=f"Imported from {source} CSV",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(sales_order)
            db.flush()

            for line_data in line_products:
                order_line = SalesOrderLine(
                    sales_order_id=sales_order.id,
                    product_id=line_data["product"].id,
                    quantity=line_data["quantity"],
                    unit_price=line_data["unit_price"],
                    total=line_data["line_total"],
                    discount=Decimal("0.00"),
                    tax_rate=Decimal("0.00"),
                    notes=None,
                    created_by=current_user_id,
                )
                db.add(order_line)

            db.commit()
            created += 1

        except Exception as e:
            db.rollback()
            errors.append({"order_id": order_id, "error": str(e)})
            skipped += 1

    return {"total_rows": total_rows, "created": created, "skipped": skipped, "errors": errors}
