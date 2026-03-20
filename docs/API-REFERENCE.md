# FilaOps API Reference

> Complete API endpoint documentation for FilaOps Core ERP system.
> Generated for AI consumption and developer reference.
> This document covers **Core (Open Source)** API endpoints only.

## Overview

| Metric | Count |
| ------ | ----- |
| **Total Endpoints** | ~439 |
| **Router Files** | 48 |
| **Router Groups** | 27 (including 15 admin sub-modules) |
| **Base Path** | `/api/v1/` |

### HTTP Method Distribution

- **GET**: ~230 endpoints (read/query operations)
- **POST**: ~140 endpoints (create/execute operations)
- **PUT/PATCH**: ~40 endpoints (update operations)
- **DELETE**: ~8 endpoints (delete operations)

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

## 1. Authentication (`/auth`)

**Tier**: Core
**File**: `endpoints/auth.py`
**Endpoints**: 9

| Method | Path | Description | Auth | Rate Limit |
| ------ | ---- | ----------- | ---- | ---------- |
| POST | `/auth/register` | Register new user account | PUBLIC | 3/min |
| POST | `/auth/login` | Login with email/password (OAuth2 flow) | PUBLIC | 5/min |
| POST | `/auth/refresh` | Refresh access token using refresh token | PUBLIC | - |
| GET | `/auth/me` | Get current user profile | CUSTOMER | - |
| POST | `/auth/password-reset/request` | Request admin-approved password reset | PUBLIC | 3/min |
| GET | `/auth/password-reset/approve/{approval_token}` | Approve password reset (admin link) | PUBLIC | - |
| GET | `/auth/password-reset/deny/{approval_token}` | Deny password reset (admin link) | PUBLIC | - |
| GET | `/auth/password-reset/status/{token}` | Check password reset token status | PUBLIC | - |
| POST | `/auth/password-reset/complete` | Complete password reset with new password | PUBLIC | - |

### Request/Response Schemas

#### POST /auth/register

```json
// Request: UserRegister
{
  "email": "string",
  "password": "string",
  "first_name": "string",
  "last_name": "string",
  "company_name": "string (optional)",
  "phone": "string (optional)"
}
// Response: UserWithTokens
{
  "id": "integer",
  "email": "string",
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer"
}
```

#### POST /auth/login

```text
// Request: OAuth2PasswordRequestForm (form-data)
username=email@example.com&password=secret

// Response: TokenResponse
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer"
}
```

---

## 2. Sales Orders (`/sales-orders`)

**Tier**: Core
**File**: `endpoints/sales_orders.py`
**Endpoints**: ~20

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/sales-orders` | List sales orders with filters | STAFF |
| POST | `/sales-orders` | Create new sales order | STAFF |
| GET | `/sales-orders/{id}` | Get sales order details | STAFF |
| PATCH | `/sales-orders/{id}` | Update sales order | STAFF |
| DELETE | `/sales-orders/{id}` | Delete/cancel sales order | STAFF |
| POST | `/sales-orders/{id}/lines` | Add line item to order | STAFF |
| PATCH | `/sales-orders/{id}/lines/{line_id}` | Update order line | STAFF |
| DELETE | `/sales-orders/{id}/lines/{line_id}` | Remove order line | STAFF |
| POST | `/sales-orders/{id}/open` | Open draft order for processing | STAFF |
| POST | `/sales-orders/{id}/hold` | Place order on hold | STAFF |
| POST | `/sales-orders/{id}/release` | Release from hold | STAFF |
| POST | `/sales-orders/{id}/complete` | Mark order complete | STAFF |
| POST | `/sales-orders/{id}/ship` | Record shipment | STAFF |
| GET | `/sales-orders/{id}/blocking-issues` | Get production blocking issues | STAFF |
| GET | `/sales-orders/{id}/fulfillment-status` | Get fulfillment tracking | STAFF |
| POST | `/sales-orders/{id}/allocate-inventory` | Allocate inventory to order | STAFF |
| POST | `/sales-orders/{id}/create-production-order` | Create MO from SO line | STAFF |

### Order Statuses

- `draft` → `open` → `in_progress` → `shipped` → `delivered` → `completed`
- `hold` (can transition from most states)
- `cancelled` (terminal state)

---

## 3. Quotes (`/quotes`)

**Tier**: Core
**File**: `endpoints/quotes.py`
**Endpoints**: ~15

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/quotes` | List quotes with filters | STAFF |
| POST | `/quotes` | Create new quote | STAFF |
| GET | `/quotes/{id}` | Get quote details | STAFF |
| PATCH | `/quotes/{id}` | Update quote | STAFF |
| DELETE | `/quotes/{id}` | Delete quote | STAFF |
| POST | `/quotes/{id}/lines` | Add line to quote | STAFF |
| PATCH | `/quotes/{id}/lines/{line_id}` | Update quote line | STAFF |
| DELETE | `/quotes/{id}/lines/{line_id}` | Remove quote line | STAFF |
| POST | `/quotes/{id}/send` | Send quote to customer | STAFF |
| POST | `/quotes/{id}/approve` | Approve quote | STAFF |
| POST | `/quotes/{id}/reject` | Reject quote | STAFF |
| POST | `/quotes/{id}/convert` | Convert quote to sales order | STAFF |
| GET | `/quotes/{id}/pdf` | Generate quote PDF | STAFF |
| POST | `/quotes/{id}/duplicate` | Duplicate quote | STAFF |

