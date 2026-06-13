"""
Customer Service — CRUD, search, stats, and CSV import for customers.

Extracted from admin/customers.py (ARCHITECT-003).
"""
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy import Integer, and_, cast, desc, func, or_
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.core.utils import escape_like
from app.logging_config import get_logger
from app.models.payment import Payment
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
    """Fetch order, quote, booked, paid, and outstanding stats for a customer."""
    return _get_customers_stats_batch(db, [customer_id]).get(
        customer_id,
        _empty_customer_stats(),
    )


def _empty_customer_stats() -> dict:
    """Return the zero-value shape used by customer stats responses."""
    return {
        "order_count": 0,
        "quote_count": 0,
        "total_spent": 0.0,
        "total_paid": 0.0,
        "outstanding_balance": 0.0,
        "last_order_date": None,
    }


def _sales_order_customer_filter(customer_id: int):
    """Match orders for a customer, preferring explicit customer_id over legacy user_id."""
    return or_(
        SalesOrder.customer_id == customer_id,
        and_(SalesOrder.customer_id.is_(None), SalesOrder.user_id == customer_id),
    )


def _quote_customer_filter(customer_id: int):
    """Match quotes for a customer, preferring explicit customer_id over legacy user_id."""
    return or_(
        Quote.customer_id == customer_id,
        and_(Quote.customer_id.is_(None), Quote.user_id == customer_id),
    )


def _sales_order_total(order: SalesOrder) -> Decimal:
    """Return the customer-facing order total, including tax, fees, and shipping."""
    if order.grand_total is not None:
        return order.grand_total
    if order.total_price is not None:
        return order.total_price
    return Decimal("0")


def _get_customers_stats_batch(db: Session, customer_ids: list[int]) -> dict[int, dict]:
    """Fetch order, quote, booked, paid, and outstanding stats for customers."""
    if not customer_ids:
        return {}

    customer_ids_set = set(customer_ids)
    stats_by_customer = {customer_id: _empty_customer_stats() for customer_id in customer_ids_set}

    orders = db.query(SalesOrder).filter(
        or_(
            SalesOrder.customer_id.in_(customer_ids_set),
            and_(
                SalesOrder.customer_id.is_(None),
                SalesOrder.user_id.in_(customer_ids_set),
            ),
        ),
        SalesOrder.status != "cancelled",
    ).all()

    paid_by_order = _completed_payment_totals_by_order(db, [order.id for order in orders])
    totals_by_customer = {
        customer_id: {
            "total_spent": Decimal("0"),
            "total_paid": Decimal("0"),
            "outstanding_balance": Decimal("0"),
        }
        for customer_id in customer_ids_set
    }

    for order in orders:
        customer_id = order.customer_id
        if customer_id not in customer_ids_set and order.customer_id is None:
            customer_id = order.user_id
        if customer_id not in customer_ids_set:
            continue

        order_total = _sales_order_total(order)
        paid = paid_by_order.get(order.id, Decimal("0"))
        stats = stats_by_customer[customer_id]
        totals = totals_by_customer[customer_id]

        stats["order_count"] += 1
        totals["total_spent"] += order_total
        totals["total_paid"] += paid
        totals["outstanding_balance"] += max(order_total - paid, Decimal("0"))
        if order.created_at and (
            stats["last_order_date"] is None or order.created_at > stats["last_order_date"]
        ):
            stats["last_order_date"] = order.created_at

    quote_customer_id = func.coalesce(Quote.customer_id, Quote.user_id)
    quote_rows = db.query(
        quote_customer_id.label("customer_id"),
        func.count(Quote.id).label("quote_count"),
    ).filter(
        or_(
            Quote.customer_id.in_(customer_ids_set),
            and_(
                Quote.customer_id.is_(None),
                Quote.user_id.in_(customer_ids_set),
            ),
        ),
    ).group_by(quote_customer_id).all()

    for row in quote_rows:
        if row.customer_id in stats_by_customer:
            stats_by_customer[row.customer_id]["quote_count"] = row.quote_count

    for customer_id, totals in totals_by_customer.items():
        stats = stats_by_customer[customer_id]
        stats["total_spent"] = float(totals["total_spent"])
        stats["total_paid"] = float(totals["total_paid"])
        stats["outstanding_balance"] = float(totals["outstanding_balance"])

    return stats_by_customer


def _completed_payment_totals_by_order(db: Session, order_ids: list[int]) -> dict[int, Decimal]:
    """Return net completed payment totals keyed by sales order id."""
    if not order_ids:
        return {}

    rows = db.query(
        Payment.sales_order_id,
        func.coalesce(func.sum(Payment.amount), 0).label("paid"),
    ).filter(
        Payment.sales_order_id.in_(order_ids),
        Payment.status == "completed",
    ).group_by(Payment.sales_order_id).all()

    return {row.sales_order_id: row.paid for row in rows}


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


