<!-- AUTO-GENERATED — Do not edit manually. Regenerate: cd backend && python scripts/generate_api_reference.py -->

# FilaOps API Reference

> Complete API endpoint documentation for FilaOps Core ERP system.
> Generated for AI consumption and developer reference.
> This document covers **Core (Open Source)** API endpoints only.

## Overview

| Metric | Count |
| ------ | ----- |
| **Total Endpoints** | ~444 |
| **Router Files** | 49 |
| **Router Groups** | 28 (including 18 admin sub-modules) |
| **Base Path** | `/api/v1/` |

### HTTP Method Distribution

- **GET**: ~218 endpoints (read/query operations)
- **POST**: ~153 endpoints (create/execute operations)
- **PUT/PATCH**: ~42 endpoints (update operations)
- **DELETE**: ~31 endpoints (delete operations)

---

## Authentication

All endpoints except those marked `PUBLIC` require JWT Bearer token authentication.

```http
Authorization: Bearer <access_token>
```

### Auth Levels

- **PUBLIC**: No authentication required
- **CUSTOMER**: Requires valid JWT (any user type); the route only returns or changes the caller's own records
- **STAFF**: Requires `account_type` in ['admin', 'operator']
- **STAFF (OWN)**: Requires a staff account; an admin reaches every record, an operator only the records that operator owns (403 otherwise)
- **ADMIN**: Requires `account_type` = 'admin'

Since 4.2.0, every route that is not marked PUBLIC or CUSTOMER refuses customer
accounts with 403. The CUSTOMER routes are `GET /auth/me` and the customer
quote routes (`POST /quotes/portal`, `POST /quotes/portal/{quote_id}/accept`,
`POST /quotes/portal/{quote_id}/checkout`, `GET /quotes/{quote_id}/archive`,
`GET /quotes/{quote_id}/files`, `GET /quotes/{quote_id}/files/{file_id}/download`).

Eight sales-order routes are marked STAFF (OWN): the order list, order detail,
material requirements, cancel, and the `events` and `shipping-events` routes
(GET and POST). An admin reaches every order; an operator gets only the orders
that operator owns (the list returns only those, the others answer 403).

---

## 1. Auth (`/auth`)

**Tier**: Core
**File**: `endpoints/auth.py`
**Endpoints**: 10

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/auth/register` | Register a new customer account (403 unless `ENABLE_PUBLIC_QUOTER=true`) | PUBLIC |
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
**Endpoints**: 33

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/sales-orders/status-transitions` | Get valid status transitions for sales orders. | STAFF |
| GET | `/sales-orders/payment-statuses` | Get valid payment status values for sales orders. | STAFF |
| GET | `/sales-orders/can-ship` | Preflight: which ready_to_ship orders can ship right now (batch, read-only). | STAFF |
| POST | `/sales-orders/` | Create a manual sales order (line_item type). | STAFF |
| POST | `/sales-orders/convert/{quote_id}` | Convert an accepted quote to a sales order. | STAFF |
| GET | `/sales-orders/` | Get list of sales orders. | STAFF (OWN) |
| GET | `/sales-orders/{order_id}` | Get detailed information about a specific sales order. | STAFF (OWN) |
| GET | `/sales-orders/{order_id}/packing-slip/pdf` | Generate and return a packing slip PDF for a sales order. | ADMIN |
| GET | `/sales-orders/{order_id}/required-orders` | Get full MRP cascade of WOs and POs needed to fulfill this sales order. | ADMIN |
| GET | `/sales-orders/{order_id}/blocking-issues` | Get blocking issues analysis for a sales order. | STAFF |
| GET | `/sales-orders/{order_id}/fulfillment-status` | Get fulfillment status for a sales order. | STAFF |
| GET | `/sales-orders/{order_id}/can-ship` | Preflight for one order in any status: can it ship right now, and if not, why. | STAFF |
| GET | `/sales-orders/{order_id}/material-requirements` | Get material requirements for a sales order. | STAFF (OWN) |
| POST | `/sales-orders/{order_id}/pre-flight-check` | Pre-flight check before confirming a sales order. | STAFF |
| PATCH | `/sales-orders/{order_id}/status` | Update sales order status (admin only). | ADMIN |
| PATCH | `/sales-orders/{order_id}/payment` | Update payment information for an order (admin only). | ADMIN |
| PATCH | `/sales-orders/{order_id}/shipping` | Update shipping information for an order (admin only). | ADMIN |
| PATCH | `/sales-orders/{order_id}/address` | Update shipping address for an order (admin only). | ADMIN |
| POST | `/sales-orders/{order_id}/cancel` | Cancel a sales order. | STAFF (OWN) |
| PATCH | `/sales-orders/{order_id}/lines` | Edit line item quantities on a sales order. | ADMIN |
| DELETE | `/sales-orders/{order_id}/lines/{line_id}` | Remove a line item from a sales order. | ADMIN |
| GET | `/sales-orders/{order_id}/close-short-preview` | Preview close-short: shows per-line achievable quantities and PO status. | ADMIN |
| POST | `/sales-orders/{order_id}/close-short` | Close an order short — accept partial fulfillment, transition to ready_to_ship. | ADMIN |
| POST | `/sales-orders/{order_id}/confirm` | Confirm a pending_confirmation order from an external source. | ADMIN |
| POST | `/sales-orders/{order_id}/reject` | Reject a pending_confirmation order from an external source. | ADMIN |
| DELETE | `/sales-orders/{order_id}` | Delete a sales order (admin only). | ADMIN |
| POST | `/sales-orders/{order_id}/ship` | Create shipping label and mark order as shipped. | ADMIN |
| POST | `/sales-orders/{order_id}/resolve-legacy-fulfillment` | Close out or reopen a legacy order marked shipped/delivered/completed that has no shipment record (admin only). | ADMIN |
| POST | `/sales-orders/{order_id}/generate-production-orders` | Generate production orders from a sales order (admin only). | ADMIN |
| GET | `/sales-orders/{order_id}/events` | Get activity timeline for a sales order. | STAFF (OWN) |
| POST | `/sales-orders/{order_id}/events` | Add an event to a sales order's activity timeline. | STAFF (OWN) |
| GET | `/sales-orders/{order_id}/shipping-events` | List shipping events for a sales order. | STAFF (OWN) |
| POST | `/sales-orders/{order_id}/shipping-events` | Add a shipping event to a sales order. | STAFF (OWN) |

