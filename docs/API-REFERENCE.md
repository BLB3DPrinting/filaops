<!-- AUTO-GENERATED — Do not edit manually. Regenerate: cd backend && python scripts/generate_api_reference.py -->

# FilaOps API Reference

> Complete API endpoint documentation for FilaOps Core ERP system.
> Generated for AI consumption and developer reference.
> This document covers **Core (Open Source)** API endpoints only.

## Overview

| Metric | Count |
| ------ | ----- |
| **Total Endpoints** | ~424 |
| **Router Files** | 49 |
| **Router Groups** | 28 (including 18 admin sub-modules) |
| **Base Path** | `/api/v1/` |

### HTTP Method Distribution

- **GET**: ~210 endpoints (read/query operations)
- **POST**: ~144 endpoints (create/execute operations)
- **PUT/PATCH**: ~41 endpoints (update operations)
- **DELETE**: ~29 endpoints (delete operations)

---

## Authentication

All endpoints except those marked `PUBLIC` require JWT Bearer token authentication.

```http
Authorization: Bearer <access_token>
```

### Auth Levels

- **PUBLIC**: No authentication required
- **CUSTOMER**: Requires valid JWT (any user type)
- **STAFF**: Requires `account_type` in ['admin', 'operator']
- **ADMIN**: Requires `account_type` = 'admin'

---

## 1. Auth (`/auth`)

**Tier**: Core
**File**: `endpoints/auth.py`
**Endpoints**: 10

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/auth/register` | Register a new user | PUBLIC |
| POST | `/auth/login` | Login with email and password. | PUBLIC |
| POST | `/auth/refresh` | Refresh access token using refresh token. | PUBLIC |
| GET | `/auth/me` | Get current user profile | CUSTOMER |
| POST | `/auth/logout` | Logout the current user. | PUBLIC |
| POST | `/auth/password-reset/request` | Request a password reset. | PUBLIC |
| POST | `/auth/password-reset/approve` | Approve a password reset request (admin action). | PUBLIC |
| POST | `/auth/password-reset/deny` | Deny a password reset request (admin action). | PUBLIC |
| GET | `/auth/password-reset/status/{token}` | Check the status of a password reset token. | PUBLIC |
| POST | `/auth/password-reset/complete` | Complete the password reset by setting a new password. | PUBLIC |

---

## 2. Setup (`/setup`)

**Tier**: Core
**File**: `endpoints/setup.py`
**Endpoints**: 3

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/setup/status` | Check if first-run setup is needed. | PUBLIC |
| POST | `/setup/initial-admin` | Create the initial admin user during first-run setup. | PUBLIC |
| POST | `/setup/seed-example-data` | Seed the database with example items and materials. | ADMIN |

---

## 3. Sales Orders (`/sales-orders`)

**Tier**: Core
**File**: `endpoints/sales_orders.py`
**Endpoints**: 24

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/sales-orders/status-transitions` | Get valid status transitions for sales orders. | CUSTOMER |
| GET | `/sales-orders/payment-statuses` | Get valid payment status values for sales orders. | CUSTOMER |
| POST | `/sales-orders/` | Create a manual sales order (line_item type). | CUSTOMER |
| POST | `/sales-orders/convert/{quote_id}` | Convert an accepted quote to a sales order. | CUSTOMER |
| GET | `/sales-orders/` | Get list of sales orders. | ADMIN |
| GET | `/sales-orders/{order_id}` | Get detailed information about a specific sales order. | ADMIN |
| GET | `/sales-orders/{order_id}/packing-slip/pdf` | Generate and return a packing slip PDF for a sales order. | ADMIN |
| GET | `/sales-orders/{order_id}/required-orders` | Get full MRP cascade of WOs and POs needed to fulfill this sales order. | ADMIN |
| GET | `/sales-orders/{order_id}/blocking-issues` | Get blocking issues analysis for a sales order. | CUSTOMER |
| GET | `/sales-orders/{order_id}/fulfillment-status` | Get fulfillment status for a sales order. | CUSTOMER |
| GET | `/sales-orders/{order_id}/material-requirements` | Get material requirements for a sales order. | ADMIN |
| POST | `/sales-orders/{order_id}/pre-flight-check` | Pre-flight check before confirming a sales order. | CUSTOMER |
| PATCH | `/sales-orders/{order_id}/status` | Update sales order status (admin only). | ADMIN |
| PATCH | `/sales-orders/{order_id}/payment` | Update payment information for an order (admin only). | ADMIN |
| PATCH | `/sales-orders/{order_id}/shipping` | Update shipping information for an order (admin only). | ADMIN |
| PATCH | `/sales-orders/{order_id}/address` | Update shipping address for an order (admin only). | ADMIN |
| POST | `/sales-orders/{order_id}/cancel` | Cancel a sales order. | ADMIN |
| DELETE | `/sales-orders/{order_id}` | Delete a sales order (admin only). | ADMIN |
| POST | `/sales-orders/{order_id}/ship` | Create shipping label and mark order as shipped. | ADMIN |
| POST | `/sales-orders/{order_id}/generate-production-orders` | Generate production orders from a sales order (admin only). | ADMIN |
| GET | `/sales-orders/{order_id}/events` | Get activity timeline for a sales order. | ADMIN |
| POST | `/sales-orders/{order_id}/events` | Add an event to a sales order's activity timeline. | ADMIN |
| GET | `/sales-orders/{order_id}/shipping-events` | List shipping events for a sales order. | PUBLIC |
| POST | `/sales-orders/{order_id}/shipping-events` | Add a shipping event to a sales order. | CUSTOMER |

---

## 4. Quotes (`/quotes`)

**Tier**: Core
**File**: `endpoints/quotes.py`
**Endpoints**: 12

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/quotes/` | List all quotes with optional filtering | CUSTOMER |
| GET | `/quotes/stats` | Get quote statistics for dashboard | CUSTOMER |
| GET | `/quotes/{quote_id}` | Get quote details | CUSTOMER |
| POST | `/quotes/` | Create a new manual quote | CUSTOMER |
| PATCH | `/quotes/{quote_id}` | Update quote details | CUSTOMER |
| PATCH | `/quotes/{quote_id}/status` | Update quote status (approve, reject, cancel, accept) | CUSTOMER |
| POST | `/quotes/{quote_id}/convert` | Convert an accepted/approved quote to a sales order | CUSTOMER |
| DELETE | `/quotes/{quote_id}` | Delete a quote (only if not converted) | CUSTOMER |
| POST | `/quotes/{quote_id}/image` | Upload an image for a quote (product photo/render) | CUSTOMER |
| GET | `/quotes/{quote_id}/image` | Get the image for a quote | CUSTOMER |
| DELETE | `/quotes/{quote_id}/image` | Delete the image for a quote | CUSTOMER |
| GET | `/quotes/{quote_id}/pdf` | Generate a PDF for a quote using ReportLab with company logo, image, and tax | CUSTOMER |