---

## 4. Production Orders (`/production-orders`)

**Tier**: Core
**File**: `endpoints/production_orders.py`
**Endpoints**: ~31

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/production-orders` | List production orders | STAFF |
| POST | `/production-orders` | Create production order | STAFF |
| GET | `/production-orders/{id}` | Get production order details | STAFF |
| PATCH | `/production-orders/{id}` | Update production order | STAFF |
| DELETE | `/production-orders/{id}` | Delete production order | STAFF |
| POST | `/production-orders/{id}/release` | Release order to production | STAFF |
| POST | `/production-orders/{id}/start` | Start production | STAFF |
| POST | `/production-orders/{id}/complete` | Complete production order | STAFF |
| POST | `/production-orders/{id}/cancel` | Cancel production order | STAFF |
| GET | `/production-orders/{id}/operations` | Get operations for order | STAFF |
| POST | `/production-orders/{id}/operations` | Add operation to order | STAFF |
| PATCH | `/production-orders/{id}/operations/{op_id}` | Update operation | STAFF |
| POST | `/production-orders/{id}/operations/{op_id}/start` | Start operation | STAFF |
| POST | `/production-orders/{id}/operations/{op_id}/complete` | Complete operation | STAFF |
| POST | `/production-orders/{id}/operations/{op_id}/pause` | Pause operation | STAFF |
| POST | `/production-orders/{id}/operations/{op_id}/resume` | Resume operation | STAFF |
| POST | `/production-orders/{id}/consume-materials` | Consume BOM materials | STAFF |
| POST | `/production-orders/{id}/record-output` | Record production output | STAFF |
| POST | `/production-orders/{id}/record-scrap` | Record scrap/waste | STAFF |
| POST | `/production-orders/{id}/qc-pass` | Pass QC inspection | STAFF |
| POST | `/production-orders/{id}/qc-fail` | Fail QC inspection | STAFF |
| GET | `/production-orders/{id}/material-requirements` | Get material requirements | STAFF |
| POST | `/production-orders/{id}/split` | Split order into multiple | STAFF |
| POST | `/production-orders/{id}/merge` | Merge orders | STAFF |
| GET | `/production-orders/queue` | Get production queue | STAFF |
| GET | `/production-orders/stats` | Get production statistics | STAFF |
| POST | `/production-orders/bulk-release` | Release multiple orders | STAFF |

### Production Order Statuses

- `draft` → `released` → `in_progress` → `completed`
- `on_hold`, `cancelled` (can transition from most states)

---

## 5. Operation Status (`/production-orders`)

**Tier**: Core
**File**: `endpoints/operation_status.py`
**Endpoints**: 9

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/production-orders/{id}/operations/{op_id}/status` | Get operation status | STAFF |
| POST | `/production-orders/{id}/operations/{op_id}/status/start` | Start operation timer | STAFF |
| POST | `/production-orders/{id}/operations/{op_id}/status/stop` | Stop operation timer | STAFF |
| POST | `/production-orders/{id}/operations/{op_id}/status/pause` | Pause operation | STAFF |
| POST | `/production-orders/{id}/operations/{op_id}/status/resume` | Resume operation | STAFF |
| GET | `/production-orders/{id}/operations/{op_id}/time-log` | Get time log entries | STAFF |
| POST | `/production-orders/{id}/operations/{op_id}/time-log` | Add manual time entry | STAFF |
| GET | `/production-orders/operations/active` | List active operations | STAFF |
| GET | `/production-orders/operations/by-work-center/{wc_id}` | Operations by work center | STAFF |

---

## 6. Inventory (`/inventory`)

**Tier**: Core
**File**: `endpoints/inventory.py`
**Endpoints**: 4

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/inventory/transactions/{id}/approve-negative` | Approve negative inventory transaction | STAFF |
| GET | `/inventory/negative-inventory-report` | Generate negative inventory report | STAFF |
| POST | `/inventory/validate-consistency` | Validate inventory consistency | STAFF |
| POST | `/inventory/adjust-quantity` | Adjust inventory with audit trail | STAFF |

### Query Parameters for `/inventory/adjust-quantity`

```text
product_id: integer (required)
location_id: integer (default: 1)
new_on_hand_quantity: float (required)
adjustment_reason: string (required)
input_unit: string (optional, e.g., 'G', 'KG')
cost_per_unit: float (optional)
notes: string (optional)
```

---

## 7. Items (`/items`)

**Tier**: Core
**File**: `endpoints/items.py`
**Endpoints**: ~19

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/items` | List all items with filters | STAFF |
| POST | `/items` | Create new item | STAFF |
| GET | `/items/{id}` | Get item details | STAFF |
| PATCH | `/items/{id}` | Update item | STAFF |
| DELETE | `/items/{id}` | Delete item | STAFF |
| GET | `/items/{id}/inventory` | Get inventory levels | STAFF |
| GET | `/items/{id}/transactions` | Get inventory transactions | STAFF |
| GET | `/items/{id}/bom` | Get BOM if exists | STAFF |
| POST | `/items/{id}/duplicate` | Duplicate item | STAFF |
| GET | `/items/categories` | List item categories | STAFF |
| POST | `/items/categories` | Create category | STAFF |
| PATCH | `/items/categories/{id}` | Update category | STAFF |
| DELETE | `/items/categories/{id}` | Delete category | STAFF |
| GET | `/items/low-stock` | Get low stock items | STAFF |
| GET | `/items/search` | Search items by SKU/name | STAFF |
| POST | `/items/bulk-update` | Bulk update items | STAFF |
| GET | `/items/export` | Export items to CSV | STAFF |
| POST | `/items/import` | Import items from CSV | STAFF |