---

## 4. Quotes (`/quotes`)

**Tier**: Core
**File**: `endpoints/quotes.py`
**Endpoints**: 21

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/quotes/` | List all quotes with optional filtering | STAFF |
| GET | `/quotes/stats` | Get quote statistics for dashboard | STAFF |
| GET | `/quotes/{quote_id}` | Get quote details | STAFF |
| POST | `/quotes/` | Create a new manual quote | STAFF |
| PATCH | `/quotes/{quote_id}` | Update quote details | STAFF |
| PATCH | `/quotes/{quote_id}/status` | Update quote status (approve, reject, cancel, accept) | STAFF |
| POST | `/quotes/{quote_id}/convert` | Convert an accepted/approved quote to a sales order | STAFF |
| DELETE | `/quotes/{quote_id}` | Delete a quote (only if not converted) | STAFF |
| POST | `/quotes/{quote_id}/image` | Upload an image for a quote (product photo/render) | STAFF |
| GET | `/quotes/{quote_id}/image` | Get the image for a quote | STAFF |
| DELETE | `/quotes/{quote_id}/image` | Delete the image for a quote | STAFF |
| GET | `/quotes/{quote_id}/pdf` | Generate a PDF for a quote using ReportLab with company logo, image, and tax | STAFF |
| POST | `/quotes/{quote_id}/create-item` | Create a Core item/product from an approved quote | STAFF |
| POST | `/quotes/{quote_id}/files` | Attach a retained file to a manual or online quote | STAFF |
| DELETE | `/quotes/{quote_id}/files/{file_id}` | Remove a retained file from a quote | STAFF |
| POST | `/quotes/portal` | Upload a file and create a quote for the logged-in customer (403 unless `ENABLE_PUBLIC_QUOTER=true`) | CUSTOMER |
| POST | `/quotes/portal/{quote_id}/accept` | Save the customer's ship-to, shipping choice and colour slots on a quote the customer created; never changes the price (409 for closed, expired, shop-drafted or shop-approved quotes) | CUSTOMER |
| POST | `/quotes/portal/{quote_id}/checkout` | Start payment for the customer's quote. Requires an add-on that is not part of Core; without it, answers 503 | CUSTOMER |
| GET | `/quotes/{quote_id}/archive` | Read-only quote archive; customers get their own quotes only, without staff notes | CUSTOMER |
| GET | `/quotes/{quote_id}/files` | List a quote's files (the customer's own quotes, or any quote for staff) | CUSTOMER |
| GET | `/quotes/{quote_id}/files/{file_id}/download` | Download a quote file (the customer's own quotes, or any quote for staff) | CUSTOMER |

---

## 5. Products (`/products`)

**Tier**: Core
**File**: `endpoints/products.py`
**Endpoints**: 6

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/products` | List products with optional filtering | STAFF |
| GET | `/products/{id}` | Get a specific product by ID | STAFF |
| GET | `/products/sku/{sku}` | Get a specific product by SKU | STAFF |
| POST | `/products` | Create a new product | STAFF |
| PUT | `/products/{id}` | Update an existing product | STAFF |
| GET | `/products/{product_id}/routing` | Get routing details for a product. | STAFF |

---

## 6. Items (`/items`)