---

## 5. Products (`/products`)

**Tier**: Core
**File**: `endpoints/products.py`
**Endpoints**: 6

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/products` | List products with optional filtering | CUSTOMER |
| GET | `/products/{id}` | Get a specific product by ID | CUSTOMER |
| GET | `/products/sku/{sku}` | Get a specific product by SKU | CUSTOMER |
| POST | `/products` | Create a new product | CUSTOMER |
| PUT | `/products/{id}` | Update an existing product | CUSTOMER |
| GET | `/products/{product_id}/routing` | Get routing details for a product. | CUSTOMER |

---

## 6. Items (`/items`)

**Tier**: Core
**File**: `endpoints/items.py`
**Endpoints**: 23

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/items/categories` | List all item categories | PUBLIC |
| GET | `/items/categories/tree` | Get categories as a nested tree structure | PUBLIC |
| POST | `/items/categories` | Create a new item category | CUSTOMER |
| GET | `/items/categories/{category_id}` | Get a specific category by ID | PUBLIC |
| PATCH | `/items/categories/{category_id}` | Update an existing category | CUSTOMER |
| DELETE | `/items/categories/{category_id}` | Soft delete a category (set is_active=False) | CUSTOMER |
| GET | `/items` | List items with filtering and pagination | PUBLIC |
| GET | `/items/stats` | Lightweight item statistics — type counts and reorder alerts. | PUBLIC |
| POST | `/items` | Create a new item | CUSTOMER |
| POST | `/items/{item_id}/duplicate` | Duplicate an existing item with a new SKU and name. | CUSTOMER |
| POST | `/items/material` | Create a material item (shortcut for supply items with material_type/color). | CUSTOMER |
| GET | `/items/low-stock` | Get items that are below their reorder point OR have shortages from active orders. | PUBLIC |
| GET | `/items/price-candidates` | Get items eligible for price suggestions (excludes materials/supplies). | CUSTOMER |
| GET | `/items/{item_id}/demand-summary` | Get demand summary for an inventory item. | PUBLIC |
| GET | `/items/{item_id}` | Get a specific item by ID | PUBLIC |
| GET | `/items/sku/{sku}` | Get a specific item by SKU | PUBLIC |
| PATCH | `/items/{item_id}` | Update an existing item | CUSTOMER |
| DELETE | `/items/{item_id}` | Soft delete an item (set active=False) | CUSTOMER |
| POST | `/items/import` | Import items from CSV file | CUSTOMER |
| POST | `/items/bulk-update` | Bulk update multiple items at once | CUSTOMER |
| POST | `/items/recost-all` | Recost all items matching filters. | CUSTOMER |
| POST | `/items/{item_id}/recost` | Recost a single item. | CUSTOMER |
| POST | `/items/apply-suggested-prices` | Apply selected suggested prices to items. | CUSTOMER |

---

## 7. Production Orders (`/production-orders`)

**Tier**: Core
**File**: `endpoints/production_orders.py`, `endpoints/operation_status.py`
**Endpoints**: 40

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/production-orders/` | List production orders with filtering and pagination. | CUSTOMER |
| POST | `/production-orders/` | Create a new production order. | CUSTOMER |
| GET | `/production-orders/status-transitions` | Get valid status transitions for production orders. | CUSTOMER |
| GET | `/production-orders/{order_id}` | Get a production order by ID. | CUSTOMER |
| PUT | `/production-orders/{order_id}` | Update a production order. | CUSTOMER |
| DELETE | `/production-orders/{order_id}` | Delete a production order. | CUSTOMER |
| GET | `/production-orders/scrap-reasons` | Get list of active scrap reasons. | CUSTOMER |
| GET | `/production-orders/scrap-reasons/all` | Get all scrap reasons including inactive. | CUSTOMER |
| POST | `/production-orders/scrap-reasons` | Create a new scrap reason. | CUSTOMER |
| PUT | `/production-orders/scrap-reasons/{reason_id}` | Update a scrap reason. | CUSTOMER |
| DELETE | `/production-orders/scrap-reasons/{reason_id}` | Delete a scrap reason. | CUSTOMER |
| GET | `/production-orders/qc-statuses` | Get valid QC status values. | CUSTOMER |
| GET | `/production-orders/operation-statuses` | Get valid operation status values. | CUSTOMER |
| POST | `/production-orders/{order_id}/release` | Release a production order for manufacturing. | CUSTOMER |
| POST | `/production-orders/{order_id}/start` | Start production on an order. | CUSTOMER |
| POST | `/production-orders/{order_id}/complete` | Complete a production order. | CUSTOMER |
| POST | `/production-orders/{order_id}/cancel` | Cancel a production order. | CUSTOMER |
| POST | `/production-orders/{order_id}/hold` | Put a production order on hold. | CUSTOMER |
| PUT | `/production-orders/{order_id}/schedule` | Schedule a production order. | CUSTOMER |
| GET | `/production-orders/schedule/summary` | Get production schedule summary. | CUSTOMER |
| GET | `/production-orders/queue/by-work-center` | Get queue of operations by work center. | CUSTOMER |
| POST | `/production-orders/{order_id}/qc` | Record QC inspection results. | CUSTOMER |
| POST | `/production-orders/{order_id}/split` | Split a production order into two. | CUSTOMER |
| POST | `/production-orders/{order_id}/scrap` | Record scrap for a production order. | CUSTOMER |
| PUT | `/production-orders/{order_id}/operations/{operation_id}` | Update a production order operation. | CUSTOMER |
| GET | `/production-orders/{order_id}/material-availability` | Get material availability analysis for a production order. | CUSTOMER |
| GET | `/production-orders/{order_id}/blocking-issues` | Get blocking issues for a production order. | CUSTOMER |
| GET | `/production-orders/{order_id}/required-orders` | Get MRP cascade of required orders. | CUSTOMER |
| GET | `/production-orders/{order_id}/cost-breakdown` | Get cost breakdown for a production order. | CUSTOMER |
| GET | `/production-orders/{order_id}/spools` | Get spools assigned to a production order. | CUSTOMER |
| POST | `/production-orders/{order_id}/spools/{spool_id}` | Assign a spool to a production order. | CUSTOMER |
| GET | `/production-orders/{po_id}/operations` | Get all operations for a production order, ordered by sequence. | CUSTOMER |
| POST | `/production-orders/{po_id}/operations/{op_id}/start` | Start an operation. | CUSTOMER |
| POST | `/production-orders/{po_id}/operations/{op_id}/complete` | Complete an operation with optional partial scrap and cascading material accounting. | CUSTOMER |
| POST | `/production-orders/{po_id}/operations/{op_id}/skip` | Skip an operation with a reason. | CUSTOMER |
| GET | `/production-orders/{po_id}/operations/{op_id}/can-start` | Quick check if an operation can start based on material availability. | CUSTOMER |
| GET | `/production-orders/{po_id}/operations/{op_id}/blocking-issues` | Get detailed blocking issues for an operation. | CUSTOMER |
| POST | `/production-orders/{po_id}/operations/{op_id}/schedule` | Schedule an operation on a resource with time slot validation. | CUSTOMER |
| POST | `/production-orders/resources/next-available` | Find the next available time slot on a resource. | CUSTOMER |
| POST | `/production-orders/{po_id}/operations/generate` | Manually generate operations from routing. | CUSTOMER |

---

## 8. Inventory (`/inventory`)

**Tier**: Core
**File**: `endpoints/inventory.py`
**Endpoints**: 4

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/inventory/transactions/{transaction_id}/approve-negative` | Approve a negative inventory transaction that requires approval. | CUSTOMER |
| GET | `/inventory/negative-inventory-report` | Generate negative inventory report showing all negative inventory occurrences. | CUSTOMER |
| POST | `/inventory/validate-consistency` | Validate inventory consistency: check that allocated doesn't exceed on_hand. | CUSTOMER |
| POST | `/inventory/adjust-quantity` | Adjust inventory on-hand quantity and create an adjustment transaction. | CUSTOMER |

