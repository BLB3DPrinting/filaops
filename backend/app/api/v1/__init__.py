"""
API v1 Router - FilaOps Open Source Core
"""
import os
from fastapi import APIRouter
from app.api.v1.endpoints import (
    accounting,
    scheduling,
    auth,
    sales_orders,
    production_orders,
    operation_status,
    inventory,
    products,
    items,
    materials,
    vendors,
    purchase_orders,
    po_documents,
    low_stock,
    vendor_items,
    work_centers,
    resources,
    routings,
    mrp,
    setup,
    quotes,
    settings,
    payments,
    printers,
    tax_rates,
    system,
    spools,
    traceability,
    maintenance,
    command_center,
    security,
    invoices,
    notifications,
    price_levels,
)
from app.api.v1.endpoints.admin import router as admin_router

router = APIRouter()

# Authentication
router.include_router(auth.router)

# First-run setup (creates initial admin)
router.include_router(setup.router)

# Sales Orders
router.include_router(sales_orders.router)

# Quotes
router.include_router(quotes.router)

# Products
router.include_router(
    products.router,
    prefix="/products",
    tags=["products"]
)

# Items (unified item management)
router.include_router(
    items.router,
    prefix="/items",
    tags=["items"]
)

# Production Orders
router.include_router(
    production_orders.router,
    prefix="/production-orders",
    tags=["production"]
)

# Operation Status (nested under production orders)
router.include_router(
    operation_status.router,
    prefix="/production-orders",
    tags=["production-operations"]
)

# Inventory
router.include_router(
    inventory.router,
    prefix="/inventory",
    tags=["inventory"]
)

# Materials
router.include_router(
    materials.router,
    prefix="/materials",
    tags=["materials"]
)

# Admin (BOM management, dashboard, traceability)
router.include_router(
    admin_router,
    prefix="/admin",
    tags=["admin"]
)

# Vendors
router.include_router(
    vendors.router,
    prefix="/vendors",
    tags=["vendors"]
)

# Purchase Orders
router.include_router(
    purchase_orders.router,
    prefix="/purchase-orders",
    tags=["purchase-orders"]
)

# Purchase Order Documents (multi-file upload)
router.include_router(
    po_documents.router,
    prefix="/purchase-orders",
    tags=["purchase-orders"]
)

# Low Stock Workflow (create POs from low stock)
router.include_router(
    low_stock.router,
    prefix="/purchase-orders",
    tags=["purchase-orders"]
)

# Vendor Items (SKU mapping for invoice parsing)
router.include_router(
    vendor_items.router,
    prefix="/purchase-orders",
    tags=["purchase-orders"]
)

# Invoices (Core billing)
router.include_router(invoices.router)

# Notifications (operator messaging)
router.include_router(notifications.router)

# Invoice Import is a PRO feature
# Exports (QuickBooks) is a PRO feature
# Amazon Import is a PRO feature

# Work Centers
router.include_router(
    work_centers.router,
    prefix="/work-centers",
    tags=["manufacturing"]
)

# Resources (scheduling and conflicts)
router.include_router(
    resources.router,
    prefix="/resources",
    tags=["manufacturing"]
)

# Routings
router.include_router(
    routings.router,
    prefix="/routings",
    tags=["manufacturing"]
)

# B2B Portal API is a PRO feature

# MRP (Material Requirements Planning)
router.include_router(mrp.router)

# Features/Licensing is a PRO feature

# Scheduling and Capacity Management
router.include_router(
    scheduling.router,
    prefix="/scheduling",
    tags=["scheduling"]
)

# Company Settings
router.include_router(settings.router)

# Tax Rates (multi-rate i18n support)
router.include_router(tax_rates.router)

# Price Levels (wholesale tiers — Core manages definitions, PRO manages customer assignment)
router.include_router(price_levels.router)

# Payments
router.include_router(payments.router)

# GL Accounting (Trial Balance, Inventory Valuation)
router.include_router(
    accounting.router,
    prefix="/accounting",
    tags=["accounting"]
)

# Printers
router.include_router(
    printers.router,
    prefix="/printers",
    tags=["printers"]
)

# System (version, updates, health)
router.include_router(system.router)

# Security Audit
router.include_router(security.router)

# Material Spools
router.include_router(spools.router)

# Quality - Traceability
router.include_router(
    traceability.router,
    prefix="/traceability",
    tags=["quality"]
)

# Maintenance
router.include_router(
    maintenance.router,
    prefix="/maintenance",
    tags=["maintenance"]
)

# Command Center (dashboard)
router.include_router(
    command_center.router,
    prefix="/command-center",
    tags=["command-center"]
)

# License activation is a PRO feature

# Test endpoints - only enabled in non-production environments
# These endpoints allow E2E tests to seed test data
if os.getenv("ENVIRONMENT", "development").lower() != "production":
    from app.api.v1.endpoints import test as test_endpoints
    router.include_router(test_endpoints.router)