**Tier**: Core
**File**: `endpoints/items.py`
**Endpoints**: 29

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/items/categories` | List all item categories | STAFF |
| GET | `/items/categories/tree` | Get categories as a nested tree structure | STAFF |
| POST | `/items/categories` | Create a new item category | STAFF |
| GET | `/items/categories/{category_id}` | Get a specific category by ID | STAFF |
| PATCH | `/items/categories/{category_id}` | Update an existing category | STAFF |
| DELETE | `/items/categories/{category_id}` | Soft delete a category (set is_active=False) | STAFF |
| GET | `/items` | List items with filtering and pagination | STAFF |
| GET | `/items/stats` | Lightweight item statistics — type counts and reorder alerts. | STAFF |
| POST | `/items` | Create a new item | STAFF |
| POST | `/items/{item_id}/duplicate` | Duplicate an existing item with a new SKU and name. | STAFF |
| POST | `/items/material` | Create a material item (shortcut for supply items with material_type/color). | STAFF |
| GET | `/items/low-stock` | Get items that are below their reorder point OR have shortages from active orders. | STAFF |
| GET | `/items/price-candidates` | Get items eligible for price suggestions (excludes materials/supplies). | STAFF |
| GET | `/items/{item_id}/demand-summary` | Get demand summary for an inventory item. | STAFF |
| GET | `/items/{item_id}` | Get a specific item by ID | STAFF |
| GET | `/items/sku/{sku}` | Get a specific item by SKU | STAFF |
| PATCH | `/items/{item_id}` | Update an existing item | STAFF |
| DELETE | `/items/{item_id}` | Soft delete an item (set active=False) | STAFF |
| POST | `/items/import` | Import items from CSV file | STAFF |
| POST | `/items/bulk-update` | Bulk update multiple items at once | STAFF |
| POST | `/items/recost-all` | Recost all items matching filters. | STAFF |
| POST | `/items/{item_id}/recost` | Recost a single item. | STAFF |
| POST | `/items/apply-suggested-prices` | Apply selected suggested prices to items. | STAFF |
| GET | `/items/{item_id}/variants` | List all variants for a template product. | STAFF |
| GET | `/items/{item_id}/variant-matrix` | Get the full variant matrix: template, variants, and available combos. | STAFF |
| POST | `/items/{item_id}/variants` | Create a single variant from a template product. | STAFF |
| POST | `/items/{item_id}/variants/bulk` | Bulk-create variants from MaterialColor selections. | STAFF |
| POST | `/items/{item_id}/variants/sync-routing` | Propagate the template's routing to all variants, preserving material substitutions. | STAFF |
| DELETE | `/items/{item_id}/variants/{variant_id}` | Delete a variant product. | STAFF |

---

## 7. Production Orders (`/production-orders`)

**Tier**: Core
**File**: `endpoints/production_orders.py`, `endpoints/operation_status.py`
**Endpoints**: 46

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/production-orders/` | List production orders with filtering and pagination. | STAFF |
| POST | `/production-orders/` | Create a new production order. | STAFF |
| GET | `/production-orders/status-transitions` | Get valid status transitions for production orders. | STAFF |
| GET | `/production-orders/{order_id}` | Get a production order by ID. | STAFF |
| PUT | `/production-orders/{order_id}` | Update a production order. | STAFF |
| DELETE | `/production-orders/{order_id}` | Delete a production order. | STAFF |
| GET | `/production-orders/scrap-reasons` | Get list of active scrap reasons. | STAFF |
| GET | `/production-orders/scrap-reasons/all` | Get all scrap reasons including inactive. | STAFF |
| POST | `/production-orders/scrap-reasons` | Create a new scrap reason. | ADMIN |
| PUT | `/production-orders/scrap-reasons/{reason_id}` | Update a scrap reason. | ADMIN |
| DELETE | `/production-orders/scrap-reasons/{reason_id}` | Delete a scrap reason. | ADMIN |
| GET | `/production-orders/qc-statuses` | Get valid QC status values. | STAFF |
| GET | `/production-orders/operation-statuses` | Get valid operation status values. | STAFF |
| POST | `/production-orders/{order_id}/release` | Release a production order for manufacturing. | STAFF |
| POST | `/production-orders/{order_id}/start` | Start production on an order. | STAFF |
| POST | `/production-orders/{order_id}/complete` | Complete a production order. | STAFF |
| POST | `/production-orders/{order_id}/accept-short` | Accept a production order short — complete it with the quantity already produced. | STAFF |
| POST | `/production-orders/{order_id}/cancel` | Cancel a production order. | STAFF |
| POST | `/production-orders/{order_id}/refresh-routing` | Re-snapshot the product's current active routing onto the production order. | STAFF |
| POST | `/production-orders/{order_id}/hold` | Put a production order on hold. | STAFF |
| PUT | `/production-orders/{order_id}/schedule` | Schedule a production order. | STAFF |
| GET | `/production-orders/schedule/summary` | Get production schedule summary. | STAFF |
| GET | `/production-orders/queue/by-work-center` | Get queue of operations by work center. | STAFF |
| POST | `/production-orders/{order_id}/qc` | Record QC inspection results. | STAFF |
| POST | `/production-orders/{order_id}/split` | Split a production order into two. | STAFF |
| POST | `/production-orders/{order_id}/scrap` | Record scrap for a production order. | STAFF |
| PUT | `/production-orders/{order_id}/operations/{operation_id}` | Update a production order operation. | STAFF |
| GET | `/production-orders/{order_id}/material-availability` | Get material availability analysis for a production order. | STAFF |
| GET | `/production-orders/{order_id}/blocking-issues` | Get blocking issues for a production order. | STAFF |
| GET | `/production-orders/{order_id}/required-orders` | Get MRP cascade of required orders. | STAFF |
| GET | `/production-orders/{order_id}/cost-breakdown` | Get cost breakdown for a production order. | STAFF |
| POST | `/production-orders/{order_id}/estimate-cost` | Re-estimate costs for a production order from its routing and BOM. | STAFF |
| GET | `/production-orders/{order_id}/compatibility` | Check material-printer compatibility for all operations in a production order. | STAFF |
| GET | `/production-orders/{order_id}/operations/{operation_id}/compatibility` | Check material-printer compatibility for a single operation. | STAFF |
| GET | `/production-orders/{order_id}/spools` | Get spools assigned to a production order. | STAFF |
| POST | `/production-orders/{order_id}/spools/{spool_id}` | Assign a spool to a production order. | STAFF |
| GET | `/production-orders/{po_id}/operations` | Get all operations for a production order, ordered by sequence. | STAFF |
| POST | `/production-orders/{po_id}/operations/{op_id}/start` | Start an operation. | STAFF |
| POST | `/production-orders/{po_id}/operations/{op_id}/complete` | Complete an operation with optional partial scrap and cascading material accounting. | STAFF |
| POST | `/production-orders/{po_id}/operations/{op_id}/skip` | Skip an operation with a reason. | STAFF |
| GET | `/production-orders/{po_id}/operations/{op_id}/can-start` | Quick check if an operation can start based on material availability. | STAFF |
| GET | `/production-orders/{po_id}/operations/{op_id}/blocking-issues` | Get detailed blocking issues for an operation. | STAFF |
| GET | `/production-orders/{po_id}/check-resource-compatibility` | Check if a resource/printer is compatible with a production order's materials. | STAFF |
| POST | `/production-orders/{po_id}/operations/{op_id}/schedule` | Schedule an operation on a resource with time slot validation. | STAFF |
| POST | `/production-orders/resources/next-available` | Find the next available time slot on a resource. | STAFF |
| POST | `/production-orders/{po_id}/operations/generate` | Manually generate operations from routing. | STAFF |

