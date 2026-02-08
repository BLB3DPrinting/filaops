# pyright: reportArgumentType=false
# pyright: reportCallIssue=false
# pyright: reportAssignmentType=false
"""
Accounting View Endpoints

Provides endpoints for viewing inventory flow through accounting lens:
- Raw Materials (1300) → WIP (1310) → Finished Goods (1320) → COGS (5100)

Also provides:
- Financial dashboard summary
- Sales journal with CSV export
- Tax summary for filing prep
- Payment summary views

These are views into the business data, formatted for accounting purposes.
"""
from typing import Optional, Dict, Any
from decimal import Decimal
from datetime import datetime, timezone, timedelta, date
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from pydantic import BaseModel, Field
import csv
import io

from app.db.session import get_db
from app.models.inventory import Inventory, InventoryTransaction
from app.models.product import Product
from app.models.production_order import ProductionOrder
from app.models.sales_order import SalesOrder
from app.models.payment import Payment
from app.models.company_settings import CompanySettings
from app.models.user import User
from app.api.v1.deps import get_current_staff_user
from app.schemas.accounting import (
    InventoryByAccountResponse,
    TransactionsJournalResponse,
    OrderCostBreakdownResponse,
    COGSSummaryResponse,
    DashboardResponse,
    SalesJournalResponse,
    TaxSummaryResponse,
    PaymentsJournalResponse,
)


router = APIRouter(prefix="/accounting", tags=["Accounting"])


# ============================================================================
# Query Parameter Schemas
# ============================================================================

class SalesExportParams(BaseModel):
    """Query parameters for sales export endpoint."""
    start_date: date = Field(..., description="Start date for export (inclusive)")
    end_date: date = Field(..., description="End date for export (inclusive)")
    format: str = Field(default="csv", description="Export format (csv)")

    class Config:
        json_schema_extra = {
            "example": {
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
                "format": "csv"
            }
        }


# Account codes matching ACCOUNTING_ARCHITECTURE.md
ACCOUNTS = {
    "1300": "Inventory - Raw Materials",
    "1310": "Inventory - Work in Progress",
    "1320": "Inventory - Finished Goods",
    "5100": "COGS - Material Cost",
}


@router.get("/inventory-by-account", response_model=InventoryByAccountResponse)
async def get_inventory_by_account(
    db: Session = Depends(get_db),
) -> InventoryByAccountResponse:
    """
    Get inventory balances organized by accounting category.

    Maps product categories to account codes:
    - Raw Materials (1300): MAT-*, consumables
    - WIP (1310): Products currently in production
    - Finished Goods (1320): PRD-*, completed products
    """
    # Get all inventory with product info
    inventory_items = db.query(
        Inventory,
        Product
    ).join(Product).filter(
        Inventory.on_hand_quantity > 0
    ).all()

    accounts: Dict[str, Dict[str, Any]] = {
        code: {
            "account_code": code,
            "account_name": name,
            "total_value": Decimal("0"),
            "total_units": Decimal("0"),
            "items": [],
        }
        for code, name in ACCOUNTS.items()
        if code.startswith("1")  # Asset accounts only
    }

    for inv, product in inventory_items:
        # Determine account based on SKU pattern
        if product.sku.startswith("MAT-"):
            account = "1300"
        elif product.sku.startswith("PKG-"):
            account = "1300"  # Packaging is raw material
        elif product.sku.startswith("PRD-"):
            account = "1320"  # Products are finished goods
        elif product.sku.startswith("SVC-"):
            continue  # Skip services
        else:
            account = "1300"  # Default to raw materials

        # Calculate value (use product standard_cost if available)
        unit_cost = getattr(product, 'standard_cost', None) or Decimal("0")
        total_value = inv.on_hand_quantity * unit_cost

        accounts[account]["total_value"] += total_value
        accounts[account]["total_units"] += inv.on_hand_quantity
        accounts[account]["items"].append({
            "product_id": product.id,
            "sku": product.sku,
            "name": product.name,
            "on_hand": float(inv.on_hand_quantity),
            "allocated": float(inv.allocated_quantity),
            "available": float(inv.available_quantity) if inv.available_quantity else float(inv.on_hand_quantity - inv.allocated_quantity),
            "unit_cost": float(unit_cost),
            "total_value": float(total_value),
        })

    # Calculate WIP from production orders
    wip_orders = db.query(ProductionOrder).filter(
        ProductionOrder.status.in_(['in_progress', 'printed'])
    ).all()

    wip_value = Decimal("0")
    wip_items = []
    for po in wip_orders:
        # Estimate WIP value from reserved materials
        reserved = db.query(
            func.sum(func.abs(InventoryTransaction.quantity) * func.coalesce(InventoryTransaction.cost_per_unit, 0))
        ).filter(
            InventoryTransaction.reference_type == 'production_order',
            InventoryTransaction.reference_id == po.id,
            InventoryTransaction.transaction_type == 'reservation'
        ).scalar() or Decimal("0")

        wip_value += reserved
        wip_items.append({
            "production_order_id": po.id,
            "code": po.code,
            "status": po.status,
            "estimated_value": float(reserved),
        })

    accounts["1310"]["total_value"] = wip_value
    accounts["1310"]["items"] = wip_items

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "accounts": list(accounts.values()),
        "summary": {
            "raw_materials": float(accounts["1300"]["total_value"]),
            "wip": float(accounts["1310"]["total_value"]),
            "finished_goods": float(accounts["1320"]["total_value"]),
            "total_inventory": float(
                accounts["1300"]["total_value"] +
                accounts["1310"]["total_value"] +
                accounts["1320"]["total_value"]
            ),
        },
    }