---

## 9. Materials (`/materials`)

**Tier**: Core
**File**: `endpoints/materials.py`
**Endpoints**: 9

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/materials/options` | Get all material options for the quote portal. | PUBLIC |
| GET | `/materials/types` | Get list of material types (for first dropdown). | PUBLIC |
| GET | `/materials/types/{material_type_code}/colors` | Get available colors for a specific material type (for second dropdown). | PUBLIC |
| POST | `/materials/types/{material_type_code}/colors` | Create a new color and link it to a material type. | ADMIN |
| GET | `/materials/for-bom` | Get all materials formatted for BOM usage. | PUBLIC |
| GET | `/materials/for-order` | Get material inventory items formatted for sales order line selection. | CUSTOMER |
| GET | `/materials/pricing/{material_type_code}` | Get pricing information for a material type. | PUBLIC |
| GET | `/materials/import/template` | Download CSV template for material inventory import. | PUBLIC |
| POST | `/materials/import` | Import material inventory from CSV file. | CUSTOMER |

---

## 10. Vendors (`/vendors`)

**Tier**: Core
**File**: `endpoints/vendors.py`
**Endpoints**: 6

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/vendors/` | List all vendors with pagination | CUSTOMER |
| GET | `/vendors/{vendor_id}` | Get vendor details by ID | CUSTOMER |
| POST | `/vendors/` | Create a new vendor | CUSTOMER |
| PUT | `/vendors/{vendor_id}` | Update a vendor | CUSTOMER |
| GET | `/vendors/{vendor_id}/metrics` | Get vendor performance metrics | CUSTOMER |
| DELETE | `/vendors/{vendor_id}` | Delete a vendor (soft delete - marks as inactive) | CUSTOMER |

---

## 11. Purchase Orders (`/purchase-orders`)

**Tier**: Core
**File**: `endpoints/purchase_orders.py`, `endpoints/po_documents.py`, `endpoints/low_stock.py`, `endpoints/vendor_items.py`
**Endpoints**: 31

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/purchase-orders/` | List purchase orders with pagination | CUSTOMER |
| GET | `/purchase-orders/{po_id}` | Get purchase order details by ID | CUSTOMER |
| POST | `/purchase-orders/` | Create a new purchase order | CUSTOMER |
| PUT | `/purchase-orders/{po_id}` | Update a purchase order | CUSTOMER |
| POST | `/purchase-orders/{po_id}/lines` | Add a line to a purchase order | CUSTOMER |
| PUT | `/purchase-orders/{po_id}/lines/{line_id}` | Update a line on a purchase order | CUSTOMER |
| DELETE | `/purchase-orders/{po_id}/lines/{line_id}` | Remove a line from a purchase order | CUSTOMER |
| POST | `/purchase-orders/{po_id}/status` | Update PO status with transition validation | CUSTOMER |
| POST | `/purchase-orders/{po_id}/receive` | Receive items from a purchase order | CUSTOMER |
| POST | `/purchase-orders/{po_id}/upload` | Upload a document for a purchase order (invoice, receipt, etc.) | CUSTOMER |
| DELETE | `/purchase-orders/{po_id}` | Delete a purchase order (draft only) | CUSTOMER |
| GET | `/purchase-orders/{po_id}/events` | List activity events for a purchase order | CUSTOMER |
| POST | `/purchase-orders/{po_id}/events` | Add a manual event to a purchase order (typically a note) | CUSTOMER |
| POST | `/purchase-orders/{po_id}/documents` | Upload a document to a purchase order | CUSTOMER |
| GET | `/purchase-orders/{po_id}/documents` | List all documents attached to a purchase order | PUBLIC |
| GET | `/purchase-orders/{po_id}/documents/{doc_id}` | Get document details by ID | PUBLIC |
| GET | `/purchase-orders/{po_id}/documents/{doc_id}/download` | Download a document | PUBLIC |
| PATCH | `/purchase-orders/{po_id}/documents/{doc_id}` | Update document metadata (type, notes) | CUSTOMER |
| DELETE | `/purchase-orders/{po_id}/documents/{doc_id}` | Delete a document | CUSTOMER |
| POST | `/purchase-orders/{po_id}/documents/bulk` | Upload multiple documents at once | CUSTOMER |
| GET | `/purchase-orders/low-stock` | Get all products below their reorder point, grouped by preferred vendor | PUBLIC |
| POST | `/purchase-orders/from-low-stock` | Create a purchase order from selected low-stock items | CUSTOMER |
| POST | `/purchase-orders/quick-reorder/{product_id}` | Quick one-click reorder for a single product | CUSTOMER |
| GET | `/purchase-orders/vendors/{vendor_id}/items` | List all SKU mappings for a vendor. | CUSTOMER |
| POST | `/purchase-orders/vendors/{vendor_id}/items` | Create a new vendor SKU mapping. | CUSTOMER |
| GET | `/purchase-orders/vendors/{vendor_id}/items/{item_id}` | Get a specific vendor item mapping. | CUSTOMER |
| PUT | `/purchase-orders/vendors/{vendor_id}/items/{item_id}` | Update a vendor item mapping. | CUSTOMER |
| DELETE | `/purchase-orders/vendors/{vendor_id}/items/{item_id}` | Delete a vendor item mapping. | CUSTOMER |
| GET | `/purchase-orders/vendor-items/search` | Search vendor items across all vendors. | CUSTOMER |
| POST | `/purchase-orders/vendor-items/suggest-match` | Get product suggestions for a vendor SKU. | CUSTOMER |
| POST | `/purchase-orders/vendor-items/bulk-update-last-seen` | Bulk update last_seen_at and increment times_ordered for vendor items. | CUSTOMER |

---

## 12. Work Centers (`/work-centers`)

**Tier**: Core
**File**: `endpoints/work_centers.py`
**Endpoints**: 13

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/work-centers/` | List all work centers. | CUSTOMER |
| POST | `/work-centers/` | Create a new work center. | CUSTOMER |
| GET | `/work-centers/{wc_id}` | Get a work center by ID. | CUSTOMER |
| PUT | `/work-centers/{wc_id}` | Update a work center. | CUSTOMER |
| DELETE | `/work-centers/{wc_id}` | Delete a work center (soft delete - marks as inactive). | CUSTOMER |
| GET | `/work-centers/{wc_id}/resources` | List all resources for a work center. | CUSTOMER |
| POST | `/work-centers/{wc_id}/resources` | Create a new resource (machine) in a work center. | CUSTOMER |
| GET | `/work-centers/resources/{resource_id}` | Get a resource by ID. | CUSTOMER |
| PUT | `/work-centers/resources/{resource_id}` | Update a resource. | CUSTOMER |
| DELETE | `/work-centers/resources/{resource_id}` | Delete a resource. | CUSTOMER |
| PATCH | `/work-centers/resources/{resource_id}/status` | Quick update of resource status. | CUSTOMER |
| GET | `/work-centers/{wc_id}/printers` | List printers assigned to a work center. | CUSTOMER |
| POST | `/work-centers/sync-bambu` | Sync printers from Bambu Print Suite configuration. | CUSTOMER |