---

## 8. Inventory (`/inventory`)

**Tier**: Core
**File**: `endpoints/inventory.py`
**Endpoints**: 4

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/inventory/transactions/{transaction_id}/approve-negative` | Approve a negative inventory transaction that requires approval. | STAFF |
| GET | `/inventory/negative-inventory-report` | Generate negative inventory report showing all negative inventory occurrences. | STAFF |
| POST | `/inventory/validate-consistency` | Validate inventory consistency: check that allocated doesn't exceed on_hand. | STAFF |
| POST | `/inventory/adjust-quantity` | Adjust inventory on-hand quantity and create an adjustment transaction. | STAFF |

---

## 9. Materials (`/materials`)

**Tier**: Core
**File**: `endpoints/materials.py`
**Endpoints**: 9

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/materials/options` | Get all material options. Nothing in Core uses this route; it is for an add-on that is not part of Core. | STAFF |
| GET | `/materials/types` | Get list of material types (for first dropdown). | STAFF |
| GET | `/materials/types/{material_type_code}/colors` | Get available colors for a specific material type (for second dropdown). | STAFF |
| POST | `/materials/types/{material_type_code}/colors` | Create a new color and link it to a material type. | ADMIN |
| GET | `/materials/for-bom` | Get all materials formatted for BOM usage. | STAFF |
| GET | `/materials/for-order` | Get material inventory items formatted for sales order line selection. | STAFF |
| GET | `/materials/pricing/{material_type_code}` | Get pricing information for a material type. | STAFF |
| GET | `/materials/import/template` | Download CSV template for material inventory import. | STAFF |
| POST | `/materials/import` | Import material inventory from CSV file. | STAFF |

---

## 10. Vendors (`/vendors`)