---

## 8. Materials (`/materials`)

**Tier**: Core
**File**: `endpoints/materials.py`
**Endpoints**: ~9

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/materials` | List material types | STAFF |
| POST | `/materials` | Create material type | STAFF |
| GET | `/materials/{id}` | Get material type | STAFF |
| PATCH | `/materials/{id}` | Update material type | STAFF |
| DELETE | `/materials/{id}` | Delete material type | STAFF |
| GET | `/materials/colors` | List material colors | STAFF |
| POST | `/materials/colors` | Create color | STAFF |
| GET | `/materials/{type}/products` | Get products by material | STAFF |
| GET | `/materials/pricing` | Get material pricing | STAFF |

---

## 9. Material Spools (`/spools`)

**Tier**: Core
**File**: `endpoints/spools.py`
**Endpoints**: ~8

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/spools` | List material spools | STAFF |
| POST | `/spools` | Create/receive spool | STAFF |
| GET | `/spools/{id}` | Get spool details | STAFF |
| PATCH | `/spools/{id}` | Update spool | STAFF |
| POST | `/spools/{id}/consume` | Record spool consumption | STAFF |
| POST | `/spools/{id}/transfer` | Transfer spool to location | STAFF |
| GET | `/spools/{id}/history` | Get spool consumption history | STAFF |
| GET | `/spools/active` | List active spools | STAFF |

---

## 10. Vendors (`/vendors`)

**Tier**: Core
**File**: `endpoints/vendors.py`
**Endpoints**: 6

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/vendors` | List vendors | STAFF |
| POST | `/vendors` | Create vendor | STAFF |
| GET | `/vendors/{id}` | Get vendor details | STAFF |
| PATCH | `/vendors/{id}` | Update vendor | STAFF |
| DELETE | `/vendors/{id}` | Delete vendor | STAFF |
| GET | `/vendors/{id}/items` | Get vendor's items | STAFF |

---

## 11. Purchase Orders (`/purchase-orders`)

**Tier**: Core
**File**: `endpoints/purchase_orders.py`
**Endpoints**: ~13

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/purchase-orders` | List purchase orders | STAFF |
| POST | `/purchase-orders` | Create purchase order | STAFF |
| GET | `/purchase-orders/{id}` | Get PO details | STAFF |
| PATCH | `/purchase-orders/{id}` | Update PO | STAFF |
| DELETE | `/purchase-orders/{id}` | Delete PO | STAFF |
| POST | `/purchase-orders/{id}/lines` | Add line to PO | STAFF |
| PATCH | `/purchase-orders/{id}/lines/{line_id}` | Update PO line | STAFF |
| DELETE | `/purchase-orders/{id}/lines/{line_id}` | Remove PO line | STAFF |
| POST | `/purchase-orders/{id}/submit` | Submit PO to vendor | STAFF |
| POST | `/purchase-orders/{id}/receive` | Receive PO items | STAFF |
| POST | `/purchase-orders/{id}/close` | Close PO | STAFF |
| GET | `/purchase-orders/{id}/receipts` | Get receipt history | STAFF |
| POST | `/purchase-orders/from-low-stock` | Create PO from low stock | STAFF |

---

## 12. PO Documents (`/purchase-orders`)

**Tier**: Core
**File**: `endpoints/po_documents.py`
**Endpoints**: 7

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/purchase-orders/{id}/documents` | List PO documents | STAFF |
| POST | `/purchase-orders/{id}/documents` | Upload document | STAFF |
| GET | `/purchase-orders/{id}/documents/{doc_id}` | Get document | STAFF |
| DELETE | `/purchase-orders/{id}/documents/{doc_id}` | Delete document | STAFF |
| POST | `/purchase-orders/{id}/documents/bulk-upload` | Upload multiple documents | STAFF |
| GET | `/purchase-orders/documents/recent` | Get recent documents | STAFF |
| POST | `/purchase-orders/{id}/documents/{doc_id}/parse` | Parse invoice document | STAFF |

---

## 13. Vendor Items (`/purchase-orders`)

**Tier**: Core
**File**: `endpoints/vendor_items.py`
**Endpoints**: 8

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/purchase-orders/vendor-items` | List vendor item mappings | STAFF |
| POST | `/purchase-orders/vendor-items` | Create vendor item mapping | STAFF |
| GET | `/purchase-orders/vendor-items/{id}` | Get mapping details | STAFF |
| PATCH | `/purchase-orders/vendor-items/{id}` | Update mapping | STAFF |
| DELETE | `/purchase-orders/vendor-items/{id}` | Delete mapping | STAFF |
| GET | `/purchase-orders/vendor-items/by-vendor/{vendor_id}` | Get mappings by vendor | STAFF |
| GET | `/purchase-orders/vendor-items/by-product/{product_id}` | Get mappings by product | STAFF |
| POST | `/purchase-orders/vendor-items/match` | Match vendor SKU to product | STAFF |