def get_customer_discount_percent(db: Session, customer_id: int) -> Optional[Decimal]:
    """Look up a customer's price level discount percentage.

    Price levels are managed by the PRO plugin. If PRO is not installed
    (tables don't exist), returns None for graceful degradation.

    Uses a savepoint so that a failed query (e.g. missing PRO tables)
    does not poison the outer transaction.

    Returns Decimal for safe arithmetic in order/invoice calculations.
    """
    try:
        nested = db.begin_nested()
        try:
            result = db.execute(
                sa.text("""
                    SELECT pl.discount_percent
                    FROM pro_customer_price_levels cpl
                    JOIN price_levels pl ON pl.id = cpl.price_level_id
                    WHERE cpl.customer_id = :customer_id
                    LIMIT 1
                """),
                {"customer_id": customer_id},
            ).fetchone()
            nested.commit()
            if result:
                return Decimal(str(result[0]))
        except Exception:
            nested.rollback()
    except Exception:
        pass
    return None


def _customer_response(customer: User, stats: dict, db: Optional[Session] = None) -> dict:
    """Build a full CustomerResponse dict from a User instance and stats."""
    discount_percent = None
    if db is not None:
        discount_percent = get_customer_discount_percent(db, customer.id)

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
        "payment_terms": customer.payment_terms or "cod",
        "credit_limit": float(customer.credit_limit) if customer.credit_limit is not None else None,
        "approved_for_terms": customer.approved_for_terms or False,
        "approved_for_terms_at": customer.approved_for_terms_at,
        "approved_for_terms_by": customer.approved_for_terms_by,
        "created_at": customer.created_at,
        "updated_at": customer.updated_at,
        "last_login_at": customer.last_login_at,
        "order_count": stats["order_count"],
        "quote_count": stats["quote_count"],
        "total_spent": stats["total_spent"],
        "total_paid": stats["total_paid"],
        "outstanding_balance": stats["outstanding_balance"],
        "last_order_date": stats.get("last_order_date"),
        "discount_percent": discount_percent,
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
    Return a list of customer records optionally filtered by search terms and status.
    
    Each item is a dict containing customer fields (id, customer_number, email, first_name, last_name, company_name, phone, status, full_name, shipping address fields, created_at) and aggregated order statistics (`order_count`, `total_spent`, `last_order_date`).
    
    Parameters:
        search (Optional[str]): Case-insensitive search term matched against email, first_name, last_name, company_name, customer_number, and phone. Wildcards and special characters are safely escaped before matching.
        status_filter (Optional[str]): If provided, only customers with this status are returned; otherwise only active customers are returned unless `include_inactive` is True.
        include_inactive (bool): When True, do not restrict results to active customers if `status_filter` is not set.
        skip (int): Number of records to skip (offset).
        limit (int): Maximum number of records to return.
    
    Returns:
        list[dict]: Customer dictionaries augmented with `order_count` (int), `total_spent` (float), and `last_order_date` (datetime or None).
    """
    query = db.query(User).filter(User.account_type == "customer")

    if status_filter:
        query = query.filter(User.status == status_filter)
    elif not include_inactive:
        query = query.filter(User.status == "active")

    if search:
        term = f"%{escape_like(search)}%"
        query = query.filter(
            (User.email.ilike(term, escape="\\"))
            | (User.first_name.ilike(term, escape="\\"))
            | (User.last_name.ilike(term, escape="\\"))
            | (User.company_name.ilike(term, escape="\\"))
            | (User.customer_number.ilike(term, escape="\\"))
            | (User.phone.ilike(term, escape="\\"))
        )

    query = query.order_by(desc(User.created_at))
    customers = query.offset(skip).limit(limit).all()
    stats_by_customer = _get_customers_stats_batch(
        db,
        [customer.id for customer in customers],
    )

    result = []
    for customer in customers:
        stats = stats_by_customer.get(customer.id, _empty_customer_stats())

        result.append({
            "id": customer.id,
            "customer_number": customer.customer_number,
            "email": customer.email,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "company_name": customer.company_name,
            "phone": customer.phone,
            "status": customer.status,
            "payment_terms": customer.payment_terms or "cod",
            "full_name": _build_full_name(customer),
            "shipping_address_line1": customer.shipping_address_line1,
            "shipping_city": customer.shipping_city,
            "shipping_state": customer.shipping_state,
            "shipping_zip": customer.shipping_zip,
            "order_count": stats["order_count"],
            "total_spent": stats["total_spent"],
            "total_paid": stats["total_paid"],
            "outstanding_balance": stats["outstanding_balance"],
            "last_order_date": stats["last_order_date"],
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
    Finds active customers matching the query for use in dropdowns or autocomplete.
    
    Matches the query case-insensitively against email, first name, last name, company name, and customer number.
    
    Returns:
        A list of dictionaries for matching customers. Each dictionary contains:
            id (int): Customer database ID.
            customer_number (str|None): Assigned customer number, if present.
            email (str): Customer email address.
            full_name (str|None): Combined first and last name when available.
            company_name (str|None): Customer's company name when available.
    """
    term = f"%{escape_like(query)}%"
    customers = (
        db.query(User)
        .filter(
            User.account_type == "customer",
            User.status == "active",
            (User.email.ilike(term, escape="\\"))
            | (User.first_name.ilike(term, escape="\\"))
            | (User.last_name.ilike(term, escape="\\"))
            | (User.company_name.ilike(term, escape="\\"))
            | (User.customer_number.ilike(term, escape="\\")),
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
    return _customer_response(customer, stats, db=db)


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
        payment_terms=data.payment_terms or "cod",
        credit_limit=data.credit_limit,
        approved_for_terms=data.approved_for_terms or False,
        approved_for_terms_at=now if data.approved_for_terms else None,
        approved_for_terms_by=admin_id if data.approved_for_terms else None,
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
        "total_paid": 0.0,
        "outstanding_balance": 0.0,
        "last_order_date": None,
    }, db=db)


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

    # Fields that can be explicitly set to NULL via PATCH
    clearable_fields = {"credit_limit", "approved_for_terms"}
    # Audit fields managed by server logic, never set directly from client
    audit_fields = {"approved_for_terms_at", "approved_for_terms_by"}

    update_fields = data.model_dump(exclude_unset=True)

    # Capture prior approval state before setattr overwrites it
    was_approved = customer.approved_for_terms

    for field, value in update_fields.items():
        if field in audit_fields:
            continue
        if value is not None or field in clearable_fields:
            setattr(customer, field, value)

    # Handle terms approval tracking — only on actual transition
    if "approved_for_terms" in update_fields:
        new_val = update_fields["approved_for_terms"]
        if new_val and not was_approved:
            # Transition: unapproved → approved
            customer.approved_for_terms_at = datetime.now(timezone.utc)
            customer.approved_for_terms_by = admin_id
        elif not new_val and was_approved:
            # Transition: approved → revoked
            customer.approved_for_terms_at = None
            customer.approved_for_terms_by = None

    customer.updated_by = admin_id
    db.commit()
    db.refresh(customer)

    stats = _get_customer_stats(db, customer_id)
    return _customer_response(customer, stats, db=db)


