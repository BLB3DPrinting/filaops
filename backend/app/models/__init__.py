"""Database models - FilaOps Open Source Core"""
from app.models.item_category import ItemCategory
from app.models.product import Product
from app.models.production_order import ProductionOrder, ProductionOrderOperation, ProductionOrderOperationMaterial, ScrapRecord
from app.models.print_job import PrintJob
from app.models.inventory import Inventory, InventoryTransaction, InventoryLocation
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.payment import Payment
from app.models.bom import BOM, BOMLine
from app.models.printer import Printer
from app.models.quote import Quote, QuoteFile, QuoteLine, QuoteMaterial
from app.models.user import User, RefreshToken
from app.models.material import MaterialType, Color, MaterialColor, MaterialInventory
from app.models.vendor import Vendor
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.purchase_order_document import PurchaseOrderDocument, VendorItem
from app.models.work_center import WorkCenter
from app.models.manufacturing import Routing, RoutingOperation, Resource, RoutingOperationMaterial
from app.models.mrp import MRPRun, PlannedOrder
from app.models.traceability import (
    SerialNumber, MaterialLot, ProductionLotConsumption, CustomerTraceabilityProfile
)
from app.models.company_settings import CompanySettings
from app.models.uom import UnitOfMeasure
from app.models.uom import UnitOfMeasure as UOM
from app.models.scrap_reason import ScrapReason
from app.models.adjustment_reason import AdjustmentReason
from app.models.order_event import OrderEvent
from app.models.purchasing_event import PurchasingEvent
from app.models.shipping_event import ShippingEvent
from app.models.material_spool import MaterialSpool, ProductionOrderSpool
from app.models.maintenance import MaintenanceLog
from app.models.customer import Customer

# Accounting (GL)
from app.models.accounting import GLAccount, GLFiscalPeriod, GLJournalEntry, GLJournalEntryLine

# Invoicing
from app.models.invoice import Invoice, InvoiceLine

# Notifications
from app.models.notification import Notification

# Close Short Audit
from app.models.close_short_record import CloseShortRecord

# i18n / Tax Rates
from app.models.tax_rate import TaxRate

__all__ = [
    # Item management
    "ItemCategory",
    "Product",
    # Production
    "ProductionOrder",
    "ProductionOrderOperation",
    "PrintJob",
    # Inventory
    "Inventory",
    "InventoryTransaction",
    "InventoryLocation",
    # Sales
    "SalesOrder",
    "SalesOrderLine",
    "Payment",
    # Manufacturing
    "BOM",
    "BOMLine",
    "Printer",
    # Quotes
    "Quote",
    "QuoteFile",
    "QuoteLine",
    "QuoteMaterial",
    # Users
    "User",
    "RefreshToken",
    # Materials
    "MaterialType",
    "Color",
    "MaterialColor",
    "MaterialInventory",
    # Purchasing
    "Vendor",
    "PurchaseOrder",
    "PurchaseOrderLine",
    "PurchaseOrderDocument",
    "VendorItem",
    # Manufacturing Routes
    "WorkCenter",
    "Resource",
    "Routing",
    "RoutingOperation",
    "RoutingOperationMaterial",
    "ProductionOrderOperationMaterial",
    "ScrapRecord",
    # MRP
    "MRPRun",
    "PlannedOrder",
    # Traceability
    "SerialNumber",
    "MaterialLot",
    "ProductionLotConsumption",
    "CustomerTraceabilityProfile",
    # Company Settings
    "CompanySettings",
    # Units of Measure
    "UnitOfMeasure",
    "UOM",
    # Scrap Reasons
    "ScrapReason",
    # Adjustment Reasons
    "AdjustmentReason",
    # Order Events (Activity Timeline)
    "OrderEvent",
    "PurchasingEvent",
    "ShippingEvent",
    # Material Spool Tracking
    "MaterialSpool",
    "ProductionOrderSpool",
    # Maintenance
    "MaintenanceLog",
    # CRM (Core)
    "Customer",
    # Accounting (GL)
    "GLAccount",
    "GLFiscalPeriod",
    "GLJournalEntry",
    "GLJournalEntryLine",
    # Tax Rates
    "TaxRate",
    # Invoicing
    "Invoice",
    "InvoiceLine",
    # Notifications
    "Notification",
    # Close Short Audit
    "CloseShortRecord",
]