---

## 14. Low Stock (`/purchase-orders`)

**Tier**: Core
**File**: `endpoints/low_stock.py`
**Endpoints**: 3

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/purchase-orders/low-stock` | Get low stock items needing reorder | STAFF |
| POST | `/purchase-orders/low-stock/create-po` | Create PO from low stock selection | STAFF |
| GET | `/purchase-orders/low-stock/summary` | Get low stock summary | STAFF |

---

## 15. MRP (`/mrp`)

**Tier**: Core
**File**: `endpoints/mrp.py`
**Endpoints**: 11

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/mrp/run` | Run MRP calculation | STAFF |
| GET | `/mrp/runs` | List MRP run history | STAFF |
| GET | `/mrp/runs/{run_id}` | Get MRP run details | STAFF |
| GET | `/mrp/planned-orders` | List planned orders | STAFF |
| GET | `/mrp/planned-orders/{id}` | Get planned order | STAFF |
| POST | `/mrp/planned-orders/{id}/firm` | Firm planned order | STAFF |
| POST | `/mrp/planned-orders/{id}/release` | Release to PO/MO | STAFF |
| DELETE | `/mrp/planned-orders/{id}` | Cancel planned order | STAFF |
| GET | `/mrp/requirements` | Calculate material requirements | STAFF |
| GET | `/mrp/supply-demand/{product_id}` | Get supply/demand timeline | STAFF |
| GET | `/mrp/explode-bom/{product_id}` | Explode BOM for requirements | STAFF |

### MRP Run Request

```json
{
  "planning_horizon_days": 30,
  "include_draft_orders": false,
  "regenerate_planned": false
}
```

### MRP Settings (from app settings)

- `INCLUDE_SALES_ORDERS_IN_MRP`: Include open SO demand
- `MRP_ENABLE_SUB_ASSEMBLY_CASCADING`: Cascade through sub-assemblies

---

## 16. Work Centers (`/work-centers`)

**Tier**: Core
**File**: `endpoints/work_centers.py`
**Endpoints**: ~8

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/work-centers` | List work centers | STAFF |
| POST | `/work-centers` | Create work center | STAFF |
| GET | `/work-centers/{id}` | Get work center | STAFF |
| PATCH | `/work-centers/{id}` | Update work center | STAFF |
| DELETE | `/work-centers/{id}` | Delete work center | STAFF |
| GET | `/work-centers/{id}/capacity` | Get capacity info | STAFF |
| GET | `/work-centers/{id}/schedule` | Get schedule | STAFF |
| GET | `/work-centers/{id}/utilization` | Get utilization metrics | STAFF |

---

## 17. Resources (`/resources`)

**Tier**: Core
**File**: `endpoints/resources.py`
**Endpoints**: ~13

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/resources` | List resources | STAFF |
| POST | `/resources` | Create resource | STAFF |
| GET | `/resources/{id}` | Get resource | STAFF |
| PATCH | `/resources/{id}` | Update resource | STAFF |
| DELETE | `/resources/{id}` | Delete resource | STAFF |
| GET | `/resources/{id}/availability` | Check availability | STAFF |
| GET | `/resources/{id}/schedule` | Get schedule | STAFF |
| POST | `/resources/{id}/reserve` | Reserve resource | STAFF |
| DELETE | `/resources/{id}/reservations/{res_id}` | Cancel reservation | STAFF |
| GET | `/resources/conflicts` | Get scheduling conflicts | STAFF |
| POST | `/resources/resolve-conflict` | Resolve conflict | STAFF |
| GET | `/resources/types` | List resource types | STAFF |
| GET | `/resources/by-work-center/{wc_id}` | Resources by work center | STAFF |

---

## 18. Routings (`/routings`)

