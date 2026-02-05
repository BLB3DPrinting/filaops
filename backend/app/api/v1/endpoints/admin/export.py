"""
Export functionality for products, orders, inventory

Business logic lives in ``app.services.export_service``.
"""
import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.v1.deps import get_current_staff_user
from app.models.user import User
from app.services import export_service as svc

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/products")
async def export_products(
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Export products to CSV."""
    rows = svc.get_products_for_export(db)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "SKU", "Name", "Description", "Item Type", "Procurement Type",
        "Unit", "Standard Cost", "Selling Price", "On Hand Qty",
        "Reorder Point", "Active",
    ])
    for r in rows:
        writer.writerow([
            r["sku"], r["name"], r["description"], r["item_type"],
            r["procurement_type"], r["unit"], r["standard_cost"],
            r["selling_price"], r["on_hand_qty"], r["reorder_point"],
            r["active"],
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=products_export_{datetime.now().strftime('%Y%m%d')}.csv"
        },
    )


@router.get("/orders")
async def export_orders(
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Export sales orders to CSV."""
    rows = svc.get_orders_for_export(db, start_date=start_date, end_date=end_date)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Order Number", "Customer", "Status", "Total", "Created Date", "Line Items",
    ])
    for r in rows:
        writer.writerow([
            r["order_number"], r["customer"], r["status"],
            r["total"], r["created_at"], r["line_items"],
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=orders_export_{datetime.now().strftime('%Y%m%d')}.csv"
        },
    )
