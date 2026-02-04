"""
Customer Service — CRUD, search, stats, and CSV import for customers.

Extracted from admin/customers.py (ARCHITECT-003).
"""
import csv
import io
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import Integer, cast, desc, func
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.logging_config import get_logger
from app.models.quote import Quote
from app.models.sales_order import SalesOrder
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerUpdate

logger = get_logger(__name__)


# =============================================================================
# Private Helpers
# =============================================================================

def _build_full_name(customer: User) -> Optional[str]:
    """Build a display name from first/last name fields."""
    if customer.first_name and customer.last_name:
        return f"{customer.first_name} {customer.last_name}"
    if customer.first_name:
        return customer.first_name
    if customer.last_name:
        return customer.last_name
    return None


def _get_customer_stats(db: Session, customer_id: int) -> dict:
    """Fetch order count, quote count, and total spent for a customer."""
    order_count = db.query(func.count(SalesOrder.id)).filter(
        SalesOrder.user_id == customer_id,
        SalesOrder.status != "cancelled",
    ).scalar() or 0

    quote_count = db.query(func.count(Quote.id)).filter(
        Quote.user_id == customer_id,
    ).scalar() or 0

    total_spent = db.query(func.sum(SalesOrder.grand_total)).filter(
        SalesOrder.user_id == customer_id,
        SalesOrder.status != "cancelled",
    ).scalar() or 0

    return {
        "order_count": order_count,
        "quote_count": quote_count,
        "total_spent": float(total_spent),
    }