**Tier**: Core
**File**: `endpoints/routings.py`
**Endpoints**: ~17

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/routings` | List routings | STAFF |
| POST | `/routings` | Create routing | STAFF |
| GET | `/routings/{id}` | Get routing details | STAFF |
| PATCH | `/routings/{id}` | Update routing | STAFF |
| DELETE | `/routings/{id}` | Delete routing | STAFF |
| POST | `/routings/{id}/operations` | Add operation | STAFF |
| PATCH | `/routings/{id}/operations/{op_id}` | Update operation | STAFF |
| DELETE | `/routings/{id}/operations/{op_id}` | Delete operation | STAFF |
| POST | `/routings/{id}/operations/reorder` | Reorder operations | STAFF |
| POST | `/routings/{id}/operations/{op_id}/materials` | Add operation material | STAFF |
| PATCH | `/routings/{id}/operations/{op_id}/materials/{mat_id}` | Update operation material | STAFF |
| DELETE | `/routings/{id}/operations/{op_id}/materials/{mat_id}` | Delete operation material | STAFF |
| POST | `/routings/{id}/activate` | Activate routing | STAFF |
| POST | `/routings/{id}/deactivate` | Deactivate routing | STAFF |
| POST | `/routings/{id}/copy` | Copy routing | STAFF |
| GET | `/routings/by-product/{product_id}` | Get routing by product | STAFF |
| POST | `/routings/{id}/recalculate-cost` | Recalculate routing cost | STAFF |

---

## 19. Scheduling (`/scheduling`)

**Tier**: Core
**File**: `endpoints/scheduling.py`
**Endpoints**: 4

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/scheduling/capacity` | Get capacity overview | STAFF |
| GET | `/scheduling/gantt` | Get Gantt chart data | STAFF |
| POST | `/scheduling/reschedule` | Reschedule operations | STAFF |
| GET | `/scheduling/bottlenecks` | Identify bottlenecks | STAFF |

---

## 20. Printers (`/printers`)

**Tier**: Core
**File**: `endpoints/printers.py`
**Endpoints**: ~13

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/printers` | List 3D printers | STAFF |
| POST | `/printers` | Add printer | STAFF |
| GET | `/printers/{id}` | Get printer details | STAFF |
| PATCH | `/printers/{id}` | Update printer | STAFF |
| DELETE | `/printers/{id}` | Delete printer | STAFF |
| GET | `/printers/{id}/status` | Get live status | STAFF |
| POST | `/printers/{id}/test-connection` | Test connection | STAFF |
| POST | `/printers/discover` | Auto-discover printers | STAFF |
| POST | `/printers/import-csv` | Import from CSV | STAFF |
| GET | `/printers/types` | List printer types | STAFF |
| GET | `/printers/stats` | Get fleet statistics | STAFF |
| POST | `/printers/{id}/assign-job` | Assign print job | STAFF |
| POST | `/printers/{id}/unassign-job` | Remove print job | STAFF |

---

## 21. MQTT / IoT (`/mqtt`)

**Tier**: Core
**File**: `endpoints/mqtt.py`
**Endpoints**: ~12

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/mqtt/status` | Get MQTT connection status | STAFF |
| GET | `/mqtt/printers` | Get live printer statuses | STAFF |
| GET | `/mqtt/printers/{id}` | Get single printer status | STAFF |
| GET | `/mqtt/printers/{id}/history` | Get status history | STAFF |
| POST | `/mqtt/printers/{id}/subscribe` | Subscribe to printer | STAFF |
| POST | `/mqtt/printers/{id}/unsubscribe` | Unsubscribe | STAFF |
| GET | `/mqtt/events` | Get recent events | STAFF |
| GET | `/mqtt/events/{printer_id}` | Get printer events | STAFF |
| POST | `/mqtt/link-production-order` | Link printer to MO | STAFF |
| POST | `/mqtt/unlink-production-order` | Unlink printer from MO | STAFF |
| GET | `/mqtt/production-order/{mo_id}` | Get linked printers | STAFF |
| POST | `/mqtt/reconnect` | Force MQTT reconnect | ADMIN |

---

## 22. Payments (`/payments`)

**Tier**: Core
**File**: `endpoints/payments.py`
**Endpoints**: ~8

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/payments` | List payments | STAFF |
| POST | `/payments` | Record payment | STAFF |
| GET | `/payments/{id}` | Get payment details | STAFF |
| PATCH | `/payments/{id}` | Update payment | STAFF |
| DELETE | `/payments/{id}` | Delete payment | STAFF |
| POST | `/payments/{id}/apply` | Apply to invoice | STAFF |
| GET | `/payments/by-order/{order_id}` | Get payments for order | STAFF |
| GET | `/payments/outstanding` | Get outstanding balances | STAFF |

---

## 23. Settings (`/settings`)

**Tier**: Core
**File**: `endpoints/settings.py`
**Endpoints**: ~11

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/settings` | Get all settings | STAFF |
| PATCH | `/settings` | Update settings | ADMIN |
| GET | `/settings/company` | Get company info | STAFF |
| PATCH | `/settings/company` | Update company info | ADMIN |
| GET | `/settings/integrations` | Get integration settings | ADMIN |
| PATCH | `/settings/integrations` | Update integrations | ADMIN |
| GET | `/settings/email` | Get email settings | ADMIN |
| PATCH | `/settings/email` | Update email settings | ADMIN |
| POST | `/settings/email/test` | Send test email | ADMIN |
| GET | `/settings/defaults` | Get system defaults | STAFF |
| POST | `/settings/reset` | Reset to defaults | ADMIN |

---

## 24. System (`/system`)

