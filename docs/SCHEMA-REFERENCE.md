# FilaOps Database Schema Reference

**Generated:** 2026-01-28
**Source:** FilaOps Core v3.0.1
**Total Models:** 52 (Core only)
**Purpose:** AI knowledge source for codebase understanding

> This is the **Core (Open Source)** schema reference.

---

## Table of Contents

1. [Core ERP Models](#core-erp-models) (12 models)
2. [Manufacturing Models](#manufacturing-models) (14 models)
3. [User & Auth Models](#user--auth-models) (3 models)
4. [Quote & Sales Models](#quote--sales-models) (4 models)
5. [Material & Traceability Models](#material--traceability-models) (10 models)
6. [MRP Models](#mrp-models) (2 models)
7. [Document Models](#document-models) (2 models)
8. [Settings Models](#settings-models) (1 model)
9. [Event Models](#event-models) (3 models)
10. [UOM Model](#uom-model) (1 model)

---

## Core ERP Models

### Product

**Table:** `products` | **Tier:** Core | **File:** `product.py:11`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK | Primary key |
| sku | String(50) | UNIQUE, NOT NULL, INDEX | Stock keeping unit |
| legacy_sku | String(50) | INDEX | Previous SKU for migration |
| name | String(255) | NOT NULL | Product name |
| description | Text | | Product description |
| unit | String(20) | DEFAULT 'EA' | Base unit of measure |
| purchase_uom | String(20) | DEFAULT 'EA' | Purchase unit of measure |
| purchase_factor | Numeric(18,6) | | Conversion: 1 purchase_uom = X unit |
| item_type | String(20) | NOT NULL, DEFAULT 'finished_good' | finished_good, component, material, supply |
| procurement_type | String(20) | NOT NULL, DEFAULT 'buy' | buy, make |
| category_id | Integer | FK→item_categories.id | Item category |
| material_type_id | Integer | FK→material_types.id | Material classification |
| color_id | Integer | FK→colors.id | Color reference |
| cost_method | String(20) | DEFAULT 'average' | average, standard, fifo |
| standard_cost | Numeric(10,2) | | Standard cost per unit |
| average_cost | Numeric(10,2) | | Weighted average cost |
| last_cost | Numeric(10,2) | | Most recent purchase cost |
| selling_price | Numeric(18,4) | | Default selling price |
| weight_oz | Numeric(8,2) | | Weight in ounces |
| length_in | Numeric(8,2) | | Length in inches |
| width_in | Numeric(8,2) | | Width in inches |
| height_in | Numeric(8,2) | | Height in inches |
| lead_time_days | Integer | | Procurement lead time |
| min_order_qty | Numeric(10,2) | | Minimum order quantity |
| reorder_point | Numeric(10,2) | | Reorder trigger level |
| safety_stock | Numeric(18,4) | DEFAULT 0 | Safety stock quantity |
| preferred_vendor_id | Integer | FK→vendors.id, INDEX | Default vendor |
| stocking_policy | String(20) | NOT NULL, DEFAULT 'on_demand' | on_demand, stock |
| upc | String(50) | | Universal product code |
| type | String(20) | NOT NULL, DEFAULT 'standard' | standard, custom |
| gcode_file_path | String(500) | | G-code file location |
| image_url | String(500) | | Product image URL |
| is_public | Boolean | DEFAULT true | Publicly visible product |
| sales_channel | String(20) | DEFAULT 'public' | public, wholesale, internal |
| customer_id | Integer | FK→users.id, INDEX | Custom product owner |
| is_raw_material | Boolean | DEFAULT false | Raw material flag |
| has_bom | Boolean | DEFAULT false | Has bill of materials |
| track_lots | Boolean | DEFAULT false | Lot tracking enabled |
| track_serials | Boolean | DEFAULT false | Serial tracking enabled |
| active | Boolean | DEFAULT true | Active/inactive |
| woocommerce_product_id | BigInteger | | WooCommerce integration |
| squarespace_product_id | String(50) | | Squarespace integration |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update timestamp |

**Relationships:**

- `boms` → BOM (one-to-many)
- `inventory_items` → Inventory (one-to-many)
- `production_orders` → ProductionOrder (one-to-many)
- `quotes` → Quote (one-to-many)
- `item_category` → ItemCategory (many-to-one)
- `routings` → Routing (one-to-many)
- `spools` → MaterialSpool (one-to-many)
- `material_type` → MaterialType (many-to-one)
- `color` → Color (many-to-one)

---

### BOM

**Table:** `boms` | **Tier:** Core | **File:** `bom.py:10`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK | Primary key |
| product_id | Integer | FK→products.id, NOT NULL | Parent product |
| code | String(50) | | BOM code |
| name | String(255) | | BOM name |
| version | Integer | DEFAULT 1 | Version number |
| revision | String(10) | | Revision identifier |
| active | Boolean | NOT NULL, DEFAULT true | Active BOM |
| total_cost | Numeric(18,4) | | Calculated total cost |
| assembly_time_minutes | Integer | | Assembly time |
| effective_date | Date | | Effective from date |
| notes | Text | | Notes |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |

**Relationships:**

- `product` → Product (many-to-one)
- `lines` → BOMLine (one-to-many, cascade delete)

---

### BOMLine

**Table:** `bom_lines` | **Tier:** Core | **File:** `bom.py:49`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK | Primary key |
| bom_id | Integer | FK→boms.id, NOT NULL | Parent BOM |
| component_id | Integer | FK→products.id, NOT NULL | Component product |
| sequence | Integer | | Sort order |
| quantity | Numeric(18,4) | NOT NULL | Quantity required |
| unit | String(20) | NOT NULL, DEFAULT 'EA' | Unit of measure |
| consume_stage | String(20) | NOT NULL, DEFAULT 'production' | production, shipping |
| is_cost_only | Boolean | NOT NULL, DEFAULT false | Cost only (not consumed) |
| scrap_factor | Numeric(5,2) | DEFAULT 0 | Scrap percentage |
| notes | Text | | Notes |

**Relationships:**

- `bom` → BOM (many-to-one)
- `component` → Product (many-to-one)

---

### InventoryLocation

**Table:** `inventory_locations` | **Tier:** Core | **File:** `inventory.py:11`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| name | String(100) | NOT NULL | Location name |
| code | String(50) | | Location code |
| type | String(50) | | warehouse, bin, zone |
| parent_id | Integer | FK→inventory_locations.id | Parent location |
| active | Boolean | DEFAULT true | Active flag |

**Relationships:**

- `parent` → InventoryLocation (self-referential)
- `children` → InventoryLocation (one-to-many)
- `inventory_items` → Inventory (one-to-many)

---

### Inventory

**Table:** `inventory` | **Tier:** Core | **File:** `inventory.py:32`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| product_id | Integer | FK→products.id, NOT NULL | Product reference |
| location_id | Integer | FK→inventory_locations.id, NOT NULL | Location reference |
| on_hand_quantity | Numeric(10,2) | NOT NULL, DEFAULT 0 | On-hand quantity |
| allocated_quantity | Numeric(10,2) | NOT NULL, DEFAULT 0 | Reserved quantity |
| available_quantity | Numeric(10,2) | COMPUTED | on_hand - allocated |
| last_counted | DateTime | | Last cycle count date |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `product` → Product (many-to-one)
- `location` → InventoryLocation (many-to-one)

---

### InventoryTransaction

**Table:** `inventory_transactions` | **Tier:** Core | **File:** `inventory.py:61`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| product_id | Integer | FK→products.id, NOT NULL | Product reference |
| location_id | Integer | FK→inventory_locations.id | Location reference |
| journal_entry_id | Integer | FK→gl_journal_entries.id | GL journal link |
| transaction_type | String(50) | NOT NULL | receipt, issue, adjustment, transfer |
| reference_type | String(50) | | po, so, wo, cycle_count |
| reference_id | Integer | | Source document ID |
| quantity | Numeric(18,4) | NOT NULL | Transaction quantity |
| lot_number | String(100) | | Lot number |
| serial_number | String(100) | | Serial number |
| cost_per_unit | Numeric(18,4) | | Unit cost |
| total_cost | Numeric(18,4) | | Pre-calculated total |
| unit | String(20) | | Transaction unit |
| notes | Text | | Notes |
| requires_approval | Boolean | NOT NULL, DEFAULT false | Needs approval |
| approval_reason | Text | | Why approval needed |
| approved_by | String(100) | | Approver email |
| approved_at | DateTime | | Approval timestamp |
| transaction_date | Date | INDEX | Business date |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| created_by | String(100) | | Creator email |

**Relationships:**

- `location` → InventoryLocation (many-to-one)
- `product` → Product (many-to-one)
- `journal_entry` → GLJournalEntry (many-to-one)

---

### SalesOrder

**Table:** `sales_orders` | **Tier:** Core | **File:** `sales_order.py:13`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| user_id | Integer | FK→users.id, NOT NULL, INDEX | Order owner |
| quote_id | Integer | FK→quotes.id, INDEX | Source quote |
| order_number | String(50) | UNIQUE, NOT NULL, INDEX | Order number |
| order_type | String(20) | INDEX, DEFAULT 'quote_based' | quote_based, line_item |
| source | String(50) | INDEX, DEFAULT 'manual' | manual, internal |
| source_order_id | String(255) | INDEX | External order ID |
| product_id | Integer | FK→products.id, INDEX | Main product (quote_based) |
| product_name | String(255) | | Product name snapshot |
| quantity | Integer | NOT NULL | Order quantity |
| material_type | String(50) | NOT NULL | Material type |
| color | String(50) | | Color |
| finish | String(50) | NOT NULL, DEFAULT 'standard' | Finish type |
| unit_price | Numeric(10,2) | NOT NULL | Unit price |
| total_price | Numeric(10,2) | NOT NULL | Line total |
| tax_amount | Numeric(10,2) | DEFAULT 0 | Tax amount |
| tax_rate | Numeric(5,4) | | Tax rate |
| is_taxable | Boolean | DEFAULT true | Taxable flag |
| shipping_cost | Numeric(10,2) | DEFAULT 0 | Shipping cost |
| grand_total | Numeric(10,2) | NOT NULL | Order total |
| status | String(50) | INDEX, DEFAULT 'draft' | draft, confirmed, in_progress, completed, cancelled |
| payment_status | String(50) | INDEX, DEFAULT 'pending' | pending, partial, paid, refunded |
| payment_method | String(50) | | Payment method |
| payment_transaction_id | String(255) | | Payment reference |
| paid_at | DateTime | | Payment timestamp |
| fulfillment_status | String(50) | INDEX, DEFAULT 'pending' | pending, partial, fulfilled |
| rush_level | String(20) | DEFAULT 'standard' | standard, rush, expedite |
| estimated_completion_date | DateTime | | Estimated completion |
| actual_completion_date | DateTime | | Actual completion |
| customer_id | Integer | FK→users.id, INDEX | Customer reference |
| customer_name | String(200) | | Customer name |
| customer_email | String(255) | | Customer email |
| customer_phone | String(30) | | Customer phone |
| shipping_address_line1 | String(255) | | Address line 1 |
| shipping_address_line2 | String(255) | | Address line 2 |
| shipping_city | String(100) | | City |
| shipping_state | String(50) | | State |
| shipping_zip | String(20) | | ZIP code |
| shipping_country | String(100) | DEFAULT 'USA' | Country |
| tracking_number | String(255) | | Tracking number |
| carrier | String(100) | | Carrier name |
| shipped_at | DateTime | | Ship date |
| delivered_at | DateTime | | Delivery date |
| customer_notes | Text | | Customer notes |
| internal_notes | Text | | Internal notes |
| production_notes | Text | | Production notes |
| cancelled_at | DateTime | | Cancellation date |
| cancellation_reason | Text | | Cancellation reason |
| created_at | DateTime | INDEX, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | onupdate utcnow | Last update |
| confirmed_at | DateTime | | Confirmation date |
| mrp_status | String(50) | INDEX | MRP processing status |
| mrp_run_id | Integer | FK→mrp_runs.id, INDEX | MRP run reference |

**Relationships:**

- `user` → User (many-to-one)
- `customer` → User (many-to-one)
- `quote` → Quote (one-to-one)
- `product` → Product (many-to-one)
- `lines` → SalesOrderLine (one-to-many, cascade delete)
- `payments` → Payment (one-to-many, cascade delete)
- `mrp_run` → MRPRun (many-to-one)

---

### SalesOrderLine

**Table:** `sales_order_lines` | **Tier:** Core | **File:** `sales_order.py:173`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| sales_order_id | Integer | FK→sales_orders.id, NOT NULL, INDEX | Parent order |
| product_id | Integer | FK→products.id, NOT NULL, INDEX | Product |
| quantity | Numeric(10,2) | NOT NULL | Order quantity |
| unit_price | Numeric(10,2) | NOT NULL | Unit price |
| discount | Numeric(10,2) | DEFAULT 0 | Discount amount |
| tax_rate | Numeric(5,2) | DEFAULT 0 | Tax rate |
| total | Numeric(10,2) | NOT NULL | Line total |
| allocated_quantity | Numeric(10,2) | DEFAULT 0 | Allocated from inventory |
| shipped_quantity | Numeric(10,2) | DEFAULT 0 | Shipped quantity |
| notes | Text | | Notes |
| created_by | Integer | | Creator user ID |

**Relationships:**

- `sales_order` → SalesOrder (many-to-one)
- `product` → Product (many-to-one)

---

### PurchaseOrder

**Table:** `purchase_orders` | **Tier:** Core | **File:** `purchase_order.py:16`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| po_number | String(50) | UNIQUE, NOT NULL, INDEX | PO number |
| vendor_id | Integer | FK→vendors.id, NOT NULL | Vendor reference |
| status | String(50) | NOT NULL, DEFAULT 'draft' | draft, ordered, shipped, partial, received, closed |
| order_date | Date | | Order date |
| expected_date | Date | | Expected delivery |
| shipped_date | Date | | Ship date |
| received_date | Date | | Receive date |
| tracking_number | String(200) | | Tracking number |
| carrier | String(100) | | Carrier |
| subtotal | Numeric(18,4) | NOT NULL, DEFAULT 0 | Subtotal |
| tax_amount | Numeric(18,4) | NOT NULL, DEFAULT 0 | Tax |
| shipping_cost | Numeric(18,4) | NOT NULL, DEFAULT 0 | Shipping |
| total_amount | Numeric(18,4) | NOT NULL, DEFAULT 0 | Total |
| payment_method | String(100) | | Payment method |
| payment_reference | String(200) | | Payment reference |
| document_url | String(1000) | | Document URL |
| notes | Text | | Notes |
| created_by | String(100) | | Creator |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `vendor` → Vendor (many-to-one)
- `lines` → PurchaseOrderLine (one-to-many, cascade delete)
- `documents` → PurchaseOrderDocument (one-to-many, cascade delete)

---

### PurchaseOrderLine

**Table:** `purchase_order_lines` | **Tier:** Core | **File:** `purchase_order.py:72`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| purchase_order_id | Integer | FK→purchase_orders.id, NOT NULL | Parent PO |
| product_id | Integer | FK→products.id, NOT NULL | Product |
| line_number | Integer | NOT NULL | Line sequence |
| quantity_ordered | Numeric(18,4) | NOT NULL | Ordered quantity |
| quantity_received | Numeric(18,4) | NOT NULL, DEFAULT 0 | Received quantity |
| purchase_unit | String(20) | | Purchase UOM |
| unit_cost | Numeric(18,4) | NOT NULL | Unit cost |
| line_total | Numeric(18,4) | NOT NULL | Line total |
| notes | Text | | Notes |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `purchase_order` → PurchaseOrder (many-to-one)
- `product` → Product (many-to-one)

---

### Vendor

**Table:** `vendors` | **Tier:** Core | **File:** `vendor.py:10`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| code | String(50) | UNIQUE, NOT NULL, INDEX | Vendor code |
| name | String(200) | NOT NULL | Vendor name |
| contact_name | String(100) | | Contact person |
| email | String(200) | | Email |
| phone | String(50) | | Phone |
| website | String(500) | | Website |
| address_line1 | String(200) | | Address line 1 |
| address_line2 | String(200) | | Address line 2 |
| city | String(100) | | City |
| state | String(100) | | State |
| postal_code | String(20) | | Postal code |
| country | String(100) | DEFAULT 'USA' | Country |
| payment_terms | String(100) | | Payment terms |
| account_number | String(100) | | Account number |
| tax_id | String(50) | | Tax ID |
| lead_time_days | Integer | | Lead time |
| rating | Numeric(3,2) | | Vendor rating |
| notes | Text | | Notes |
| is_active | Boolean | NOT NULL, DEFAULT true | Active flag |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `purchase_orders` → PurchaseOrder (one-to-many)
- `vendor_items` → VendorItem (one-to-many)

---

### ItemCategory

**Table:** `item_categories` | **Tier:** Core | **File:** `item_category.py:11`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| code | String(50) | UNIQUE, NOT NULL, INDEX | Category code |
| name | String(100) | NOT NULL | Category name |
| parent_id | Integer | FK→item_categories.id | Parent category |
| description | Text | | Description |
| sort_order | Integer | DEFAULT 0 | Sort order |
| is_active | Boolean | DEFAULT true | Active flag |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `parent` → ItemCategory (self-referential)
- `children` → ItemCategory (one-to-many)
- `products` → Product (one-to-many)

---

## Manufacturing Models

### ProductionOrder

**Table:** `production_orders` | **Tier:** Core | **File:** `production_order.py:17`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| code | String(50) | UNIQUE, NOT NULL, INDEX | Work order code |
| product_id | Integer | FK→products.id, NOT NULL, INDEX | Product to make |
| bom_id | Integer | FK→boms.id, INDEX | BOM reference |
| routing_id | Integer | FK→routings.id, INDEX | Routing reference |
| sales_order_id | Integer | FK→sales_orders.id, INDEX | Source sales order |
| sales_order_line_id | Integer | FK→sales_order_lines.id, INDEX | Source SO line |
| parent_order_id | Integer | FK→production_orders.id, INDEX | Parent (for splits) |
| split_sequence | Integer | | Split sequence number |
| quantity_ordered | Numeric(18,4) | NOT NULL | Quantity to make |
| quantity_completed | Numeric(18,4) | NOT NULL, DEFAULT 0 | Completed quantity |
| quantity_scrapped | Numeric(18,4) | NOT NULL, DEFAULT 0 | Scrapped quantity |
| source | String(50) | NOT NULL, DEFAULT 'manual' | manual, sales_order, mrp |
| order_type | String(20) | NOT NULL, DEFAULT 'MAKE_TO_ORDER' | MTO, MTS |
| status | String(50) | NOT NULL, INDEX, DEFAULT 'draft' | draft, released, in_progress, completed, cancelled |
| qc_status | String(50) | NOT NULL, DEFAULT 'not_required' | not_required, pending, passed, failed |
| qc_notes | Text | | QC notes |
| qc_inspected_by | String(100) | | QC inspector |
| qc_inspected_at | DateTime | | QC date |
| priority | Integer | NOT NULL, DEFAULT 3 | 1=highest, 5=lowest |
| due_date | Date | INDEX | Due date |
| scheduled_start | DateTime | | Scheduled start |
| scheduled_end | DateTime | | Scheduled end |
| actual_start | DateTime | | Actual start |
| actual_end | DateTime | | Actual end |
| estimated_time_minutes | Integer | | Estimated time |
| actual_time_minutes | Integer | | Actual time |
| estimated_material_cost | Numeric(18,4) | | Estimated material cost |
| estimated_labor_cost | Numeric(18,4) | | Estimated labor cost |
| estimated_total_cost | Numeric(18,4) | | Estimated total cost |
| actual_material_cost | Numeric(18,4) | | Actual material cost |
| actual_labor_cost | Numeric(18,4) | | Actual labor cost |
| actual_total_cost | Numeric(18,4) | | Actual total cost |
| assigned_to | String(100) | | Assigned operator |
| notes | Text | | Notes |
| scrap_reason | String(100) | | Scrap reason |
| scrapped_at | DateTime | | Scrap date |
| remake_of_id | Integer | FK→production_orders.id | Replacement for |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |
| created_by | String(100) | | Creator |
| released_at | DateTime | | Release date |
| completed_at | DateTime | | Completion date |

**Relationships:**

- `product` → Product (many-to-one)
- `bom` → BOM (many-to-one)
- `routing` → Routing (many-to-one)
- `sales_order` → SalesOrder (many-to-one)
- `operations` → ProductionOrderOperation (one-to-many, cascade delete)
- `parent_order` → ProductionOrder (self-referential)
- `child_orders` → ProductionOrder (one-to-many)
- `original_order` → ProductionOrder (self-referential for remakes)
- `remakes` → ProductionOrder (one-to-many)
- `spools_used` → ProductionOrderSpool (one-to-many)
- `material_overrides` → ProductionOrderMaterial (one-to-many)
- `print_jobs` → PrintJob (one-to-many)
- `scrap_records` → ScrapRecord (one-to-many)

---

### ProductionOrderOperation

**Table:** `production_order_operations` | **Tier:** Core | **File:** `production_order.py:202`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| production_order_id | Integer | FK→production_orders.id, NOT NULL | Parent order |
| routing_operation_id | Integer | FK→routing_operations.id | Source routing op |
| work_center_id | Integer | FK→work_centers.id, NOT NULL | Work center |
| resource_id | Integer | FK→resources.id | Specific resource |
| printer_id | Integer | FK→printers.id | Specific printer |
| sequence | Integer | NOT NULL | Operation sequence |
| operation_code | String(50) | | Operation code |
| operation_name | String(200) | | Operation name |
| status | String(50) | NOT NULL, INDEX, DEFAULT 'pending' | pending, in_progress, completed, skipped |
| quantity_completed | Numeric(18,4) | NOT NULL, DEFAULT 0 | Completed qty |
| quantity_scrapped | Numeric(18,4) | NOT NULL, DEFAULT 0 | Scrapped qty |
| scrap_reason | String(100) | | Scrap reason |
| planned_setup_minutes | Numeric(10,2) | NOT NULL, DEFAULT 0 | Planned setup time |
| planned_run_minutes | Numeric(10,2) | NOT NULL | Planned run time |
| actual_setup_minutes | Numeric(10,2) | | Actual setup time |
| actual_run_minutes | Numeric(10,2) | | Actual run time |
| scheduled_start | DateTime | | Scheduled start |
| scheduled_end | DateTime | | Scheduled end |
| actual_start | DateTime | | Actual start |
| actual_end | DateTime | | Actual end |
| bambu_task_id | String(100) | | Bambu Lab task ID |
| bambu_plate_index | Integer | | Bambu plate index |
| operator_id | Integer | | Operator user ID |
| operator_name | String(100) | | Operator name |
| notes | Text | | Notes |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `production_order` → ProductionOrder (many-to-one)
- `routing_operation` → RoutingOperation (many-to-one)
- `work_center` → WorkCenter (many-to-one)
- `resource` → Resource (many-to-one)
- `printer` → Printer (many-to-one)
- `materials` → ProductionOrderOperationMaterial (one-to-many)
- `scrap_records` → ScrapRecord (one-to-many)

---

### ProductionOrderMaterial

**Table:** `production_order_materials` | **Tier:** Core | **File:** `production_order.py:288`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| production_order_id | Integer | FK→production_orders.id, NOT NULL, INDEX | Parent order |
| bom_line_id | Integer | FK→bom_lines.id | Source BOM line |
| original_product_id | Integer | FK→products.id, NOT NULL | Original material |
| original_quantity | Numeric(18,4) | NOT NULL | Original quantity |
| substitute_product_id | Integer | FK→products.id, NOT NULL | Substitute material |
| planned_quantity | Numeric(18,4) | NOT NULL | Planned quantity |
| actual_quantity_used | Numeric(18,4) | | Actual used |
| reason | Text | NOT NULL | Substitution reason |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| created_by | String(100) | | Creator |

**Relationships:**

- `production_order` → ProductionOrder (many-to-one)
- `original_product` → Product (many-to-one)
- `substitute_product` → Product (many-to-one)

---

### ProductionOrderOperationMaterial

**Table:** `production_order_operation_materials` | **Tier:** Core | **File:** `production_order.py:329`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| production_order_operation_id | Integer | FK→production_order_operations.id, NOT NULL, INDEX | Parent operation |
| component_id | Integer | FK→products.id, NOT NULL, INDEX | Material product |
| routing_operation_material_id | Integer | FK→routing_operation_materials.id | Source routing material |
| quantity_required | Numeric(18,6) | NOT NULL | Required quantity |
| unit | String(20) | NOT NULL, DEFAULT 'EA' | Unit |
| quantity_allocated | Numeric(18,6) | NOT NULL, DEFAULT 0 | Allocated qty |
| quantity_consumed | Numeric(18,6) | NOT NULL, DEFAULT 0 | Consumed qty |
| lot_number | String(100) | | Lot number |
| inventory_transaction_id | Integer | FK→inventory_transactions.id | Consumption transaction |
| status | String(20) | NOT NULL, DEFAULT 'pending' | pending, allocated, consumed |
| consumed_at | DateTime | | Consumption timestamp |
| consumed_by | Integer | FK→users.id | Consumer user |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `operation` → ProductionOrderOperation (many-to-one)
- `component` → Product (many-to-one)
- `routing_material` → RoutingOperationMaterial (many-to-one)
- `transaction` → InventoryTransaction (many-to-one)
- `consumed_by_user` → User (many-to-one)

---

### ScrapRecord

**Table:** `scrap_records` | **Tier:** Core | **File:** `production_order.py:410`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| production_order_id | Integer | FK→production_orders.id, INDEX | Parent order |
| production_operation_id | Integer | FK→production_order_operations.id, INDEX | Parent operation |
| operation_sequence | Integer | | Operation sequence |
| product_id | Integer | FK→products.id, NOT NULL, INDEX | Product |
| quantity | Numeric(18,4) | NOT NULL | Scrap quantity |
| unit_cost | Numeric(18,4) | NOT NULL | Unit cost |
| total_cost | Numeric(18,4) | NOT NULL | Total cost |
| scrap_reason_id | Integer | FK→scrap_reasons.id | Scrap reason |
| scrap_reason_code | String(50) | | Reason code |
| notes | Text | | Notes |
| inventory_transaction_id | Integer | FK→inventory_transactions.id | Inventory transaction |
| journal_entry_id | Integer | FK→gl_journal_entries.id | GL journal entry |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| created_by_user_id | Integer | FK→users.id | Creator |

**Relationships:**

- `production_order` → ProductionOrder (many-to-one)
- `production_operation` → ProductionOrderOperation (many-to-one)
- `product` → Product (many-to-one)
- `scrap_reason` → ScrapReason (many-to-one)
- `inventory_transaction` → InventoryTransaction (many-to-one)
- `journal_entry` → GLJournalEntry (many-to-one)
- `created_by` → User (many-to-one)

---

### WorkCenter

**Table:** `work_centers` | **Tier:** Core | **File:** `work_center.py:14`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| code | String(50) | UNIQUE, NOT NULL, INDEX | Work center code |
| name | String(200) | NOT NULL | Work center name |
| description | Text | | Description |
| center_type | String(50) | NOT NULL, DEFAULT 'production' | production, assembly, shipping |
| capacity_hours_per_day | Numeric(10,2) | | Daily capacity |
| capacity_units_per_hour | Numeric(10,2) | | Hourly capacity |
| machine_rate_per_hour | Numeric(18,4) | | Machine rate |
| labor_rate_per_hour | Numeric(18,4) | | Labor rate |
| overhead_rate_per_hour | Numeric(18,4) | | Overhead rate |
| hourly_rate | Numeric(10,2) | NOT NULL, DEFAULT 0 | Combined hourly rate |
| is_bottleneck | Boolean | NOT NULL, DEFAULT false | Bottleneck flag |
| scheduling_priority | Integer | NOT NULL, DEFAULT 5 | Scheduling priority |
| is_active | Boolean | NOT NULL, DEFAULT true | Active flag |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `operations` → ProductionOrderOperation (one-to-many)
- `printers` → Printer (one-to-many)
- `resources` → Resource (one-to-many)
- `routing_operations` → RoutingOperation (one-to-many)

---

### Resource

**Table:** `resources` | **Tier:** Core | **File:** `manufacturing.py:15`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| work_center_id | Integer | FK→work_centers.id, NOT NULL | Work center |
| code | String(50) | NOT NULL, INDEX | Resource code |
| name | String(200) | NOT NULL | Resource name |
| machine_type | String(100) | | Machine type |
| serial_number | String(100) | | Serial number |
| printer_class | String(20) | DEFAULT 'open' | open, bambu |
| bambu_device_id | String(100) | | Bambu device ID |
| bambu_ip_address | String(50) | | Bambu IP address |
| capacity_hours_per_day | Numeric(10,2) | | Daily capacity |
| status | String(50) | NOT NULL, DEFAULT 'available' | available, busy, maintenance |
| is_active | Boolean | NOT NULL, DEFAULT true | Active flag |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `work_center` → WorkCenter (many-to-one)
- `operations` → ProductionOrderOperation (one-to-many)

---

### Routing

**Table:** `routings` | **Tier:** Core | **File:** `manufacturing.py:73`

| Column | Type | Constraints | Description |
| ------ | ---- | ----------- | ----------- |
| id | Integer | PK | Primary key |
| product_id | Integer | FK→products.id | Product reference |
| code | String(50) | NOT NULL, INDEX | Routing code |
| name | String(200) | | Routing name |
| is_template | Boolean | NOT NULL, DEFAULT false | Template routing |
| version | Integer | NOT NULL, DEFAULT 1 | Version |
| revision | String(20) | NOT NULL, DEFAULT '1.0' | Revision |
| is_active | Boolean | NOT NULL, DEFAULT true | Active flag |
| total_setup_time_minutes | Numeric(10,2) | | Total setup time |
| total_run_time_minutes | Numeric(10,2) | | Total run time |
| total_cost | Numeric(18,4) | | Total cost |
| effective_date | Date | | Effective date |
| notes | Text | | Notes |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `product` → Product (many-to-one)
- `operations` → RoutingOperation (one-to-many, cascade delete)

---

### RoutingOperation

**Table:** `routing_operations` | **Tier:** Core | **File:** `manufacturing.py:139`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| routing_id | Integer | FK→routings.id, NOT NULL | Parent routing |
| work_center_id | Integer | FK→work_centers.id, NOT NULL | Work center |
| sequence | Integer | NOT NULL | Operation sequence |
| operation_code | String(50) | | Operation code |
| operation_name | String(200) | | Operation name |
| description | Text | | Description |
| setup_time_minutes | Numeric(10,2) | NOT NULL, DEFAULT 0 | Setup time |
| run_time_minutes | Numeric(10,2) | NOT NULL | Run time |
| wait_time_minutes | Numeric(10,2) | NOT NULL, DEFAULT 0 | Wait time |
| move_time_minutes | Numeric(10,2) | NOT NULL, DEFAULT 0 | Move time |
| runtime_source | String(50) | NOT NULL, DEFAULT 'manual' | manual, slicer |
| slicer_file_path | String(500) | | Slicer file |
| units_per_cycle | Integer | NOT NULL, DEFAULT 1 | Units per cycle |
| scrap_rate_percent | Numeric(5,2) | NOT NULL, DEFAULT 0 | Scrap rate |
| labor_rate_override | Numeric(18,4) | | Labor rate override |
| machine_rate_override | Numeric(18,4) | | Machine rate override |
| predecessor_operation_id | Integer | FK→routing_operations.id | Predecessor |
| can_overlap | Boolean | NOT NULL, DEFAULT false | Can overlap |
| is_active | Boolean | NOT NULL, DEFAULT true | Active flag |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `routing` → Routing (many-to-one)
- `work_center` → WorkCenter (many-to-one)
- `predecessor` → RoutingOperation (self-referential)
- `materials` → RoutingOperationMaterial (one-to-many)

---

### RoutingOperationMaterial

**Table:** `routing_operation_materials` | **Tier:** Core | **File:** `manufacturing.py:226`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| routing_operation_id | Integer | FK→routing_operations.id, NOT NULL, INDEX | Parent operation |
| component_id | Integer | FK→products.id, NOT NULL, INDEX | Component product |
| quantity | Numeric(18,6) | NOT NULL | Quantity per |
| quantity_per | String(20) | NOT NULL, DEFAULT 'unit' | unit, batch, order |
| unit | String(20) | NOT NULL, DEFAULT 'EA' | Unit of measure |
| scrap_factor | Numeric(5,2) | DEFAULT 0 | Scrap factor % |
| is_cost_only | Boolean | NOT NULL, DEFAULT false | Cost only flag |
| is_optional | Boolean | NOT NULL, DEFAULT false | Optional material |
| notes | Text | | Notes |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `routing_operation` → RoutingOperation (many-to-one)
- `component` → Product (many-to-one)

---

### Printer

**Table:** `printers` | **Tier:** Core | **File:** `printer.py:11`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| code | String(50) | UNIQUE, NOT NULL, INDEX | Printer code |
| name | String(255) | NOT NULL | Printer name |
| model | String(100) | NOT NULL | Model |
| serial_number | String(100) | | Serial number |
| brand | String(50) | NOT NULL, INDEX, DEFAULT 'generic' | Brand |
| ip_address | String(50) | | IP address |
| mqtt_topic | String(255) | | MQTT topic |
| connection_config | JSON | DEFAULT {} | Connection config |
| capabilities | JSON | DEFAULT {} | Capabilities |
| status | String(50) | DEFAULT 'offline' | online, offline, printing |
| last_seen | DateTime | | Last seen timestamp |
| location | String(255) | | Physical location |
| work_center_id | Integer | FK→work_centers.id | Work center |
| notes | Text | | Notes |
| active | Boolean | DEFAULT true | Active flag |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `print_jobs` → PrintJob (one-to-many)
- `work_center` → WorkCenter (many-to-one)
- `maintenance_logs` → MaintenanceLog (one-to-many)

---

### PrintJob

**Table:** `print_jobs` | **Tier:** Core | **File:** `print_job.py:10`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| production_order_id | Integer | FK→production_orders.id | Production order |
| printer_id | Integer | FK→printers.id | Printer |
| gcode_file | String(500) | | G-code file |
| status | String(50) | NOT NULL, DEFAULT 'queued' | queued, printing, completed, failed |
| priority | String(20) | DEFAULT 'normal' | Priority |
| estimated_time_minutes | Integer | | Estimated time |
| actual_time_minutes | Integer | | Actual time |
| estimated_material_grams | Numeric(18,4) | | Estimated material |
| actual_material_grams | Numeric(18,4) | | Actual material |
| variance_percent | Numeric(5,2) | | Material variance |
| queued_at | DateTime | | Queue timestamp |
| started_at | DateTime | | Start timestamp |
| finished_at | DateTime | | Finish timestamp |
| notes | Text | | Notes |

**Relationships:**

- `production_order` → ProductionOrder (many-to-one)
- `printer` → Printer (many-to-one)

---

### MaintenanceLog

**Table:** `maintenance_logs` | **Tier:** Core | **File:** `maintenance.py:14`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| printer_id | Integer | FK→printers.id, NOT NULL, INDEX | Printer |
| maintenance_type | String(50) | NOT NULL, INDEX | preventive, corrective, calibration |
| description | Text | | Description |
| performed_by | String(100) | | Performer |
| performed_at | DateTime | NOT NULL, INDEX, DEFAULT utcnow | Performed timestamp |
| next_due_at | DateTime | INDEX | Next due date |
| cost | Numeric(10,2) | | Cost |
| downtime_minutes | Integer | | Downtime |
| parts_used | Text | | Parts used |
| notes | Text | | Notes |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |

**Relationships:**

- `printer` → Printer (many-to-one)

---

### ScrapReason

**Table:** `scrap_reasons` | **Tier:** Core | **File:** `scrap_reason.py:13`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| code | String(50) | UNIQUE, NOT NULL, INDEX | Reason code |
| name | String(100) | NOT NULL | Reason name |
| description | Text | | Description |
| active | Boolean | NOT NULL, DEFAULT true | Active flag |
| sequence | Integer | DEFAULT 0 | Sort order |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

---

## User & Auth Models

### User

**Table:** `users` | **Tier:** Core | **File:** `user.py:10`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| customer_number | String(20) | INDEX | Customer number |
| email | String(255) | UNIQUE, NOT NULL, INDEX | Email address |
| password_hash | String(255) | NOT NULL | Password hash |
| email_verified | Boolean | NOT NULL, DEFAULT false | Email verified |
| first_name | String(100) | | First name |
| last_name | String(100) | | Last name |
| company_name | String(200) | | Company name |
| phone | String(20) | | Phone |
| billing_address_line1 | String(255) | | Billing address |
| billing_address_line2 | String(255) | | Billing address 2 |
| billing_city | String(100) | | Billing city |
| billing_state | String(50) | | Billing state |
| billing_zip | String(20) | | Billing ZIP |
| billing_country | String(100) | DEFAULT 'USA' | Billing country |
| shipping_address_line1 | String(255) | | Shipping address |
| shipping_address_line2 | String(255) | | Shipping address 2 |
| shipping_city | String(100) | | Shipping city |
| shipping_state | String(50) | | Shipping state |
| shipping_zip | String(20) | | Shipping ZIP |
| shipping_country | String(100) | DEFAULT 'USA' | Shipping country |
| status | String(20) | NOT NULL, INDEX, DEFAULT 'active' | active, inactive, suspended |
| account_type | String(20) | NOT NULL, DEFAULT 'customer' | customer, staff, admin |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |
| last_login_at | DateTime | | Last login |
| created_by | Integer | | Creator user ID |
| updated_by | Integer | | Updater user ID |

**Relationships:**

- `refresh_tokens` → RefreshToken (one-to-many, cascade delete)
- `quotes` → Quote (one-to-many, cascade delete)
- `sales_orders` → SalesOrder (one-to-many, cascade delete)

---

### RefreshToken

**Table:** `refresh_tokens` | **Tier:** Core | **File:** `user.py:108`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| user_id | Integer | FK→users.id, NOT NULL, INDEX | User reference |
| token_hash | String(255) | UNIQUE, NOT NULL, INDEX | Token hash |
| expires_at | DateTime | NOT NULL, INDEX | Expiration |
| revoked | Boolean | NOT NULL, DEFAULT false | Revoked flag |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| revoked_at | DateTime | | Revocation timestamp |

**Relationships:**

- `user` → User (many-to-one)

---

### PasswordResetRequest

**Table:** `password_reset_requests` | **Tier:** Core | **File:** `user.py:146`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| user_id | Integer | FK→users.id, NOT NULL, INDEX | User reference |
| token | String(255) | UNIQUE, NOT NULL, INDEX | Reset token |
| approval_token | String(255) | UNIQUE, NOT NULL, INDEX | Admin approval token |
| status | String(20) | NOT NULL, INDEX, DEFAULT 'pending' | pending, approved, denied, completed |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| expires_at | DateTime | NOT NULL | Expiration |
| approved_at | DateTime | | Approval timestamp |
| completed_at | DateTime | | Completion timestamp |
| admin_notes | String(500) | | Admin notes |

**Relationships:**

- `user` → User (many-to-one)

---

## Quote & Sales Models

### Quote

**Table:** `quotes` | **Tier:** Core | **File:** `quote.py:16`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| user_id | Integer | FK→users.id, NOT NULL, INDEX | Quote owner |
| quote_number | String(50) | UNIQUE, NOT NULL, INDEX | Quote number |
| product_name | String(255) | | Product name |
| quantity | Integer | NOT NULL, DEFAULT 1 | Quantity |
| material_type | String(50) | | Material type |
| color | String(30) | | Color |
| finish | String(50) | DEFAULT 'standard' | Finish |
| gcode_file_path | String(500) | | G-code path |
| material_grams | Numeric(10,2) | | Material grams |
| print_time_hours | Numeric(10,2) | | Print time |
| unit_price | Numeric(10,2) | | Unit price |
| subtotal | Numeric(10,2) | | Subtotal |
| tax_rate | Numeric(5,4) | | Tax rate |
| tax_amount | Numeric(10,2) | | Tax amount |
| total_price | Numeric(10,2) | NOT NULL | Total price |
| margin_percent | Numeric(5,2) | | Margin % |
| image_data | LargeBinary | | Image data |
| image_filename | String(255) | | Image filename |
| image_mime_type | String(100) | | Image MIME type |
| file_format | String(10) | NOT NULL | stl, 3mf, obj |
| file_size_bytes | BigInteger | NOT NULL | File size |
| dimensions_x | Numeric(10,2) | | X dimension |
| dimensions_y | Numeric(10,2) | | Y dimension |
| dimensions_z | Numeric(10,2) | | Z dimension |
| status | String(50) | INDEX, DEFAULT 'pending' | pending, approved, rejected, expired |
| approval_method | String(50) | | auto, manual |
| approved_by | Integer | | Approver user ID |
| approved_at | DateTime | | Approval timestamp |
| rejection_reason | String(500) | | Rejection reason |
| auto_approved | Boolean | NOT NULL, DEFAULT false | Auto-approved |
| auto_approve_eligible | Boolean | NOT NULL, DEFAULT false | Eligible for auto |
| requires_review_reason | String(255) | | Review reason |
| rush_level | String(20) | DEFAULT 'standard' | Rush level |
| requested_delivery_date | Date | | Requested delivery |
| customer_notes | String(1000) | | Customer notes |
| admin_notes | String(1000) | | Admin notes |
| internal_notes | String(1000) | | Internal notes |
| customer_id | Integer | FK→users.id, INDEX | Customer user |
| customer_email | String(255) | | Customer email |
| customer_name | String(200) | | Customer name |
| shipping_name | String(200) | | Shipping name |
| shipping_address_line1 | String(255) | | Shipping address |
| shipping_address_line2 | String(255) | | Shipping address 2 |
| shipping_city | String(100) | | Shipping city |
| shipping_state | String(50) | | Shipping state |
| shipping_zip | String(20) | | Shipping ZIP |
| shipping_country | String(100) | DEFAULT 'USA' | Shipping country |
| shipping_phone | String(30) | | Shipping phone |
| shipping_rate_id | String(100) | | Shipping rate ID |
| shipping_carrier | String(50) | | Carrier |
| shipping_service | String(100) | | Service |
| shipping_cost | Numeric(10,2) | | Shipping cost |
| sales_order_id | Integer | | Converted SO ID |
| converted_at | DateTime | | Conversion timestamp |
| product_id | Integer | FK→products.id, INDEX | Product reference |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, DEFAULT utcnow | Last update |
| expires_at | DateTime | NOT NULL | Expiration |

**Relationships:**

- `user` → User (many-to-one)
- `customer` → User (many-to-one)
- `files` → QuoteFile (one-to-many, cascade delete)
- `sales_order` → SalesOrder (one-to-one)
- `product` → Product (many-to-one)
- `materials` → QuoteMaterial (one-to-many, cascade delete)

---

### QuoteFile

**Table:** `quote_files` | **Tier:** Core | **File:** `quote.py:185`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| quote_id | Integer | FK→quotes.id, NOT NULL, INDEX | Parent quote |
| original_filename | String(255) | NOT NULL | Original filename |
| stored_filename | String(255) | UNIQUE, NOT NULL | Storage filename |
| file_path | String(500) | NOT NULL | File path |
| file_size_bytes | BigInteger | NOT NULL | File size |
| file_format | String(10) | NOT NULL | File format |
| mime_type | String(100) | NOT NULL | MIME type |
| is_valid | Boolean | NOT NULL, DEFAULT true | Valid flag |
| validation_errors | String(1000) | | Validation errors |
| file_hash | String(64) | NOT NULL, INDEX | File hash |
| model_name | String(255) | | Model name |
| vertex_count | Integer | | Vertex count |
| triangle_count | Integer | | Triangle count |
| bambu_file_id | String(100) | | Bambu file ID |
| processed | Boolean | NOT NULL, DEFAULT false | Processed flag |
| processing_error | String(500) | | Processing error |
| uploaded_at | DateTime | NOT NULL, DEFAULT utcnow | Upload timestamp |
| processed_at | DateTime | | Processing timestamp |

**Relationships:**

- `quote` → Quote (many-to-one)

---

### QuoteMaterial

**Table:** `quote_materials` | **Tier:** Core | **File:** `quote.py:240`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| quote_id | Integer | FK→quotes.id, NOT NULL, INDEX | Parent quote |
| slot_number | Integer | NOT NULL, DEFAULT 1 | Slot number |
| is_primary | Boolean | NOT NULL, DEFAULT false | Primary material |
| material_type | String(50) | NOT NULL | Material type |
| color_code | String(30) | | Color code |
| color_name | String(100) | | Color name |
| color_hex | String(7) | | Hex color |
| material_grams | Numeric(10,2) | NOT NULL | Material grams |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |

**Relationships:**

- `quote` → Quote (many-to-one)

---

### Payment

**Table:** `payments` | **Tier:** Core | **File:** `payment.py:14`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| sales_order_id | Integer | FK→sales_orders.id, NOT NULL, INDEX | Sales order |
| recorded_by_id | Integer | FK→users.id, INDEX | Recorder |
| payment_number | String(50) | UNIQUE, NOT NULL, INDEX | Payment number |
| amount | Numeric(10,2) | NOT NULL | Amount |
| payment_method | String(50) | NOT NULL | cash, check, card, wire |
| transaction_id | String(255) | | Transaction ID |
| check_number | String(50) | | Check number |
| payment_type | String(20) | NOT NULL, DEFAULT 'payment' | payment, refund |
| status | String(20) | NOT NULL, INDEX, DEFAULT 'completed' | completed, pending, failed |
| notes | Text | | Notes |
| payment_date | DateTime | NOT NULL, INDEX, DEFAULT utcnow | Payment date |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `sales_order` → SalesOrder (many-to-one)
- `recorded_by` → User (many-to-one)

---

## Material & Traceability Models

### MaterialType

**Table:** `material_types` | **Tier:** Core | **File:** `material.py:17`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| code | String(50) | UNIQUE, NOT NULL, INDEX | Material code |
| name | String(100) | NOT NULL | Material name |
| base_material | String(20) | NOT NULL, INDEX | PLA, PETG, ABS, etc. |
| process_type | String(20) | NOT NULL, DEFAULT 'FDM' | FDM, SLA, SLS |
| density | Numeric(6,4) | NOT NULL | Density g/cm³ |
| volumetric_flow_limit | Numeric(6,2) | | Flow limit |
| nozzle_temp_min | Integer | | Min nozzle temp |
| nozzle_temp_max | Integer | | Max nozzle temp |
| bed_temp_min | Integer | | Min bed temp |
| bed_temp_max | Integer | | Max bed temp |
| requires_enclosure | Boolean | DEFAULT false | Enclosure required |
| base_price_per_kg | Numeric(10,2) | NOT NULL | Base price/kg |
| price_multiplier | Numeric(4,2) | DEFAULT 1.0 | Price multiplier |
| description | Text | | Description |
| strength_rating | Integer | | Strength 1-10 |
| is_customer_visible | Boolean | DEFAULT true | Visible to customers |
| display_order | Integer | DEFAULT 100 | Display order |
| active | Boolean | DEFAULT true | Active flag |
| created_at | DateTime | DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | onupdate utcnow | Last update |

**Relationships:**

- `material_colors` → MaterialColor (one-to-many)
- `inventory_items` → MaterialInventory (one-to-many)

---

### Color

**Table:** `colors` | **Tier:** Core | **File:** `material.py:74`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| code | String(30) | UNIQUE, NOT NULL, INDEX | Color code |
| name | String(100) | NOT NULL | Color name |
| hex_code | String(7) | | Primary hex |
| hex_code_secondary | String(7) | | Secondary hex |
| display_order | Integer | DEFAULT 100 | Display order |
| is_customer_visible | Boolean | DEFAULT true | Visible to customers |
| active | Boolean | DEFAULT true | Active flag |
| created_at | DateTime | DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | onupdate utcnow | Last update |

**Relationships:**

- `material_colors` → MaterialColor (one-to-many)
- `inventory_items` → MaterialInventory (one-to-many)

---

### MaterialColor

**Table:** `material_colors` | **Tier:** Core | **File:** `material.py:112`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| material_type_id | Integer | FK→material_types.id, NOT NULL | Material type |
| color_id | Integer | FK→colors.id, NOT NULL | Color |
| is_customer_visible | Boolean | DEFAULT true | Visible to customers |
| display_order | Integer | DEFAULT 100 | Display order |
| active | Boolean | DEFAULT true | Active flag |

**Relationships:**

- `material_type` → MaterialType (many-to-one)
- `color` → Color (many-to-one)

---

### MaterialInventory

**Table:** `material_inventory` | **Tier:** Core | **File:** `material.py:148`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| material_type_id | Integer | FK→material_types.id, NOT NULL, INDEX | Material type |
| color_id | Integer | FK→colors.id, NOT NULL, INDEX | Color |
| product_id | Integer | FK→products.id, INDEX | Product link |
| sku | String(50) | UNIQUE, NOT NULL, INDEX | SKU |
| in_stock | Boolean | DEFAULT true | In stock |
| quantity_kg | Numeric(10,3) | DEFAULT 0 | Quantity in KG |
| reorder_point_kg | Numeric(10,3) | DEFAULT 1.0 | Reorder point |
| cost_per_kg | Numeric(10,2) | | Cost per KG |
| last_purchase_date | DateTime | | Last purchase |
| last_purchase_price | Numeric(10,2) | | Last price |
| preferred_vendor | String(100) | | Preferred vendor |
| vendor_sku | String(100) | | Vendor SKU |
| active | Boolean | DEFAULT true | Active flag |
| created_at | DateTime | DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | onupdate utcnow | Last update |

**Relationships:**

- `material_type` → MaterialType (many-to-one)
- `color` → Color (many-to-one)
- `product` → Product (many-to-one)

---

### MaterialSpool

**Table:** `material_spools` | **Tier:** Core | **File:** `material_spool.py:14`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| spool_number | String(100) | UNIQUE, NOT NULL, INDEX | Spool number |
| product_id | Integer | FK→products.id, NOT NULL | Product |
| initial_weight_kg | Numeric(10,3) | NOT NULL | Initial weight |
| current_weight_kg | Numeric(10,3) | NOT NULL | Current weight |
| status | String(50) | NOT NULL, DEFAULT 'active' | active, empty, expired |
| received_date | DateTime | NOT NULL, DEFAULT utcnow | Received date |
| expiry_date | DateTime | | Expiry date |
| location_id | Integer | FK→inventory_locations.id | Location |
| supplier_lot_number | String(100) | | Supplier lot |
| notes | Text | | Notes |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |
| created_by | String(100) | | Creator |

**Relationships:**

- `product` → Product (many-to-one)
- `location` → InventoryLocation (many-to-one)
- `production_orders` → ProductionOrderSpool (one-to-many)

---

### ProductionOrderSpool

**Table:** `production_order_spools` | **Tier:** Core | **File:** `material_spool.py:77`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| production_order_id | Integer | FK→production_orders.id, NOT NULL | Production order |
| spool_id | Integer | FK→material_spools.id, NOT NULL | Spool |
| weight_consumed_kg | Numeric(10,3) | NOT NULL, DEFAULT 0 | Weight consumed |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| created_by | String(100) | | Creator |

**Relationships:**

- `production_order` → ProductionOrder (many-to-one)
- `spool` → MaterialSpool (many-to-one)

---

### SerialNumber

**Table:** `serial_numbers` | **Tier:** Core | **File:** `traceability.py:34`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| serial_number | String(50) | UNIQUE, NOT NULL, INDEX | Serial number |
| product_id | Integer | FK→products.id, NOT NULL, INDEX | Product |
| production_order_id | Integer | FK→production_orders.id, NOT NULL, INDEX | Production order |
| status | String(30) | NOT NULL, INDEX, DEFAULT 'manufactured' | manufactured, sold, returned |
| qc_passed | Boolean | NOT NULL, DEFAULT true | QC passed |
| qc_date | DateTime | | QC date |
| qc_notes | Text | | QC notes |
| sales_order_id | Integer | FK→sales_orders.id, INDEX | Sales order |
| sales_order_line_id | Integer | FK→sales_order_lines.id | SO line |
| sold_at | DateTime | | Sold timestamp |
| shipped_at | DateTime | | Shipped timestamp |
| tracking_number | String(100) | | Tracking number |
| returned_at | DateTime | | Return timestamp |
| return_reason | Text | | Return reason |
| manufactured_at | DateTime | NOT NULL, DEFAULT utcnow | Manufacture timestamp |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |

**Relationships:**

- `product` → Product (many-to-one)
- `production_order` → ProductionOrder (many-to-one)
- `sales_order` → SalesOrder (many-to-one)
- `lot_consumptions` → ProductionLotConsumption (one-to-many)

---

### MaterialLot

**Table:** `material_lots` | **Tier:** Core | **File:** `traceability.py:115`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| lot_number | String(100) | UNIQUE, NOT NULL, INDEX | Lot number |
| product_id | Integer | FK→products.id, NOT NULL, INDEX | Product |
| vendor_id | Integer | FK→vendors.id, INDEX | Vendor |
| purchase_order_id | Integer | FK→purchase_orders.id | Purchase order |
| vendor_lot_number | String(100) | | Vendor lot |
| quantity_received | Numeric(12,4) | NOT NULL | Received qty |
| quantity_consumed | Numeric(12,4) | NOT NULL, DEFAULT 0 | Consumed qty |
| quantity_scrapped | Numeric(12,4) | NOT NULL, DEFAULT 0 | Scrapped qty |
| quantity_adjusted | Numeric(12,4) | NOT NULL, DEFAULT 0 | Adjusted qty |
| status | String(30) | NOT NULL, INDEX, DEFAULT 'active' | active, depleted, expired, quarantine |
| certificate_of_analysis | Text | | CoA text |
| coa_file_path | String(500) | | CoA file |
| inspection_status | String(30) | DEFAULT 'pending' | pending, passed, failed |
| manufactured_date | Date | | Manufacture date |
| expiration_date | Date | INDEX | Expiration |
| received_date | Date | NOT NULL, DEFAULT utcnow | Received date |
| unit_cost | Numeric(10,4) | | Unit cost |
| location | String(100) | | Location |
| notes | Text | | Notes |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `product` → Product (many-to-one)
- `vendor` → Vendor (many-to-one)
- `purchase_order` → PurchaseOrder (many-to-one)
- `consumptions` → ProductionLotConsumption (one-to-many)

---

### ProductionLotConsumption

**Table:** `production_lot_consumptions` | **Tier:** Core | **File:** `traceability.py:212`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| production_order_id | Integer | FK→production_orders.id, NOT NULL, INDEX | Production order |
| material_lot_id | Integer | FK→material_lots.id, NOT NULL, INDEX | Material lot |
| serial_number_id | Integer | FK→serial_numbers.id, INDEX | Serial number |
| bom_line_id | Integer | FK→bom_lines.id | BOM line |
| quantity_consumed | Numeric(12,4) | NOT NULL | Consumed qty |
| consumed_at | DateTime | NOT NULL, DEFAULT utcnow | Consumption timestamp |

**Relationships:**

- `production_order` → ProductionOrder (many-to-one)
- `material_lot` → MaterialLot (many-to-one)
- `serial_number` → SerialNumber (many-to-one)

---

### CustomerTraceabilityProfile

**Table:** `customer_traceability_profiles` | **Tier:** Core | **File:** `traceability.py:258`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| user_id | Integer | FK→users.id, UNIQUE, NOT NULL, INDEX | User reference |
| traceability_level | String(20) | NOT NULL, DEFAULT 'none' | none, lot, full |
| requires_coc | Boolean | DEFAULT false | Require CoC |
| requires_coa | Boolean | DEFAULT false | Require CoA |
| requires_first_article | Boolean | DEFAULT false | Require FAI |
| record_retention_days | Integer | DEFAULT 2555 | Retention days |
| custom_serial_prefix | String(20) | | Serial prefix |
| compliance_standards | String(255) | | Standards |
| notes | Text | | Notes |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `user` → User (one-to-one)

---

## MRP Models

### MRPRun

**Table:** `mrp_runs` | **Tier:** Core | **File:** `mrp.py:15`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| run_date | DateTime | NOT NULL, DEFAULT utcnow | Run date |
| planning_horizon_days | Integer | NOT NULL, DEFAULT 30 | Planning horizon |
| orders_processed | Integer | DEFAULT 0 | Orders processed |
| components_analyzed | Integer | DEFAULT 0 | Components analyzed |
| shortages_found | Integer | DEFAULT 0 | Shortages found |
| planned_orders_created | Integer | DEFAULT 0 | Planned orders created |
| status | String(20) | NOT NULL, DEFAULT 'running' | running, completed, failed |
| error_message | Text | | Error message |
| created_by | Integer | | Creator user ID |
| completed_at | DateTime | | Completion timestamp |

**Relationships:**

- `planned_orders` → PlannedOrder (one-to-many)

---

### PlannedOrder

**Table:** `planned_orders` | **Tier:** Core | **File:** `mrp.py:49`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| order_type | String(20) | NOT NULL | purchase, production |
| product_id | Integer | FK→products.id, NOT NULL | Product |
| quantity | Numeric(18,4) | NOT NULL | Quantity |
| due_date | Date | NOT NULL | Due date |
| start_date | Date | NOT NULL | Start date |
| source_demand_type | String(50) | | Demand source type |
| source_demand_id | Integer | | Demand source ID |
| mrp_run_id | Integer | FK→mrp_runs.id | MRP run |
| status | String(20) | NOT NULL, DEFAULT 'planned' | planned, firmed, released |
| converted_to_po_id | Integer | FK→purchase_orders.id | Converted to PO |
| converted_to_mo_id | Integer | FK→production_orders.id | Converted to MO |
| notes | Text | | Notes |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| created_by | Integer | | Creator user ID |
| updated_at | DateTime | onupdate utcnow | Last update |
| firmed_at | DateTime | | Firmed timestamp |
| released_at | DateTime | | Released timestamp |

**Relationships:**

- `product` → Product (many-to-one)
- `mrp_run` → MRPRun (many-to-one)
- `converted_po` → PurchaseOrder (many-to-one)
- `converted_mo` → ProductionOrder (many-to-one)

---

## Document Models

### PurchaseOrderDocument

**Table:** `purchase_order_documents` | **Tier:** Core | **File:** `purchase_order_document.py:11`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| purchase_order_id | Integer | FK→purchase_orders.id, NOT NULL | Purchase order |
| document_type | String(50) | NOT NULL | invoice, receipt, packing_slip |
| file_name | String(255) | NOT NULL | File name |
| original_file_name | String(255) | | Original name |
| file_url | String(1000) | | File URL |
| file_path | String(500) | | File path |
| storage_type | String(50) | NOT NULL, DEFAULT 'local' | local, s3 |
| file_size | Integer | | File size |
| mime_type | String(100) | | MIME type |
| google_drive_id | String(100) | | Google Drive ID |
| notes | Text | | Notes |
| uploaded_by | String(100) | | Uploader |
| uploaded_at | DateTime | NOT NULL, DEFAULT utcnow | Upload timestamp |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Relationships:**

- `purchase_order` → PurchaseOrder (many-to-one)

---

### VendorItem

**Table:** `vendor_items` | **Tier:** Core | **File:** `purchase_order_document.py:82`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| vendor_id | Integer | FK→vendors.id, NOT NULL | Vendor |
| vendor_sku | String(100) | NOT NULL | Vendor SKU |
| vendor_description | String(500) | | Vendor description |
| product_id | Integer | FK→products.id (SET NULL) | Mapped product |
| default_unit_cost | String(20) | | Default cost |
| default_purchase_unit | String(20) | | Default UOM |
| last_seen_at | DateTime | | Last seen |
| times_ordered | Integer | DEFAULT 0 | Order count |
| notes | Text | | Notes |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

**Constraints:** UNIQUE(vendor_id, vendor_sku)

**Relationships:**

- `vendor` → Vendor (many-to-one)
- `product` → Product (many-to-one)

---

## Settings Models

### CompanySettings

**Table:** `company_settings` | **Tier:** Core | **File:** `company_settings.py:15`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| company_name | String(200) | | Company name |
| settings_json | JSON | | Settings JSON |
| business_hours_start | Integer | | Business hours start (0-23) |
| business_hours_end | Integer | | Business hours end (0-23) |
| business_days_per_week | Integer | | Days per week |
| business_work_days | String(20) | | Work days string |
| timezone | String(50) | | Timezone |
| business_type | String(30) | DEFAULT 'sole_proprietor' | Business type |
| ai_provider | String(20) | | AI provider |
| ai_api_key | String(500) | | AI API key |
| ai_ollama_url | String(255) | DEFAULT '<http://localhost:11434>' | Ollama URL |
| ai_ollama_model | String(100) | DEFAULT 'llama3.2' | Ollama model |
| ai_anthropic_model | String(100) | DEFAULT 'claude-sonnet-4-20250514' | Anthropic model |
| external_ai_blocked | Boolean | DEFAULT false | Block external AI |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

---

## Event Models

### OrderEvent

**Table:** `order_events` | **Tier:** Core | **File:** `order_event.py:14`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| order_id | Integer | FK→sales_orders.id, NOT NULL, INDEX | Sales order |
| event_type | String(50) | NOT NULL | status_change, note, etc. |
| title | String(200) | NOT NULL | Event title |
| description | Text | | Event description |
| old_value | String(100) | | Previous value |
| new_value | String(100) | | New value |
| user_id | Integer | FK→users.id | User who triggered |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |

---

### PurchasingEvent

**Table:** `purchasing_events` | **Tier:** Core | **File:** `purchasing_event.py:14`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| purchase_order_id | Integer | FK→purchase_orders.id, NOT NULL, INDEX | Purchase order |
| event_type | String(50) | NOT NULL | Event type |
| title | String(200) | NOT NULL | Event title |
| description | Text | | Description |
| old_value | String(100) | | Old value |
| new_value | String(100) | | New value |
| event_date | Date | | Event date |
| user_id | Integer | FK→users.id | User |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |

---

### ShippingEvent

**Table:** `shipping_events` | **Tier:** Core | **File:** `shipping_event.py:14`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| order_id | Integer | FK→sales_orders.id, NOT NULL, INDEX | Sales order |
| event_type | String(50) | NOT NULL | Event type |
| title | String(200) | NOT NULL | Event title |
| description | Text | | Description |
| tracking_number | String(100) | | Tracking number |
| carrier | String(50) | | Carrier |
| event_date | Date | | Event date |
| event_timestamp | DateTime | | Event timestamp |
| user_id | Integer | FK→users.id | User |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |

---

## UOM Model

### UnitOfMeasure

**Table:** `units_of_measure` | **Tier:** Core | **File:** `uom.py:15`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | PK | Primary key |
| code | String(20) | UNIQUE, NOT NULL, INDEX | UOM code |
| name | String(100) | NOT NULL | UOM name |
| base_unit | String(20) | | Base unit |
| conversion_factor | Numeric(18,8) | DEFAULT 1 | Conversion factor |
| uom_class | String(20) | | mass, length, volume, each |
| is_default | Boolean | DEFAULT false | Default for class |
| active | Boolean | DEFAULT true | Active flag |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | Creation timestamp |
| updated_at | DateTime | NOT NULL, onupdate utcnow | Last update |

---

## Summary Statistics

| Category | Models | Tables |
|----------|--------|--------|
| Core ERP | 12 | 12 |
| Manufacturing | 14 | 14 |
| User & Auth | 3 | 3 |
| Quote & Sales | 4 | 4 |
| Material & Traceability | 10 | 10 |
| MRP | 2 | 2 |
| Document | 2 | 2 |
| Settings | 1 | 1 |
| Events | 3 | 3 |
| UOM | 1 | 1 |
| **Total** | **52** | **52** |