**Tier**: Core
**File**: `endpoints/vendors.py`
**Endpoints**: 6

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/vendors/` | List all vendors with pagination | STAFF |
| GET | `/vendors/{vendor_id}` | Get vendor details by ID | STAFF |
| POST | `/vendors/` | Create a new vendor | STAFF |
| PUT | `/vendors/{vendor_id}` | Update a vendor | STAFF |
| GET | `/vendors/{vendor_id}/metrics` | Get vendor performance metrics | STAFF |
| DELETE | `/vendors/{vendor_id}` | Delete a vendor (soft delete - marks as inactive) | STAFF |

---

## 11. Purchase Orders (`/purchase-orders`)

**Tier**: Core
**File**: `endpoints/purchase_orders.py`, `endpoints/po_documents.py`, `endpoints/vendor_items.py`
**Endpoints**: 29

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/purchase-orders/` | List purchase orders with pagination | STAFF |
| GET | `/purchase-orders/{po_id}` | Get purchase order details by ID | STAFF |
| POST | `/purchase-orders/` | Create a new purchase order | STAFF |
| PUT | `/purchase-orders/{po_id}` | Update a purchase order | STAFF |
| POST | `/purchase-orders/{po_id}/lines` | Add a line to a purchase order | STAFF |
| PUT | `/purchase-orders/{po_id}/lines/{line_id}` | Update a line on a purchase order | STAFF |
| DELETE | `/purchase-orders/{po_id}/lines/{line_id}` | Remove a line from a purchase order | STAFF |
| POST | `/purchase-orders/{po_id}/status` | Update PO status with transition validation | STAFF |
| POST | `/purchase-orders/{po_id}/receive` | Receive items from a purchase order | STAFF |
| POST | `/purchase-orders/{po_id}/upload` | Upload a document for a purchase order (invoice, receipt, etc.) | STAFF |
| DELETE | `/purchase-orders/{po_id}` | Delete a purchase order (draft only) | STAFF |
| GET | `/purchase-orders/{po_id}/events` | List activity events for a purchase order | STAFF |
| POST | `/purchase-orders/{po_id}/events` | Add a manual event to a purchase order (typically a note) | STAFF |
| GET | `/purchase-orders/{po_id}/pdf` | Generate and download a PDF for a purchase order. | STAFF |
| POST | `/purchase-orders/{po_id}/documents` | Upload a document to a purchase order | STAFF |
| GET | `/purchase-orders/{po_id}/documents` | List all documents attached to a purchase order | STAFF |
| GET | `/purchase-orders/{po_id}/documents/{doc_id}` | Get document details by ID | STAFF |
| GET | `/purchase-orders/{po_id}/documents/{doc_id}/download` | Download a document | STAFF |
| PATCH | `/purchase-orders/{po_id}/documents/{doc_id}` | Update document metadata (type, notes) | STAFF |
| DELETE | `/purchase-orders/{po_id}/documents/{doc_id}` | Delete a document | STAFF |
| POST | `/purchase-orders/{po_id}/documents/bulk` | Upload multiple documents at once | STAFF |
| GET | `/purchase-orders/vendors/{vendor_id}/items` | List all SKU mappings for a vendor. | STAFF |
| POST | `/purchase-orders/vendors/{vendor_id}/items` | Create a new vendor SKU mapping. | STAFF |
| GET | `/purchase-orders/vendors/{vendor_id}/items/{item_id}` | Get a specific vendor item mapping. | STAFF |
| PUT | `/purchase-orders/vendors/{vendor_id}/items/{item_id}` | Update a vendor item mapping. | STAFF |
| DELETE | `/purchase-orders/vendors/{vendor_id}/items/{item_id}` | Delete a vendor item mapping. | STAFF |
| GET | `/purchase-orders/vendor-items/search` | Search vendor items across all vendors. | STAFF |
| POST | `/purchase-orders/vendor-items/suggest-match` | Get product suggestions for a vendor SKU. | STAFF |
| POST | `/purchase-orders/vendor-items/bulk-update-last-seen` | Bulk update last_seen_at and increment times_ordered for vendor items. | STAFF |

---

## 12. Work Centers (`/work-centers`)

**Tier**: Core
**File**: `endpoints/work_centers.py`
**Endpoints**: 13

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/work-centers/` | List all work centers. | STAFF |
| POST | `/work-centers/` | Create a new work center. | STAFF |
| GET | `/work-centers/{wc_id}` | Get a work center by ID. | STAFF |
| PUT | `/work-centers/{wc_id}` | Update a work center. | STAFF |
| DELETE | `/work-centers/{wc_id}` | Delete a work center (soft delete - marks as inactive). | STAFF |
| GET | `/work-centers/{wc_id}/resources` | List all resources for a work center. | STAFF |
| POST | `/work-centers/{wc_id}/resources` | Create a new resource (machine) in a work center. | STAFF |
| GET | `/work-centers/resources/{resource_id}` | Get a resource by ID. | STAFF |
| PUT | `/work-centers/resources/{resource_id}` | Update a resource. | STAFF |
| DELETE | `/work-centers/resources/{resource_id}` | Delete a resource. | STAFF |
| PATCH | `/work-centers/resources/{resource_id}/status` | Quick update of resource status. | STAFF |
| GET | `/work-centers/{wc_id}/printers` | List printers assigned to a work center. | STAFF |
| POST | `/work-centers/sync-bambu` | Sync printers from Bambu Print Suite configuration. | STAFF |

---

## 13. Resources (`/resources`)

**Tier**: Core
**File**: `endpoints/resources.py`
**Endpoints**: 2

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/resources/{resource_id}/schedule` | Get scheduled operations for a resource. | STAFF |
| GET | `/resources/{resource_id}/conflicts` | Check if a time range conflicts with existing scheduled operations. | STAFF |