**Tier**: Core
**File**: `endpoints/system.py`
**Endpoints**: 4

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/system/version` | Get system version | PUBLIC |
| GET | `/system/health` | Health check | PUBLIC |
| GET | `/system/info` | Get system info | STAFF |
| GET | `/system/updates` | Check for updates | ADMIN |

---

## 25. Security (`/security`)

**Tier**: Core
**File**: `endpoints/security.py`
**Endpoints**: ~13

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/security/audit-log` | Get audit log | ADMIN |
| GET | `/security/audit-log/{id}` | Get audit entry | ADMIN |
| GET | `/security/sessions` | List active sessions | ADMIN |
| DELETE | `/security/sessions/{id}` | Terminate session | ADMIN |
| GET | `/security/login-history` | Get login history | ADMIN |
| GET | `/security/failed-logins` | Get failed login attempts | ADMIN |
| POST | `/security/lock-user/{user_id}` | Lock user account | ADMIN |
| POST | `/security/unlock-user/{user_id}` | Unlock user account | ADMIN |
| GET | `/security/permissions` | List permissions | ADMIN |
| GET | `/security/roles` | List roles | ADMIN |
| POST | `/security/roles` | Create role | ADMIN |
| PATCH | `/security/roles/{id}` | Update role | ADMIN |
| DELETE | `/security/roles/{id}` | Delete role | ADMIN |

---

## 26. Setup (`/setup`)

**Tier**: Core
**File**: `endpoints/setup.py`
**Endpoints**: 3

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/setup/status` | Check if setup completed | PUBLIC |
| POST | `/setup/initial` | Create initial admin user | PUBLIC |
| POST | `/setup/complete` | Mark setup complete | PUBLIC |

---

## 28. Traceability (`/traceability`)

**Tier**: Core
**File**: `endpoints/traceability.py`
**Endpoints**: 4

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/traceability/forward/{serial}` | Trace forward (where used) | STAFF |
| GET | `/traceability/backward/{serial}` | Trace backward (sources) | STAFF |
| GET | `/traceability/lot/{lot_number}` | Trace by lot number | STAFF |
| GET | `/traceability/recall-impact` | Analyze recall impact | STAFF |

---

## 29. Maintenance (`/maintenance`)

**Tier**: Core
**File**: `endpoints/maintenance.py`
**Endpoints**: 7

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/maintenance/logs` | List maintenance logs | STAFF |
| POST | `/maintenance/logs` | Create maintenance log | STAFF |
| GET | `/maintenance/logs/{id}` | Get maintenance log | STAFF |
| PATCH | `/maintenance/logs/{id}` | Update log | STAFF |
| DELETE | `/maintenance/logs/{id}` | Delete log | STAFF |
| GET | `/maintenance/upcoming` | Get upcoming maintenance | STAFF |
| GET | `/maintenance/overdue` | Get overdue maintenance | STAFF |

---

## 30. Command Center (`/command-center`)

**Tier**: Core
**File**: `endpoints/command_center.py`
**Endpoints**: 3

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/command-center/dashboard` | Get command center data | STAFF |
| GET | `/command-center/alerts` | Get active alerts | STAFF |
| POST | `/command-center/alerts/{id}/dismiss` | Dismiss alert | STAFF |

---

## 31. Exports (`/exports`)

**Tier**: Core
**File**: `endpoints/exports.py`
**Endpoints**: ~4

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/exports/products` | Export products CSV | STAFF |
| GET | `/exports/orders` | Export orders CSV | STAFF |
| GET | `/exports/inventory` | Export inventory CSV | STAFF |

---

## Admin Endpoints (`/admin`)

All admin endpoints require STAFF or ADMIN authentication.

### 32. Admin - Users (`/admin/users`)

**Tier**: Core
**File**: `endpoints/admin/users.py`
**Endpoints**: 8

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/users` | List admin/operator users | ADMIN |
| POST | `/admin/users` | Create admin/operator user | ADMIN |
| GET | `/admin/users/{id}` | Get user details | ADMIN |
| PATCH | `/admin/users/{id}` | Update user | ADMIN |
| DELETE | `/admin/users/{id}` | Delete user | ADMIN |
| POST | `/admin/users/{id}/reset-password` | Reset user password | ADMIN |
| POST | `/admin/users/{id}/activate` | Activate user | ADMIN |
| POST | `/admin/users/{id}/deactivate` | Deactivate user | ADMIN |

---

### 33. Admin - BOM (`/admin/bom`)

