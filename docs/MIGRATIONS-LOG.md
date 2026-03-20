# FilaOps Migrations Log

> Chronological record of all database migrations with feature mapping.
> Generated for AI consumption and developer reference.
>
> This document covers **Core (Open Source)** migrations only.

## Overview

| Metric | Count |
| ------ | ----- |
| **Total Migrations** | 47 |
| **Database** | PostgreSQL |
| **Tool** | Alembic |

---

## Migration Categories

### By Feature Area

| Area | Count | Migrations |
|------|-------|------------|
| Initial Schema | 2 | 001, baseline_001 |
| Manufacturing | 8 | 017, 022, 023, 032, 033, 034, 054, 056 |
| Inventory | 6 | 017, 018, 021, 024, 029, 039 |
| Purchasing | 5 | 019, 027, 035, 036, add_production_order_materials |
| MRP | 3 | 031, 033, add_operation_materials |
| Users/Auth | 1 | 043 |
| Settings | 2 | 020, 028 |
| Quality | 3 | 053, 055, 057 |
| Events | 2 | 030, add_event_tables |
| Maintenance | 2 | 025, 026 |
| Performance | 2 | 021, 024 |
| Merges | 1 | 905ef924f499 |

---

## Chronological Migration List

### Phase 1: Initial Schema

#### `b1815de543ea_001_initial_postgres_schema.py`

**Tier**: Core
**Date**: Initial
**Purpose**: Complete initial PostgreSQL schema from SQLite migration

**Creates Tables**:

- `users` - User accounts (admin, operator, customer)
- `products` - Product catalog
- `inventory` - Inventory levels by location
- `inventory_locations` - Warehouse/bin locations
- `inventory_transactions` - Transaction audit log
- `sales_orders` - Sales order headers
- `sales_order_lines` - Sales order line items
- `production_orders` - Manufacturing work orders
- `production_order_operations` - Work order operations
- `work_centers` - Manufacturing work centers
- `resources` - Manufacturing resources
- `routings` - Product routings
- `routing_operations` - Routing operation templates
- `boms` - Bill of materials headers
- `bom_lines` - BOM component lines
- `vendors` - Supplier master
- `purchase_orders` - Purchase order headers
- `purchase_order_lines` - PO line items
- `quotes` - Customer quotes
- `quote_lines` - Quote line items
- `payments` - Payment records
- `company_settings` - System configuration

---

#### `baseline_001_stamp_existing.py`

**Tier**: Core
**Purpose**: Stamp existing database with baseline revision

---

### Phase 2: Core Features (017-031)

#### `017_add_material_spool_tracking.py`

**Tier**: Core
**Date**: 2025-12-22
**Purpose**: Material spool/lot tracking for 3D printing filament

**Creates Tables**:

- `material_spools` - Individual spool records with weight tracking
  - `spool_number` (unique identifier)
  - `product_id` (FK to products)
  - `initial_weight_kg`, `current_weight_kg`
  - `status` (active, consumed, expired)
  - `supplier_lot_number` (vendor traceability)
  - `expiry_date`, `location_id`
- `production_order_spools` - Junction table linking POs to consumed spools
  - `weight_consumed_kg`

---

#### `018_add_negative_inventory_approval_columns.py`

**Tier**: Core
**Purpose**: Approval workflow for negative inventory transactions

**Adds Columns to `inventory_transactions`**:

- `requires_approval` (boolean)
- `approval_reason` (text)
- `approved_by` (string)
- `approved_at` (datetime)

---

#### `019_add_purchase_unit_to_po_lines.py`

**Tier**: Core
**Purpose**: Purchase unit tracking on PO lines

**Adds Column to `purchase_order_lines`**:

- `purchase_unit` - Unit of measure for purchasing (may differ from inventory unit)

---

#### `020_add_business_hours_to_company_settings.py`

**Tier**: Core
**Purpose**: Business hours configuration for scheduling

**Adds Columns to `company_settings`**:

- `business_hours_start` (time)
- `business_hours_end` (time)
- `business_days` (array of weekdays)

---

#### `021_add_performance_indexes.py`

**Tier**: Core
**Purpose**: Performance optimization indexes

**Creates Indexes on**:

- `inventory_transactions` (product_id, created_at, transaction_type)
- `sales_orders` (status, created_at)
- `production_orders` (status, due_date)
- `products` (sku, is_active)

---

#### `022_sprint3_cleanup_work_center.py`

**Tier**: Core
**Purpose**: Work center schema cleanup

**Changes**:

- Adds missing columns to `work_centers`
- Standardizes column naming

---

#### `023_sprint3_cleanup_product.py`

**Tier**: Core
**Purpose**: Product schema cleanup

**Changes**:

- Adds cost columns (`standard_cost`, `average_cost`, `last_cost`)
- Adds procurement columns (`lead_time_days`, `reorder_point`, `reorder_qty`)

---

#### `024_sprint3_add_fk_indexes.py`

**Tier**: Core
**Purpose**: Foreign key indexes for query performance

**Creates Indexes on FK columns across all tables**

---

#### `025_add_maintenance_logs_table.py`

**Tier**: Core
**Purpose**: Equipment maintenance tracking

**Creates Table**:

- `maintenance_logs`
  - `resource_id` (FK to resources)
  - `maintenance_type` (preventive, corrective, calibration)
  - `performed_by`, `performed_at`
  - `next_due_date`
  - `notes`

---

#### `026_add_maintenance_tracking_fields.py`

**Tier**: Core
**Purpose**: Additional maintenance fields

**Adds Columns to `resources`**:

- `last_maintenance_date`
- `next_maintenance_date`
- `maintenance_interval_days`

---

#### `027_backfill_po_received_date.py`

**Tier**: Core
**Purpose**: Backfill received_date for existing POs

**Data Migration**: Populates `received_date` from receipt transactions

---

#### `028_add_company_timezone.py`

**Tier**: Core
**Purpose**: Company timezone configuration

**Adds Column to `company_settings`**:

- `timezone` (string, default 'America/New_York')

---

#### `029_add_transaction_date.py`

**Tier**: Core
**Purpose**: Transaction date vs created_at separation

**Adds Column to `inventory_transactions`**:

- `transaction_date` (date) - Business date separate from audit timestamp

---

#### `030_add_event_tables.py`

**Tier**: Core
**Purpose**: Event/webhook logging system

**Creates Tables**:

- `event_log` - General event log
- `webhook_log` - Outbound webhook calls

---

#### `031_add_stocking_policy_to_products.py`

**Tier**: Core
**Purpose**: MRP stocking policy configuration

**Adds Columns to `products`**:

- `stocking_policy` (make_to_order, make_to_stock, phantom)
- `min_order_qty`
- `order_multiple`

---

### Phase 3: Manufacturing Enhancement (032-034)

#### `032_cleanup_machines_table.py`

**Tier**: Core
**Purpose**: Rename machines to printers, cleanup schema

**Changes**:

- Renames `machines` -> `printers`
- Standardizes column naming
- Adds printer-specific columns

---

#### `033_add_operation_materials.py`

**Tier**: Core
**Date**: 2024-12-30
**Purpose**: Operation-level material tracking (Manufacturing BOM)

**Creates Tables**:

- `routing_operation_materials` - Template materials per routing operation
  - `routing_operation_id` (FK)
  - `component_id` (FK to products)
  - `quantity`, `quantity_per` (unit, batch, order)
  - `scrap_factor`
  - `is_cost_only`, `is_optional`

- `production_order_operation_materials` - Actual consumption per PO operation
  - `quantity_required`, `quantity_allocated`, `quantity_consumed`
  - `lot_number`, `inventory_transaction_id`
  - `status` (pending, allocated, consumed, returned)
  - `consumed_at`, `consumed_by`

**Enables**:

- Materials tied to specific operations
- Precise MRP planning (know WHEN material needed)
- Partial release capability

---

#### `034_add_operation_scrap_reason.py`

**Tier**: Core
**Purpose**: Scrap reason tracking for operations

**Adds Columns to `production_order_operations`**:

- `scrap_reason_id` (FK to scrap_reasons)
- `scrap_notes`

---

### Phase 4: Purchasing & UOM (035-040)

#### `035_add_purchase_uom_to_products.py`