@router.get("/transactions-journal", response_model=TransactionsJournalResponse)
async def get_transactions_as_journal(
    db: Session = Depends(get_db),
    days: int = Query(30, description="Number of days to look back"),
    order_id: Optional[int] = Query(None, description="Filter by sales order"),
) -> TransactionsJournalResponse:
    """
    Get inventory transactions formatted as journal entries.

    Each transaction maps to a debit/credit pair based on transaction type:
    - reservation: DR WIP (1310), CR Raw Materials (1300)
    - consumption: DR COGS (5100), CR WIP (1310)
    - receipt (finished goods): DR Finished Goods (1320), CR WIP (1310)
    - scrap: DR COGS (5100), CR WIP (1310)
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    query = db.query(InventoryTransaction).filter(
        InventoryTransaction.created_at >= cutoff
    ).order_by(InventoryTransaction.created_at.desc())

    if order_id:
        # Get production order IDs for this sales order
        po_ids = [po.id for po in db.query(ProductionOrder).filter(
            ProductionOrder.sales_order_id == order_id
        ).all()]

        query = query.filter(
            ((InventoryTransaction.reference_type == 'production_order') &
             (InventoryTransaction.reference_id.in_(po_ids))) |
            ((InventoryTransaction.reference_type.in_(['shipment', 'consolidated_shipment'])) &
             (InventoryTransaction.reference_id == order_id))
        )

    transactions = query.limit(200).all()

    # Batch fetch all products to avoid N+1 query
    product_ids = [txn.product_id for txn in transactions if txn.product_id]
    products = {}
    if product_ids:
        product_list = db.query(Product).filter(Product.id.in_(product_ids)).all()
        products = {p.id: p for p in product_list}

    journal_entries = []
    for txn in transactions:
        product = products.get(txn.product_id)
        sku = product.sku if product else "N/A"

        # Skip services from journal
        if sku.startswith("SVC-"):
            continue

        qty = abs(float(txn.quantity)) if txn.quantity else 0
        unit_cost = float(txn.cost_per_unit) if txn.cost_per_unit else 0
        value = qty * unit_cost

        # Map transaction type to journal entry
        entry = {
            "date": txn.created_at.isoformat() if txn.created_at else None,
            "transaction_id": txn.id,
            "transaction_type": txn.transaction_type,
            "reference_type": txn.reference_type,
            "reference_id": txn.reference_id,
            "product_sku": sku,
            "quantity": qty,
            "unit_cost": unit_cost,
            "value": value,
            "debit_account": None,
            "credit_account": None,
            "notes": txn.notes,
        }

        # Determine accounts based on transaction type
        if txn.transaction_type == 'reservation':
            entry["debit_account"] = {"code": "1310", "name": "WIP", "amount": value}
            entry["credit_account"] = {"code": "1300", "name": "Raw Materials", "amount": value}
        elif txn.transaction_type == 'consumption':
            if txn.reference_type in ['shipment', 'consolidated_shipment']:
                # Packaging consumption at shipping
                entry["debit_account"] = {"code": "5100", "name": "COGS", "amount": value}
                entry["credit_account"] = {"code": "1300", "name": "Raw Materials", "amount": value}
            else:
                # Material consumption at production complete
                entry["debit_account"] = {"code": "5100", "name": "COGS", "amount": value}
                entry["credit_account"] = {"code": "1310", "name": "WIP", "amount": value}
        elif txn.transaction_type == 'receipt':
            if sku.startswith("PRD-"):
                # Finished goods receipt
                entry["debit_account"] = {"code": "1320", "name": "Finished Goods", "amount": value}
                entry["credit_account"] = {"code": "1310", "name": "WIP", "amount": value}
            else:
                # Raw material receipt
                entry["debit_account"] = {"code": "1300", "name": "Raw Materials", "amount": value}
                entry["credit_account"] = {"code": "2100", "name": "Accounts Payable", "amount": value}
        elif txn.transaction_type == 'scrap':
            entry["debit_account"] = {"code": "5100", "name": "COGS (Scrap)", "amount": value}
            entry["credit_account"] = {"code": "1310", "name": "WIP", "amount": value}
        elif txn.transaction_type == 'release':
            # Reservation released (e.g., consolidated shipping)
            entry["debit_account"] = {"code": "1300", "name": "Raw Materials", "amount": value}
            entry["credit_account"] = {"code": "1310", "name": "WIP", "amount": value}

        journal_entries.append(entry)

    return {
        "period": f"Last {days} days",
        "transaction_count": len(journal_entries),
        "entries": journal_entries,
    }


@router.get("/order-cost-breakdown/{order_id}", response_model=OrderCostBreakdownResponse)
async def get_order_cost_breakdown(
    order_id: int,
    db: Session = Depends(get_db),
) -> OrderCostBreakdownResponse:
    """
    Get a cost breakdown for a specific sales order.

    Shows:
    - Material costs (consumed)
    - Labor/machine time (if tracked)
    - Packaging costs
    - Shipping costs
    - Total COGS
    - Gross margin
    """
    order = db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Get production orders
    production_orders = db.query(ProductionOrder).filter(
        ProductionOrder.sales_order_id == order_id
    ).all()

    po_ids = [po.id for po in production_orders]

    # Get all consumption and scrap transactions
    # Scrap transactions from failed WOs also count as COGS (materials consumed with no output)
    consumptions = db.query(InventoryTransaction).filter(
        InventoryTransaction.reference_type == 'production_order',
        InventoryTransaction.reference_id.in_(po_ids),
        InventoryTransaction.transaction_type.in_(['consumption', 'scrap'])
    ).all()

    # Packaging consumptions
    packaging = db.query(InventoryTransaction).filter(
        InventoryTransaction.reference_type.in_(['shipment', 'consolidated_shipment']),
        InventoryTransaction.reference_id == order_id,
        InventoryTransaction.transaction_type == 'consumption'
    ).all()

    # Calculate costs
    material_cost = Decimal("0")
    labor_cost = Decimal("0")
    packaging_cost = Decimal("0")

    material_items = []
    for txn in consumptions:
        product = db.query(Product).filter(Product.id == txn.product_id).first()
        sku = product.sku if product else "N/A"
        qty = abs(float(txn.quantity)) if txn.quantity else 0
        unit_cost = float(txn.cost_per_unit) if txn.cost_per_unit else 0
        value = Decimal(str(qty * unit_cost))

        if sku.startswith("SVC-"):
            labor_cost += value
        else:
            material_cost += value
            material_items.append({
                "sku": sku,
                "quantity": qty,
                "unit_cost": unit_cost,
                "total": float(value),
            })

    packaging_items = []
    for txn in packaging:
        product = db.query(Product).filter(Product.id == txn.product_id).first()
        sku = product.sku if product else "N/A"
        qty = abs(float(txn.quantity)) if txn.quantity else 0
        unit_cost = float(txn.cost_per_unit) if txn.cost_per_unit else 0
        value = Decimal(str(qty * unit_cost))
        packaging_cost += value
        packaging_items.append({
            "sku": sku,
            "quantity": qty,
            "unit_cost": unit_cost,
            "total": float(value),
        })

    # Shipping cost from order (not included in COGS - it's an operating expense)
    shipping_cost = order.shipping_cost or Decimal("0")

    # Total COGS (production costs only per GAAP)
    total_cogs = material_cost + labor_cost + packaging_cost

    # Revenue and margin (excluding tax per GAAP)
    revenue = (order.grand_total or order.total_price or Decimal("0")) - (order.tax_amount or Decimal("0"))
    gross_profit = revenue - total_cogs
    margin_pct = (gross_profit / revenue * 100) if revenue > 0 else Decimal("0")

    return {
        "order_id": order_id,
        "order_number": order.order_number,
        "order_status": order.status,
        "revenue": float(revenue),
        "costs": {
            "materials": {
                "total": float(material_cost),
                "items": material_items,
            },
            "labor": float(labor_cost),
            "packaging": {
                "total": float(packaging_cost),
                "items": packaging_items,
            },
        },
        "shipping_expense": float(shipping_cost),  # Operating expense, not COGS
        "total_cogs": float(total_cogs),
        "gross_profit": float(gross_profit),
        "gross_margin_pct": float(margin_pct),
        "note": "Revenue excludes tax (liability). Shipping is operating expense, not COGS. Values may be incomplete if transactions are missing.",
    }


@router.get("/cogs-summary", response_model=COGSSummaryResponse)
async def get_cogs_summary(
    db: Session = Depends(get_db),
    days: int = Query(30, description="Number of days"),
) -> COGSSummaryResponse:
    """
    Get COGS summary for recent period.

    Shows total cost of goods sold broken down by category.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Get shipped orders in period
    shipped_orders = db.query(SalesOrder).filter(
        SalesOrder.status.in_(['shipped', 'completed']),
        SalesOrder.shipped_at >= cutoff
    ).all()

    total_revenue = Decimal("0")
    total_material = Decimal("0")
    total_labor = Decimal("0")
    total_packaging = Decimal("0")
    total_shipping = Decimal("0")

    # Batch queries to avoid N+1
    shipped_order_ids = [order.id for order in shipped_orders]
    
    # Get all production orders for shipped orders
    sales_to_po_map = {}
    all_po_ids = []
    if shipped_order_ids:
        production_orders = db.query(ProductionOrder).filter(
            ProductionOrder.sales_order_id.in_(shipped_order_ids)
        ).all()
        for po in production_orders:
            if po.sales_order_id not in sales_to_po_map:
                sales_to_po_map[po.sales_order_id] = []
            sales_to_po_map[po.sales_order_id].append(po.id)
            all_po_ids.append(po.id)
    
    # Get all consumption and scrap transactions in one query
    # Scrap = materials consumed in failed WOs (remake costs roll into COGS)
    po_consumptions = {}
    if all_po_ids:
        consumptions = db.query(InventoryTransaction).options(
            joinedload(InventoryTransaction.product)
        ).filter(
            InventoryTransaction.reference_type == 'production_order',
            InventoryTransaction.reference_id.in_(all_po_ids),
            InventoryTransaction.transaction_type.in_(['consumption', 'scrap'])
        ).all()
        
        for txn in consumptions:
            if txn.reference_id not in po_consumptions:
                po_consumptions[txn.reference_id] = []
            po_consumptions[txn.reference_id].append(txn)
    
    # Get all packaging transactions in one query
    pkg_consumptions_map = {}
    if shipped_order_ids:
        pkg_consumptions = db.query(InventoryTransaction).filter(
            InventoryTransaction.reference_type.in_(['shipment', 'consolidated_shipment']),
            InventoryTransaction.reference_id.in_(shipped_order_ids),
            InventoryTransaction.transaction_type == 'consumption'
        ).all()
        
        for txn in pkg_consumptions:
            if txn.reference_id not in pkg_consumptions_map:
                pkg_consumptions_map[txn.reference_id] = []
            pkg_consumptions_map[txn.reference_id].append(txn)

    for order in shipped_orders:
        # Revenue excludes tax per GAAP
        total_revenue += (order.total_price or Decimal("0"))
        total_shipping += order.shipping_cost or Decimal("0")

        # Get costs from batched transactions
        po_ids = sales_to_po_map.get(order.id, [])
        for po_id in po_ids:
            for txn in po_consumptions.get(po_id, []):
                product = txn.product
                sku = product.sku if product else ""
                qty = abs(float(txn.quantity)) if txn.quantity else 0
                unit_cost = float(txn.cost_per_unit) if txn.cost_per_unit else 0
                value = Decimal(str(qty * unit_cost))

                if sku.startswith("SVC-"):
                    total_labor += value
                else:
                    total_material += value

        # Packaging from batched data
        for txn in pkg_consumptions_map.get(order.id, []):
            qty = abs(float(txn.quantity)) if txn.quantity else 0
            unit_cost = float(txn.cost_per_unit) if txn.cost_per_unit else 0
            total_packaging += Decimal(str(qty * unit_cost))

    # COGS = production costs only (materials, labor, packaging)
    # Shipping is an operating expense, not COGS
    total_cogs = total_material + total_labor + total_packaging
    gross_profit = total_revenue - total_cogs
    margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else Decimal("0")

    return {
        "period": f"Last {days} days",
        "orders_shipped": len(shipped_orders),
        "revenue": float(total_revenue),
        "cogs": {
            "materials": float(total_material),
            "labor": float(total_labor),
            "packaging": float(total_packaging),
            "total": float(total_cogs),
        },
        "shipping_expense": float(total_shipping),  # Separate operating expense
        "gross_profit": float(gross_profit),
        "gross_margin_pct": float(margin),
    }