**Tier**: Core
**File**: `endpoints/admin/bom.py`
**Endpoints**: 15

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/bom` | List BOMs | STAFF |
| POST | `/admin/bom` | Create BOM | STAFF |
| GET | `/admin/bom/{id}` | Get BOM with lines | STAFF |
| PATCH | `/admin/bom/{id}` | Update BOM header | STAFF |
| DELETE | `/admin/bom/{id}` | Delete/deactivate BOM | STAFF |
| POST | `/admin/bom/{id}/lines` | Add BOM line | STAFF |
| PATCH | `/admin/bom/{id}/lines/{line_id}` | Update BOM line | STAFF |
| DELETE | `/admin/bom/{id}/lines/{line_id}` | Delete BOM line | STAFF |
| POST | `/admin/bom/{id}/recalculate` | Recalculate cost | STAFF |
| POST | `/admin/bom/{id}/copy` | Copy BOM to product | STAFF |
| GET | `/admin/bom/product/{product_id}` | Get BOM by product | STAFF |
| GET | `/admin/bom/{id}/explode` | Multi-level BOM explosion | STAFF |
| GET | `/admin/bom/{id}/cost-rollup` | Get rolled-up costs | STAFF |
| GET | `/admin/bom/where-used/{product_id}` | Find BOMs using component | STAFF |
| POST | `/admin/bom/{id}/validate` | Validate BOM | STAFF |

---

### 35. Admin - Dashboard (`/admin/dashboard`)

**Tier**: Core
**File**: `endpoints/admin/dashboard.py`
**Endpoints**: 11

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/dashboard` | Get dashboard overview | STAFF |
| GET | `/admin/dashboard/sales` | Get sales metrics | STAFF |
| GET | `/admin/dashboard/production` | Get production metrics | STAFF |
| GET | `/admin/dashboard/inventory` | Get inventory metrics | STAFF |
| GET | `/admin/dashboard/orders` | Get order metrics | STAFF |
| GET | `/admin/dashboard/trends` | Get trend data | STAFF |
| GET | `/admin/dashboard/alerts` | Get active alerts | STAFF |
| GET | `/admin/dashboard/kpis` | Get KPI summary | STAFF |
| GET | `/admin/dashboard/recent-activity` | Get recent activity | STAFF |
| GET | `/admin/dashboard/quick-stats` | Get quick stats | STAFF |
| GET | `/admin/dashboard/charts` | Get chart data | STAFF |

---

### 36. Admin - Fulfillment (`/admin/fulfillment`)

**Tier**: Core
**File**: `endpoints/admin/fulfillment.py`
**Endpoints**: ~17

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/fulfillment/queue` | Get production queue | STAFF |
| GET | `/admin/fulfillment/in-progress` | Get in-progress items | STAFF |
| GET | `/admin/fulfillment/ready-to-ship` | Get ready to ship | STAFF |
| POST | `/admin/fulfillment/{id}/start` | Start fulfillment | STAFF |
| POST | `/admin/fulfillment/{id}/complete` | Complete fulfillment | STAFF |
| POST | `/admin/fulfillment/{id}/qc-pass` | Pass QC | STAFF |
| POST | `/admin/fulfillment/{id}/qc-fail` | Fail QC | STAFF |
| POST | `/admin/fulfillment/{id}/ship` | Record shipment | STAFF |
| POST | `/admin/fulfillment/{id}/pack` | Record packing | STAFF |
| GET | `/admin/fulfillment/{id}/checklist` | Get fulfillment checklist | STAFF |
| POST | `/admin/fulfillment/{id}/checklist` | Update checklist | STAFF |
| GET | `/admin/fulfillment/stats` | Get fulfillment stats | STAFF |
| GET | `/admin/fulfillment/by-order/{order_id}` | Get by order | STAFF |
| GET | `/admin/fulfillment/timeline/{order_id}` | Get timeline | STAFF |
| POST | `/admin/fulfillment/{id}/assign` | Assign operator | STAFF |
| POST | `/admin/fulfillment/{id}/unassign` | Unassign operator | STAFF |
| GET | `/admin/fulfillment/workload` | Get workload distribution | STAFF |

---

### 37. Admin - Audit (`/admin/audit`)

**Tier**: Core
**File**: `endpoints/admin/audit.py`
**Endpoints**: 4

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/audit` | Get audit log | STAFF |
| GET | `/admin/audit/{id}` | Get audit entry | STAFF |
| GET | `/admin/audit/by-entity/{entity_type}/{entity_id}` | Get by entity | STAFF |
| GET | `/admin/audit/by-user/{user_id}` | Get by user | STAFF |

---

### 38. Admin - Traceability (`/admin/traceability`)