---

## 13. Resources (`/resources`)

**Tier**: Core
**File**: `endpoints/resources.py`
**Endpoints**: 2

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/resources/{resource_id}/schedule` | Get scheduled operations for a resource. | CUSTOMER |
| GET | `/resources/{resource_id}/conflicts` | Check if a time range conflicts with existing scheduled operations. | CUSTOMER |

---

## 14. Routings (`/routings`)

**Tier**: Core
**File**: `endpoints/routings.py`
**Endpoints**: 17

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/routings/` | List all routings. | PUBLIC |
| POST | `/routings/` | Create a new routing for a product or a template routing. | CUSTOMER |
| POST | `/routings/seed-templates` | Seed the two standard routing templates: | CUSTOMER |
| POST | `/routings/apply-template` | Apply a routing template to a product, creating a product-specific routing. | CUSTOMER |
| GET | `/routings/{routing_id}` | Get a routing by ID with all operations. | PUBLIC |
| GET | `/routings/product/{product_id}` | Get the active routing for a product. | PUBLIC |
| PUT | `/routings/{routing_id}` | Update a routing. | CUSTOMER |
| DELETE | `/routings/{routing_id}` | Delete a routing (soft delete - marks as inactive). | CUSTOMER |
| GET | `/routings/{routing_id}/operations` | List all operations for a routing. | PUBLIC |
| POST | `/routings/{routing_id}/operations` | Add a new operation to a routing. | CUSTOMER |
| PUT | `/routings/operations/{operation_id}` | Update a routing operation. | CUSTOMER |
| DELETE | `/routings/operations/{operation_id}` | Delete a routing operation (soft delete). | CUSTOMER |
| GET | `/routings/operations/{operation_id}/materials` | List all materials for a routing operation. | PUBLIC |
| POST | `/routings/operations/{operation_id}/materials` | Add a material to a routing operation. | CUSTOMER |
| PUT | `/routings/materials/{material_id}` | Update a routing operation material. | CUSTOMER |
| DELETE | `/routings/materials/{material_id}` | Delete a routing operation material. | CUSTOMER |
| GET | `/routings/manufacturing-bom/{product_id}` | Get the complete Manufacturing BOM for a product. | PUBLIC |

---

## 15. Mrp (`/mrp`)

**Tier**: Core
**File**: `endpoints/mrp.py`
**Endpoints**: 11

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/mrp/run` | Run MRP calculation. | STAFF |
| GET | `/mrp/runs` | List recent MRP runs | PUBLIC |
| GET | `/mrp/runs/{run_id}` | Get details of a specific MRP run | PUBLIC |
| GET | `/mrp/planned-orders` | List planned orders with optional filters | PUBLIC |
| GET | `/mrp/planned-orders/{order_id}` | Get a specific planned order | PUBLIC |
| POST | `/mrp/planned-orders/{order_id}/firm` | Firm a planned order. | PUBLIC |
| POST | `/mrp/planned-orders/{order_id}/release` | Release a planned order to an actual PO or MO. | PUBLIC |
| DELETE | `/mrp/planned-orders/{order_id}` | Cancel/delete a planned order | PUBLIC |
| GET | `/mrp/requirements` | Calculate and return material requirements. | PUBLIC |
| GET | `/mrp/supply-demand/{product_id}` | Get supply and demand timeline for a product. | PUBLIC |
| GET | `/mrp/explode-bom/{product_id}` | Explode a BOM to see all component requirements. | PUBLIC |

---

## 16. Scheduling (`/scheduling`)

**Tier**: Core
**File**: `endpoints/scheduling.py`
**Endpoints**: 4

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/scheduling/capacity/check` | Check if a machine has capacity for a production order at a given time. | CUSTOMER |
| GET | `/scheduling/capacity/available-slots` | Find available time slots for a resource within a date range. | CUSTOMER |
| GET | `/scheduling/capacity/machine-availability` | Get availability status for all machines in a date range. | CUSTOMER |
| POST | `/scheduling/auto-schedule` | Automatically find the best available slot for a production order. | CUSTOMER |