**Tier**: Core
**Purpose**: Purchase UOM separate from inventory UOM

**Adds Columns to `products`**:

- `purchase_uom` - Unit for purchasing (e.g., KG)
- `purchase_conversion` - Conversion factor to base unit

---

#### `036_add_po_documents_table.py`

**Tier**: Core
**Purpose**: PO document attachments (invoices, receipts)

**Creates Table**:

- `po_documents`
  - `purchase_order_id` (FK)
  - `document_type` (invoice, receipt, quote, other)
  - `file_name`, `file_path`, `file_size`
  - `uploaded_by`, `uploaded_at`

---

#### `038_add_missing_sales_order_columns.py`

**Tier**: Core
**Purpose**: Sales order enhancement

**Adds Columns to `sales_orders`**:

- `fulfillment_status` - Overall fulfillment state
- `ship_date`, `delivery_date`
- Additional tracking fields

---

#### `039_uom_cost_normalization.py`

**Tier**: Core
**Purpose**: UOM conversion and cost normalization

**Creates Table**:

- `uom_conversions`
  - `from_unit`, `to_unit`
  - `conversion_factor`
  - `is_bidirectional`

**Note**: Critical migration for material costing ($/KG normalization)

---

#### `040_update_material_item_types.py`

**Tier**: Core
**Purpose**: Update item type enumeration for materials

**Changes**:

- Adds `material` to item_type enum
- Backfills existing filament products

---

### Phase 5: Users (043)

#### `043_add_customer_name_fields.py`

**Tier**: Core
**Purpose**: Customer name fields on users

**Adds Columns to `users`**:

- `first_name`, `last_name` (separate from display_name)

---

### Phase 6: Quality & Cleanup (053-057)

#### `053_create_scrap_records_table.py`

**Tier**: Core
**Purpose**: Scrap/defect tracking

**Creates Tables**:

- `scrap_reasons` - Scrap reason codes
  - `code`, `name`, `description`
  - `active`

- `scrap_records` - Scrap event records
  - `production_order_id`, `operation_id`
  - `product_id`, `quantity`
  - `scrap_reason_id`
  - `notes`, `recorded_by`

---

#### `054_add_printer_id_to_operations.py`

**Tier**: Core
**Purpose**: Link operations to printers

**Adds Column to `production_order_operations`**:

- `printer_id` (FK to printers)

---

#### `055_add_product_image_url.py`

**Tier**: Core
**Purpose**: Product image storage

**Adds Column to `products`**:

- `image_url` (string)

---

#### `056_migrate_bom_to_operations.py`

**Tier**: Core
**Purpose**: Migrate BOM lines to operation materials

**Data Migration**: Copies `bom_lines` to `routing_operation_materials`

---

#### `057_seed_scrap_reasons.py`

**Tier**: Core
**Purpose**: Seed default scrap reasons

**Seeds**:

- Defective material
- Print failure
- Dimensional out of spec
- Surface defects
- Operator error
- Equipment malfunction
- Wrong material used
- Customer rejection

---

### Merge Migrations

#### `905ef924f499_merge_sprint1_migrations.py`

**Purpose**: Merge multiple sprint 1 branches

---

### Other Migrations

#### `65be66a7c00f_add_production_order_materials_table.py`

**Purpose**: Production order materials junction table

---

#### `9056086f1897_add_order_type_to_production_order.py`

**Purpose**: Order type for production orders

**Adds Column to `production_orders`**:

- `order_type` (standard, rework, sample)

---

## Migration Dependencies

```
b1815de543ea (001_initial)
    |
baseline_001_stamp_existing
    |
017_add_material_spool_tracking
    |
018-031 (linear chain)
    |
032_cleanup_machines_table
    |
033_add_operation_materials
    |
034-040 (with branches)
    |
905ef924f499 (merge)
    |
043_add_customer_name_fields
    |
053-057 (quality & cleanup)
```

---

## Running Migrations

```bash
# Upgrade to latest
cd backend
alembic upgrade head

# Downgrade one revision
alembic downgrade -1

# Show current revision
alembic current

# Show migration history
alembic history --verbose
```

---

*Last updated: 2026-01-28*
*Generated for FilaOps Core (Open Source)*