**Tier**: Core
**File**: `endpoints/admin/traceability.py`
**Endpoints**: 18

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/traceability/serials` | List serial numbers | STAFF |
| POST | `/admin/traceability/serials` | Create serial | STAFF |
| GET | `/admin/traceability/serials/{serial}` | Get serial details | STAFF |
| PATCH | `/admin/traceability/serials/{serial}` | Update serial | STAFF |
| GET | `/admin/traceability/serials/{serial}/history` | Get serial history | STAFF |
| GET | `/admin/traceability/lots` | List lots | STAFF |
| POST | `/admin/traceability/lots` | Create lot | STAFF |
| GET | `/admin/traceability/lots/{lot}` | Get lot details | STAFF |
| PATCH | `/admin/traceability/lots/{lot}` | Update lot | STAFF |
| GET | `/admin/traceability/lots/{lot}/serials` | Get serials in lot | STAFF |
| POST | `/admin/traceability/lots/{lot}/recall` | Initiate recall | ADMIN |
| GET | `/admin/traceability/forward/{identifier}` | Forward trace | STAFF |
| GET | `/admin/traceability/backward/{identifier}` | Backward trace | STAFF |
| GET | `/admin/traceability/recall-analysis` | Analyze recall impact | STAFF |
| GET | `/admin/traceability/genealogy/{serial}` | Get full genealogy | STAFF |
| POST | `/admin/traceability/link` | Link serial to parent | STAFF |
| GET | `/admin/traceability/alerts` | Get traceability alerts | STAFF |
| POST | `/admin/traceability/alerts/{id}/resolve` | Resolve alert | STAFF |

---

### 39. Admin - Inventory Transactions (`/admin/inventory-transactions`)

**Tier**: Core
**File**: `endpoints/admin/inventory_transactions.py`
**Endpoints**: 5

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/inventory-transactions` | List transactions | STAFF |
| GET | `/admin/inventory-transactions/{id}` | Get transaction | STAFF |
| GET | `/admin/inventory-transactions/by-product/{product_id}` | Get by product | STAFF |
| GET | `/admin/inventory-transactions/by-location/{location_id}` | Get by location | STAFF |
| POST | `/admin/inventory-transactions/batch-adjustment` | Batch adjustment | STAFF |

---

### 40. Admin - Export (`/admin/export`)

**Tier**: Core
**File**: `endpoints/admin/export.py`
**Endpoints**: 2

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/export/products` | Export products | STAFF |
| GET | `/admin/export/orders` | Export orders | STAFF |

---

### 41. Admin - Data Import (`/admin/data-import`)

**Tier**: Core
**File**: `endpoints/admin/data_import.py`
**Endpoints**: 2

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/admin/data-import/products` | Import products | STAFF |
| POST | `/admin/data-import/inventory` | Import inventory | STAFF |

---

### 42. Admin - Orders (`/admin/orders`)

**Tier**: Core
**File**: `endpoints/admin/orders.py`
**Endpoints**: 2

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/admin/orders/import-template` | Import order template | STAFF |
| GET | `/admin/orders/template` | Get order template | STAFF |

---

### 43. Admin - UOM (`/admin/uom`)

**Tier**: Core
**File**: `endpoints/admin/uom.py`
**Endpoints**: 6

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/uom` | List units of measure | STAFF |
| POST | `/admin/uom` | Create UOM | ADMIN |
| GET | `/admin/uom/{id}` | Get UOM | STAFF |
| PATCH | `/admin/uom/{id}` | Update UOM | ADMIN |
| DELETE | `/admin/uom/{id}` | Delete UOM | ADMIN |
| POST | `/admin/uom/convert` | Convert quantity | STAFF |

---

### 44. Admin - Locations (`/admin/locations`)

**Tier**: Core
**File**: `endpoints/admin/locations.py`
**Endpoints**: 5

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/locations` | List locations | STAFF |
| POST | `/admin/locations` | Create location | STAFF |
| GET | `/admin/locations/{id}` | Get location | STAFF |
| PATCH | `/admin/locations/{id}` | Update location | STAFF |
| DELETE | `/admin/locations/{id}` | Delete location | STAFF |

---

### 45. Admin - System (`/admin/system`)

**Tier**: Core
**File**: `endpoints/admin/system.py`
**Endpoints**: 3

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| GET | `/admin/system/version` | Get version info | STAFF |
| GET | `/admin/system/updates` | Check for updates | ADMIN |
| POST | `/admin/system/maintenance` | Run maintenance | ADMIN |

---

### 46. Admin - Uploads (`/admin/uploads`)

**Tier**: Core
**File**: `endpoints/admin/uploads.py`
**Endpoints**: 2

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/admin/uploads/product-image` | Upload product image | STAFF |
| DELETE | `/admin/uploads/product-image/{id}` | Delete product image | STAFF |

---

## Test Endpoints

### 47. Test (`/test`)

**Tier**: Development only
**File**: `endpoints/test.py`
**Endpoints**: ~5 (non-production only)

| Method | Path | Description | Auth |
| ------ | ---- | ----------- | ---- |
| POST | `/test/seed-data` | Seed test data | STAFF |
| POST | `/test/reset-db` | Reset database | ADMIN |
| GET | `/test/health` | Extended health check | PUBLIC |
| POST | `/test/create-user` | Create test user | STAFF |
| POST | `/test/cleanup` | Clean up test data | STAFF |

> Only enabled when ENVIRONMENT != "production"

---

## Error Responses

All endpoints return standard error responses:

```json
{
  "detail": "Error message here"
}
```

### HTTP Status Codes

- `200` - Success
- `201` - Created
- `204` - No Content (successful delete)
- `400` - Bad Request (validation error)
- `401` - Unauthorized (missing/invalid token)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `409` - Conflict (duplicate resource)
- `422` - Unprocessable Entity (validation failed)
- `429` - Too Many Requests (rate limited)
- `500` - Internal Server Error

---

## Pagination

List endpoints support standard pagination:

```text
?page=1&page_size=50
```

Response includes:

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

*Last updated: 2026-01-28*
*Generated for FilaOps Core*
