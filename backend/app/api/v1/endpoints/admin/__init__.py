"""
Admin endpoints - requires admin authentication
"""
from fastapi import APIRouter
from . import (
    bom, dashboard, fulfillment_queue, fulfillment_shipping, audit, accounting, traceability,
    customers, inventory_transactions, analytics, export, data_import, orders,
    users, uom, locations, system, uploads, pro_install, reconciliation, reservations,
    operation_types,
)

router = APIRouter()

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