---

## 17. Settings (`/settings`)

**Tier**: Core
**File**: `endpoints/settings.py`
**Endpoints**: 11

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/settings/company` | Get company settings | CUSTOMER |
| PATCH | `/settings/company` | Update company settings | ADMIN |
| POST | `/settings/company/logo` | Upload company logo | ADMIN |
| GET | `/settings/company/logo` | Get company logo image (no auth required for PDF generation) | PUBLIC |
| DELETE | `/settings/company/logo` | Delete company logo | ADMIN |
| GET | `/settings/ai` | Get AI configuration settings (API keys masked) | CUSTOMER |
| PATCH | `/settings/ai` | Update AI configuration settings | ADMIN |
| POST | `/settings/ai/test` | Test the configured AI connection | ADMIN |
| POST | `/settings/ai/start-ollama` | Attempt to start the Ollama service | ADMIN |
| GET | `/settings/ai/anthropic-status` | Check if the anthropic package is installed. | CUSTOMER |
| POST | `/settings/ai/install-anthropic` | Install the anthropic Python package. | ADMIN |

---

## 18. Tax Rates (`/tax-rates`)

**Tier**: Core
**File**: `endpoints/tax_rates.py`
**Endpoints**: 5

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/tax-rates` | List active tax rates. Pass include_inactive=true to see all. | CUSTOMER |
| GET | `/tax-rates/{tax_rate_id}` | Get tax rate | CUSTOMER |
| POST | `/tax-rates` | Create tax rate | ADMIN |
| PATCH | `/tax-rates/{tax_rate_id}` | Update tax rate | ADMIN |
| DELETE | `/tax-rates/{tax_rate_id}` | Delete tax rate | ADMIN |

---

## 19. Payments (`/payments`)

**Tier**: Core
**File**: `endpoints/payments.py`
**Endpoints**: 8

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/payments` | Record a new payment for a sales order. | CUSTOMER |
| POST | `/payments/refund` | Record a refund for a sales order. | CUSTOMER |
| GET | `/payments` | List payments with filtering and pagination. | CUSTOMER |
| GET | `/payments/dashboard` | Get payment dashboard statistics. | CUSTOMER |
| GET | `/payments/order/{order_id}/summary` | Get payment summary for a specific order. | CUSTOMER |
| GET | `/payments/{payment_id}` | Get a specific payment by ID. | CUSTOMER |
| PATCH | `/payments/{payment_id}` | Update a payment record (limited to notes and status). | CUSTOMER |
| DELETE | `/payments/{payment_id}` | Void a payment (sets status to 'voided', doesn't delete). | CUSTOMER |

---

## 20. Accounting (`/accounting`)

**Tier**: Core
**File**: `endpoints/accounting.py`
**Endpoints**: 8

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/accounting/trial-balance` | Generate a trial balance report. | ADMIN |
| GET | `/accounting/inventory-valuation` | Generate an inventory valuation report with GL reconciliation. | ADMIN |
| GET | `/accounting/ledger/{account_code}` | Get the transaction ledger for a specific GL account. | ADMIN |
| GET | `/accounting/periods` | List all fiscal periods with summary information. | ADMIN |
| POST | `/accounting/periods/{period_id}/close` | Close a fiscal period. | ADMIN |
| POST | `/accounting/periods/{period_id}/reopen` | Reopen a closed fiscal period. | ADMIN |
| GET | `/accounting/summary` | Get a quick financial summary for the dashboard. | ADMIN |
| GET | `/accounting/recent-entries` | Get recent journal entries for dashboard display. | ADMIN |

---

## 21. Printers (`/printers`)

**Tier**: Core
**File**: `endpoints/printers.py`
**Endpoints**: 13

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/printers/generate-code` | Generate a new unique printer code | CUSTOMER |
| GET | `/printers/brands/info` | Get information about supported printer brands | CUSTOMER |
| GET | `/printers/active-work` | Get active/scheduled work for all printers. | CUSTOMER |
| GET | `/printers/` | List all printers with filtering and pagination | CUSTOMER |
| GET | `/printers/{printer_id}` | Get a single printer by ID | CUSTOMER |
| POST | `/printers/` | Create a new printer | CUSTOMER |
| PUT | `/printers/{printer_id}` | Update an existing printer | CUSTOMER |
| DELETE | `/printers/{printer_id}` | Delete a printer | CUSTOMER |
| PATCH | `/printers/{printer_id}/status` | Update printer status | CUSTOMER |
| POST | `/printers/discover` | Discover printers on the local network | CUSTOMER |
| POST | `/printers/probe-ip` | Probe an IP address to detect printer info. | CUSTOMER |
| POST | `/printers/test-connection` | Test connection to a printer | CUSTOMER |
| POST | `/printers/import-csv` | Import printers from CSV data | CUSTOMER |

---

## 22. System (`/system`)

**Tier**: Core
**File**: `endpoints/system.py`
**Endpoints**: 5

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/system/version` | Get current FilaOps version and build date. | PUBLIC |
| GET | `/system/info` | Get system tier and enabled features. | PUBLIC |
| GET | `/system/updates/check` | Check GitHub releases for available updates | PUBLIC |
| GET | `/system/updates/instructions` | Get step-by-step update instructions for current deployment method | PUBLIC |
| GET | `/system/health` | System health check endpoint | PUBLIC |

---

## 23. Security (`/security`)

