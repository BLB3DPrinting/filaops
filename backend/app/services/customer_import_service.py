"""
Customer Import Service — CSV parsing, column mapping, preview, and bulk import.

Extracted from customer_service.py (DEBT-1 D2-C, mechanical split — no behavior
change). Public names remain importable from ``app.services.customer_service``
via re-export for backward compatibility.
"""
import csv
import io
import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.logging_config import get_logger
from app.models.user import User

logger = get_logger(__name__)


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
    from app.services.customer_service import generate_customer_number

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