---

## 14. Routings (`/routings`)

**Tier**: Core
**File**: `endpoints/routings.py`
**Endpoints**: 17

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/routings/` | List all routings. | STAFF |
| POST | `/routings/` | Create a new routing for a product or a template routing. | STAFF |
| POST | `/routings/seed-templates` | Seed the two standard routing templates: | STAFF |
| POST | `/routings/apply-template` | Apply a routing template to a product, creating a product-specific routing. | STAFF |
| GET | `/routings/{routing_id}` | Get a routing by ID with all operations. | STAFF |
| GET | `/routings/product/{product_id}` | Get the active routing for a product. | STAFF |
| PUT | `/routings/{routing_id}` | Update a routing. | STAFF |
| DELETE | `/routings/{routing_id}` | Delete a routing (soft delete - marks as inactive). | STAFF |
| GET | `/routings/{routing_id}/operations` | List all operations for a routing. | STAFF |
| POST | `/routings/{routing_id}/operations` | Add a new operation to a routing. | STAFF |
| PUT | `/routings/operations/{operation_id}` | Update a routing operation. | STAFF |
| DELETE | `/routings/operations/{operation_id}` | Delete a routing operation (soft delete). | STAFF |
| GET | `/routings/operations/{operation_id}/materials` | List all materials for a routing operation. | STAFF |
| POST | `/routings/operations/{operation_id}/materials` | Add a material to a routing operation. | STAFF |
| PUT | `/routings/materials/{material_id}` | Update a routing operation material. | STAFF |
| DELETE | `/routings/materials/{material_id}` | Delete a routing operation material. | STAFF |
| GET | `/routings/manufacturing-bom/{product_id}` | Get the complete Manufacturing BOM for a product. | STAFF |

---

## 15. Mrp (`/mrp`)

**Tier**: Core
**File**: `endpoints/mrp.py`
**Endpoints**: 11

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/mrp/run` | Run MRP calculation. | STAFF |
| GET | `/mrp/runs` | List recent MRP runs | STAFF |
| GET | `/mrp/runs/{run_id}` | Get details of a specific MRP run | STAFF |
| GET | `/mrp/planned-orders` | List planned orders with optional filters | STAFF |
| GET | `/mrp/planned-orders/{order_id}` | Get a specific planned order | STAFF |
| POST | `/mrp/planned-orders/{order_id}/firm` | Firm a planned order. | STAFF |
| POST | `/mrp/planned-orders/{order_id}/release` | Release a planned order to an actual PO or MO. | STAFF |
| DELETE | `/mrp/planned-orders/{order_id}` | Cancel/delete a planned order | STAFF |
| GET | `/mrp/requirements` | Calculate and return material requirements. | STAFF |
| GET | `/mrp/supply-demand/{product_id}` | Get supply and demand timeline for a product. | STAFF |
| GET | `/mrp/explode-bom/{product_id}` | Explode a BOM to see all component requirements. | STAFF |

---

## 16. Scheduling (`/scheduling`)

**Tier**: Core
**File**: `endpoints/scheduling.py`
**Endpoints**: 5

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/scheduling/capacity/check` | Check if a machine has capacity for a production order at a given time. | STAFF |
| GET | `/scheduling/capacity/available-slots` | Find available time slots for a resource within a date range. | STAFF |
| GET | `/scheduling/capacity/machine-availability` | Get availability status for all machines in a date range. | STAFF |
| POST | `/scheduling/auto-schedule` | Automatically find the best available slot for a production order. | STAFF |
| GET | `/scheduling/resource-conflicts` | Check for scheduling conflicts on a resource/printer in a time range. | STAFF |

---

## 17. Settings (`/settings`)

**Tier**: Core
**File**: `endpoints/settings.py`
**Endpoints**: 11

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/settings/company` | Get company settings | STAFF |
| PATCH | `/settings/company` | Update company settings | ADMIN |
| POST | `/settings/company/logo` | Upload company logo | ADMIN |
| GET | `/settings/company/logo` | Get company logo image (no auth required for PDF generation) | PUBLIC |
| DELETE | `/settings/company/logo` | Delete company logo | ADMIN |
| GET | `/settings/ai` | Get AI configuration settings (API keys masked) | STAFF |
| PATCH | `/settings/ai` | Update AI configuration settings | ADMIN |
| POST | `/settings/ai/test` | Test the configured AI connection | ADMIN |
| POST | `/settings/ai/start-ollama` | Attempt to start the Ollama service | ADMIN |
| GET | `/settings/ai/anthropic-status` | Check if the anthropic package is installed. | STAFF |
| POST | `/settings/ai/install-anthropic` | Install the anthropic Python package. | ADMIN |