**Tier**: Core
**File**: `endpoints/security.py`
**Endpoints**: 13

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/security/audit` | Run security audit and return results. | ADMIN |
| GET | `/security/audit/export` | Export security audit report. | ADMIN |
| GET | `/security/status` | Get quick security status overview. | ADMIN |
| POST | `/security/remediate/generate-secret-key` | Generate a secure SECRET_KEY for the user to copy. | ADMIN |
| POST | `/security/remediate/open-env-file` | Open the .env file in the system's default text editor. | ADMIN |
| POST | `/security/remediate/update-secret-key` | Automatically update the SECRET_KEY in the .env file. | ADMIN |
| POST | `/security/remediate/open-restart-terminal` | Open a terminal window with instructions to restart the backend. | ADMIN |
| POST | `/security/remediate/fix-dependencies` | Automatically scan and fix vulnerable dependencies. | ADMIN |
| POST | `/security/remediate/fix-rate-limiting` | Automatically install slowapi for rate limiting. | ADMIN |
| POST | `/security/remediate/setup-https` | Automatically set up HTTPS with Caddy reverse proxy. | ADMIN |
| GET | `/security/remediate/check-caddy` | Check if Caddy is installed and get its version. | ADMIN |
| POST | `/security/remediate/fix-dotfile-blocking` | Automatically update Caddyfile to block access to dotfiles (.env, .git, etc.). | ADMIN |
| GET | `/security/remediate/{check_id}` | Get detailed remediation steps for a specific check. | ADMIN |

---

## 24. Spools (`/spools`)

**Tier**: Core
**File**: `endpoints/spools.py`
**Endpoints**: 8

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/spools/` | List all material spools with optional filters. | CUSTOMER |
| GET | `/spools/{spool_id}` | Get details for a specific spool including usage history. | CUSTOMER |
| POST | `/spools/` | Create a new material spool. | CUSTOMER |
| PATCH | `/spools/{spool_id}` | Update spool information (weight, status, location, notes). | CUSTOMER |
| GET | `/spools/product/{product_id}/available` | Get available spools for a product, optionally filtered by minimum weight. | CUSTOMER |
| GET | `/spools/traceability/production-order/{production_order_id}` | Get spool traceability information for a production order. | CUSTOMER |
| GET | `/spools/traceability/spool/{spool_id}` | Get full traceability for a spool: which production orders used it, which finished goods were produced. | CUSTOMER |
| POST | `/spools/{spool_id}/consume` | Record material consumption from a spool for a production order. | CUSTOMER |

---

## 25. Traceability (`/traceability`)

**Tier**: Core
**File**: `endpoints/traceability.py`
**Endpoints**: 4

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/traceability/forward/spool/{spool_id}` | Trace a spool forward to all products and customers. | CUSTOMER |
| GET | `/traceability/backward/serial/{serial_number}` | Trace a serial number back to source materials and vendor. | CUSTOMER |
| GET | `/traceability/backward/sales-order/{so_id}` | Trace a sales order back to all source materials. | CUSTOMER |
| POST | `/traceability/recall-impact` | Calculate the impact of recalling specific spools. | CUSTOMER |

---

## 26. Maintenance (`/maintenance`)

**Tier**: Core
**File**: `endpoints/maintenance.py`
**Endpoints**: 7

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/maintenance/` | List all maintenance logs with filtering and pagination | CUSTOMER |
| GET | `/maintenance/due` | Get printers that are due for maintenance | CUSTOMER |
| GET | `/maintenance/{log_id}` | Get a single maintenance log by ID | CUSTOMER |
| GET | `/maintenance/printers/{printer_id}/maintenance` | List all maintenance logs for a specific printer | CUSTOMER |
| POST | `/maintenance/printers/{printer_id}/maintenance` | Add a maintenance log entry for a printer | CUSTOMER |
| PUT | `/maintenance/{log_id}` | Update an existing maintenance log | CUSTOMER |
| DELETE | `/maintenance/{log_id}` | Delete a maintenance log | CUSTOMER |

---

## 27. Command Center (`/command-center`)

**Tier**: Core
**File**: `endpoints/command_center.py`
**Endpoints**: 3

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/command-center/action-items` | Get prioritized list of action items requiring attention. | ADMIN |
| GET | `/command-center/summary` | Get aggregate statistics for today's operations. | ADMIN |
| GET | `/command-center/resources` | Get current status of all resources/machines. | ADMIN |

---

## 28. Admin (`/admin`)
### 28.1. Users (`/admin/users`)

**Tier**: Core
**File**: `endpoints/admin/users.py`
**Endpoints**: 8

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/users/` | List all admin and operator users. | ADMIN |
| GET | `/admin/users/stats/summary` | Get summary stats for admin/operator users. | ADMIN |
| GET | `/admin/users/{user_id}` | Get a single admin or operator user. | ADMIN |
| POST | `/admin/users/` | Create a new admin or operator user. | ADMIN |
| PATCH | `/admin/users/{user_id}` | Update an admin or operator user. | ADMIN |
| POST | `/admin/users/{user_id}/reset-password` | Reset password for an admin or operator user. | ADMIN |
| DELETE | `/admin/users/{user_id}` | Deactivate an admin or operator user. | ADMIN |
| POST | `/admin/users/{user_id}/reactivate` | Reactivate a previously deactivated admin or operator user. | ADMIN |

### 28.2. Customers (`/admin/customers`)

**Tier**: Core
**File**: `endpoints/admin/customers.py`
**Endpoints**: 10

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/customers/` | List all customers with optional filters. | ADMIN |
| GET | `/admin/customers/search` | Quick search for customer dropdown/autocomplete. | ADMIN |
| GET | `/admin/customers/{customer_id}` | Get a single customer with full details. | ADMIN |
| POST | `/admin/customers/` | Create a new customer. | ADMIN |
| PATCH | `/admin/customers/{customer_id}` | Update a customer. | ADMIN |
| DELETE | `/admin/customers/{customer_id}` | Delete a customer (soft-deactivate if orders exist, hard-delete otherwise). | ADMIN |
| GET | `/admin/customers/{customer_id}/orders` | Get recent orders for a customer. | ADMIN |
| GET | `/admin/customers/import/template` | Download a CSV template for customer import. | ADMIN |
| POST | `/admin/customers/import/preview` | Preview CSV import - validates data and returns parsed rows with errors. | ADMIN |
| POST | `/admin/customers/import` | Import customers from CSV file. | ADMIN |

### 28.3. Bom (`/admin/bom`)

**Tier**: Core
**File**: `endpoints/admin/bom.py`
**Endpoints**: 15

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/bom/` | List all BOMs with summary info. | STAFF |
| GET | `/admin/bom/{bom_id}` | Get a single BOM with all lines and component details. | STAFF |
| POST | `/admin/bom/` | Create or update a BOM for a product. | STAFF |
| PATCH | `/admin/bom/{bom_id}` | Update BOM header fields (not lines). | STAFF |
| DELETE | `/admin/bom/{bom_id}` | Delete a BOM (soft delete by setting active=False). | STAFF |
| POST | `/admin/bom/{bom_id}/lines` | Add a new line to a BOM. | STAFF |
| PATCH | `/admin/bom/{bom_id}/lines/{line_id}` | Update a BOM line. | STAFF |
| DELETE | `/admin/bom/{bom_id}/lines/{line_id}` | Delete a BOM line. | STAFF |
| POST | `/admin/bom/{bom_id}/recalculate` | Recalculate BOM total cost from current component costs. | STAFF |
| POST | `/admin/bom/{bom_id}/copy` | Copy a BOM to another product. | STAFF |
| GET | `/admin/bom/product/{product_id}` | Get the active BOM for a product. | STAFF |
| GET | `/admin/bom/{bom_id}/explode` | Explode a BOM to show all components at all levels. | STAFF |
| GET | `/admin/bom/{bom_id}/cost-rollup` | Get a detailed cost breakdown with sub-assembly costs rolled up. | STAFF |
| GET | `/admin/bom/where-used/{product_id}` | Find all BOMs that use a specific product as a component. | STAFF |
| POST | `/admin/bom/{bom_id}/validate` | Validate a BOM for issues like circular references, missing costs, etc. | STAFF |

