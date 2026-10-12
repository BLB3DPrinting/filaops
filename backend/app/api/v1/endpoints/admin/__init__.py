"""
Admin endpoints - requires staff authentication (admin or operator).

Every /api/v1/admin/* route needs a staff account; admin-only sub-routers
additionally depend on get_current_admin_user.
"""
from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_staff_user
from . import (
    bom, dashboard, fulfillment_queue, fulfillment_shipping, audit, accounting, traceability,
    customers, inventory_transactions, analytics, export, data_import, orders,
    users, uom, locations, system, uploads, pro_install, reconciliation, reservations,
    operation_types,
)

# SEC-406: gate the whole /admin tree to staff (admin or operator), fail-closed.
# The aggregator used to apply no auth at all, so a sub-route that forgot its
# own dependency was anonymous. Admin-only sub-routers keep their
# get_current_admin_user on top of this gate.
router = APIRouter(dependencies=[Depends(get_current_staff_user)])

# User Management (Admin/Operator users)
router.include_router(users.router)

# Customer Management
router.include_router(customers.router)

# BOM Management
router.include_router(bom.router)

# Admin Dashboard
router.include_router(dashboard.router)

# Analytics (Pro tier)
router.include_router(analytics.router)

# Fulfillment (Quote-to-Ship workflow)
router.include_router(fulfillment_queue.router)
router.include_router(fulfillment_shipping.router)

# Transaction Audit
router.include_router(audit.router)

# Accounting Views
router.include_router(accounting.router)

# Traceability (Serial Numbers, Material Lots, Recall Queries)
router.include_router(traceability.router)

# Inventory Transactions
router.include_router(inventory_transactions.router)

# Inventory Reconciliation Report (HARD-4b)
router.include_router(reconciliation.router)

# Reservation Reconciliation + Stranded Allocation Repair (HARD-5)
router.include_router(reservations.router)

# Operation Type Catalog: audit + human-gated classifier + hardened CRUD (876 PR-3)
router.include_router(operation_types.router)

# Export/Import
router.include_router(export.router)
router.include_router(data_import.router)

# Orders Import
router.include_router(orders.router)

# Units of Measure
router.include_router(uom.router)

# Inventory Locations
router.include_router(locations.router)

# System Management (updates, maintenance)
router.include_router(system.router)

# PRO Installer (PR-04 — wheel download + pip install, Core-only, no PRO imports)
router.include_router(pro_install.router)

# File Uploads (product images, etc.)
router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