# ==============================================================================
# Financial Dashboard
# ==============================================================================

@router.get("/dashboard", response_model=DashboardResponse)
async def get_accounting_dashboard(
    db: Session = Depends(get_db),
) -> DashboardResponse:
    """
    Get accounting dashboard with key financial metrics.

    Returns:
    - Revenue summary (MTD, YTD)
    - Payment summary (received, outstanding)
    - Tax collected summary
    - COGS summary
    - Gross profit margins
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)

    # Get company settings for fiscal year
    settings = db.query(CompanySettings).first()
    fiscal_month = (settings.fiscal_year_start_month if settings and settings.fiscal_year_start_month else 1)

    # Calculate fiscal year start
    if now.month >= fiscal_month:
        fiscal_year_start = today_start.replace(month=fiscal_month, day=1)
    else:
        fiscal_year_start = today_start.replace(year=now.year - 1, month=fiscal_month, day=1)

    # Revenue MTD (recognized at shipment per GAAP)
    mtd_orders = db.query(SalesOrder).filter(
        SalesOrder.shipped_at >= month_start,
        SalesOrder.status.in_(["shipped", "completed"])
    ).all()

    # Revenue excludes tax (tax is a liability, not revenue)
    mtd_revenue = sum(float((o.grand_total or o.total_price or 0) - (o.tax_amount or 0)) for o in mtd_orders)
    mtd_tax = sum(float(o.tax_amount or 0) for o in mtd_orders)
    mtd_orders_count = len(mtd_orders)

    # Revenue YTD
    ytd_orders = db.query(SalesOrder).filter(
        SalesOrder.shipped_at >= fiscal_year_start,
        SalesOrder.status.in_(["shipped", "completed"])
    ).all()

    # Revenue excludes tax (tax is a liability, not revenue)
    ytd_revenue = sum(float((o.grand_total or o.total_price or 0) - (o.tax_amount or 0)) for o in ytd_orders)
    ytd_tax = sum(float(o.tax_amount or 0) for o in ytd_orders)
    ytd_orders_count = len(ytd_orders)

    # Payments received MTD
    mtd_payments = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.payment_date >= month_start,
        Payment.status == "completed",
        Payment.payment_type == "payment"
    ).scalar() or Decimal("0")

    # Payments received YTD
    ytd_payments = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.payment_date >= fiscal_year_start,
        Payment.status == "completed",
        Payment.payment_type == "payment"
    ).scalar() or Decimal("0")

    # Outstanding payments
    # Batch query to avoid N+1: fetch all payment sums for outstanding orders in one query
    outstanding_orders = db.query(SalesOrder).filter(
        SalesOrder.payment_status.in_(["pending", "partial"]),
        SalesOrder.status.notin_(["cancelled"])
    ).all()

    # Fetch all payment sums in one query
    order_ids = [order.id for order in outstanding_orders]
    payment_sums = {}
    if order_ids:
        payments_result = db.query(
            Payment.sales_order_id,
            func.coalesce(func.sum(Payment.amount), 0).label('paid')
        ).filter(
            Payment.sales_order_id.in_(order_ids),
            Payment.status == "completed"
        ).group_by(Payment.sales_order_id).all()
        payment_sums = {row.sales_order_id: row.paid for row in payments_result}

    total_outstanding = Decimal("0")
    for order in outstanding_orders:
        order_total = order.grand_total or order.total_price or Decimal("0")
        paid = payment_sums.get(order.id, Decimal("0"))
        total_outstanding += max(order_total - paid, Decimal("0"))

    # COGS this month (from shipped orders)
    shipped_mtd = db.query(SalesOrder).filter(
        SalesOrder.shipped_at >= month_start,
        SalesOrder.status.in_(["shipped", "completed"])
    ).all()

    mtd_cogs = Decimal("0")
    
    # Batch queries to avoid N+1
    shipped_order_ids = [order.id for order in shipped_mtd]
    
    # Build mapping of sales_order_id -> list of production_order_ids
    sales_to_po_map = {}
    all_po_ids = []
    if shipped_order_ids:
        production_orders = db.query(ProductionOrder).filter(
            ProductionOrder.sales_order_id.in_(shipped_order_ids)
        ).all()
        
        for po in production_orders:
            if po.sales_order_id not in sales_to_po_map:
                sales_to_po_map[po.sales_order_id] = []
            sales_to_po_map[po.sales_order_id].append(po.id)
            all_po_ids.append(po.id)
    
    # Query all material costs in one batch (including scrap from failed WOs)
    po_material_costs = {}
    if all_po_ids:
        material_costs_result = db.query(
            InventoryTransaction.reference_id,
            func.coalesce(
                func.sum(func.abs(InventoryTransaction.quantity) * func.coalesce(InventoryTransaction.cost_per_unit, 0)),
                0
            ).label('material_cost')
        ).filter(
            InventoryTransaction.reference_type == 'production_order',
            InventoryTransaction.reference_id.in_(all_po_ids),
            InventoryTransaction.transaction_type.in_(['consumption', 'scrap'])
        ).group_by(InventoryTransaction.reference_id).all()
        
        po_material_costs = {row.reference_id: row.material_cost for row in material_costs_result}
    
    # Calculate COGS using batched data
    # Note: Only include actual production costs, not customer shipping charges
    for order in shipped_mtd:
        # Add material costs from production orders
        po_ids = sales_to_po_map.get(order.id, [])
        for po_id in po_ids:
            material_cost = po_material_costs.get(po_id, Decimal("0"))
            mtd_cogs += material_cost

    # Gross profit = Revenue - COGS (tax excluded per GAAP)
    mtd_gross_profit = Decimal(str(mtd_revenue)) - mtd_cogs
    mtd_margin = float(mtd_gross_profit / Decimal(str(mtd_revenue)) * 100) if mtd_revenue > 0 else 0

    return {
        "as_of": now.isoformat(),
        "fiscal_year_start": fiscal_year_start.isoformat(),
        "revenue": {
            "mtd": mtd_revenue,
            "mtd_orders": mtd_orders_count,
            "ytd": ytd_revenue,
            "ytd_orders": ytd_orders_count,
        },
        "payments": {
            "mtd_received": float(mtd_payments),
            "ytd_received": float(ytd_payments),
            "outstanding": float(total_outstanding),
            "outstanding_orders": len(outstanding_orders),
        },
        "tax": {
            "mtd_collected": mtd_tax,
            "ytd_collected": ytd_tax,
        },
        "cogs": {
            "mtd": float(mtd_cogs),
        },
        "profit": {
            "mtd_gross": float(mtd_gross_profit),
            "mtd_margin_pct": mtd_margin,
        },
    }


# ==============================================================================
# Sales Journal
# ==============================================================================

@router.get("/sales-journal", response_model=SalesJournalResponse)
async def get_sales_journal(
    db: Session = Depends(get_db),
    start_date: Optional[datetime] = Query(None, description="Start date (defaults to 30 days ago)"),
    end_date: Optional[datetime] = Query(None, description="End date (defaults to today)"),
    status: Optional[str] = Query(None, description="Filter by order status"),
    include_cancelled: bool = Query(False, description="Include cancelled orders"),
) -> SalesJournalResponse:
    """
    Get sales journal - all sales transactions for the period.
    Uses shipped_at for accrual accounting (revenue recognized when earned).

    Returns detailed list of all sales orders with:
    - Order details
    - Line items (if applicable)
    - Tax breakdown
    - Payment status
    """
    if not end_date:
        end_date = datetime.now(timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # Extend end_date to end of day to include all transactions on that date
    # (Frontend sends dates as midnight UTC, but we want to include the whole day)
    end_date_eod = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Use shipped_at for accrual basis revenue recognition per GAAP
    query = db.query(SalesOrder).filter(
        SalesOrder.shipped_at >= start_date,
        SalesOrder.shipped_at <= end_date_eod,
        SalesOrder.status.in_(["shipped", "completed"])
    )

    if status:
        query = query.filter(SalesOrder.status == status)

    if not include_cancelled:
        query = query.filter(SalesOrder.status != "cancelled")

    orders = query.order_by(SalesOrder.created_at.desc()).all()

    journal_entries = []
    totals = {
        "subtotal": Decimal("0"),
        "tax": Decimal("0"),
        "shipping": Decimal("0"),
        "grand_total": Decimal("0"),
    }

    for order in orders:
        subtotal = order.total_price or Decimal("0")
        tax = order.tax_amount or Decimal("0")
        shipping = order.shipping_cost or Decimal("0")
        grand_total = order.grand_total or (subtotal + tax + shipping)

        totals["subtotal"] += subtotal
        totals["tax"] += tax
        totals["shipping"] += shipping
        totals["grand_total"] += grand_total

        entry = {
            "date": order.shipped_at.isoformat() if order.shipped_at else None,  # Revenue recognition date
            "order_number": order.order_number,
            "order_id": order.id,
            "status": order.status,
            "payment_status": order.payment_status,
            "source": order.source or "portal",
            "product_name": order.product_name,
            "quantity": order.quantity,
            "subtotal": float(subtotal),
            "tax_rate": float(order.tax_rate or 0) if order.tax_rate else None,
            "tax_amount": float(tax),
            "is_taxable": order.is_taxable if hasattr(order, 'is_taxable') else (tax > 0),
            "shipping": float(shipping),
            "grand_total": float(grand_total),
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
        }

        journal_entries.append(entry)

    return {
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "totals": {
            "subtotal": float(totals["subtotal"]),
            "tax": float(totals["tax"]),
            "shipping": float(totals["shipping"]),
            "grand_total": float(totals["grand_total"]),
            "order_count": len(journal_entries),
        },
        "entries": journal_entries,
    }


@router.get("/sales-journal/export")
async def export_sales_journal_csv(
    db: Session = Depends(get_db),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
):
    """
    Export sales journal as CSV.
    Uses shipped_at for accrual basis revenue recognition per GAAP.
    """
    if not end_date:
        end_date = datetime.now(timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # Extend end_date to end of day to include all transactions on that date
    end_date_eod = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Use shipped_at for accrual accounting (revenue recognized at shipment)
    orders = db.query(SalesOrder).filter(
        SalesOrder.shipped_at >= start_date,
        SalesOrder.shipped_at <= end_date_eod,
        SalesOrder.status.in_(["shipped", "completed"])
    ).order_by(SalesOrder.shipped_at).all()

    output = io.StringIO()

    writer = csv.writer(output)
    # Disclaimer header
    writer.writerow(["# FilaOps Sales Journal - For Reference Only"])
    writer.writerow(["# Verify with qualified accountant before use in tax filings."])
    writer.writerow([f"# Date Range: {start_date} to {end_date}"])
    writer.writerow([])
    writer.writerow([
        "Date", "Order Number", "Status", "Payment Status", "Source",
        "Product", "Quantity", "Subtotal", "Tax Rate", "Tax Amount",
        "Shipping", "Grand Total", "Paid Date", "Shipped Date"
    ])

    for order in orders:
        writer.writerow([
            order.shipped_at.strftime("%Y-%m-%d") if order.shipped_at else "",  # Revenue recognition date
            order.order_number,
            order.status,
            order.payment_status,
            order.source or "portal",
            order.product_name or "",
            order.quantity,
            float(order.total_price or 0),  # Subtotal (excludes tax)
            float(order.tax_rate or 0) if order.tax_rate else "",
            float(order.tax_amount or 0),  # Tax liability
            float(order.shipping_cost or 0),
            float(order.grand_total or 0),
            order.paid_at.strftime("%Y-%m-%d") if order.paid_at else "",
            order.shipped_at.strftime("%Y-%m-%d") if order.shipped_at else "",
        ])

    output.seek(0)
    filename = f"sales_journal_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ==============================================================================
# Tax Center
# ==============================================================================

@router.get("/tax-summary", response_model=TaxSummaryResponse)
async def get_tax_summary(
    db: Session = Depends(get_db),
    period: str = Query("month", description="Period: month, quarter, year"),
) -> TaxSummaryResponse:
    """
    Get tax summary for filing preparation.

    Returns:
    - Total taxable sales
    - Total non-taxable sales
    - Tax collected by rate
    - Tax collected by period
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Determine period start
    if period == "month":
        period_start = today_start.replace(day=1)
        period_name = now.strftime("%B %Y")
    elif period == "quarter":
        quarter_month = ((now.month - 1) // 3) * 3 + 1
        period_start = today_start.replace(month=quarter_month, day=1)
        quarter_num = (now.month - 1) // 3 + 1
        period_name = f"Q{quarter_num} {now.year}"
    else:  # year
        period_start = today_start.replace(month=1, day=1)
        period_name = str(now.year)

    # Get orders in period (use shipped_at for accrual accounting per GAAP)
    # Tax liability is recognized when revenue is recognized (at shipment)
    orders = db.query(SalesOrder).filter(
        SalesOrder.shipped_at >= period_start,
        SalesOrder.status.in_(["shipped", "completed"])
    ).all()

    # Get pending orders (not yet shipped) to show future tax liability
    pending_orders = db.query(SalesOrder).filter(
        SalesOrder.status.notin_(["shipped", "completed", "cancelled"]),
        SalesOrder.tax_amount > 0
    ).all()

    pending_tax = sum(float(o.tax_amount or 0) for o in pending_orders)
    pending_order_count = len(pending_orders)

    # Calculate totals
    taxable_sales = Decimal("0")
    non_taxable_sales = Decimal("0")
    total_tax_collected = Decimal("0")
    tax_by_rate: Dict[str, Dict[str, Any]] = {}

    for order in orders:
        subtotal = order.total_price or Decimal("0")
        tax = order.tax_amount or Decimal("0")

        # Check if taxable (use is_taxable field if available, otherwise check tax_amount)
        is_taxable = getattr(order, 'is_taxable', None)
        if is_taxable is None:
            is_taxable = tax > 0

        if is_taxable:
            taxable_sales += subtotal
            total_tax_collected += tax

            # Group by tax rate
            rate_key = str(float(order.tax_rate or 0) * 100) if order.tax_rate else "default"
            if rate_key not in tax_by_rate:
                tax_by_rate[rate_key] = {
                    "rate_pct": float(order.tax_rate or 0) * 100 if order.tax_rate else 0,
                    "taxable_sales": Decimal("0"),
                    "tax_collected": Decimal("0"),
                    "order_count": 0,
                }
            tax_by_rate[rate_key]["taxable_sales"] += subtotal
            tax_by_rate[rate_key]["tax_collected"] += tax
            tax_by_rate[rate_key]["order_count"] += 1
        else:
            non_taxable_sales += subtotal

    # Monthly breakdown for the period
    monthly_breakdown = []
    current = period_start
    while current < now:
        month_end = (current.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(seconds=1)
        if month_end > now:
            month_end = now

        # shipped_at is naive (DateTime without timezone=True), so strip
        # tzinfo from the aware boundaries for a safe comparison.
        cur_naive = current.replace(tzinfo=None)
        end_naive = month_end.replace(tzinfo=None)
        month_orders = [
            o for o in orders
            if o.shipped_at and cur_naive <= o.shipped_at <= end_naive
        ]
        month_tax = sum(float(o.tax_amount or 0) for o in month_orders)
        month_taxable = sum(
            float(o.total_price or 0)
            for o in month_orders
            if (getattr(o, 'is_taxable', None) or (o.tax_amount and o.tax_amount > 0))
        )

        monthly_breakdown.append({
            "month": current.strftime("%B %Y"),
            "taxable_sales": month_taxable,
            "tax_collected": month_tax,
            "order_count": len(month_orders),
        })

        # Move to next month
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)

    return {
        "period": period_name,
        "period_start": period_start.isoformat(),
        "period_end": now.isoformat(),
        "summary": {
            "total_sales": float(taxable_sales + non_taxable_sales),
            "taxable_sales": float(taxable_sales),
            "non_taxable_sales": float(non_taxable_sales),
            "tax_collected": float(total_tax_collected),
            "order_count": len(orders),
        },
        "pending": {
            "tax_amount": pending_tax,
            "order_count": pending_order_count,
        },
        "by_rate": [
            {
                "rate_pct": v["rate_pct"],
                "taxable_sales": float(v["taxable_sales"]),
                "tax_collected": float(v["tax_collected"]),
                "order_count": v["order_count"],
            }
            for v in tax_by_rate.values()
        ],
        "monthly_breakdown": monthly_breakdown,
    }


@router.get("/tax-summary/export")
async def export_tax_summary_csv(
    db: Session = Depends(get_db),
    period: str = Query("quarter", description="Period: month, quarter, year"),
):
    """
    Export tax summary as CSV for filing.
    """
    # Get the tax summary data
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == "month":
        period_start = today_start.replace(day=1)
    elif period == "quarter":
        quarter_month = ((now.month - 1) // 3) * 3 + 1
        period_start = today_start.replace(month=quarter_month, day=1)
    else:
        period_start = today_start.replace(month=1, day=1)

    # Use shipped_at for accrual accounting (tax liability at revenue recognition)
    orders = db.query(SalesOrder).filter(
        SalesOrder.shipped_at >= period_start,
        SalesOrder.status.in_(["shipped", "completed"])
    ).order_by(SalesOrder.shipped_at).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Disclaimer header
    writer.writerow(["# FilaOps Tax Summary - For Reference Only"])
    writer.writerow(["# This is NOT a tax filing. Verify with qualified accountant."])
    writer.writerow([f"# Period: {period} ending {now.strftime('%Y-%m-%d')}"])
    writer.writerow([])

    # Header
    writer.writerow([
        "Date", "Order Number", "Taxable", "Subtotal", "Tax Rate %",
        "Tax Amount", "Grand Total", "Payment Status"
    ])

    for order in orders:
        is_taxable = getattr(order, 'is_taxable', None)
        if is_taxable is None:
            is_taxable = (order.tax_amount or 0) > 0

        writer.writerow([
            order.shipped_at.strftime("%Y-%m-%d") if order.shipped_at else "",  # Tax recognition date
            order.order_number,
            "Yes" if is_taxable else "No",
            float(order.total_price or 0),  # Taxable amount (excludes tax itself)
            float(order.tax_rate or 0) * 100 if order.tax_rate else "",
            float(order.tax_amount or 0),
            float(order.grand_total or 0),
            order.payment_status,
        ])

    # Summary row
    total_taxable = sum(float(o.total_price or 0) for o in orders if getattr(o, 'is_taxable', (o.tax_amount or 0) > 0))
    total_tax = sum(float(o.tax_amount or 0) for o in orders)
    total_grand = sum(float(o.grand_total or 0) for o in orders)

    writer.writerow([])
    writer.writerow(["TOTALS", "", "", total_taxable, "", total_tax, total_grand, ""])

    output.seek(0)
    filename = f"tax_summary_{period}_{now.strftime('%Y%m%d')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ==============================================================================
# Payments Journal
# ==============================================================================

@router.get("/payments-journal", response_model=PaymentsJournalResponse)
async def get_payments_journal(
    db: Session = Depends(get_db),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    payment_method: Optional[str] = Query(None),
) -> PaymentsJournalResponse:
    """
    Get payments journal - all payment transactions for the period.
    """
    if not end_date:
        end_date = datetime.now(timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # Extend end_date to end of day to include all transactions on that date
    end_date_eod = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

    query = db.query(Payment).options(
        joinedload(Payment.sales_order)
    ).filter(
        Payment.payment_date >= start_date,
        Payment.payment_date <= end_date_eod,
        Payment.status == "completed"
    )

    if payment_method:
        query = query.filter(Payment.payment_method == payment_method)

    payments = query.order_by(Payment.payment_date.desc()).all()

    # Group by method
    by_method: Dict[str, Decimal] = {}
    total_payments = Decimal("0")
    total_refunds = Decimal("0")

    entries = []
    for p in payments:
        amount = p.amount or Decimal("0")

        if p.payment_type == "refund" or amount < 0:
            total_refunds += abs(amount)
        else:
            total_payments += amount
            method = p.payment_method or "other"
            by_method[method] = by_method.get(method, Decimal("0")) + amount

        entries.append({
            "date": p.payment_date.isoformat() if p.payment_date else None,
            "payment_number": p.payment_number,
            "order_number": p.sales_order.order_number if p.sales_order else None,
            "payment_method": p.payment_method,
            "payment_type": p.payment_type,
            "amount": float(amount),
            "transaction_id": p.transaction_id,
            "notes": p.notes,
        })

    return {
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "totals": {
            "payments": float(total_payments),
            "refunds": float(total_refunds),
            "net": float(total_payments - total_refunds),
            "count": len(payments),
        },
        "by_method": {k: float(v) for k, v in by_method.items()},
        "entries": entries,
    }


@router.get("/payments-journal/export")
async def export_payments_journal_csv(
    db: Session = Depends(get_db),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
):
    """
    Export payments journal as CSV.
    """
    if not end_date:
        end_date = datetime.now(timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # Extend end_date to end of day to include all transactions on that date
    end_date_eod = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

    payments = db.query(Payment).options(
        joinedload(Payment.sales_order)
    ).filter(
        Payment.payment_date >= start_date,
        Payment.payment_date <= end_date_eod,
        Payment.status == "completed"
    ).order_by(Payment.payment_date).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Disclaimer header
    writer.writerow(["# FilaOps Payments Journal - For Reference Only"])
    writer.writerow(["# Verify with qualified accountant before use in tax filings."])
    writer.writerow([f"# Date Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"])
    writer.writerow([])

    writer.writerow([
        "Date", "Payment Number", "Order Number", "Type", "Method",
        "Amount", "Transaction ID", "Notes"
    ])

    for p in payments:
        writer.writerow([
            p.payment_date.strftime("%Y-%m-%d") if p.payment_date else "",
            p.payment_number,
            p.sales_order.order_number if p.sales_order else "",
            p.payment_type,
            p.payment_method,
            float(p.amount or 0),
            p.transaction_id or "",
            p.notes or "",
        ])

    output.seek(0)
    filename = f"payments_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ==============================================================================
# Tax Time Export
# ==============================================================================

@router.get("/export/sales")
async def export_sales_for_tax_time(
    start_date: date = Query(..., description="Start date (inclusive)"),
    end_date: date = Query(..., description="End date (inclusive)"),
    format: str = Query("csv", description="Export format (currently only csv)"),
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """
    Export sales data for tax time / accounting purposes.

    This endpoint provides a simplified CSV export of sales orders for the specified
    date range. Designed for freemium accounting features and tax preparation.

    The export includes:
    - Order identification and dates
    - Customer information
    - Financial breakdown (subtotal, tax, shipping, total)
    - Order and payment status

    Date range is based on order creation date (created_at).
    """
    # Convert date objects to datetime for querying
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())

    # Query sales orders in the date range
    # Use created_at for the date range (can be changed to shipped_at for accrual basis)
    orders = db.query(SalesOrder).options(
        joinedload(SalesOrder.user)
    ).filter(
        SalesOrder.created_at >= start_datetime,
        SalesOrder.created_at <= end_datetime
    ).order_by(SalesOrder.created_at).all()

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Disclaimer header (important for liability)
    writer.writerow(["# FilaOps Sales Export - For Reference Only"])
    writer.writerow(["# This data should be verified by a qualified accountant before use in tax filings."])
    writer.writerow(["# FilaOps is operational software, not a certified accounting system."])
    writer.writerow([f"# Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([f"# Date Range: {start_date} to {end_date}"])
    writer.writerow([])  # Blank line before data

    # CSV Header
    writer.writerow([
        "Order Number",
        "Order Date",
        "Customer Name",
        "Subtotal",
        "Tax Amount",
        "Shipping",
        "Total",
        "Status",
        "Payment Status"
    ])

    # Write data rows
    for order in orders:
        # Get customer name from user relationship
        customer_name = ""
        if order.user:
            if order.user.company_name:
                customer_name = order.user.company_name
            elif order.user.first_name or order.user.last_name:
                customer_name = f"{order.user.first_name or ''} {order.user.last_name or ''}".strip()
            else:
                customer_name = order.user.email

        # Format date
        order_date = order.created_at.strftime("%Y-%m-%d") if order.created_at else ""

        # Financial values
        subtotal = float(order.total_price or 0)
        tax_amount = float(order.tax_amount or 0)
        shipping = float(order.shipping_cost or 0)
        total = float(order.grand_total or 0)

        writer.writerow([
            order.order_number,
            order_date,
            customer_name,
            f"{subtotal:.2f}",
            f"{tax_amount:.2f}",
            f"{shipping:.2f}",
            f"{total:.2f}",
            order.status,
            order.payment_status
        ])

    # Prepare response
    output.seek(0)
    filename = f"sales_export_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