### 28.4. Dashboard (`/admin/dashboard`)

**Tier**: Core
**File**: `endpoints/admin/dashboard.py`
**Endpoints**: 11

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/dashboard/` | Get admin dashboard with summary stats and module navigation. | STAFF |
| GET | `/admin/dashboard/summary` | Get dashboard summary stats organized by module. | STAFF |
| GET | `/admin/dashboard/recent-orders` | Get recent orders for dashboard display. | STAFF |
| GET | `/admin/dashboard/pending-bom-reviews` | Get BOMs that need admin review. | STAFF |
| GET | `/admin/dashboard/sales-trend` | Get sales trend data for charting. | STAFF |
| GET | `/admin/dashboard/shipping-trend` | Get shipping trend data for charting. | STAFF |
| GET | `/admin/dashboard/production-trend` | Get production trend data for charting. | STAFF |
| GET | `/admin/dashboard/purchasing-trend` | Get purchasing trend data for charting. | STAFF |
| GET | `/admin/dashboard/stats` | Get quick stats for dashboard header. | STAFF |
| GET | `/admin/dashboard/modules` | Get list of available admin modules. | STAFF |
| GET | `/admin/dashboard/profit-summary` | Get profit and revenue summary for the dashboard. | STAFF |

### 28.5. Analytics (`/admin/analytics`)

**Tier**: Core
**File**: `endpoints/admin/analytics.py`
**Endpoints**: 1

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/analytics/dashboard` | Get comprehensive analytics dashboard (Pro feature) | ADMIN |

### 28.6. Fulfillment Queue (`/admin/fulfillment`)

**Tier**: Core
**File**: `endpoints/admin/fulfillment_queue.py`
**Endpoints**: 8

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/fulfillment/stats` | Get fulfillment dashboard statistics. | STAFF |
| GET | `/admin/fulfillment/queue` | Get the production queue with all orders that need to be fulfilled. | STAFF |
| GET | `/admin/fulfillment/queue/{production_order_id}` | Get detailed information about a specific production order. | STAFF |
| POST | `/admin/fulfillment/queue/{production_order_id}/start` | Start production on an order. | STAFF |
| POST | `/admin/fulfillment/queue/{production_order_id}/complete-print` | Mark printing as complete with good/bad quantity tracking. | STAFF |
| POST | `/admin/fulfillment/queue/{production_order_id}/pass-qc` | Mark order as passed QC, receipt finished goods, and mark ready to ship. | STAFF |
| POST | `/admin/fulfillment/queue/{production_order_id}/fail-qc` | Mark order as failed QC. | STAFF |
| POST | `/admin/fulfillment/bulk-update` | Update status for multiple production orders at once. | STAFF |

### 28.7. Fulfillment Shipping (`/admin/fulfillment`)

**Tier**: Core
**File**: `endpoints/admin/fulfillment_shipping.py`
**Endpoints**: 9

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/fulfillment/ready-to-ship` | Get all orders that are ready to ship. | STAFF |
| GET | `/admin/fulfillment/ship/boxes` | Get all available shipping boxes for shipper selection. | STAFF |
| POST | `/admin/fulfillment/ship/consolidate/get-rates` | Get shipping rates for multiple orders consolidated into one package. | PUBLIC |
| POST | `/admin/fulfillment/ship/consolidate/buy-label` | Purchase a shipping label for consolidated orders. | PUBLIC |
| POST | `/admin/fulfillment/ship/{sales_order_id}/get-rates` | Get shipping rate options for an order. | STAFF |
| POST | `/admin/fulfillment/ship/{sales_order_id}/buy-label` | Purchase a shipping label for an order. | STAFF |
| POST | `/admin/fulfillment/ship-from-stock/{sales_order_id}/check` | Check if a sales order can be fulfilled directly from existing FG inventory. | STAFF |
| POST | `/admin/fulfillment/ship-from-stock/{sales_order_id}/ship` | Ship a sales order directly from existing FG inventory (Ship-from-Stock path). | STAFF |
| POST | `/admin/fulfillment/ship/{sales_order_id}/mark-shipped` | Manually mark an order as shipped (for when label was created outside system). | STAFF |

### 28.8. Audit (`/admin/audit`)

**Tier**: Core
**File**: `endpoints/admin/audit.py`
**Endpoints**: 4

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/audit/transactions` | Run a transaction audit to find gaps in inventory tracking. | PUBLIC |
| GET | `/admin/audit/transactions/order/{order_id}` | Audit a single order for transaction gaps. | PUBLIC |
| GET | `/admin/audit/transactions/timeline/{order_id}` | Get the complete transaction timeline for an order. | PUBLIC |
| GET | `/admin/audit/transactions/summary` | Get a quick summary of transaction health across all active orders. | PUBLIC |

### 28.9. Accounting (`/admin/accounting`)

**Tier**: Core
**File**: `endpoints/admin/accounting.py`
**Endpoints**: 12

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/accounting/inventory-by-account` | Get inventory balances organized by accounting category. | PUBLIC |
| GET | `/admin/accounting/transactions-journal` | Get inventory transactions formatted as journal entries. | PUBLIC |
| GET | `/admin/accounting/order-cost-breakdown/{order_id}` | Get a cost breakdown for a specific sales order. | PUBLIC |
| GET | `/admin/accounting/cogs-summary` | Get COGS summary for recent period. | PUBLIC |
| GET | `/admin/accounting/dashboard` | Get accounting dashboard with key financial metrics. | PUBLIC |
| GET | `/admin/accounting/sales-journal` | Get sales journal - all sales transactions for the period. | PUBLIC |
| GET | `/admin/accounting/sales-journal/export` | Export sales journal as CSV. | PUBLIC |
| GET | `/admin/accounting/tax-summary` | Get tax summary for filing preparation. | PUBLIC |
| GET | `/admin/accounting/tax-summary/export` | Export tax summary as CSV for filing. | PUBLIC |
| GET | `/admin/accounting/payments-journal` | Get payments journal - all payment transactions for the period. | PUBLIC |
| GET | `/admin/accounting/payments-journal/export` | Export payments journal as CSV. | PUBLIC |
| GET | `/admin/accounting/export/sales` | Export sales data for tax time / accounting purposes. | STAFF |