def _get_customer_or_404(db: Session, customer_id: int) -> User:
    """Fetch a customer by ID or raise 404."""
    customer = (
        db.query(User)
        .filter(User.id == customer_id, User.account_type == "customer")
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


def _customer_response(customer: User, stats: dict) -> dict:
    """Build a full CustomerResponse dict from a User instance and stats."""
    return {
        "id": customer.id,
        "customer_number": customer.customer_number,
        "email": customer.email,
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "company_name": customer.company_name,
        "phone": customer.phone,
        "status": customer.status,
        "email_verified": customer.email_verified,
        "billing_address_line1": customer.billing_address_line1,
        "billing_address_line2": customer.billing_address_line2,
        "billing_city": customer.billing_city,
        "billing_state": customer.billing_state,
        "billing_zip": customer.billing_zip,
        "billing_country": customer.billing_country,
        "shipping_address_line1": customer.shipping_address_line1,
        "shipping_address_line2": customer.shipping_address_line2,
        "shipping_city": customer.shipping_city,
        "shipping_state": customer.shipping_state,
        "shipping_zip": customer.shipping_zip,
        "shipping_country": customer.shipping_country,
        "created_at": customer.created_at,
        "updated_at": customer.updated_at,
        "last_login_at": customer.last_login_at,
        "order_count": stats["order_count"],
        "quote_count": stats["quote_count"],
        "total_spent": stats["total_spent"],
    }


# =============================================================================
# Code Generation
# =============================================================================

def generate_customer_number(db: Session) -> str:
    """Generate next customer number (CUST-001, CUST-002, etc.).

    Uses DB-side numeric extraction to avoid lexicographic ordering issues
    (e.g. CUST-100 sorting before CUST-099).  Regex filter ensures only
    simple ``CUST-NNN`` values are considered (excludes legacy formats
    like ``CUST-2026-000001``).
    """
    prefix = "CUST-"
    max_seq = (
        db.query(
            func.max(
                cast(func.replace(User.customer_number, prefix, ""), Integer)
            )
        )
        .filter(User.customer_number.op("~")(r"^CUST-\d+$"))
        .scalar()
        or 0
    )
    return f"CUST-{max_seq + 1:03d}"


# =============================================================================
# List & Search
# =============================================================================

def list_customers(
    db: Session,
    *,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    include_inactive: bool = False,
    skip: int = 0,
    limit: int = 50,
) -> list[dict]:
    """
    List customers with optional search and status filters.

    Returns list of dicts matching CustomerListResponse schema, each
    enriched with order_count, total_spent, and last_order_date.
    """
    query = db.query(User).filter(User.account_type == "customer")

    if status_filter:
        query = query.filter(User.status == status_filter)
    elif not include_inactive:
        query = query.filter(User.status == "active")

    if search:
        term = f"%{search}%"
        query = query.filter(
            (User.email.ilike(term))
            | (User.first_name.ilike(term))
            | (User.last_name.ilike(term))
            | (User.company_name.ilike(term))
            | (User.customer_number.ilike(term))
            | (User.phone.ilike(term))
        )

    query = query.order_by(desc(User.created_at))
    customers = query.offset(skip).limit(limit).all()

    result = []
    for customer in customers:
        order_stats = db.query(
            func.count(SalesOrder.id).label("order_count"),
            func.sum(SalesOrder.grand_total).label("total_spent"),
            func.max(SalesOrder.created_at).label("last_order"),
        ).filter(
            SalesOrder.user_id == customer.id,
            SalesOrder.status != "cancelled",
        ).first()

        result.append({
            "id": customer.id,
            "customer_number": customer.customer_number,
            "email": customer.email,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "company_name": customer.company_name,
            "phone": customer.phone,
            "status": customer.status,
            "full_name": _build_full_name(customer),
            "shipping_address_line1": customer.shipping_address_line1,
            "shipping_city": customer.shipping_city,
            "shipping_state": customer.shipping_state,
            "shipping_zip": customer.shipping_zip,
            "order_count": order_stats.order_count or 0,
            "total_spent": float(order_stats.total_spent or 0),
            "last_order_date": order_stats.last_order,
            "created_at": customer.created_at,
        })

    return result


def search_customers(
    db: Session,
    *,
    query: str,
    limit: int = 20,
) -> list[dict]:
    """
    Lightweight customer search for dropdown/autocomplete.

    Searches email, names, company, and customer number among active customers.
    """
    term = f"%{query}%"
    customers = (
        db.query(User)
        .filter(
            User.account_type == "customer",
            User.status == "active",
            (User.email.ilike(term))
            | (User.first_name.ilike(term))
            | (User.last_name.ilike(term))
            | (User.company_name.ilike(term))
            | (User.customer_number.ilike(term)),
        )
        .order_by(User.last_name, User.first_name)
        .limit(limit)
        .all()
    )

    return [
        {
            "id": c.id,
            "customer_number": c.customer_number,
            "email": c.email,
            "full_name": _build_full_name(c),
            "company_name": c.company_name,
        }
        for c in customers
    ]


# =============================================================================
# CRUD
# =============================================================================

def get_customer_detail(db: Session, customer_id: int) -> dict:
    """Get a single customer with full details and stats."""
    customer = _get_customer_or_404(db, customer_id)
    stats = _get_customer_stats(db, customer_id)
    return _customer_response(customer, stats)


def create_customer(
    db: Session,
    data: CustomerCreate,
    admin_id: int,
) -> dict:
    """
    Create a new customer (User with account_type='customer').

    Generates a customer number and random unusable password (portal login
    is a Pro feature; in open source, customers are CRM records only).
    """
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    customer_number = generate_customer_number(db)
    now = datetime.now(timezone.utc)

    customer = User(
        customer_number=customer_number,
        email=data.email,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        first_name=data.first_name,
        last_name=data.last_name,
        company_name=data.company_name,
        phone=data.phone,
        status=data.status or "active",
        account_type="customer",
        email_verified=False,
        billing_address_line1=data.billing_address_line1,
        billing_address_line2=data.billing_address_line2,
        billing_city=data.billing_city,
        billing_state=data.billing_state,
        billing_zip=data.billing_zip,
        billing_country=data.billing_country or "USA",
        shipping_address_line1=data.shipping_address_line1,
        shipping_address_line2=data.shipping_address_line2,
        shipping_city=data.shipping_city,
        shipping_state=data.shipping_state,
        shipping_zip=data.shipping_zip,
        shipping_country=data.shipping_country or "USA",
        created_by=admin_id,
        created_at=now,
        updated_at=now,
    )

    db.add(customer)
    db.commit()
    db.refresh(customer)

    return _customer_response(customer, {
        "order_count": 0,
        "quote_count": 0,
        "total_spent": 0.0,
    })


def update_customer(
    db: Session,
    customer_id: int,
    data: CustomerUpdate,
    admin_id: int,
) -> dict:
    """
    Partial-update a customer.

    Only fields present in the request body are changed.
    """
    customer = _get_customer_or_404(db, customer_id)

    # Check for duplicate email if changing
    if data.email and data.email != customer.email:
        existing = db.query(User).filter(User.email == data.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")

    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        if value is not None:
            setattr(customer, field, value)

    customer.updated_by = admin_id
    db.commit()
    db.refresh(customer)

    stats = _get_customer_stats(db, customer_id)
    return _customer_response(customer, stats)


def delete_customer(db: Session, customer_id: int, admin_id: int) -> dict:
    """
    Delete a customer — soft-delete (deactivate) if orders exist, hard-delete otherwise.

    Returns a dict with the action taken and the customer number.
    """
    customer = _get_customer_or_404(db, customer_id)

    order_count = db.query(func.count(SalesOrder.id)).filter(
        SalesOrder.user_id == customer_id,
    ).scalar() or 0

    customer_number = customer.customer_number

    if order_count > 0:
        customer.status = "inactive"
        db.commit()
        logger.info(
            "Customer deactivated",
            extra={
                "customer_number": customer_number,
                "customer_id": customer_id,
                "admin_id": admin_id,
                "order_count": order_count,
            },
        )
        return {
            "action": "deactivated",
            "customer_number": customer_number,
            "order_count": order_count,
        }

    db.delete(customer)
    db.commit()
    logger.info(
        "Customer deleted",
        extra={
            "customer_number": customer_number,
            "customer_id": customer_id,
            "admin_id": admin_id,
        },
    )
    return {
        "action": "deleted",
        "customer_number": customer_number,
        "order_count": 0,
    }


# =============================================================================
# Customer Orders
# =============================================================================

def get_customer_orders(
    db: Session,
    customer_id: int,
    limit: int = 20,
) -> list[dict]:
    """Get recent orders for a customer, most recent first."""
    _get_customer_or_404(db, customer_id)

    orders = (
        db.query(SalesOrder)
        .filter(SalesOrder.user_id == customer_id)
        .order_by(desc(SalesOrder.created_at))
        .limit(limit)
        .all()
    )

    return [
        {
            "id": o.id,
            "order_number": o.order_number,
            "status": o.status,
            "grand_total": float(o.grand_total or 0),
            "payment_status": o.payment_status,
            "created_at": o.created_at,
        }
        for o in orders
    ]


# =============================================================================
# CSV Import Helpers
# =============================================================================

# Column mapping for common e-commerce platforms.
# Maps various column names to our standard field names.
COLUMN_MAPPINGS = {
    # Email variations
    "email": "email",
    "e-mail": "email",
    "email_address": "email",
    "billing_email": "email",
    "billing email": "email",
    "customer_email": "email",
    "buyer_email": "email",
    "buyer email": "email",
    "customer email": "email",

    # First name variations
    "first_name": "first_name",
    "firstname": "first_name",
    "first name": "first_name",
    "billing_first_name": "first_name",
    "billing first name": "first_name",
    "contact_first_name": "first_name",
    "ship_name": "first_name",
    "shipping name": "first_name",
    "shipping_name": "first_name",
    "billing name": "first_name",
    "billing_name": "first_name",
    "buyer_name": "first_name",
    "buyer name": "first_name",
    "customer_name": "first_name",
    "customer name": "first_name",

    # Last name variations
    "last_name": "last_name",
    "lastname": "last_name",
    "last name": "last_name",
    "billing_last_name": "last_name",
    "billing last name": "last_name",
    "contact_last_name": "last_name",
    "Last Name": "last_name",
    "LastName": "last_name",

    # Company variations
    "company_name": "company_name",
    "company": "company_name",
    "billing_company": "company_name",
    "billing company": "company_name",

    # Phone variations
    "phone": "phone",
    "telephone": "phone",
    "phone_number": "phone",
    "billing_phone": "phone",
    "billing phone": "phone",

    # Billing address line 1
    "billing_address_line1": "billing_address_line1",
    "billing_address_1": "billing_address_line1",
    "billing address 1": "billing_address_line1",
    "billing_address1": "billing_address_line1",
    "billingaddress1": "billing_address_line1",
    "address1": "billing_address_line1",
    "address_1": "billing_address_line1",
    "address 1": "billing_address_line1",
    "street_address": "billing_address_line1",
    "street": "billing_address_line1",

    # Billing address line 2
    "billing_address_line2": "billing_address_line2",
    "billing_address_2": "billing_address_line2",
    "billing address 2": "billing_address_line2",
    "billing_address2": "billing_address_line2",
    "billingaddress2": "billing_address_line2",
    "address2": "billing_address_line2",
    "address_2": "billing_address_line2",
    "address 2": "billing_address_line2",

    # Billing city
    "billing_city": "billing_city",
    "billing city": "billing_city",
    "city": "billing_city",
    "City": "billing_city",

    # Billing state/province
    "billing_state": "billing_state",
    "billing state": "billing_state",
    "billing_province": "billing_state",
    "billing province": "billing_state",
    "province": "billing_state",
    "state": "billing_state",
    "province_code": "billing_state",
    "Province": "billing_state",
    "Province Code": "billing_state",
    "ProvinceCode": "billing_state",

    # Billing zip/postal
    "billing_zip": "billing_zip",
    "billing zip": "billing_zip",
    "billing_postcode": "billing_zip",
    "billing postcode": "billing_zip",
    "billing_postal_code": "billing_zip",
    "zip": "billing_zip",
    "postcode": "billing_zip",
    "postal_code": "billing_zip",
    "Zip": "billing_zip",
    "Postal Code": "billing_zip",
    "PostalCode": "billing_zip",

    # Billing country
    "billing_country": "billing_country",
    "billing country": "billing_country",
    "country": "billing_country",
    "country_code": "billing_country",
    "Country": "billing_country",
    "Country Code": "billing_country",
    "CountryCode": "billing_country",

    # Shipping address line 1
    "shipping_address_line1": "shipping_address_line1",
    "shipping_address_1": "shipping_address_line1",
    "shipping address 1": "shipping_address_line1",
    "shipping_address1": "shipping_address_line1",
    "shippingaddress1": "shipping_address_line1",
    "ship_address1": "shipping_address_line1",
    "ship address1": "shipping_address_line1",
    "shipping address": "shipping_address_line1",
    "shipping_address": "shipping_address_line1",
    "ship_to_address": "shipping_address_line1",
    "ship to address": "shipping_address_line1",

    # Shipping address line 2
    "shipping_address_line2": "shipping_address_line2",
    "shipping_address_2": "shipping_address_line2",
    "shipping address 2": "shipping_address_line2",
    "shipping_address2": "shipping_address_line2",
    "shippingaddress2": "shipping_address_line2",
    "ship_address2": "shipping_address_line2",

    # Shipping city
    "shipping_city": "shipping_city",
    "shipping city": "shipping_city",
    "ship_city": "shipping_city",
    "ship_to_city": "shipping_city",
    "ship to city": "shipping_city",

    # Shipping state/province
    "shipping_state": "shipping_state",
    "shipping state": "shipping_state",
    "shipping_province": "shipping_state",
    "shipping province": "shipping_state",
    "ship_state": "shipping_state",
    "ship_to_state": "shipping_state",
    "ship to state": "shipping_state",
    "ship_to_province": "shipping_state",
    "ship to province": "shipping_state",

    # Shipping zip/postal
    "shipping_zip": "shipping_zip",
    "shipping zip": "shipping_zip",
    "shipping_postcode": "shipping_zip",
    "shipping postcode": "shipping_zip",
    "ship_zip": "shipping_zip",
    "ship_zipcode": "shipping_zip",
    "ship_to_zip": "shipping_zip",
    "ship to zip": "shipping_zip",
    "ship_to_postcode": "shipping_zip",
    "ship to postcode": "shipping_zip",

    # Shipping country
    "shipping_country": "shipping_country",
    "shipping country": "shipping_country",
    "ship_country": "shipping_country",
    "ship_to_country": "shipping_country",
    "ship to country": "shipping_country",
}

# All recognized standard field names for CSV row mapping.
_STANDARD_FIELDS = {
    "email", "first_name", "last_name", "company_name", "phone",
    "billing_address_line1", "billing_address_line2",
    "billing_city", "billing_state", "billing_zip", "billing_country",
    "shipping_address_line1", "shipping_address_line2",
    "shipping_city", "shipping_state", "shipping_zip", "shipping_country",
}

# Column names that represent a combined full name.
_COMBINED_NAME_COLUMNS = {
    "name", "full_name", "fullname", "buyer_name", "buyer name",
    "customer_name", "customer name", "contact_name", "contact name",
}


def normalize_column_name(col: str) -> str:
    """Normalize a column name to our standard field name."""
    normalized = col.strip().lower().replace(" ", "_").replace("-", "_")
    return COLUMN_MAPPINGS.get(normalized, normalized)


def map_row_to_fields(row: dict) -> dict:
    """Map a CSV row with various column names to our standard fields."""
    result = {
        "email": "",
        "first_name": "",
        "last_name": "",
        "company_name": "",
        "phone": "",
        "billing_address_line1": "",
        "billing_address_line2": "",
        "billing_city": "",
        "billing_state": "",
        "billing_zip": "",
        "billing_country": "USA",
        "shipping_address_line1": "",
        "shipping_address_line2": "",
        "shipping_city": "",
        "shipping_state": "",
        "shipping_zip": "",
        "shipping_country": "USA",
    }

    for original_col, value in row.items():
        if not value:
            continue
        value = value.strip()
        if not value:
            continue

        field_name = normalize_column_name(original_col)

        # Only set if it's a recognized field and not already populated
        if field_name in _STANDARD_FIELDS:
            if not result[field_name] or result[field_name] == "USA":
                result[field_name] = value

    # Handle combined name fields (e.g. Etsy "Buyer Name", "Ship Name")
    if not result["first_name"] and not result["last_name"]:
        for col, value in row.items():
            col_lower = col.strip().lower()
            if col_lower in _COMBINED_NAME_COLUMNS and value and value.strip():
                parts = value.strip().split(" ", 1)
                result["first_name"] = parts[0]
                if len(parts) > 1:
                    result["last_name"] = parts[1]
                break

    # Copy billing to shipping if shipping is empty
    if not result["shipping_address_line1"] and result["billing_address_line1"]:
        result["shipping_address_line1"] = result["billing_address_line1"]
        result["shipping_address_line2"] = result["billing_address_line2"]
        result["shipping_city"] = result["billing_city"]
        result["shipping_state"] = result["billing_state"]
        result["shipping_zip"] = result["billing_zip"]
        result["shipping_country"] = result["billing_country"] or "USA"

    # Default countries
    if not result["billing_country"]:
        result["billing_country"] = "USA"
    if not result["shipping_country"]:
        result["shipping_country"] = "USA"

    return result


def _detect_csv_format(headers: list[str]) -> str:
    """Detect the source platform from CSV column headers."""
    headers_lower = [h.lower().strip() for h in headers]

    if any("billing" in h and "first" in h for h in headers_lower):
        return "WooCommerce"
    if (
        any(h in ("first name", "last name") for h in headers_lower)
        and "company" in headers_lower
    ):
        return "Shopify"
    if any("ship_" in h or ("buyer" in h and "name" in h) for h in headers_lower):
        return "Etsy/TikTok Shop"
    if any("unit_price" in h or "cost_price" in h for h in headers_lower):
        return "TikTok Shop"
    if "email" in headers_lower:
        return "Generic/Squarespace"
    return "Unknown"


# =============================================================================
# CSV Import Operations
# =============================================================================

def preview_customer_import(db: Session, text: str) -> dict:
    """
    Parse CSV text and validate rows against the database.

    Returns a preview dict with total/valid/error counts, detected format,
    and the first 100 rows with per-row errors.
    """
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    detected_format = _detect_csv_format(headers)

    existing_emails = set(
        e[0].lower() for e in db.query(User.email).all()
    )
    seen_emails: set[str] = set()

    rows = []
    for i, raw_row in enumerate(reader, start=2):  # Header is row 1
        row_errors = []
        mapped_data = map_row_to_fields(raw_row)

        email = mapped_data.get("email", "").lower().strip()
        if not email:
            row_errors.append("Email is required")
        elif "@" not in email:
            row_errors.append("Invalid email format")
        elif email in existing_emails:
            row_errors.append("Email already exists in database")
        elif email in seen_emails:
            row_errors.append("Duplicate email in CSV")
        else:
            seen_emails.add(email)

        mapped_data["email"] = email

        rows.append({
            "row_number": i,
            "data": mapped_data,
            "errors": row_errors,
            "valid": len(row_errors) == 0,
        })

    valid_count = sum(1 for r in rows if r["valid"])

    return {
        "total_rows": len(rows),
        "valid_rows": valid_count,
        "error_rows": len(rows) - valid_count,
        "detected_format": detected_format,
        "rows": rows[:100],
        "truncated": len(rows) > 100,
    }


def import_customers(db: Session, text: str, admin_id: int) -> dict:
    """
    Import customers from decoded CSV text.

    Skips rows with invalid/duplicate emails. Returns counts of imported
    vs skipped and the first 20 error details.
    """
    reader = csv.DictReader(io.StringIO(text))

    existing_emails = set(
        e[0].lower() for e in db.query(User.email).all()
    )

    imported = 0
    skipped = 0
    errors = []

    for i, raw_row in enumerate(reader, start=2):
        mapped_data = map_row_to_fields(raw_row)
        email = mapped_data.get("email", "").lower().strip()

        if not email or "@" not in email:
            skipped += 1
            errors.append({"row": i, "reason": "Invalid or missing email"})
            continue

        if email in existing_emails:
            skipped += 1
            errors.append({"row": i, "reason": f"Email {email} already exists"})
            continue

        customer_number = generate_customer_number(db)
        now = datetime.now(timezone.utc)

        customer = User(
            customer_number=customer_number,
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            first_name=mapped_data.get("first_name", "") or None,
            last_name=mapped_data.get("last_name", "") or None,
            company_name=mapped_data.get("company_name", "") or None,
            phone=mapped_data.get("phone", "") or None,
            status="active",
            account_type="customer",
            email_verified=False,
            billing_address_line1=mapped_data.get("billing_address_line1", "") or None,
            billing_address_line2=mapped_data.get("billing_address_line2", "") or None,
            billing_city=mapped_data.get("billing_city", "") or None,
            billing_state=mapped_data.get("billing_state", "") or None,
            billing_zip=mapped_data.get("billing_zip", "") or None,
            billing_country=mapped_data.get("billing_country", "") or "USA",
            shipping_address_line1=mapped_data.get("shipping_address_line1", "") or None,
            shipping_address_line2=mapped_data.get("shipping_address_line2", "") or None,
            shipping_city=mapped_data.get("shipping_city", "") or None,
            shipping_state=mapped_data.get("shipping_state", "") or None,
            shipping_zip=mapped_data.get("shipping_zip", "") or None,
            shipping_country=mapped_data.get("shipping_country", "") or "USA",
            created_by=admin_id,
            created_at=now,
            updated_at=now,
        )

        try:
            savepoint = db.begin_nested()
            db.add(customer)
            db.flush()
            existing_emails.add(email)
            imported += 1
        except Exception as e:
            savepoint.rollback()
            skipped += 1
            errors.append({"row": i, "reason": f"Database error: {str(e)}", "email": email})
            continue

    db.commit()

    logger.info(
        "Customer CSV import completed",
        extra={
            "admin_id": admin_id,
            "imported": imported,
            "skipped": skipped,
        },
    )

    message = f"Successfully imported {imported} customers"
    if skipped:
        message += f", skipped {skipped} rows with errors"

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors[:20],
        "message": message,
    }