def delete_customer(db: Session, customer_id: int, admin_id: int) -> dict:
    """
    Delete a customer — soft-delete (deactivate) if orders exist, hard-delete otherwise.

    Returns a dict with the action taken and the customer number.
    """
    customer = _get_customer_or_404(db, customer_id)

    order_count = db.query(func.count(SalesOrder.id)).filter(
        _sales_order_customer_filter(customer_id),
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
        .filter(_sales_order_customer_filter(customer_id))
        .order_by(desc(SalesOrder.created_at))
        .limit(limit)
        .all()
    )
    paid_by_order = _completed_payment_totals_by_order(db, [order.id for order in orders])

    result = []
    for order in orders:
        order_total = _sales_order_total(order)
        amount_paid = paid_by_order.get(order.id, Decimal("0"))
        result.append({
            "id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "grand_total": float(order_total),
            "amount_paid": float(amount_paid),
            "balance_due": float(max(order_total - amount_paid, Decimal("0"))),
            "payment_status": order.payment_status,
            "created_at": order.created_at,
        })
    return result


# =============================================================================
# Backward-compatibility re-exports (DEBT-1 D2-C)
# =============================================================================
# CSV parsing and bulk-import logic moved to customer_import_service.py.
# Re-exported here so existing imports and ``customer_service.X`` attribute
# access keep working unchanged (e.g. the admin/customers endpoint and tests).
from app.services.customer_import_service import (  # noqa: E402,F401
    COLUMN_MAPPINGS,
    _detect_csv_format,
    import_customers,
    map_row_to_fields,
    normalize_column_name,
    preview_customer_import,
)

__all__ = [
    # Code generation
    "generate_customer_number",
    # List & search
    "list_customers",
    "search_customers",
    # CRUD
    "get_customer_detail",
    "create_customer",
    "update_customer",
    "delete_customer",
    # Customer orders
    "get_customer_orders",
    # Pricing
    "get_customer_discount_percent",
    # CSV import (re-exported from customer_import_service)
    "COLUMN_MAPPINGS",
    "normalize_column_name",
    "map_row_to_fields",
    "_detect_csv_format",
    "preview_customer_import",
    "import_customers",
]
