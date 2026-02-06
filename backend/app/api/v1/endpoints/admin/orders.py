"""
Admin Orders Management - CSV Import

Business logic lives in ``app.services.order_import_service``.
"""
import io
from typing import List
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.models.user import User
from app.api.v1.deps import get_current_staff_user
from app.services import order_import_service as svc
from app.api.v1.endpoints.admin.data_import import _read_csv_upload

router = APIRouter(prefix="/orders", tags=["Admin Orders"])


# ============================================================================
# SCHEMAS
# ============================================================================

class OrderCSVImportResult(BaseModel):
    """Result of order CSV import"""
    total_rows: int
    created: int
    skipped: int
    errors: List[dict]


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/import/template")
async def download_order_import_template():
    """Download CSV template for order import.

    Template format supports single-line orders (one product per order) or
    multi-line orders (multiple products per order using Order ID grouping).
    """
    template = """Order ID,Order Date,Order Status,Payment Status,Customer Email,Customer Name,Product SKU,Quantity,Unit Price,Shipping Cost,Tax Amount,Shipping Address Line 1,Shipping City,Shipping State,Shipping Zip,Shipping Country,Customer Notes
ORD-001,2025-01-15,pending,paid,customer@example.com,John Doe,PROD-001,2,19.99,5.00,2.00,123 Main St,New York,NY,10001,USA,Please handle with care
ORD-002,2025-01-16,processing,paid,jane@example.com,Jane Smith,PROD-002,1,29.99,7.50,2.25,456 Oak Ave,Los Angeles,CA,90001,USA,"""

    return StreamingResponse(
        io.BytesIO(template.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=order_import_template.csv"},
    )


@router.post("/import", response_model=OrderCSVImportResult)
async def import_orders_csv(
    file: UploadFile = File(...),
    create_customers: bool = Query(True, description="Create customers if they don't exist"),
    source: str = Query("manual", description="Order source: manual, squarespace, shopify, woocommerce, etsy, tiktok"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """Import orders from CSV file.

    Supports single-line orders (one product per row) or multi-line orders
    (multiple products per order, grouped by Order ID).
    """
    text = await _read_csv_upload(file)

    result = svc.import_orders_from_csv(
        db,
        text,
        create_customers=create_customers,
        source=source,
        current_user_id=current_user.id,
    )
    return OrderCSVImportResult(**result)