### 28.10. Traceability (`/admin/traceability`)

**Tier**: Core
**File**: `endpoints/admin/traceability.py`
**Endpoints**: 18

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/traceability/profiles` | List all customer traceability profiles. | CUSTOMER |
| GET | `/admin/traceability/profiles/{user_id}` | Get traceability profile for a specific customer. | CUSTOMER |
| POST | `/admin/traceability/profiles` | Create a traceability profile for a customer. | CUSTOMER |
| PATCH | `/admin/traceability/profiles/{user_id}` | Update a customer's traceability profile. | CUSTOMER |
| GET | `/admin/traceability/lots` | List material lots with filtering and pagination. | CUSTOMER |
| GET | `/admin/traceability/lots/{lot_id}` | Get a specific material lot by ID. | CUSTOMER |
| POST | `/admin/traceability/lots` | Create a new material lot (typically when receiving materials). | CUSTOMER |
| PATCH | `/admin/traceability/lots/{lot_id}` | Update a material lot. | CUSTOMER |
| POST | `/admin/traceability/lots/generate-number` | Generate the next lot number for a material. | CUSTOMER |
| GET | `/admin/traceability/serials` | List serial numbers with filtering and pagination. | CUSTOMER |
| GET | `/admin/traceability/serials/{serial_id}` | Get a specific serial number by ID. | CUSTOMER |
| GET | `/admin/traceability/serials/lookup/{serial_number}` | Look up a serial number by the serial string. | CUSTOMER |
| POST | `/admin/traceability/serials` | Generate serial numbers for a production order. | CUSTOMER |
| PATCH | `/admin/traceability/serials/{serial_id}` | Update a serial number (e.g., mark as sold, shipped, returned). | CUSTOMER |
| POST | `/admin/traceability/consumptions` | Record material lot consumption for a production order. | CUSTOMER |
| GET | `/admin/traceability/consumptions/production/{production_order_id}` | Get all lot consumptions for a production order. | CUSTOMER |
| GET | `/admin/traceability/recall/forward/{lot_number}` | Forward recall query: What did we make with this lot? | CUSTOMER |
| GET | `/admin/traceability/recall/backward/{serial_number}` | Backward recall query: What material lots went into this serial number? | CUSTOMER |

### 28.11. Inventory Transactions (`/admin/inventory`)

**Tier**: Core
**File**: `endpoints/admin/inventory_transactions.py`
**Endpoints**: 6

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/inventory/transactions/adjustment-reasons` | List all adjustment reasons for dropdown selection. | STAFF |
| GET | `/admin/inventory/transactions` | List inventory transactions with filters. | STAFF |
| POST | `/admin/inventory/transactions` | Create an inventory transaction. | STAFF |
| GET | `/admin/inventory/transactions/locations` | List all inventory locations. | STAFF |
| POST | `/admin/inventory/transactions/batch` | Batch update inventory quantities for cycle counting. | STAFF |
| GET | `/admin/inventory/transactions/inventory-summary` | Get inventory summary for cycle counting. | STAFF |

### 28.12. Export (`/admin/export`)

**Tier**: Core
**File**: `endpoints/admin/export.py`
**Endpoints**: 2

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/export/products` | Export products to CSV. | STAFF |
| GET | `/admin/export/orders` | Export sales orders to CSV. | STAFF |

### 28.13. Data Import (`/admin/import`)

**Tier**: Core
**File**: `endpoints/admin/data_import.py`
**Endpoints**: 2

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/admin/import/products` | Import products from CSV. | STAFF |
| POST | `/admin/import/inventory` | Import inventory from CSV. | STAFF |

### 28.14. Orders (`/admin/orders`)

**Tier**: Core
**File**: `endpoints/admin/orders.py`
**Endpoints**: 2

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/orders/import/template` | Download CSV template for order import. | PUBLIC |
| POST | `/admin/orders/import` | Import orders from CSV file. | STAFF |

### 28.15. Uom (`/admin/uom`)

**Tier**: Core
**File**: `endpoints/admin/uom.py`
**Endpoints**: 6

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/uom/` | List all units of measure. | ADMIN |
| GET | `/admin/uom/classes` | List all UOM classes with their units. | ADMIN |
| POST | `/admin/uom/convert` | Convert a quantity from one unit to another. | ADMIN |
| GET | `/admin/uom/{code}` | Get a single unit of measure by code. | ADMIN |
| POST | `/admin/uom/` | Create a new unit of measure. | ADMIN |
| PATCH | `/admin/uom/{code}` | Update an existing unit of measure. | ADMIN |

### 28.16. Locations (`/admin/locations`)

**Tier**: Core
**File**: `endpoints/admin/locations.py`
**Endpoints**: 5

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/locations` | List all inventory locations | STAFF |
| GET | `/admin/locations/{location_id}` | Get a single location by ID | STAFF |
| POST | `/admin/locations` | Create a new inventory location | STAFF |
| PUT | `/admin/locations/{location_id}` | Update an inventory location | STAFF |
| DELETE | `/admin/locations/{location_id}` | Soft delete (deactivate) an inventory location | STAFF |

### 28.17. System (`/admin/system`)

**Tier**: Core
**File**: `endpoints/admin/system.py`
**Endpoints**: 3

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/system/update/status` | Get current update status | ADMIN |
| POST | `/admin/system/update/start` | Start system update | ADMIN |
| GET | `/admin/system/version` | Get current system version | ADMIN |

### 28.18. Uploads (`/admin/uploads`)

**Tier**: Core
**File**: `endpoints/admin/uploads.py`
**Endpoints**: 2

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/admin/uploads/product-image` | Upload a product image. | CUSTOMER |
| DELETE | `/admin/uploads/product-image/{filename}` | Delete a previously uploaded product image. | CUSTOMER |


---

## Pagination

Most list endpoints return paginated responses:

```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 50,
  "pages": 2
}
```

---

## Filtering

Most list endpoints support filtering via query parameters:

- `status` - Filter by status
- `search` - Text search
- `date_from`, `date_to` - Date range
- `product_id`, `customer_id`, etc. - Foreign key filters

---

## Versioning

Current API version: `v1`

All endpoints are prefixed with `/api/v1/`

---

*Last updated: 2026-03-22*
*Generated for FilaOps Core v3.5.0*
