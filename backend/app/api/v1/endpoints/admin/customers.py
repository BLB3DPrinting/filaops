"""
Customer Management Endpoints (Admin Only)

Handles customer CRUD operations for admin users.
Customers are users with account_type='customer'.
Business logic lives in ``app.services.customer_service``.

Note: Customer portal login is a Pro feature. In open source, customers
are CRM records for order management. They cannot log in to a portal.
"""
from typing import List, Optional
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.api.v1.endpoints.auth import get_current_admin_user
from app.logging_config import get_logger
from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerListResponse,
    CustomerResponse,
    CustomerSearchResult,
)
from app.services import customer_service as svc

router = APIRouter(prefix="/customers", tags=["Admin - Customer Management"])

logger = get_logger(__name__)


# ============================================================================
# LIST & SEARCH ENDPOINTS
# ============================================================================

@router.get("/", response_model=List[CustomerListResponse])
async def list_customers(
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    include_inactive: bool = False,
):
    """
    List all customers with optional filters.

    Admin only. Returns customers (users with account_type='customer').
    """
    return svc.list_customers(
        db,
        search=search,
        status_filter=status_filter,
        include_inactive=include_inactive,
        skip=skip,
        limit=limit,
    )


@router.get("/search", response_model=List[CustomerSearchResult])
async def search_customers(
    q: str = Query(..., min_length=1, description="Search term"),
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=50),
):
    """
    Quick search for customer dropdown/autocomplete.

    Returns lightweight results for fast UI.
    """
    return svc.search_customers(db, query=q, limit=limit)


# ============================================================================
# GET & CREATE ENDPOINTS
# ============================================================================

@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Get a single customer with full details.

    Admin only.
    """
    return svc.get_customer_detail(db, customer_id)


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    request: CustomerCreate,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Create a new customer.

    Admin only. Creates user with account_type='customer'.
    """
    result = svc.create_customer(db, request, current_admin.id)

    logger.info(
        "Customer created",
        extra={
            "customer_number": result["customer_number"],
            "customer_id": result["id"],
            "admin_id": current_admin.id,
        }
    )

    return result


# ============================================================================
# UPDATE & DELETE ENDPOINTS
# ============================================================================

@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: int,
    request: CustomerUpdate,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Update a customer.

    Admin only. Partial update supported.
    """
    result = svc.update_customer(db, customer_id, request, current_admin.id)

    logger.info(
        "Customer updated",
        extra={
            "customer_number": result["customer_number"],
            "customer_id": customer_id,
            "admin_id": current_admin.id,
        }
    )

    return result


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Delete a customer (soft-deactivate if orders exist, hard-delete otherwise).

    Admin only. Customers with orders are set to 'inactive' instead of deleted.
    """
    info = svc.delete_customer(db, customer_id, current_admin.id)

    logger.info(
        f"Customer {info['action']}",
        extra={
            "customer_number": info["customer_number"],
            "customer_id": customer_id,
            "admin_id": current_admin.id,
            "admin_email": current_admin.email,
            "order_count": info["order_count"],
        }
    )

    return None


# ============================================================================
# CUSTOMER ORDERS
# ============================================================================

@router.get("/{customer_id}/orders")
async def get_customer_orders(
    customer_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Get recent orders for a customer.

    Admin only.
    """
    return svc.get_customer_orders(db, customer_id, limit=limit)


# ============================================================================
# CSV IMPORT
# ============================================================================

@router.get("/import/template")
async def download_customer_template(
    current_admin: User = Depends(get_current_admin_user),
):
    """
    Download a CSV template for customer import.
    """
    headers = [
        "email",
        "first_name",
        "last_name",
        "company_name",
        "phone",
        "billing_address_line1",
        "billing_address_line2",
        "billing_city",
        "billing_state",
        "billing_zip",
        "billing_country",
        "shipping_address_line1",
        "shipping_address_line2",
        "shipping_city",
        "shipping_state",
        "shipping_zip",
        "shipping_country",
    ]

    example = [
        "john@example.com",
        "John",
        "Smith",
        "Acme Corp",
        "555-123-4567",
        "123 Main St",
        "Suite 100",
        "Springfield",
        "IL",
        "62701",
        "USA",
        "123 Main St",
        "Suite 100",
        "Springfield",
        "IL",
        "62701",
        "USA",
    ]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerow(example)
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=customer_import_template.csv"}
    )


@router.post("/import/preview")
async def preview_customer_import(
    file: UploadFile = File(...),
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Preview CSV import - validates data and returns parsed rows with errors.

    Supports exports from:
    - Shopify (First Name, Last Name, Email, Company, Address1, etc.)
    - WooCommerce (Billing First Name, Billing Email, Billing Address 1, etc.)
    - Squarespace (contacts export)
    - Etsy (order exports with Buyer Name, Ship Address, etc.)
    - TikTok Shop (order exports with Buyer Email, Buyer Name, etc.)
    - Generic CSV with common column names
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        text = content.decode('latin-1')

    if text.startswith('\ufeff'):
        text = text[1:]

    return svc.preview_customer_import(db, text)


@router.post("/import")
async def import_customers(
    file: UploadFile = File(...),
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Import customers from CSV file.

    Supports exports from Shopify, WooCommerce, Squarespace, Etsy, TikTok Shop, and generic CSV.
    Automatically maps common column names to our standard fields.

    Skips rows with errors (duplicate emails, missing required fields).
    Returns count of imported vs skipped.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        text = content.decode('latin-1')

    if text.startswith('\ufeff'):
        text = text[1:]

    try:
        return svc.import_customers(db, text, current_admin.id)
    except Exception:
        logger.error("Customer import failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Customer import failed. Check server logs for details.")
