<!-- AUTO-GENERATED — Do not edit manually. Regenerate: cd backend && python scripts/generate_schema_reference.py -->

# FilaOps Database Schema Reference

**Generated:** 2026-03-22
**Source:** FilaOps Core v3.5.0
**Total Models:** 59 (Core only)
**Purpose:** AI knowledge source for codebase understanding

> This is the **Core (Open Source)** schema reference.

---

## Table of Contents

1. [Core ERP Models](#core-erp-models) (13 models)
2. [Manufacturing Models](#manufacturing-models) (11 models)
3. [User & Auth Models](#user-auth-models) (4 models)
4. [Quote & Sales Models](#quote-sales-models) (3 models)
5. [Material & Traceability Models](#material-traceability-models) (10 models)
6. [MRP Models](#mrp-models) (2 models)
7. [Document Models](#document-models) (2 models)
8. [Settings Models](#settings-models) (1 model)
9. [Event Models](#event-models) (3 models)
10. [UOM Models](#uom-models) (1 model)
11. [Accounting Models](#accounting-models) (4 models)
12. [Tax Models](#tax-models) (1 model)
13. [Reference Data Models](#reference-data-models) (4 models)

---

## Core ERP Models

### BOM

**Table:** `boms` | **Tier:** Core | **File:** `bom.py:10`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| product_id | Integer | FK->products.id, NOT NULL | FK reference to products.id |
| code | String(50) |  | Unique code identifier |
| name | String(255) |  | Display name |
| version | Integer | DEFAULT 1 | Version number |
| revision | String(10) |  | Revision identifier |
| active | Boolean | DEFAULT True, NOT NULL | Active flag |
| total_cost | Numeric(18, 4) |  | Total cost amount |
| assembly_time_minutes | Integer |  | Assembly time minutes |
| effective_date | Date |  | Effective date |
| notes | Text |  | Additional notes |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |

**Relationships:**

- `product` -> Product (many-to-one)
- `lines` -> BOMLine (one-to-many)

---

### BOMLine

**Table:** `bom_lines` | **Tier:** Core | **File:** `bom.py:49`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| bom_id | Integer | FK->boms.id, NOT NULL | FK reference to boms.id |
| component_id | Integer | FK->products.id, NOT NULL | FK reference to products.id |
| sequence | Integer |  | Sort order / sequence |
| quantity | Numeric(18, 4) | NOT NULL | Quantity value |
| unit | String(20) | DEFAULT 'EA', NOT NULL | Unit of measure |
| consume_stage | String(20) | DEFAULT 'production', NOT NULL | Consume stage |
| is_cost_only | Boolean | DEFAULT False, NOT NULL | Cost Only flag |
| scrap_factor | Numeric(5, 2) | DEFAULT 0 | Scrap factor |
| notes | Text |  | Additional notes |

**Relationships:**

- `bom` -> BOM (many-to-one)
- `component` -> Product (many-to-one)

---

### Inventory

**Table:** `inventory` | **Tier:** Core | **File:** `inventory.py:32`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| product_id | Integer | FK->products.id, NOT NULL | FK reference to products.id |
| location_id | Integer | FK->inventory_locations.id, NOT NULL | FK reference to inventory_locations.id |
| on_hand_quantity | Numeric(10, 2) | DEFAULT 0, NOT NULL | Physical quantity on hand |
| allocated_quantity | Numeric(10, 2) | DEFAULT 0, NOT NULL | Quantity allocated to orders |
| available_quantity | Numeric(10, 2) | COMPUTED | Quantity available (on_hand - allocated) |
| last_counted | DateTime |  | Last counted |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `product` -> Product (many-to-one)
- `location` -> InventoryLocation (many-to-one)

---

### InventoryLocation

**Table:** `inventory_locations` | **Tier:** Core | **File:** `inventory.py:11`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| name | String(100) | NOT NULL | Display name |
| code | String(50) |  | Unique code identifier |
| type | String(50) |  | Type classifier |
| parent_id | Integer | FK->inventory_locations.id | FK reference to inventory_locations.id |
| active | Boolean | DEFAULT True | Active flag |

**Relationships:**

- `parent` -> InventoryLocation (many-to-one)
- `inventory_items` -> Inventory (one-to-many)

---

### InventoryTransaction

**Table:** `inventory_transactions` | **Tier:** Core | **File:** `inventory.py:61`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| product_id | Integer | FK->products.id, NOT NULL | FK reference to products.id |
| location_id | Integer | FK->inventory_locations.id | FK reference to inventory_locations.id |
| journal_entry_id | Integer | FK->gl_journal_entries.id | FK reference to gl_journal_entries.id |
| transaction_type | String(50) | NOT NULL | Transaction type |
| reference_type | String(50) |  | Reference type |
| reference_id | Integer |  | Reference reference |
| quantity | Numeric(18, 4) | NOT NULL | Quantity value |
| lot_number | String(100) |  | Lot number |
| serial_number | String(100) |  | Serial number |
| cost_per_unit | Numeric(18, 4) |  | Cost per unit |
| total_cost | Numeric(18, 4) |  | Total cost amount |
| unit | String(20) |  | Unit of measure |
| notes | Text |  | Additional notes |
| reason_code | String(50) |  | Reason code |
| requires_approval | Boolean | DEFAULT False, NOT NULL | Requires approval |
| approval_reason | Text |  | Approval reason |
| approved_by | String(100) |  | Approver reference |
| approved_at | DateTime |  | Approval timestamp |
| transaction_date | Date | INDEX | Transaction date |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| created_by | String(100) |  | Creator reference |

**Relationships:**

- `location` -> InventoryLocation (many-to-one)
- `product` -> Product (many-to-one)
- `journal_entry` -> GLJournalEntry (many-to-one)

---

### ItemCategory

**Table:** `item_categories` | **Tier:** Core | **File:** `item_category.py:11`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| code | String(50) | UNIQUE, NOT NULL, INDEX | Unique code identifier |
| name | String(100) | NOT NULL | Display name |
| parent_id | Integer | FK->item_categories.id | FK reference to item_categories.id |
| description | Text |  | Description text |
| sort_order | Integer | DEFAULT 0 | Sort order |
| is_active | Boolean | DEFAULT True | Active flag |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `parent` -> ItemCategory (many-to-one)
- `products` -> Product (one-to-many)

---

### Payment

**Table:** `payments` | **Tier:** Core | **File:** `payment.py:14`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| sales_order_id | Integer | FK->sales_orders.id, NOT NULL, INDEX | FK reference to sales_orders.id |
| recorded_by_id | Integer | FK->users.id, INDEX | FK reference to users.id |
| payment_number | String(50) | UNIQUE, NOT NULL, INDEX | Payment number |
| amount | Numeric(10, 2) | NOT NULL | Amount |
| payment_method | String(50) | NOT NULL | Payment method |
| transaction_id | String(255) |  | Transaction reference |
| check_number | String(50) |  | Check number |
| payment_type | String(20) | NOT NULL, DEFAULT 'payment' | Payment type |
| status | String(20) | NOT NULL, DEFAULT 'completed', INDEX | Current status |
| notes | Text |  | Additional notes |
| payment_date | DateTime | NOT NULL, DEFAULT utcnow, INDEX | Payment date |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, DEFAULT utcnow | Last update timestamp |

**Relationships:**

- `sales_order` -> SalesOrder (many-to-one)
- `recorded_by` -> User (many-to-one)

---

### Product

**Table:** `products` | **Tier:** Core | **File:** `product.py:11`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| sku | String(50) | UNIQUE, NOT NULL, INDEX | Stock keeping unit |
| legacy_sku | String(50) | INDEX | Legacy sku |
| name | String(255) | NOT NULL | Display name |
| description | Text |  | Description text |
| unit | String(20) | DEFAULT 'EA' | Unit of measure |
| purchase_uom | String(20) | DEFAULT 'EA' | Purchase uom |
| purchase_factor | Numeric(18, 6) |  | Purchase factor |
| item_type | String(20) | DEFAULT 'finished_good', NOT NULL | Item type |
| procurement_type | String(20) | DEFAULT 'buy', NOT NULL | Procurement type |
| category_id | Integer | FK->item_categories.id | FK reference to item_categories.id |
| material_type_id | Integer | FK->material_types.id | FK reference to material_types.id |
| color_id | Integer | FK->colors.id | FK reference to colors.id |
| cost_method | String(20) | DEFAULT 'average' | Cost method |
| standard_cost | Numeric(18, 4) |  | Standard cost for costing |
| average_cost | Numeric(18, 4) |  | Running average cost |
| last_cost | Numeric(18, 4) |  | Most recent purchase cost |
| selling_price | Numeric(18, 4) |  | Selling price |
| weight_oz | Numeric(8, 2) |  | Weight oz |
| length_in | Numeric(8, 2) |  | Length in |
| width_in | Numeric(8, 2) |  | Width in |
| height_in | Numeric(8, 2) |  | Height in |
| lead_time_days | Integer |  | Lead time days |
| min_order_qty | Numeric(10, 2) |  | Min order qty |
| reorder_point | Numeric(10, 2) |  | Reorder point |
| safety_stock | Numeric(18, 4) | DEFAULT 0 | Safety stock |
| preferred_vendor_id | Integer | FK->vendors.id, INDEX | FK reference to vendors.id |
| stocking_policy | String(20) | DEFAULT 'on_demand', NOT NULL | Stocking policy |
| upc | String(50) |  | Upc |
| type | String(20) | DEFAULT 'standard', NOT NULL | Type classifier |
| gcode_file_path | String(500) |  | Gcode file path |
| image_url | String(500) |  | Product image URL |
| is_public | Boolean | DEFAULT True | Public visibility flag |
| sales_channel | String(20) | DEFAULT 'public' | Sales channel |
| customer_id | Integer | FK->customers.id, INDEX | FK reference to customers.id |
| is_raw_material | Boolean | DEFAULT False | Raw Material flag |
| has_bom | Boolean | DEFAULT False | Has Bom flag |
| track_lots | Boolean | DEFAULT False | Track Lots flag |
| track_serials | Boolean | DEFAULT False | Track Serials flag |
| active | Boolean | DEFAULT True | Active flag |
| woocommerce_product_id | BigInteger |  | Woocommerce Product reference |
| squarespace_product_id | String(50) |  | Squarespace Product reference |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `boms` -> BOM (one-to-many)
- `inventory_items` -> Inventory (one-to-many)
- `production_orders` -> ProductionOrder (one-to-many)
- `quotes` -> Quote (one-to-many)
- `item_category` -> ItemCategory (one-to-many)
- `routings` -> Routing (one-to-many)
- `spools` -> MaterialSpool (one-to-many)
- `material_type` -> MaterialType (many-to-one)
- `color` -> Color (many-to-one)

---

### PurchaseOrder

**Table:** `purchase_orders` | **Tier:** Core | **File:** `purchase_order.py:11`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| po_number | String(50) | UNIQUE, NOT NULL, INDEX | Po number |
| vendor_id | Integer | FK->vendors.id, NOT NULL, INDEX | FK reference to vendors.id |
| status | String(50) | DEFAULT 'draft', NOT NULL | Current status |
| order_date | Date |  | Order date |
| expected_date | Date |  | Expected date |
| shipped_date | Date |  | Shipped date |
| received_date | Date |  | Received date |
| tracking_number | String(200) |  | Tracking number |
| carrier | String(100) |  | Carrier |
| subtotal | Numeric(18, 4) | DEFAULT 0, NOT NULL | Subtotal |
| tax_amount | Numeric(18, 4) | DEFAULT 0, NOT NULL | Tax amount |
| shipping_cost | Numeric(18, 4) | DEFAULT 0, NOT NULL | Shipping cost |
| total_amount | Numeric(18, 4) | DEFAULT 0, NOT NULL | Total amount |
| payment_method | String(100) |  | Payment method |
| payment_reference | String(200) |  | Payment reference |
| document_url | String(1000) |  | Document url |
| notes | Text |  | Additional notes |
| created_by | String(100) |  | Creator reference |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `vendor` -> Vendor (many-to-one)
- `lines` -> PurchaseOrderLine (one-to-many)
- `documents` -> PurchaseOrderDocument (one-to-many)

---

### PurchaseOrderLine

**Table:** `purchase_order_lines` | **Tier:** Core | **File:** `purchase_order.py:67`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| purchase_order_id | Integer | FK->purchase_orders.id, NOT NULL, INDEX | FK reference to purchase_orders.id |
| product_id | Integer | FK->products.id, NOT NULL, INDEX | FK reference to products.id |
| line_number | Integer | NOT NULL | Line number |
| quantity_ordered | Numeric(18, 4) | NOT NULL | Quantity ordered |
| quantity_received | Numeric(18, 4) | DEFAULT 0, NOT NULL | Quantity received |
| purchase_unit | String(20) |  | Purchase unit |
| unit_cost | Numeric(18, 4) | NOT NULL | Unit cost |
| line_total | Numeric(18, 4) | NOT NULL | Line total |
| notes | Text |  | Additional notes |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `purchase_order` -> PurchaseOrder (many-to-one)
- `product` -> Product (many-to-one)

---

### SalesOrder

**Table:** `sales_orders` | **Tier:** Core | **File:** `sales_order.py:13`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| user_id | Integer | FK->users.id, NOT NULL, INDEX | FK reference to users.id |
| quote_id | Integer | FK->quotes.id, INDEX | FK reference to quotes.id |
| order_number | String(50) | UNIQUE, NOT NULL, INDEX | Order number identifier |
| order_type | String(20) | NOT NULL, DEFAULT 'quote_based', INDEX | Order type |
| source | String(50) | NOT NULL, DEFAULT 'portal', INDEX | Source |
| source_order_id | String(255) | INDEX | Source Order reference |
| product_id | Integer | FK->products.id, INDEX | FK reference to products.id |
| product_name | String(255) |  | Product name |
| quantity | Integer | NOT NULL | Quantity value |
| material_type | String(50) | NOT NULL | Material type |
| color | String(50) |  | Color |
| finish | String(50) | NOT NULL, DEFAULT 'standard' | Finish |
| unit_price | Numeric(10, 2) | NOT NULL | Unit price |
| total_price | Numeric(10, 2) | NOT NULL | Total price |
| tax_amount | Numeric(10, 2) | DEFAULT 0.0 | Tax amount |
| tax_rate | Numeric(5, 4) |  | Tax rate |
| tax_name | String(100) |  | Tax name |
| is_taxable | Boolean | DEFAULT True | Taxable flag |
| shipping_cost | Numeric(10, 2) | DEFAULT 0.0 | Shipping cost |
| grand_total | Numeric(10, 2) | NOT NULL | Grand total |
| status | String(50) | NOT NULL, DEFAULT 'draft', INDEX | Current status |
| payment_status | String(50) | NOT NULL, DEFAULT 'pending', INDEX | Payment status |
| payment_method | String(50) |  | Payment method |
| payment_transaction_id | String(255) |  | Payment Transaction reference |
| paid_at | DateTime |  | Paid timestamp |
| fulfillment_status | String(50) | NOT NULL, DEFAULT 'pending', INDEX | Fulfillment status |
| rush_level | String(20) | NOT NULL, DEFAULT 'standard' | Rush level |
| estimated_completion_date | DateTime |  | Estimated Completion date |
| actual_completion_date | DateTime |  | Actual Completion date |
| customer_id | Integer | FK->users.id, INDEX | FK reference to users.id |
| customer_name | String(200) |  | Customer name |
| customer_email | String(255) |  | Customer email |
| customer_phone | String(30) |  | Customer phone |
| shipping_address_line1 | String(255) |  | Shipping address line1 |
| shipping_address_line2 | String(255) |  | Shipping address line2 |
| shipping_city | String(100) |  | Shipping city |
| shipping_state | String(50) |  | Shipping state |
| shipping_zip | String(20) |  | Shipping zip |
| shipping_country | String(100) | DEFAULT 'USA' | Shipping country |
| tracking_number | String(255) |  | Tracking number |
| carrier | String(100) |  | Carrier |
| shipped_at | DateTime |  | Shipped timestamp |
| delivered_at | DateTime |  | Delivered timestamp |
| customer_notes | Text |  | Customer notes |
| internal_notes | Text |  | Internal notes |
| production_notes | Text |  | Production notes |
| cancelled_at | DateTime |  | Cancelled timestamp |
| cancellation_reason | Text |  | Cancellation reason |
| created_at | DateTime | NOT NULL, DEFAULT utcnow, INDEX | Creation timestamp |
| updated_at | DateTime | NOT NULL, DEFAULT utcnow | Last update timestamp |
| confirmed_at | DateTime |  | Confirmed timestamp |
| mrp_status | String(50) | INDEX | Mrp status |
| mrp_run_id | Integer | FK->mrp_runs.id, INDEX | FK reference to mrp_runs.id |

**Relationships:**

- `user` -> User (many-to-one)
- `customer` -> User (many-to-one)
- `quote` -> Quote (one-to-one)
- `product` -> Product (many-to-one)
- `lines` -> SalesOrderLine (one-to-many)
- `payments` -> Payment (one-to-many)
- `mrp_run` -> MRPRun (many-to-one)

---

### SalesOrderLine

**Table:** `sales_order_lines` | **Tier:** Core | **File:** `sales_order.py:174`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| sales_order_id | Integer | FK->sales_orders.id, NOT NULL, INDEX | FK reference to sales_orders.id |
| product_id | Integer | FK->products.id, INDEX | FK reference to products.id |
| material_inventory_id | Integer | FK->material_inventory.id, INDEX | FK reference to material_inventory.id |
| quantity | Numeric(10, 2) | NOT NULL | Quantity value |
| unit_price | Numeric(10, 2) | NOT NULL | Unit price |
| discount | Numeric(10, 2) | DEFAULT 0 | Discount |
| tax_rate | Numeric(5, 2) | DEFAULT 0 | Tax rate |
| tax_name | String(100) |  | Tax name |
| total | Numeric(10, 2) | NOT NULL | Total |
| allocated_quantity | Numeric(10, 2) | DEFAULT 0 | Quantity allocated to orders |
| shipped_quantity | Numeric(10, 2) | DEFAULT 0 | Shipped quantity |
| notes | Text |  | Additional notes |
| created_by | Integer |  | Creator reference |

**Relationships:**

- `sales_order` -> SalesOrder (many-to-one)
- `product` -> Product (many-to-one)
- `material_inventory` -> MaterialInventory (many-to-one)

---

### Vendor

**Table:** `vendors` | **Tier:** Core | **File:** `vendor.py:10`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| code | String(50) | UNIQUE, NOT NULL, INDEX | Unique code identifier |
| name | String(200) | NOT NULL | Display name |
| contact_name | String(100) |  | Contact name |
| email | String(200) |  | Email address |
| phone | String(50) |  | Phone |
| website | String(500) |  | Website |
| address_line1 | String(200) |  | Address line1 |
| address_line2 | String(200) |  | Address line2 |
| city | String(100) |  | City |
| state | String(100) |  | State |
| postal_code | String(20) |  | Postal code |
| country | String(100) | DEFAULT 'USA' | Country |
| payment_terms | String(100) |  | Payment terms |
| account_number | String(100) |  | Account number |
| tax_id | String(50) |  | Tax reference |
| lead_time_days | Integer |  | Lead time days |
| rating | Numeric(3, 2) |  | Rating |
| notes | Text |  | Additional notes |
| is_active | Boolean | DEFAULT True, NOT NULL | Active flag |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

---

## Manufacturing Models

### PrintJob

**Table:** `print_jobs` | **Tier:** Core | **File:** `print_job.py:10`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| production_order_id | Integer | FK->production_orders.id | FK reference to production_orders.id |
| printer_id | Integer | FK->printers.id | FK reference to printers.id |
| gcode_file | String(500) |  | Gcode file |
| status | String(50) | NOT NULL, DEFAULT 'queued' | Current status |
| priority | String(20) | DEFAULT 'normal' | Priority |
| estimated_time_minutes | Integer |  | Estimated time minutes |
| actual_time_minutes | Integer |  | Actual time minutes |
| estimated_material_grams | Numeric(18, 4) |  | Estimated material grams |
| actual_material_grams | Numeric(18, 4) |  | Actual material grams |
| variance_percent | Numeric(5, 2) |  | Variance percent |
| queued_at | DateTime | DEFAULT utcnow | Queued timestamp |
| started_at | DateTime |  | Started timestamp |
| finished_at | DateTime |  | Finished timestamp |
| notes | Text |  | Additional notes |

**Relationships:**

- `production_order` -> ProductionOrder (many-to-one)
- `printer` -> Printer (many-to-one)

---

### Printer

**Table:** `printers` | **Tier:** Core | **File:** `printer.py:11`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| code | String(50) | UNIQUE, NOT NULL, INDEX | Unique code identifier |
| name | String(255) | NOT NULL | Display name |
| model | String(100) | NOT NULL | Model |
| serial_number | String(100) |  | Serial number |
| brand | String(50) | NOT NULL, DEFAULT 'generic', INDEX | Brand |
| ip_address | String(50) |  | Ip address |
| mqtt_topic | String(255) |  | Mqtt topic |
| connection_config | JSON |  | Connection config |
| capabilities | JSON |  | Capabilities |
| status | String(50) | DEFAULT 'offline' | Current status |
| last_seen | DateTime |  | Last seen |
| location | String(255) |  | Location |
| work_center_id | Integer | FK->work_centers.id | FK reference to work_centers.id |
| notes | Text |  | Additional notes |
| active | Boolean | DEFAULT True | Active flag |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `print_jobs` -> PrintJob (one-to-many)
- `work_center` -> WorkCenter (many-to-one)
- `maintenance_logs` -> MaintenanceLog (one-to-many)

---

### ProductionOrder

**Table:** `production_orders` | **Tier:** Core | **File:** `production_order.py:17`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| code | String(50) | UNIQUE, NOT NULL, INDEX | Unique code identifier |
| product_id | Integer | FK->products.id, NOT NULL, INDEX | FK reference to products.id |
| bom_id | Integer | FK->boms.id, INDEX | FK reference to boms.id |
| routing_id | Integer | FK->routings.id, INDEX | FK reference to routings.id |
| sales_order_id | Integer | FK->sales_orders.id, INDEX | FK reference to sales_orders.id |
| sales_order_line_id | Integer | FK->sales_order_lines.id, INDEX | FK reference to sales_order_lines.id |
| parent_order_id | Integer | FK->production_orders.id, INDEX | FK reference to production_orders.id |
| split_sequence | Integer |  | Split sequence |
| quantity_ordered | Numeric(18, 4) | NOT NULL | Quantity ordered |
| quantity_completed | Numeric(18, 4) | DEFAULT 0, NOT NULL | Quantity completed |
| quantity_scrapped | Numeric(18, 4) | DEFAULT 0, NOT NULL | Quantity scrapped |
| source | String(50) | DEFAULT 'manual', NOT NULL | Source |
| order_type | String(20) | DEFAULT 'MAKE_TO_ORDER', NOT NULL | Order type |
| status | String(50) | DEFAULT 'draft', NOT NULL, INDEX | Current status |
| qc_status | String(50) | DEFAULT 'not_required', NOT NULL | Qc status |
| qc_notes | Text |  | Qc notes |
| qc_inspected_by | String(100) |  | Qc inspected by |
| qc_inspected_at | DateTime |  | Qc Inspected timestamp |
| priority | Integer | DEFAULT 3, NOT NULL | Priority |
| due_date | Date | INDEX | Due date |
| scheduled_start | DateTime |  | Scheduled start |
| scheduled_end | DateTime |  | Scheduled end |
| actual_start | DateTime |  | Actual start |
| actual_end | DateTime |  | Actual end |
| estimated_time_minutes | Integer |  | Estimated time minutes |
| actual_time_minutes | Integer |  | Actual time minutes |
| estimated_material_cost | Numeric(18, 4) |  | Estimated material cost |
| estimated_labor_cost | Numeric(18, 4) |  | Estimated labor cost |
| estimated_total_cost | Numeric(18, 4) |  | Estimated total cost |
| actual_material_cost | Numeric(18, 4) |  | Actual material cost |
| actual_labor_cost | Numeric(18, 4) |  | Actual labor cost |
| actual_total_cost | Numeric(18, 4) |  | Actual total cost |
| assigned_to | String(100) |  | Assigned to |
| notes | Text |  | Additional notes |
| scrap_reason | String(100) |  | Scrap reason |
| scrapped_at | DateTime |  | Scrapped timestamp |
| remake_of_id | Integer | FK->production_orders.id | FK reference to production_orders.id |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |
| created_by | String(100) |  | Creator reference |
| released_at | DateTime |  | Released timestamp |
| completed_at | DateTime |  | Completion timestamp |

**Relationships:**

- `product` -> Product (many-to-one)
- `bom` -> BOM (many-to-one)
- `routing` -> Routing (many-to-one)
- `sales_order` -> SalesOrder (many-to-one)
- `print_jobs` -> PrintJob (one-to-many)
- `operations` -> ProductionOrderOperation (one-to-many)
- `parent_order` -> ProductionOrder (many-to-one)
- `original_order` -> ProductionOrder (one-to-many)
- `spools_used` -> ProductionOrderSpool (one-to-many)

---

### ProductionOrderOperation

**Table:** `production_order_operations` | **Tier:** Core | **File:** `production_order.py:202`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| production_order_id | Integer | FK->production_orders.id, NOT NULL | FK reference to production_orders.id |
| routing_operation_id | Integer | FK->routing_operations.id | FK reference to routing_operations.id |
| work_center_id | Integer | FK->work_centers.id, NOT NULL | FK reference to work_centers.id |
| resource_id | Integer | FK->resources.id | FK reference to resources.id |
| printer_id | Integer | FK->printers.id | FK reference to printers.id |
| sequence | Integer | NOT NULL | Sort order / sequence |
| operation_code | String(50) |  | Operation code |
| operation_name | String(200) |  | Operation name |
| status | String(50) | DEFAULT 'pending', NOT NULL, INDEX | Current status |
| quantity_completed | Numeric(18, 4) | DEFAULT 0, NOT NULL | Quantity completed |
| quantity_scrapped | Numeric(18, 4) | DEFAULT 0, NOT NULL | Quantity scrapped |
| scrap_reason | String(100) |  | Scrap reason |
| planned_setup_minutes | Numeric(10, 2) | DEFAULT 0, NOT NULL | Planned setup minutes |
| planned_run_minutes | Numeric(10, 2) | NOT NULL | Planned run minutes |
| actual_setup_minutes | Numeric(10, 2) |  | Actual setup minutes |
| actual_run_minutes | Numeric(10, 2) |  | Actual run minutes |
| scheduled_start | DateTime |  | Scheduled start |
| scheduled_end | DateTime |  | Scheduled end |
| actual_start | DateTime |  | Actual start |
| actual_end | DateTime |  | Actual end |
| bambu_task_id | String(100) |  | Bambu Task reference |
| bambu_plate_index | Integer |  | Bambu plate index |
| operator_id | Integer |  | Operator reference |
| operator_name | String(100) |  | Operator name |
| notes | Text |  | Additional notes |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `production_order` -> ProductionOrder (many-to-one)
- `routing_operation` -> RoutingOperation (many-to-one)
- `work_center` -> WorkCenter (many-to-one)
- `resource` -> Resource (many-to-one)
- `printer` -> Printer (many-to-one)
- `materials` -> ProductionOrderOperationMaterial (one-to-many)

---

### ProductionOrderOperationMaterial

**Table:** `production_order_operation_materials` | **Tier:** Core | **File:** `production_order.py:329`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| production_order_operation_id | Integer | FK->production_order_operations.id, NOT NULL, INDEX | FK reference to production_order_operations.id |
| component_id | Integer | FK->products.id, NOT NULL, INDEX | FK reference to products.id |
| routing_operation_material_id | Integer | FK->routing_operation_materials.id | FK reference to routing_operation_materials.id |
| quantity_required | Numeric(18, 6) | NOT NULL | Quantity required |
| unit | String(20) | DEFAULT 'EA', NOT NULL | Unit of measure |
| quantity_allocated | Numeric(18, 6) | DEFAULT 0, NOT NULL | Quantity allocated |
| quantity_consumed | Numeric(18, 6) | DEFAULT 0, NOT NULL | Quantity consumed |
| lot_number | String(100) |  | Lot number |
| inventory_transaction_id | Integer | FK->inventory_transactions.id | FK reference to inventory_transactions.id |
| status | String(20) | DEFAULT 'pending', NOT NULL | Current status |
| consumed_at | DateTime |  | Consumed timestamp |
| consumed_by | Integer | FK->users.id | FK reference to users.id |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `operation` -> ProductionOrderOperation (one-to-many)
- `component` -> Product (many-to-one)
- `routing_material` -> RoutingOperationMaterial (one-to-many)
- `transaction` -> InventoryTransaction (one-to-many)
- `consumed_by_user` -> User (one-to-many)

---

### Resource

**Table:** `resources` | **Tier:** Core | **File:** `manufacturing.py:15`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| work_center_id | Integer | FK->work_centers.id, NOT NULL, INDEX | FK reference to work_centers.id |
| code | String(50) | NOT NULL, INDEX | Unique code identifier |
| name | String(200) | NOT NULL | Display name |
| machine_type | String(100) |  | Machine type |
| serial_number | String(100) |  | Serial number |
| printer_class | String(20) | DEFAULT 'open' | Printer class |
| bambu_device_id | String(100) |  | Bambu Device reference |
| bambu_ip_address | String(50) |  | Bambu ip address |
| capacity_hours_per_day | Numeric(10, 2) |  | Capacity hours per day |
| status | String(50) | DEFAULT 'available', NOT NULL | Current status |
| is_active | Boolean | DEFAULT True, NOT NULL | Active flag |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `work_center` -> WorkCenter (many-to-one)
- `operations` -> ProductionOrderOperation (one-to-many)

---

### Routing

**Table:** `routings` | **Tier:** Core | **File:** `manufacturing.py:73`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| product_id | Integer | FK->products.id | FK reference to products.id |
| code | String(50) | NOT NULL, INDEX | Unique code identifier |
| name | String(200) |  | Display name |
| is_template | Boolean | DEFAULT False, NOT NULL | Template flag |
| version | Integer | DEFAULT 1, NOT NULL | Version number |
| revision | String(20) | DEFAULT '1.0', NOT NULL | Revision identifier |
| is_active | Boolean | DEFAULT True, NOT NULL | Active flag |
| total_setup_time_minutes | Numeric(10, 2) |  | Total setup time minutes |
| total_run_time_minutes | Numeric(10, 2) |  | Total run time minutes |
| total_cost | Numeric(18, 4) |  | Total cost amount |
| effective_date | Date |  | Effective date |
| notes | Text |  | Additional notes |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `product` -> Product (many-to-one)
- `operations` -> RoutingOperation (one-to-many)

---

### RoutingOperation

**Table:** `routing_operations` | **Tier:** Core | **File:** `manufacturing.py:141`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| routing_id | Integer | FK->routings.id, NOT NULL, INDEX | FK reference to routings.id |
| work_center_id | Integer | FK->work_centers.id, NOT NULL, INDEX | FK reference to work_centers.id |
| sequence | Integer | NOT NULL | Sort order / sequence |
| operation_code | String(50) |  | Operation code |
| operation_name | String(200) |  | Operation name |
| description | Text |  | Description text |
| setup_time_minutes | Numeric(10, 2) | DEFAULT 0, NOT NULL | Setup time minutes |
| run_time_minutes | Numeric(10, 2) | NOT NULL | Run time minutes |
| wait_time_minutes | Numeric(10, 2) | DEFAULT 0, NOT NULL | Wait time minutes |
| move_time_minutes | Numeric(10, 2) | DEFAULT 0, NOT NULL | Move time minutes |
| runtime_source | String(50) | DEFAULT 'manual', NOT NULL | Runtime source |
| slicer_file_path | String(500) |  | Slicer file path |
| units_per_cycle | Integer | DEFAULT 1, NOT NULL | Units per cycle |
| scrap_rate_percent | Numeric(5, 2) | DEFAULT 0, NOT NULL | Scrap rate percent |
| labor_rate_override | Numeric(18, 4) |  | Labor rate override |
| machine_rate_override | Numeric(18, 4) |  | Machine rate override |
| predecessor_operation_id | Integer | FK->routing_operations.id | FK reference to routing_operations.id |
| can_overlap | Boolean | DEFAULT False, NOT NULL | Can overlap |
| is_active | Boolean | DEFAULT True, NOT NULL | Active flag |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `routing` -> Routing (many-to-one)
- `work_center` -> WorkCenter (many-to-one)
- `predecessor` -> RoutingOperation (one-to-many)
- `materials` -> RoutingOperationMaterial (one-to-many)

---

### RoutingOperationMaterial

**Table:** `routing_operation_materials` | **Tier:** Core | **File:** `manufacturing.py:253`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| routing_operation_id | Integer | FK->routing_operations.id, NOT NULL, INDEX | FK reference to routing_operations.id |
| component_id | Integer | FK->products.id, NOT NULL, INDEX | FK reference to products.id |
| quantity | Numeric(18, 6) | NOT NULL | Quantity value |
| quantity_per | String(20) | DEFAULT 'unit', NOT NULL | Quantity per |
| unit | String(20) | DEFAULT 'EA', NOT NULL | Unit of measure |
| scrap_factor | Numeric(5, 2) | DEFAULT 0 | Scrap factor |
| is_cost_only | Boolean | DEFAULT False, NOT NULL | Cost Only flag |
| is_optional | Boolean | DEFAULT False, NOT NULL | Optional flag |
| notes | Text |  | Additional notes |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `routing_operation` -> RoutingOperation (many-to-one)
- `component` -> Product (many-to-one)

---

### ScrapRecord

**Table:** `scrap_records` | **Tier:** Core | **File:** `production_order.py:410`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| production_order_id | Integer | FK->production_orders.id, INDEX | FK reference to production_orders.id |
| production_operation_id | Integer | FK->production_order_operations.id, INDEX | FK reference to production_order_operations.id |
| operation_sequence | Integer |  | Operation sequence |
| product_id | Integer | FK->products.id, NOT NULL, INDEX | FK reference to products.id |
| quantity | Numeric(18, 4) | NOT NULL | Quantity value |
| unit_cost | Numeric(18, 4) | NOT NULL | Unit cost |
| total_cost | Numeric(18, 4) | NOT NULL | Total cost amount |
| scrap_reason_id | Integer | FK->scrap_reasons.id | FK reference to scrap_reasons.id |
| scrap_reason_code | String(50) |  | Scrap reason code |
| notes | Text |  | Additional notes |
| inventory_transaction_id | Integer | FK->inventory_transactions.id | FK reference to inventory_transactions.id |
| journal_entry_id | Integer | FK->gl_journal_entries.id | FK reference to gl_journal_entries.id |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| created_by_user_id | Integer | FK->users.id | FK reference to users.id |

**Relationships:**

- `production_order` -> ProductionOrder (many-to-one)
- `production_operation` -> ProductionOrderOperation (many-to-one)
- `product` -> Product (many-to-one)
- `scrap_reason` -> ScrapReason (many-to-one)
- `inventory_transaction` -> InventoryTransaction (many-to-one)
- `journal_entry` -> GLJournalEntry (many-to-one)
- `created_by` -> User (one-to-many)

---

### WorkCenter

**Table:** `work_centers` | **Tier:** Core | **File:** `work_center.py:14`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| code | String(50) | UNIQUE, NOT NULL, INDEX | Unique code identifier |
| name | String(200) | NOT NULL | Display name |
| description | Text |  | Description text |
| center_type | String(50) | DEFAULT 'production', NOT NULL | Center type |
| capacity_hours_per_day | Numeric(10, 2) |  | Capacity hours per day |
| capacity_units_per_hour | Numeric(10, 2) |  | Capacity units per hour |
| machine_rate_per_hour | Numeric(18, 4) |  | Machine rate per hour |
| labor_rate_per_hour | Numeric(18, 4) |  | Labor rate per hour |
| overhead_rate_per_hour | Numeric(18, 4) |  | Overhead rate per hour |
| hourly_rate | Numeric(10, 2) | DEFAULT 0, NOT NULL | Hourly rate |
| is_bottleneck | Boolean | DEFAULT False, NOT NULL | Bottleneck flag |
| scheduling_priority | Integer | DEFAULT 5, NOT NULL | Scheduling priority |
| is_active | Boolean | DEFAULT True, NOT NULL | Active flag |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `operations` -> ProductionOrderOperation (one-to-many)
- `printers` -> Printer (one-to-many)
- `resources` -> Resource (one-to-many)
- `routing_operations` -> RoutingOperation (one-to-many)

---

## User & Auth Models

### Customer

**Table:** `customers` | **Tier:** Core | **File:** `customer.py:20`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| customer_number | String(50) | UNIQUE, INDEX | Customer number |
| company_name | String(200) | INDEX | Company name |
| first_name | String(100) |  | First name |
| last_name | String(100) |  | Last name |
| email | String(255) | INDEX | Email address |
| phone | String(20) |  | Phone |
| status | String(20) | NOT NULL, DEFAULT 'active', INDEX | Current status |
| billing_address_line1 | String(255) |  | Billing address line1 |
| billing_address_line2 | String(255) |  | Billing address line2 |
| billing_city | String(100) |  | Billing city |
| billing_state | String(50) |  | Billing state |
| billing_zip | String(20) |  | Billing zip |
| billing_country | String(100) | DEFAULT 'USA' | Billing country |
| shipping_address_line1 | String(255) |  | Shipping address line1 |
| shipping_address_line2 | String(255) |  | Shipping address line2 |
| shipping_city | String(100) |  | Shipping city |
| shipping_state | String(50) |  | Shipping state |
| shipping_zip | String(20) |  | Shipping zip |
| shipping_country | String(100) | DEFAULT 'USA' | Shipping country |
| notes | Text |  | Additional notes |
| created_at | DateTime | DEFAULT now(), NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT now(), NOT NULL | Last update timestamp |

**Relationships:**

- `users` -> User (one-to-many)

---

### PasswordResetRequest

**Table:** `password_reset_requests` | **Tier:** Core | **File:** `user.py:137`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| user_id | Integer | FK->users.id, NOT NULL, INDEX | FK reference to users.id |
| token | String(255) | UNIQUE, NOT NULL, INDEX | Token |
| approval_token | String(255) | UNIQUE, NOT NULL, INDEX | Approval token |
| status | String(20) | DEFAULT 'pending', NOT NULL, INDEX | Current status |
| created_at | DateTime | DEFAULT now(), NOT NULL | Creation timestamp |
| expires_at | DateTime | NOT NULL | Expiration timestamp |
| approved_at | DateTime |  | Approval timestamp |
| completed_at | DateTime |  | Completion timestamp |
| admin_notes | String(500) |  | Admin notes |

**Relationships:**

- `user` -> User (many-to-one)

---

### RefreshToken

**Table:** `refresh_tokens` | **Tier:** Core | **File:** `user.py:100`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| user_id | Integer | FK->users.id, NOT NULL, INDEX | FK reference to users.id |
| token_hash | String(255) | UNIQUE, NOT NULL, INDEX | Token hash |
| expires_at | DateTime | NOT NULL, INDEX | Expiration timestamp |
| revoked | Boolean | DEFAULT False, NOT NULL | Revocation flag |
| created_at | DateTime | DEFAULT now(), NOT NULL | Creation timestamp |
| revoked_at | DateTime |  | Revocation timestamp |

**Relationships:**

- `user` -> User (many-to-one)

---

### User

**Table:** `users` | **Tier:** Core | **File:** `user.py:10`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| customer_number | String(20) | INDEX | Customer number |
| email | String(255) | UNIQUE, NOT NULL, INDEX | Email address |
| password_hash | String(255) | NOT NULL | Password hash |
| email_verified | Boolean | DEFAULT False, NOT NULL | Email verified |
| first_name | String(100) |  | First name |
| last_name | String(100) |  | Last name |
| company_name | String(200) |  | Company name |
| phone | String(20) |  | Phone |
| billing_address_line1 | String(255) |  | Billing address line1 |
| billing_address_line2 | String(255) |  | Billing address line2 |
| billing_city | String(100) |  | Billing city |
| billing_state | String(50) |  | Billing state |
| billing_zip | String(20) |  | Billing zip |
| billing_country | String(100) | DEFAULT 'USA' | Billing country |
| shipping_address_line1 | String(255) |  | Shipping address line1 |
| shipping_address_line2 | String(255) |  | Shipping address line2 |
| shipping_city | String(100) |  | Shipping city |
| shipping_state | String(50) |  | Shipping state |
| shipping_zip | String(20) |  | Shipping zip |
| shipping_country | String(100) | DEFAULT 'USA' | Shipping country |
| status | String(20) | DEFAULT 'active', NOT NULL, INDEX | Current status |
| account_type | String(20) | DEFAULT 'customer', NOT NULL | Account type |
| created_at | DateTime | DEFAULT now(), NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT now(), NOT NULL | Last update timestamp |
| last_login_at | DateTime |  | Last login timestamp |
| created_by | Integer |  | Creator reference |
| updated_by | Integer |  | Last updater reference |
| customer_id | Integer | FK->customers.id, INDEX | FK reference to customers.id |

**Relationships:**

- `customer` -> Customer (many-to-one)
- `refresh_tokens` -> RefreshToken (one-to-many)
- `quotes` -> Quote (one-to-many)
- `sales_orders` -> SalesOrder (one-to-many)

---

## Quote & Sales Models

### Quote

**Table:** `quotes` | **Tier:** Core | **File:** `quote.py:16`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| user_id | Integer | FK->users.id, NOT NULL, INDEX | FK reference to users.id |
| quote_number | String(50) | UNIQUE, NOT NULL, INDEX | Quote number |
| product_name | String(255) |  | Product name |
| quantity | Integer | NOT NULL, DEFAULT 1 | Quantity value |
| material_type | String(50) |  | Material type |
| color | String(30) |  | Color |
| finish | String(50) | DEFAULT 'standard' | Finish |
| gcode_file_path | String(500) |  | Gcode file path |
| material_grams | Numeric(10, 2) |  | Material grams |
| print_time_hours | Numeric(10, 2) |  | Print time hours |
| unit_price | Numeric(10, 2) |  | Unit price |
| subtotal | Numeric(10, 2) |  | Subtotal |
| tax_rate | Numeric(5, 4) |  | Tax rate |
| tax_amount | Numeric(10, 2) |  | Tax amount |
| tax_name | String(100) |  | Tax name |
| total_price | Numeric(10, 2) | NOT NULL | Total price |
| margin_percent | Numeric(5, 2) |  | Margin percent |
| image_data | LargeBinary |  | Image data |
| image_filename | String(255) |  | Image filename |
| image_mime_type | String(100) |  | Image mime type |
| file_format | String(10) | NOT NULL | File format |
| file_size_bytes | BigInteger | NOT NULL | File size bytes |
| dimensions_x | Numeric(10, 2) |  | Dimensions x |
| dimensions_y | Numeric(10, 2) |  | Dimensions y |
| dimensions_z | Numeric(10, 2) |  | Dimensions z |
| status | String(50) | NOT NULL, DEFAULT 'pending', INDEX | Current status |
| approval_method | String(50) |  | Approval method |
| approved_by | Integer |  | Approver reference |
| approved_at | DateTime |  | Approval timestamp |
| rejection_reason | String(500) |  | Rejection reason |
| auto_approved | Boolean | NOT NULL, DEFAULT False | Auto approved |
| auto_approve_eligible | Boolean | NOT NULL, DEFAULT False | Auto approve eligible |
| requires_review_reason | String(255) |  | Requires review reason |
| rush_level | String(20) | DEFAULT 'standard' | Rush level |
| requested_delivery_date | Date |  | Requested Delivery date |
| customer_notes | String(1000) |  | Customer notes |
| admin_notes | String(1000) |  | Admin notes |
| internal_notes | String(1000) |  | Internal notes |
| customer_id | Integer | FK->users.id, INDEX | FK reference to users.id |
| customer_email | String(255) |  | Customer email |
| customer_name | String(200) |  | Customer name |
| shipping_name | String(200) |  | Shipping name |
| shipping_address_line1 | String(255) |  | Shipping address line1 |
| shipping_address_line2 | String(255) |  | Shipping address line2 |
| shipping_city | String(100) |  | Shipping city |
| shipping_state | String(50) |  | Shipping state |
| shipping_zip | String(20) |  | Shipping zip |
| shipping_country | String(100) | DEFAULT 'USA' | Shipping country |
| shipping_phone | String(30) |  | Shipping phone |
| shipping_rate_id | String(100) |  | Shipping Rate reference |
| shipping_carrier | String(50) |  | Shipping carrier |
| shipping_service | String(100) |  | Shipping service |
| shipping_cost | Numeric(10, 2) |  | Shipping cost |
| sales_order_id | Integer |  | Sales Order reference |
| converted_at | DateTime |  | Converted timestamp |
| product_id | Integer | FK->products.id, INDEX | FK reference to products.id |
| created_at | DateTime | NOT NULL, DEFAULT now() | Creation timestamp |
| updated_at | DateTime | NOT NULL, DEFAULT now() | Last update timestamp |
| expires_at | DateTime | NOT NULL | Expiration timestamp |

**Relationships:**

- `user` -> User (many-to-one)
- `customer` -> User (many-to-one)
- `files` -> QuoteFile (one-to-many)
- `sales_order` -> SalesOrder (one-to-one)
- `product` -> Product (many-to-one)
- `materials` -> QuoteMaterial (one-to-many)

---

### QuoteFile

**Table:** `quote_files` | **Tier:** Core | **File:** `quote.py:188`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| quote_id | Integer | FK->quotes.id, NOT NULL, INDEX | FK reference to quotes.id |
| original_filename | String(255) | NOT NULL | Original filename |
| stored_filename | String(255) | UNIQUE, NOT NULL | Stored filename |
| file_path | String(500) | NOT NULL | File path |
| file_size_bytes | BigInteger | NOT NULL | File size bytes |
| file_format | String(10) | NOT NULL | File format |
| mime_type | String(100) | NOT NULL | Mime type |
| is_valid | Boolean | NOT NULL, DEFAULT True | Valid flag |
| validation_errors | String(1000) |  | Validation errors |
| file_hash | String(64) | NOT NULL, INDEX | File hash |
| model_name | String(255) |  | Model name |
| vertex_count | Integer |  | Vertex count |
| triangle_count | Integer |  | Triangle count |
| bambu_file_id | String(100) |  | Bambu File reference |
| processed | Boolean | NOT NULL, DEFAULT False | Processed |
| processing_error | String(500) |  | Processing error |
| uploaded_at | DateTime | NOT NULL, DEFAULT now() | Uploaded timestamp |
| processed_at | DateTime |  | Processed timestamp |

**Relationships:**

- `quote` -> Quote (many-to-one)

---

### QuoteMaterial

**Table:** `quote_materials` | **Tier:** Core | **File:** `quote.py:243`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| quote_id | Integer | FK->quotes.id, NOT NULL, INDEX | FK reference to quotes.id |
| slot_number | Integer | NOT NULL, DEFAULT 1 | Slot number |
| is_primary | Boolean | NOT NULL, DEFAULT False | Primary flag |
| material_type | String(50) | NOT NULL | Material type |
| color_code | String(30) |  | Color code |
| color_name | String(100) |  | Color name |
| color_hex | String(7) |  | Color hex |
| material_grams | Numeric(10, 2) | NOT NULL | Material grams |
| created_at | DateTime | NOT NULL, DEFAULT now() | Creation timestamp |

**Relationships:**

- `quote` -> Quote (many-to-one)

---

## Material & Traceability Models

### Color

**Table:** `colors` | **Tier:** Core | **File:** `material.py:74`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| code | String(30) | UNIQUE, NOT NULL, INDEX | Unique code identifier |
| name | String(100) | NOT NULL | Display name |
| hex_code | String(7) |  | Hex code |
| hex_code_secondary | String(7) |  | Hex code secondary |
| display_order | Integer | DEFAULT 100 | Display order |
| is_customer_visible | Boolean | DEFAULT True | Customer Visible flag |
| active | Boolean | DEFAULT True | Active flag |
| created_at | DateTime | DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow | Last update timestamp |

**Relationships:**

- `material_colors` -> MaterialColor (one-to-many)
- `inventory_items` -> MaterialInventory (one-to-many)

---

### CustomerTraceabilityProfile

**Table:** `customer_traceability_profiles` | **Tier:** Core | **File:** `traceability.py:258`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| user_id | Integer | FK->users.id, UNIQUE, NOT NULL, INDEX | FK reference to users.id |
| traceability_level | String(20) | DEFAULT 'none', NOT NULL | Traceability level |
| requires_coc | Boolean | DEFAULT False | Requires coc |
| requires_coa | Boolean | DEFAULT False | Requires coa |
| requires_first_article | Boolean | DEFAULT False | Requires first article |
| record_retention_days | Integer | DEFAULT 2555 | Record retention days |
| custom_serial_prefix | String(20) |  | Custom serial prefix |
| compliance_standards | String(255) |  | Compliance standards |
| notes | Text |  | Additional notes |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `user` -> User (many-to-one)

---

### MaterialColor

**Table:** `material_colors` | **Tier:** Core | **File:** `material.py:112`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| material_type_id | Integer | FK->material_types.id, NOT NULL | FK reference to material_types.id |
| color_id | Integer | FK->colors.id, NOT NULL | FK reference to colors.id |
| is_customer_visible | Boolean | DEFAULT True | Customer Visible flag |
| display_order | Integer | DEFAULT 100 | Display order |
| active | Boolean | DEFAULT True | Active flag |

**Relationships:**

- `material_type` -> MaterialType (many-to-one)
- `color` -> Color (many-to-one)

---

### MaterialInventory

**Table:** `material_inventory` | **Tier:** Core | **File:** `material.py:148`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| material_type_id | Integer | FK->material_types.id, NOT NULL, INDEX | FK reference to material_types.id |
| color_id | Integer | FK->colors.id, NOT NULL, INDEX | FK reference to colors.id |
| product_id | Integer | FK->products.id, INDEX | FK reference to products.id |
| sku | String(50) | NOT NULL, UNIQUE, INDEX | Stock keeping unit |
| in_stock | Boolean | DEFAULT True | In stock |
| quantity_kg | Numeric(10, 3) | DEFAULT 0 | Quantity kg |
| reorder_point_kg | Numeric(10, 3) | DEFAULT 1.0 | Reorder point kg |
| cost_per_kg | Numeric(10, 2) |  | Cost per kg |
| last_purchase_date | DateTime |  | Last Purchase date |
| last_purchase_price | Numeric(10, 2) |  | Last purchase price |
| preferred_vendor | String(100) |  | Preferred vendor |
| vendor_sku | String(100) |  | Vendor sku |
| active | Boolean | DEFAULT True | Active flag |
| created_at | DateTime | DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow | Last update timestamp |

**Relationships:**

- `material_type` -> MaterialType (many-to-one)
- `color` -> Color (many-to-one)
- `product` -> Product (many-to-one)

---

### MaterialLot

**Table:** `material_lots` | **Tier:** Core | **File:** `traceability.py:115`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| lot_number | String(100) | UNIQUE, NOT NULL, INDEX | Lot number |
| product_id | Integer | FK->products.id, NOT NULL, INDEX | FK reference to products.id |
| vendor_id | Integer | FK->vendors.id, INDEX | FK reference to vendors.id |
| purchase_order_id | Integer | FK->purchase_orders.id | FK reference to purchase_orders.id |
| vendor_lot_number | String(100) |  | Vendor lot number |
| quantity_received | Numeric(12, 4) | NOT NULL | Quantity received |
| quantity_consumed | Numeric(12, 4) | DEFAULT 0, NOT NULL | Quantity consumed |
| quantity_scrapped | Numeric(12, 4) | DEFAULT 0, NOT NULL | Quantity scrapped |
| quantity_adjusted | Numeric(12, 4) | DEFAULT 0, NOT NULL | Quantity adjusted |
| status | String(30) | DEFAULT 'active', NOT NULL, INDEX | Current status |
| certificate_of_analysis | Text |  | Certificate of analysis |
| coa_file_path | String(500) |  | Coa file path |
| inspection_status | String(30) | DEFAULT 'pending' | Inspection status |
| manufactured_date | Date |  | Manufactured date |
| expiration_date | Date | INDEX | Expiration date |
| received_date | Date | NOT NULL, DEFAULT utcnow | Received date |
| unit_cost | Numeric(10, 4) |  | Unit cost |
| location | String(100) |  | Location |
| notes | Text |  | Additional notes |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `product` -> Product (many-to-one)
- `vendor` -> Vendor (many-to-one)
- `purchase_order` -> PurchaseOrder (many-to-one)
- `consumptions` -> ProductionLotConsumption (one-to-many)

---

### MaterialSpool

**Table:** `material_spools` | **Tier:** Core | **File:** `material_spool.py:14`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| spool_number | String(100) | UNIQUE, NOT NULL, INDEX | Spool number |
| product_id | Integer | FK->products.id, NOT NULL | FK reference to products.id |
| initial_weight_kg | Numeric(10, 3) | NOT NULL | Initial weight kg |
| current_weight_kg | Numeric(10, 3) | NOT NULL | Current weight kg |
| status | String(50) | DEFAULT 'active', NOT NULL | Current status |
| received_date | DateTime | DEFAULT utcnow, NOT NULL | Received date |
| expiry_date | DateTime |  | Expiry date |
| location_id | Integer | FK->inventory_locations.id | FK reference to inventory_locations.id |
| supplier_lot_number | String(100) |  | Supplier lot number |
| notes | Text |  | Additional notes |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |
| created_by | String(100) |  | Creator reference |

**Relationships:**

- `product` -> Product (many-to-one)
- `location` -> InventoryLocation (many-to-one)
- `production_orders` -> ProductionOrderSpool (one-to-many)

---

### MaterialType

**Table:** `material_types` | **Tier:** Core | **File:** `material.py:17`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| code | String(50) | UNIQUE, NOT NULL, INDEX | Unique code identifier |
| name | String(100) | NOT NULL | Display name |
| base_material | String(20) | NOT NULL, INDEX | Base material |
| process_type | String(20) | NOT NULL, DEFAULT 'FDM' | Process type |
| density | Numeric(6, 4) | NOT NULL | Density |
| volumetric_flow_limit | Numeric(6, 2) |  | Volumetric flow limit |
| nozzle_temp_min | Integer |  | Nozzle temp min |
| nozzle_temp_max | Integer |  | Nozzle temp max |
| bed_temp_min | Integer |  | Bed temp min |
| bed_temp_max | Integer |  | Bed temp max |
| requires_enclosure | Boolean | DEFAULT False | Requires enclosure |
| base_price_per_kg | Numeric(10, 2) | NOT NULL | Base price per kg |
| price_multiplier | Numeric(4, 2) | DEFAULT 1.0 | Price multiplier |
| description | Text |  | Description text |
| strength_rating | Integer |  | Strength rating |
| is_customer_visible | Boolean | DEFAULT True | Customer Visible flag |
| display_order | Integer | DEFAULT 100 | Display order |
| active | Boolean | DEFAULT True | Active flag |
| created_at | DateTime | DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow | Last update timestamp |

**Relationships:**

- `material_colors` -> MaterialColor (one-to-many)
- `inventory_items` -> MaterialInventory (one-to-many)

---

### ProductionLotConsumption

**Table:** `production_lot_consumptions` | **Tier:** Core | **File:** `traceability.py:212`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| production_order_id | Integer | FK->production_orders.id, NOT NULL, INDEX | FK reference to production_orders.id |
| material_lot_id | Integer | FK->material_lots.id, NOT NULL, INDEX | FK reference to material_lots.id |
| serial_number_id | Integer | FK->serial_numbers.id, INDEX | FK reference to serial_numbers.id |
| bom_line_id | Integer | FK->bom_lines.id | FK reference to bom_lines.id |
| quantity_consumed | Numeric(12, 4) | NOT NULL | Quantity consumed |
| consumed_at | DateTime | DEFAULT utcnow, NOT NULL | Consumed timestamp |

**Relationships:**

- `production_order` -> ProductionOrder (many-to-one)
- `material_lot` -> MaterialLot (many-to-one)
- `serial_number` -> SerialNumber (many-to-one)

---

### ProductionOrderSpool

**Table:** `production_order_spools` | **Tier:** Core | **File:** `material_spool.py:77`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| production_order_id | Integer | FK->production_orders.id, NOT NULL | FK reference to production_orders.id |
| spool_id | Integer | FK->material_spools.id, NOT NULL | FK reference to material_spools.id |
| weight_consumed_kg | Numeric(10, 3) | NOT NULL, DEFAULT 0 | Weight consumed kg |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| created_by | String(100) |  | Creator reference |

**Relationships:**

- `production_order` -> ProductionOrder (many-to-one)
- `spool` -> MaterialSpool (many-to-one)

---

### SerialNumber

**Table:** `serial_numbers` | **Tier:** Core | **File:** `traceability.py:34`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| serial_number | String(50) | UNIQUE, NOT NULL, INDEX | Serial number |
| product_id | Integer | FK->products.id, NOT NULL, INDEX | FK reference to products.id |
| production_order_id | Integer | FK->production_orders.id, NOT NULL, INDEX | FK reference to production_orders.id |
| status | String(30) | DEFAULT 'manufactured', NOT NULL, INDEX | Current status |
| qc_passed | Boolean | DEFAULT True, NOT NULL | Qc passed |
| qc_date | DateTime |  | Qc date |
| qc_notes | Text |  | Qc notes |
| sales_order_id | Integer | FK->sales_orders.id, INDEX | FK reference to sales_orders.id |
| sales_order_line_id | Integer | FK->sales_order_lines.id | FK reference to sales_order_lines.id |
| sold_at | DateTime |  | Sold timestamp |
| shipped_at | DateTime |  | Shipped timestamp |
| tracking_number | String(100) |  | Tracking number |
| returned_at | DateTime |  | Returned timestamp |
| return_reason | Text |  | Return reason |
| manufactured_at | DateTime | DEFAULT utcnow, NOT NULL | Manufactured timestamp |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |

**Relationships:**

- `product` -> Product (many-to-one)
- `production_order` -> ProductionOrder (many-to-one)
- `sales_order` -> SalesOrder (many-to-one)
- `lot_consumptions` -> ProductionLotConsumption (one-to-many)

---

## MRP Models

### MRPRun

**Table:** `mrp_runs` | **Tier:** Core | **File:** `mrp.py:15`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| run_date | DateTime | DEFAULT utcnow, NOT NULL | Run date |
| planning_horizon_days | Integer | DEFAULT 30, NOT NULL | Planning horizon days |
| orders_processed | Integer | DEFAULT 0 | Orders processed |
| components_analyzed | Integer | DEFAULT 0 | Components analyzed |
| shortages_found | Integer | DEFAULT 0 | Shortages found |
| planned_orders_created | Integer | DEFAULT 0 | Planned orders created |
| status | String(20) | DEFAULT 'running', NOT NULL | Current status |
| error_message | Text |  | Error message |
| created_by | Integer |  | Creator reference |
| completed_at | DateTime |  | Completion timestamp |

**Relationships:**

- `planned_orders` -> PlannedOrder (one-to-many)

---

### PlannedOrder

**Table:** `planned_orders` | **Tier:** Core | **File:** `mrp.py:49`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| order_type | String(20) | NOT NULL | Order type |
| product_id | Integer | FK->products.id, NOT NULL | FK reference to products.id |
| quantity | Numeric(18, 4) | NOT NULL | Quantity value |
| due_date | Date | NOT NULL | Due date |
| start_date | Date | NOT NULL | Start date |
| source_demand_type | String(50) |  | Source demand type |
| source_demand_id | Integer |  | Source Demand reference |
| mrp_run_id | Integer | FK->mrp_runs.id | FK reference to mrp_runs.id |
| status | String(20) | DEFAULT 'planned', NOT NULL | Current status |
| converted_to_po_id | Integer | FK->purchase_orders.id | FK reference to purchase_orders.id |
| converted_to_mo_id | Integer | FK->production_orders.id | FK reference to production_orders.id |
| notes | Text |  | Additional notes |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| created_by | Integer |  | Creator reference |
| updated_at | DateTime |  | Last update timestamp |
| firmed_at | DateTime |  | Firmed timestamp |
| released_at | DateTime |  | Released timestamp |

**Relationships:**

- `product` -> Product (many-to-one)
- `mrp_run` -> MRPRun (many-to-one)
- `converted_po` -> PurchaseOrder (one-to-many)
- `converted_mo` -> ProductionOrder (one-to-many)

---

## Document Models

### PurchaseOrderDocument

**Table:** `purchase_order_documents` | **Tier:** Core | **File:** `purchase_order_document.py:11`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| purchase_order_id | Integer | FK->purchase_orders.id, NOT NULL | FK reference to purchase_orders.id |
| document_type | String(50) | NOT NULL | Document type |
| file_name | String(255) | NOT NULL | File name |
| original_file_name | String(255) |  | Original file name |
| file_url | String(1000) |  | File url |
| file_path | String(500) |  | File path |
| storage_type | String(50) | NOT NULL, DEFAULT 'local' | Storage type |
| file_size | Integer |  | File size |
| mime_type | String(100) |  | Mime type |
| google_drive_id | String(100) |  | Google Drive reference |
| notes | Text |  | Additional notes |
| uploaded_by | String(100) |  | Uploaded by |
| uploaded_at | DateTime | DEFAULT utcnow, NOT NULL | Uploaded timestamp |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `purchase_order` -> PurchaseOrder (many-to-one)

---

### VendorItem

**Table:** `vendor_items` | **Tier:** Core | **File:** `purchase_order_document.py:78`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| vendor_id | Integer | FK->vendors.id, NOT NULL | FK reference to vendors.id |
| vendor_sku | String(100) | NOT NULL | Vendor sku |
| vendor_description | String(500) |  | Vendor description |
| product_id | Integer | FK->products.id | FK reference to products.id |
| default_unit_cost | String(20) |  | Default unit cost |
| default_purchase_unit | String(20) |  | Default purchase unit |
| last_seen_at | DateTime |  | Last Seen timestamp |
| times_ordered | Integer | DEFAULT 0 | Times ordered |
| notes | Text |  | Additional notes |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

**Relationships:**

- `vendor` -> Vendor (many-to-one)
- `product` -> Product (many-to-one)

---

## Settings Models

### CompanySettings

**Table:** `company_settings` | **Tier:** Core | **File:** `company_settings.py:15`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, DEFAULT 1 | Primary key |
| company_name | String(255) |  | Company name |
| company_address_line1 | String(255) |  | Company address line1 |
| company_address_line2 | String(255) |  | Company address line2 |
| company_city | String(100) |  | Company city |
| company_state | String(50) |  | Company state |
| company_zip | String(20) |  | Company zip |
| company_country | String(100) | DEFAULT 'USA' | Company country |
| company_phone | String(30) |  | Company phone |
| company_email | String(255) |  | Company email |
| company_website | String(255) |  | Company website |
| logo_data | LargeBinary |  | Logo data |
| logo_filename | String(255) |  | Logo filename |
| logo_mime_type | String(100) |  | Logo mime type |
| tax_enabled | Boolean | NOT NULL, DEFAULT False | Tax enabled |
| tax_rate | Numeric(5, 4) |  | Tax rate |
| tax_name | String(50) | DEFAULT 'Sales Tax' | Tax name |
| tax_registration_number | String(100) |  | Tax registration number |
| default_quote_validity_days | Integer | NOT NULL, DEFAULT 30 | Default quote validity days |
| quote_terms | String(2000) |  | Quote terms |
| quote_footer | String(1000) |  | Quote footer |
| invoice_prefix | String(20) | DEFAULT 'INV' | Invoice prefix |
| invoice_terms | String(2000) |  | Invoice terms |
| fiscal_year_start_month | Integer | DEFAULT 1 | Fiscal year start month |
| accounting_method | String(20) | DEFAULT 'cash' | Accounting method |
| currency_code | String(10) | DEFAULT 'USD' | Currency code |
| locale | String(20) | DEFAULT 'en-US' | Locale |
| timezone | String(50) | DEFAULT 'America/New_York' | Timezone |
| business_hours_start | Integer | DEFAULT 8 | Business hours start |
| business_hours_end | Integer | DEFAULT 16 | Business hours end |
| business_days_per_week | Integer | DEFAULT 5 | Business days per week |
| business_work_days | String(20) | DEFAULT '0,1,2,3,4' | Business work days |
| ai_provider | String(20) |  | Ai provider |
| ai_api_key | String(500) |  | Ai api key |
| ai_ollama_url | String(255) | DEFAULT 'http://localhost:11434' | Ai ollama url |
| ai_ollama_model | String(100) | DEFAULT 'llama3.2' | Ai ollama model |
| ai_anthropic_model | String(100) | DEFAULT 'claude-sonnet-4-20250514' | Ai anthropic model |
| external_ai_blocked | Boolean | NOT NULL, DEFAULT False | External ai blocked |
| default_margin_percent | Numeric(5, 2) |  | Default margin percent |
| created_at | DateTime | NOT NULL, DEFAULT now() | Creation timestamp |
| updated_at | DateTime | NOT NULL, DEFAULT now() | Last update timestamp |

---

## Event Models

### OrderEvent

**Table:** `order_events` | **Tier:** Core | **File:** `order_event.py:14`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| sales_order_id | Integer | FK->sales_orders.id, NOT NULL, INDEX | FK reference to sales_orders.id |
| user_id | Integer | FK->users.id, INDEX | FK reference to users.id |
| event_type | String(50) | NOT NULL, INDEX | Event type |
| title | String(255) | NOT NULL | Title |
| description | Text |  | Description text |
| old_value | String(100) |  | Old value |
| new_value | String(100) |  | New value |
| metadata_key | String(100) |  | Metadata key |
| metadata_value | String(255) |  | Metadata value |
| created_at | DateTime | NOT NULL, DEFAULT utcnow, INDEX | Creation timestamp |

**Relationships:**

- `sales_order` -> SalesOrder (many-to-one)
- `user` -> User (many-to-one)

---

### PurchasingEvent

**Table:** `purchasing_events` | **Tier:** Core | **File:** `purchasing_event.py:14`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| purchase_order_id | Integer | FK->purchase_orders.id, NOT NULL, INDEX | FK reference to purchase_orders.id |
| user_id | Integer | FK->users.id, INDEX | FK reference to users.id |
| event_type | String(50) | NOT NULL, INDEX | Event type |
| title | String(255) | NOT NULL | Title |
| description | Text |  | Description text |
| old_value | String(100) |  | Old value |
| new_value | String(100) |  | New value |
| event_date | Date | INDEX | Event date |
| metadata_key | String(100) |  | Metadata key |
| metadata_value | String(255) |  | Metadata value |
| created_at | DateTime | NOT NULL, DEFAULT utcnow, INDEX | Creation timestamp |

**Relationships:**

- `purchase_order` -> PurchaseOrder (many-to-one)
- `user` -> User (many-to-one)

---

### ShippingEvent

**Table:** `shipping_events` | **Tier:** Core | **File:** `shipping_event.py:14`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| sales_order_id | Integer | FK->sales_orders.id, NOT NULL, INDEX | FK reference to sales_orders.id |
| user_id | Integer | FK->users.id, INDEX | FK reference to users.id |
| event_type | String(50) | NOT NULL, INDEX | Event type |
| title | String(255) | NOT NULL | Title |
| description | Text |  | Description text |
| tracking_number | String(100) | INDEX | Tracking number |
| carrier | String(50) |  | Carrier |
| location_city | String(100) |  | Location city |
| location_state | String(50) |  | Location state |
| location_zip | String(20) |  | Location zip |
| event_date | Date | INDEX | Event date |
| event_timestamp | DateTime |  | Event timestamp |
| metadata_key | String(100) |  | Metadata key |
| metadata_value | String(255) |  | Metadata value |
| source | String(50) | DEFAULT 'manual', NOT NULL | Source |
| created_at | DateTime | NOT NULL, DEFAULT utcnow, INDEX | Creation timestamp |

**Relationships:**

- `sales_order` -> SalesOrder (many-to-one)
- `user` -> User (many-to-one)

---

## UOM Models

### UnitOfMeasure

**Table:** `units_of_measure` | **Tier:** Core | **File:** `uom.py:15`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| code | String(10) | UNIQUE, NOT NULL, INDEX | Unique code identifier |
| name | String(50) | NOT NULL | Display name |
| symbol | String(10) |  | Symbol |
| uom_class | String(20) | NOT NULL | Uom class |
| base_unit_id | Integer | FK->units_of_measure.id | FK reference to units_of_measure.id |
| to_base_factor | Numeric(18, 8) | DEFAULT 1, NOT NULL | To base factor |
| active | Boolean | DEFAULT True, NOT NULL | Active flag |

**Relationships:**

- `base_unit` -> UnitOfMeasure (many-to-one)

---

## Accounting Models

### GLAccount

**Table:** `gl_accounts` | **Tier:** Core | **File:** `accounting.py:16`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| account_code | String(20) | UNIQUE, NOT NULL, INDEX | Account code |
| name | String(100) | NOT NULL | Display name |
| account_type | String(20) | NOT NULL, INDEX | Account type |
| schedule_c_line | String(10) | INDEX | Schedule c line |
| parent_id | Integer | FK->gl_accounts.id | FK reference to gl_accounts.id |
| is_system | Boolean | NOT NULL, DEFAULT False | System flag |
| active | Boolean | NOT NULL, DEFAULT True, INDEX | Active flag |
| description | Text |  | Description text |
| created_at | DateTime | DEFAULT now(), NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT now(), NOT NULL | Last update timestamp |

**Relationships:**

- `parent` -> GLAccount (many-to-one)
- `journal_lines` -> GLJournalEntryLine (one-to-many)

---

### GLFiscalPeriod

**Table:** `gl_fiscal_periods` | **Tier:** Core | **File:** `accounting.py:57`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| year | Integer | NOT NULL, INDEX | Year |
| period | Integer | NOT NULL | Period |
| start_date | Date | NOT NULL | Start date |
| end_date | Date | NOT NULL | End date |
| status | String(20) | NOT NULL, DEFAULT 'open', INDEX | Current status |
| closed_by | Integer | FK->users.id | FK reference to users.id |
| closed_at | DateTime |  | Closure timestamp |
| created_at | DateTime | DEFAULT now(), NOT NULL | Creation timestamp |

**Relationships:**

- `closed_by_user` -> User (one-to-many)
- `journal_entries` -> GLJournalEntry (one-to-many)

---

### GLJournalEntry

**Table:** `gl_journal_entries` | **Tier:** Core | **File:** `accounting.py:91`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| entry_number | String(20) | UNIQUE, NOT NULL, INDEX | Entry number |
| entry_date | Date | NOT NULL, INDEX | Entry date |
| description | String(255) | NOT NULL | Description text |
| source_type | String(50) |  | Source type |
| source_id | Integer |  | Source reference |
| status | String(20) | NOT NULL, DEFAULT 'draft', INDEX | Current status |
| fiscal_period_id | Integer | FK->gl_fiscal_periods.id | FK reference to gl_fiscal_periods.id |
| created_by | Integer | FK->users.id | FK reference to users.id |
| created_at | DateTime | DEFAULT now(), NOT NULL | Creation timestamp |
| posted_by | Integer | FK->users.id | FK reference to users.id |
| posted_at | DateTime |  | Posting timestamp |
| voided_by | Integer | FK->users.id | FK reference to users.id |
| voided_at | DateTime |  | Void timestamp |
| void_reason | Text |  | Reason for voiding |

**Relationships:**

- `fiscal_period` -> GLFiscalPeriod (many-to-one)
- `lines` -> GLJournalEntryLine (one-to-many)
- `created_by_user` -> User (one-to-many)
- `posted_by_user` -> User (one-to-many)
- `voided_by_user` -> User (one-to-many)

---

### GLJournalEntryLine

**Table:** `gl_journal_entry_lines` | **Tier:** Core | **File:** `accounting.py:169`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| journal_entry_id | Integer | FK->gl_journal_entries.id, NOT NULL, INDEX | FK reference to gl_journal_entries.id |
| account_id | Integer | FK->gl_accounts.id, NOT NULL, INDEX | FK reference to gl_accounts.id |
| debit_amount | Numeric(10, 2) | NOT NULL, DEFAULT 0 | Debit amount |
| credit_amount | Numeric(10, 2) | NOT NULL, DEFAULT 0 | Credit amount |
| memo | String(255) |  | Memo |
| line_order | Integer | NOT NULL, DEFAULT 0 | Line order |

**Relationships:**

- `journal_entry` -> GLJournalEntry (many-to-one)
- `account` -> GLAccount (many-to-one)

---

## Tax Models

### TaxRate

**Table:** `tax_rates` | **Tier:** Core | **File:** `tax_rate.py:16`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| name | String(100) | NOT NULL | Display name |
| rate | Numeric(7, 4) | NOT NULL | Rate |
| description | String(500) |  | Description text |
| is_default | Boolean | NOT NULL, DEFAULT False | Default flag |
| is_active | Boolean | NOT NULL, DEFAULT True | Active flag |
| created_at | DateTime | NOT NULL, DEFAULT now() | Creation timestamp |
| updated_at | DateTime | NOT NULL, DEFAULT now() | Last update timestamp |

---

## Reference Data Models

### AdjustmentReason

**Table:** `adjustment_reasons` | **Tier:** Core | **File:** `adjustment_reason.py:13`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| code | String(50) | UNIQUE, NOT NULL, INDEX | Unique code identifier |
| name | String(100) | NOT NULL | Display name |
| description | Text |  | Description text |
| active | Boolean | DEFAULT True, NOT NULL | Active flag |
| sequence | Integer | DEFAULT 0 | Sort order / sequence |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

---

### MaintenanceLog

**Table:** `maintenance_logs` | **Tier:** Core | **File:** `maintenance.py:14`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| printer_id | Integer | FK->printers.id, NOT NULL, INDEX | FK reference to printers.id |
| maintenance_type | String(50) | NOT NULL, INDEX | Maintenance type |
| description | Text |  | Description text |
| performed_by | String(100) |  | Performed by |
| performed_at | DateTime | NOT NULL, DEFAULT utcnow, INDEX | Performed timestamp |
| next_due_at | DateTime | INDEX | Next Due timestamp |
| cost | Numeric(10, 2) |  | Cost |
| downtime_minutes | Integer |  | Downtime minutes |
| parts_used | Text |  | Parts used |
| notes | Text |  | Additional notes |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |

**Relationships:**

- `printer` -> Printer (many-to-one)

---

### ScrapReason

**Table:** `scrap_reasons` | **Tier:** Core | **File:** `scrap_reason.py:13`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| code | String(50) | UNIQUE, NOT NULL, INDEX | Unique code identifier |
| name | String(100) | NOT NULL | Display name |
| description | Text |  | Description text |
| active | Boolean | DEFAULT True, NOT NULL | Active flag |
| sequence | Integer | DEFAULT 0 | Sort order / sequence |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| updated_at | DateTime | DEFAULT utcnow, NOT NULL | Last update timestamp |

---

### ProductionOrderMaterial

**Table:** `production_order_materials` | **Tier:** Core | **File:** `production_order.py:288`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK, INDEX | Primary key |
| production_order_id | Integer | FK->production_orders.id, NOT NULL, INDEX | FK reference to production_orders.id |
| bom_line_id | Integer | FK->bom_lines.id | FK reference to bom_lines.id |
| original_product_id | Integer | FK->products.id, NOT NULL | FK reference to products.id |
| original_quantity | Numeric(18, 4) | NOT NULL | Original quantity |
| substitute_product_id | Integer | FK->products.id, NOT NULL | FK reference to products.id |
| planned_quantity | Numeric(18, 4) | NOT NULL | Planned quantity |
| actual_quantity_used | Numeric(18, 4) |  | Actual quantity used |
| reason | Text | NOT NULL | Reason |
| created_at | DateTime | DEFAULT utcnow, NOT NULL | Creation timestamp |
| created_by | String(100) |  | Creator reference |

**Relationships:**

- `production_order` -> ProductionOrder (many-to-one)
- `original_product` -> Product (many-to-one)
- `substitute_product` -> Product (many-to-one)

---

## Summary Statistics

| Category | Models | Tables |
|----------|--------|--------|
| Core ERP Models | 13 | 13 |
| Manufacturing Models | 11 | 11 |
| User & Auth Models | 4 | 4 |
| Quote & Sales Models | 3 | 3 |
| Material & Traceability Models | 10 | 10 |
| MRP Models | 2 | 2 |
| Document Models | 2 | 2 |
| Settings Models | 1 | 1 |
| Event Models | 3 | 3 |
| UOM Models | 1 | 1 |
| Accounting Models | 4 | 4 |
| Tax Models | 1 | 1 |
| Reference Data Models | 4 | 4 |
| **Total** | **59** | **59** |