---

## 18. Tax Rates (`/tax-rates`)

**Tier**: Core
**File**: `endpoints/tax_rates.py`
**Endpoints**: 5

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/tax-rates` | List active tax rates. Pass include_inactive=true to see all. | STAFF |
| GET | `/tax-rates/{tax_rate_id}` | Get tax rate | STAFF |
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
| POST | `/payments` | Record a new payment for a sales order. | STAFF |
| POST | `/payments/refund` | Record a refund for a sales order. | STAFF |
| GET | `/payments` | List payments with filtering and pagination. | STAFF |
| GET | `/payments/dashboard` | Get payment dashboard statistics. | STAFF |
| GET | `/payments/order/{order_id}/summary` | Get payment summary for a specific order. | STAFF |
| GET | `/payments/{payment_id}` | Get a specific payment by ID. | STAFF |
| PATCH | `/payments/{payment_id}` | Update a payment record (limited to notes and status). | STAFF |
| DELETE | `/payments/{payment_id}` | Void a payment (sets status to 'voided', doesn't delete). | STAFF |

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
| GET | `/printers/generate-code` | Generate a new unique printer code | STAFF |
| GET | `/printers/brands/info` | Get information about supported printer brands | STAFF |
| GET | `/printers/active-work` | Get active/scheduled work for all printers. | STAFF |
| GET | `/printers/` | List all printers with filtering and pagination | STAFF |
| GET | `/printers/{printer_id}` | Get a single printer by ID | STAFF |
| POST | `/printers/` | Create a new printer | STAFF |
| PUT | `/printers/{printer_id}` | Update an existing printer | STAFF |
| DELETE | `/printers/{printer_id}` | Delete a printer | STAFF |
| PATCH | `/printers/{printer_id}/status` | Update printer status | STAFF |
| POST | `/printers/discover` | Discover printers on the local network | STAFF |
| POST | `/printers/probe-ip` | Probe an IP address to detect printer info. | STAFF |
| POST | `/printers/test-connection` | Test connection to a printer | STAFF |
| POST | `/printers/import-csv` | Import printers from CSV data | STAFF |

---

## 22. System (`/system`)

**Tier**: Core
**File**: `endpoints/system.py`
**Endpoints**: 5

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/system/version` | Get current FilaOps version and build date. | PUBLIC |
| GET | `/system/info` | Get system tier and enabled features. | PUBLIC |
| GET | `/system/updates/check` | Check GitHub releases for available updates | STAFF |
| GET | `/system/updates/instructions` | Get step-by-step update instructions for current deployment method | STAFF |
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
| GET | `/spools/` | List all material spools with optional filters. | STAFF |
| GET | `/spools/{spool_id}` | Get details for a specific spool including usage history. | STAFF |
| POST | `/spools/` | Create a new material spool. | STAFF |
| PATCH | `/spools/{spool_id}` | Update spool information (weight, status, location, notes). | STAFF |
| GET | `/spools/product/{product_id}/available` | Get available spools for a product, optionally filtered by minimum weight. | STAFF |
| GET | `/spools/traceability/production-order/{production_order_id}` | Get spool traceability information for a production order. | STAFF |
| GET | `/spools/traceability/spool/{spool_id}` | Get full traceability for a spool: which production orders used it, which finished goods were produced. | STAFF |
| POST | `/spools/{spool_id}/consume` | Record material consumption from a spool for a production order. | STAFF |

---

## 25. Traceability (`/traceability`)

**Tier**: Core
**File**: `endpoints/traceability.py`
**Endpoints**: 4

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/traceability/forward/spool/{spool_id}` | Trace a spool forward to all products and customers. | STAFF |
| GET | `/traceability/backward/serial/{serial_number}` | Trace a serial number back to source materials and vendor. | STAFF |
| GET | `/traceability/backward/sales-order/{so_id}` | Trace a sales order back to all source materials. | STAFF |
| POST | `/traceability/recall-impact` | Calculate the impact of recalling specific spools. | STAFF |

---

## 26. Maintenance (`/maintenance`)

**Tier**: Core
**File**: `endpoints/maintenance.py`
**Endpoints**: 7

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/maintenance/` | List all maintenance logs with filtering and pagination | STAFF |
| GET | `/maintenance/due` | Get printers that are due for maintenance | STAFF |
| GET | `/maintenance/{log_id}` | Get a single maintenance log by ID | STAFF |
| GET | `/maintenance/printers/{printer_id}/maintenance` | List all maintenance logs for a specific printer | STAFF |
| POST | `/maintenance/printers/{printer_id}/maintenance` | Add a maintenance log entry for a printer | STAFF |
| PUT | `/maintenance/{log_id}` | Update an existing maintenance log | STAFF |
| DELETE | `/maintenance/{log_id}` | Delete a maintenance log | STAFF |

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
| POST | `/admin/fulfillment/ship/consolidate/get-rates` | Get shipping rates for multiple orders consolidated into one package. | STAFF |
| POST | `/admin/fulfillment/ship/consolidate/buy-label` | Purchase a shipping label for consolidated orders. | STAFF |
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
| GET | `/admin/audit/transactions` | Run a transaction audit to find gaps in inventory tracking. | STAFF |
| GET | `/admin/audit/transactions/order/{order_id}` | Audit a single order for transaction gaps. | STAFF |
| GET | `/admin/audit/transactions/timeline/{order_id}` | Get the complete transaction timeline for an order. | STAFF |
| GET | `/admin/audit/transactions/summary` | Get a quick summary of transaction health across all active orders. | STAFF |

