"""
Pydantic schemas for the consolidated buy list (HARD-7).
"""
from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class BuyListIncomingDetail(BaseModel):
    """One open PO line contributing to projected supply."""
    purchase_order_id: int
    po_number: str
    quantity: Decimal
    expected_date: Optional[date]
    status: str  # "draft", "ordered", "shipped" — callers may surface "(draft)" label

    model_config = {"from_attributes": True}


class BuyListItem(BaseModel):
    """
    One short component that needs to be purchased.

    Net shortage is the quantity we must still buy after netting
    on-hand, allocated, and all open POs against gross demand.
    """
    product_id: int
    sku: str
    name: str
    unit: str

    # Demand
    gross_demand: Decimal       # Total gross requirement across all open orders
    on_hand: Decimal
    allocated: Decimal
    available: Decimal          # on_hand − allocated (may be negative)
    incoming_qty: Decimal       # Σ remaining on open POs
    projected: Decimal          # available + incoming_qty
    safety_stock: Decimal       # Product.safety_stock threshold applied

    # Shortage
    net_shortage: Decimal       # max(0, gross_demand − projected + safety_stock)
    suggested_qty: Decimal      # max(net_shortage, min_order_qty)

    # Purchasing hint
    preferred_vendor_id: Optional[int]
    preferred_vendor_name: Optional[str]
    unit_cost: Decimal          # standard_cost or last_cost
    estimated_buy_value: Decimal  # suggested_qty × unit_cost

    # Earliest-need hint (earliest due / completion date among demanding orders)
    earliest_need: Optional[date]

    # Incoming PO detail (for "draft" visibility)
    incoming_details: List[BuyListIncomingDetail] = []

    model_config = {"from_attributes": True}


class BuyListSummary(BaseModel):
    """Summary header for the buy list page."""
    components_short: int               # Number of distinct short components
    total_estimated_buy_value: Decimal  # Σ estimated_buy_value
    open_sales_orders_included: int
    open_production_orders_included: int
    draft_incoming_qty: Decimal         # Σ incoming from draft POs (uncommitted supply)

    model_config = {"from_attributes": True}


class BuyListResponse(BaseModel):
    """Full buy list response."""
    summary: BuyListSummary
    items: List[BuyListItem]

    model_config = {"from_attributes": True}