### 28.9. Accounting (`/admin/accounting`)

**Tier**: Core
**File**: `endpoints/admin/accounting.py`
**Endpoints**: 12

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/accounting/inventory-by-account` | Get inventory balances organized by accounting category. | STAFF |
| GET | `/admin/accounting/transactions-journal` | Get inventory transactions formatted as journal entries. | STAFF |
| GET | `/admin/accounting/order-cost-breakdown/{order_id}` | Get a cost breakdown for a specific sales order. | STAFF |
| GET | `/admin/accounting/cogs-summary` | Get COGS summary for recent period. | STAFF |
| GET | `/admin/accounting/dashboard` | Get accounting dashboard with key financial metrics. | STAFF |
| GET | `/admin/accounting/sales-journal` | Get sales journal - all sales transactions for the period. | STAFF |
| GET | `/admin/accounting/sales-journal/export` | Export sales journal as CSV. | STAFF |
| GET | `/admin/accounting/tax-summary` | Get tax summary for filing preparation. | STAFF |
| GET | `/admin/accounting/tax-summary/export` | Export tax summary as CSV for filing. | STAFF |
| GET | `/admin/accounting/payments-journal` | Get payments journal - all payment transactions for the period. | STAFF |
| GET | `/admin/accounting/payments-journal/export` | Export payments journal as CSV. | STAFF |
| GET | `/admin/accounting/export/sales` | Export sales data for tax time / accounting purposes. | STAFF |

### 28.10. Traceability (`/admin/traceability`)

**Tier**: Core
**File**: `endpoints/admin/traceability.py`
**Endpoints**: 18

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/traceability/profiles` | List all customer traceability profiles. | STAFF |
| GET | `/admin/traceability/profiles/{user_id}` | Get traceability profile for a specific customer. | STAFF |
| POST | `/admin/traceability/profiles` | Create a traceability profile for a customer. | STAFF |
| PATCH | `/admin/traceability/profiles/{user_id}` | Update a customer's traceability profile. | STAFF |
| GET | `/admin/traceability/lots` | List material lots with filtering and pagination. | STAFF |
| GET | `/admin/traceability/lots/{lot_id}` | Get a specific material lot by ID. | STAFF |
| POST | `/admin/traceability/lots` | Create a new material lot (typically when receiving materials). | STAFF |
| PATCH | `/admin/traceability/lots/{lot_id}` | Update a material lot. | STAFF |
| POST | `/admin/traceability/lots/generate-number` | Generate the next lot number for a material. | STAFF |
| GET | `/admin/traceability/serials` | List serial numbers with filtering and pagination. | STAFF |
| GET | `/admin/traceability/serials/{serial_id}` | Get a specific serial number by ID. | STAFF |
| GET | `/admin/traceability/serials/lookup/{serial_number}` | Look up a serial number by the serial string. | STAFF |
| POST | `/admin/traceability/serials` | Generate serial numbers for a production order. | STAFF |
| PATCH | `/admin/traceability/serials/{serial_id}` | Update a serial number (e.g., mark as sold, shipped, returned). | STAFF |
| POST | `/admin/traceability/consumptions` | Record material lot consumption for a production order. | STAFF |
| GET | `/admin/traceability/consumptions/production/{production_order_id}` | Get all lot consumptions for a production order. | STAFF |
| GET | `/admin/traceability/recall/forward/{lot_number}` | Forward recall query: What did we make with this lot? | STAFF |
| GET | `/admin/traceability/recall/backward/{serial_number}` | Backward recall query: What material lots went into this serial number? | STAFF |

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
| GET | `/admin/orders/import/template` | Download CSV template for order import. | STAFF |
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
| POST | `/admin/uploads/product-image` | Upload a product image. | STAFF |
| DELETE | `/admin/uploads/product-image/{filename}` | Delete a previously uploaded product image. | STAFF |


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

*Last updated: 2026-04-14*
*Generated for FilaOps Core v4.0.0*
