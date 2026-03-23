<!-- AUTO-GENERATED — Do not edit manually. Regenerate: cd backend && python scripts/generate_migrations_log.py -->

# FilaOps Migrations Log

> Chronological record of all database migrations with feature mapping.
> Generated for AI consumption and developer reference.
>
> This document covers **Core (Open Source)** migrations only.

## Overview

| Metric | Count |
| ------ | ----- |
| **Total Migrations** | 50 |
| **Database** | PostgreSQL |
| **Tool** | Alembic |

---

## Migration Categories

### By Feature Area

| Area | Count | Migrations |
|------|-------|------------|
| Initial Schema | 2 | baseline_001, b1815de543ea |
| Manufacturing | 15 | 017, 021, 65be66a7c00f, 022, 023, 032, 033, 034, 9056086f1897, 054, 056, 057, 058, 060, 067 |
| Inventory | 8 | 018, 029, 030, 031, 035, 039, 059, 064 |
| Purchasing | 5 | 019, 027, 028, 036, 2940c6a93ea7 |
| Settings | 3 | 020, 037, 062 |
| Performance | 1 | 905ef924f499 |
| Sales | 5 | 024, 038, 043, 061, 066 |
| Maintenance | 2 | 025, 026 |
| Products | 3 | 040, 055, 065 |
| Accounting | 5 | 044, 045, 046, 052, 053 |
| Tax | 1 | 063 |

---

## Chronological Migration List

### Phase 1: Initial Schema

#### `baseline_001_stamp_existing.py`

**Tier**: Core
**Date**: 2025-12-09
**Purpose**: baseline - stamp existing database

*Baseline stamp — no schema changes.*

---

#### `b1815de543ea_001_initial_postgres_schema.py`

**Tier**: Core
**Date**: 2025-12-21
**Purpose**: Initial postgres schema
**Revises**: baseline_001

**Creates Tables**:

- `colors` - Product color definitions
- `company_settings` - Company configuration
- `inventory_locations` - Warehouse/bin locations
- `item_categories` - Item Categories
- `material_types` - Material Types
- `mrp_runs` - Mrp Runs
- `scrap_reasons` - Scrap reason codes
- `units_of_measure` - Units Of Measure
- `users` - User accounts
- `vendors` - Vendors
- `work_centers` - Manufacturing work centers
- `customer_traceability_profiles` - Customer Traceability Profiles
- `machines` - Machine/equipment records
- `material_colors` - Material Colors
- `password_reset_requests` - Password Reset Requests
- `printers` - Printers
- `products` - Product catalog
- `purchase_orders` - Purchase order headers
- `refresh_tokens` - Refresh Tokens
- `resources` - Resources
- `boms` - Boms
- `inventory` - Inventory levels by location
- `inventory_transactions` - Transaction audit log
- `material_inventory` - Material Inventory
- `material_lots` - Material Lots
- `purchase_order_lines` - Purchase order line items
- `quotes` - Quotes
- `routings` - Routings
- `bom_lines` - Bill of Materials line items
- `quote_files` - Quote Files
- `quote_materials` - Quote Materials
- `routing_operations` - Routing Operations
- `sales_orders` - Sales order headers
- `order_events` - Order Events
- `payments` - Payments
- `sales_order_lines` - Sales order line items
- `production_orders` - Manufacturing work orders
- `planned_orders` - Planned Orders
- `print_jobs` - Print Jobs
- `production_order_operations` - Work order operations
- `serial_numbers` - Serial Numbers
- `production_lot_consumptions` - Production Lot Consumptions

**Creates Indexes**:

- `ix_colors_code`
- `ix_colors_id`
- `ix_inventory_locations_id`
- `ix_item_categories_code`
- `ix_item_categories_id`
- `ix_material_types_base_material`
- `ix_material_types_code`
- `ix_material_types_id`
- `ix_mrp_runs_id`
- `ix_scrap_reasons_code`
- `ix_scrap_reasons_id`
- `ix_units_of_measure_code`
- `ix_units_of_measure_id`
- `ix_users_customer_number`
- `ix_users_email`
- `ix_users_id`
- `ix_users_status`
- `ix_vendors_code`
- `ix_vendors_id`
- `ix_work_centers_code`
- `ix_work_centers_id`
- `ix_customer_traceability_profiles_id`
- `ix_customer_traceability_profiles_user_id`
- `ix_machines_code`
- `ix_machines_id`
- `ix_machines_status`
- `ix_material_colors_id`
- `ix_material_colors_lookup`
- `ix_password_reset_requests_approval_token`
- `ix_password_reset_requests_id`
- `ix_password_reset_requests_status`
- `ix_password_reset_requests_token`
- `ix_password_reset_requests_user_id`
- `ix_printers_brand`
- `ix_printers_code`
- `ix_printers_id`
- `ix_products_id`
- `ix_products_legacy_sku`
- `ix_products_sku`
- `ix_purchase_orders_id`
- `ix_purchase_orders_po_number`
- `ix_refresh_tokens_expires_at`
- `ix_refresh_tokens_id`
- `ix_refresh_tokens_token_hash`
- `ix_refresh_tokens_user_id`
- `ix_resources_code`
- `ix_resources_id`
- `ix_boms_id`
- `ix_inventory_id`
- `ix_inventory_transactions_id`
- `ix_material_inventory_color_id`
- `ix_material_inventory_id`
- `ix_material_inventory_lookup`
- `ix_material_inventory_material_type_id`
- `ix_material_inventory_product_id`
- `ix_material_inventory_sku`
- `ix_material_inventory_stock`
- `ix_lot_expiration`
- `ix_lot_product_status`
- `ix_lot_received_date`
- `ix_material_lots_expiration_date`
- `ix_material_lots_id`
- `ix_material_lots_lot_number`
- `ix_material_lots_product_id`
- `ix_material_lots_status`
- `ix_material_lots_vendor_id`
- `ix_purchase_order_lines_id`
- `ix_quotes_customer_id`
- `ix_quotes_id`
- `ix_quotes_product_id`
- `ix_quotes_quote_number`
- `ix_quotes_status`
- `ix_quotes_user_id`
- `ix_routings_code`
- `ix_routings_id`
- `ix_bom_lines_id`
- `ix_quote_files_file_hash`
- `ix_quote_files_id`
- `ix_quote_files_quote_id`
- `ix_quote_materials_id`
- `ix_quote_materials_quote_id`
- `ix_routing_operations_id`
- `ix_sales_orders_created_at`
- `ix_sales_orders_fulfillment_status`
- `ix_sales_orders_id`
- `ix_sales_orders_mrp_run_id`
- `ix_sales_orders_mrp_status`
- `ix_sales_orders_order_number`
- `ix_sales_orders_order_type`
- `ix_sales_orders_payment_status`
- `ix_sales_orders_product_id`
- `ix_sales_orders_quote_id`
- `ix_sales_orders_source`
- `ix_sales_orders_source_order_id`
- `ix_sales_orders_status`
- `ix_sales_orders_user_id`
- `ix_order_events_created_at`
- `ix_order_events_event_type`
- `ix_order_events_id`
- `ix_order_events_sales_order_id`
- `ix_order_events_user_id`
- `ix_payments_id`
- `ix_payments_payment_date`
- `ix_payments_payment_number`
- `ix_payments_recorded_by_id`
- `ix_payments_sales_order_id`
- `ix_payments_status`
- `ix_sales_order_lines_id`
- `ix_sales_order_lines_product_id`
- `ix_sales_order_lines_sales_order_id`
- `ix_production_orders_code`
- `ix_production_orders_due_date`
- `ix_production_orders_id`
- `ix_production_orders_parent_order_id`
- `ix_production_orders_status`
- `ix_planned_orders_id`
- `ix_print_jobs_id`
- `ix_production_order_operations_id`
- `ix_production_order_operations_status`
- `ix_serial_manufactured_date`
- `ix_serial_numbers_id`
- `ix_serial_numbers_product_id`
- `ix_serial_numbers_production_order_id`
- `ix_serial_numbers_sales_order_id`
- `ix_serial_numbers_serial_number`
- `ix_serial_numbers_status`
- `ix_serial_product_status`
- `ix_consumption_lot_production`
- `ix_production_lot_consumptions_id`
- `ix_production_lot_consumptions_material_lot_id`
- `ix_production_lot_consumptions_production_order_id`
- `ix_production_lot_consumptions_serial_number_id`

---

### Phase 2: Core Features (017-031)

#### `017_add_material_spool_tracking.py`

**Tier**: Core
**Date**: 2025-12-22
**Purpose**: Add material spool tracking tables
**Revises**: b1815de543ea

**Creates Tables**:

- `material_spools` - Individual spool records with weight tracking
- `production_order_spools` - Production Order Spools

**Creates Indexes**:

- `ix_material_spools_spool_number`
- `ix_material_spools_product_id`
- `ix_material_spools_status`
- `ix_production_order_spools_production_order_id`
- `ix_production_order_spools_spool_id`

---

#### `018_add_negative_inventory_approval_columns.py`

**Tier**: Core
**Date**: 2025-12-22
**Purpose**: Add negative inventory approval columns to inventory_transactions
**Revises**: 017

**Adds Columns**:

- `inventory_transactions.requires_approval`
- `inventory_transactions.approval_reason`
- `inventory_transactions.approved_by`
- `inventory_transactions.approved_at`

---

#### `019_add_purchase_unit_to_po_lines.py`

**Tier**: Core
**Date**: 2025-12-22
**Purpose**: Add purchase_unit to purchase_order_lines
**Revises**: 018

**Adds Columns**:

- `purchase_order_lines.purchase_unit`

---

#### `020_add_business_hours_to_company_settings.py`

**Tier**: Core
**Date**: 2025-12-22
**Purpose**: Add business hours to company settings
**Revises**: 019

**Adds Columns**:

- `company_settings.business_hours_start`
- `company_settings.business_hours_end`
- `company_settings.business_days_per_week`
- `company_settings.business_work_days`

---

#### `021_add_performance_indexes.py`

**Tier**: Core
**Date**: 2025-12-23
**Purpose**: add performance indexes for common queries
**Revises**: 020

**Creates Indexes**:

- `ix_sales_orders_status_created_at`
- `ix_sales_orders_payment_status_paid_at`
- `ix_inventory_product_location`
- `ix_production_orders_status_created_at`
- `ix_sales_order_lines_order_product`
- `ix_bom_lines_bom_component`
- `ix_products_active_type_procurement`
- `ix_inventory_transactions_product_created`

---

#### `65be66a7c00f_add_production_order_materials_table.py`

**Tier**: Core
**Date**: 2025-12-22
**Purpose**: Add production order materials table
**Revises**: 020

**Creates Tables**:

- `production_order_materials` - Production order material tracking

**Creates Indexes**:

- `idx_po_materials_production_order`
- `idx_po_materials_original_product`
- `idx_po_materials_substitute_product`

---

#### `905ef924f499_merge_sprint1_migrations.py`

**Tier**: Core
**Date**: 2025-12-23
**Purpose**: Merge sprint1 migrations
**Revises**: 021_add_performance_indexes, 65be66a7c00f
**Type**: Merge migration

*Merge migration — no schema changes.*

---

#### `022_sprint3_cleanup_work_center.py`

**Tier**: Core
**Date**: 2025-12-23
**Purpose**: Sprint 3-4: Remove duplicate active column from work_centers
**Revises**: 905ef924f499

**Drops Columns**:

- `work_centers.active`

---

#### `023_sprint3_cleanup_product.py`

**Tier**: Core
**Date**: 2025-12-23
**Purpose**: Sprint 3-4: Remove legacy fields from products table
**Revises**: 022_sprint3_cleanup_work_center

---

#### `024_sprint3_add_fk_indexes.py`

**Tier**: Core
**Date**: 2025-12-23
**Purpose**: Sprint 3-4: Add missing indexes on foreign key columns
**Revises**: 023_sprint3_cleanup_product

---

#### `025_add_maintenance_logs_table.py`

**Tier**: Core
**Date**: 2025-12-24
**Purpose**: Add maintenance logs table
**Revises**: 024_sprint3_add_fk_indexes

**Creates Tables**:

- `maintenance_logs` - Equipment maintenance records

**Creates Indexes**:

- `ix_maintenance_logs_printer_id`
- `ix_maintenance_logs_maintenance_type`
- `ix_maintenance_logs_performed_at`
- `ix_maintenance_logs_next_due_at`

---

#### `026_add_maintenance_tracking_fields.py`

**Tier**: Core
**Date**: 2024-12-24
**Purpose**: Add downtime and parts tracking to maintenance logs
**Revises**: 025_add_maintenance_logs_table

**Adds Columns**:

- `maintenance_logs.downtime_minutes`
- `maintenance_logs.parts_used`

---

#### `027_backfill_po_received_date.py`

**Tier**: Core
**Date**: 2025-12-24
**Purpose**: Backfill received_date for POs with status=received but no date
**Revises**: 026_maintenance_tracking

---

#### `028_add_company_timezone.py`

**Tier**: Core
**Date**: 2025-12-24
**Purpose**: Add timezone column to company_settings
**Revises**: 027_backfill_po_received_date

**Adds Columns**:

- `company_settings.timezone`

---

#### `029_add_transaction_date.py`

**Tier**: Core
**Date**: 2025-12-24
**Purpose**: Add transaction_date column to inventory_transactions
**Revises**: 028_add_company_timezone

**Adds Columns**:

- `inventory_transactions.transaction_date`

**Creates Indexes**:

- `ix_inventory_transactions_transaction_date`

---

#### `030_add_event_tables.py`

**Tier**: Core
**Date**: 2025-12-24
**Purpose**: Add PurchasingEvent and ShippingEvent tables
**Revises**: 029_add_transaction_date

**Creates Tables**:

- `purchasing_events` - Purchasing Events
- `shipping_events` - Shipping Events

**Creates Indexes**:

- `ix_purchasing_events_id`
- `ix_purchasing_events_purchase_order_id`
- `ix_purchasing_events_user_id`
- `ix_purchasing_events_event_type`
- `ix_purchasing_events_event_date`
- `ix_purchasing_events_created_at`
- `ix_shipping_events_id`
- `ix_shipping_events_sales_order_id`
- `ix_shipping_events_user_id`
- `ix_shipping_events_event_type`
- `ix_shipping_events_tracking_number`
- `ix_shipping_events_event_date`
- `ix_shipping_events_created_at`

---

#### `031_add_stocking_policy_to_products.py`

**Tier**: Core
**Date**: 2025-01-01
**Purpose**: Add stocking_policy column to products table
**Revises**: 030_add_event_tables

**Adds Columns**:

- `products.stocking_policy`

**Creates Indexes**:

- `ix_products_stocking_policy`

---

### Phase 3: Cleanup & MRP (032-040)

#### `032_cleanup_machines_table.py`

**Tier**: Core
**Date**: Initial
**Purpose**: 032: Cleanup machines table and consolidate to resources
**Revises**: 031_add_stocking_policy

**Adds Columns**:

- `resources.printer_class`

**Creates Foreign Keys**:

- `fk_poo_resource_id`

**Drops Tables**:

- `machines`

---

#### `033_add_operation_materials.py`

**Tier**: Core
**Date**: Initial
**Purpose**: 033: Add operation-level material tables for Manufacturing BOM
**Revises**: 032_cleanup_machines_table

**Creates Tables**:

- `routing_operation_materials` - Materials consumed per routing operation
- `production_order_operation_materials` - Production Order Operation Materials

---

#### `034_add_operation_scrap_reason.py`

**Tier**: Core
**Date**: 2026-01-01
**Purpose**: Add scrap_reason column to production_order_operations
**Revises**: 033_add_operation_materials

**Adds Columns**:

- `production_order_operations.scrap_reason`

---

#### `035_add_purchase_uom_to_products.py`

**Tier**: Core
**Date**: 2025-01-02
**Purpose**: Add purchase_uom to products table for proper cost conversion
**Revises**: 034_add_operation_scrap_reason

**Adds Columns**:

- `products.purchase_uom`

---

#### `036_add_po_documents_table.py`

**Tier**: Core
**Date**: 2025-01-03
**Purpose**: Add purchase_order_documents table for multi-file storage
**Revises**: 035_add_purchase_uom

**Creates Tables**:

- `purchase_order_documents` - Purchase Order Documents
- `vendor_items` - Vendor Items

**Creates Indexes**:

- `ix_po_documents_po_id`
- `ix_po_documents_type`
- `ix_vendor_items_vendor_id`
- `ix_vendor_items_product_id`

---

#### `2940c6a93ea7_add_ai_configuration_columns.py`

**Tier**: Core
**Date**: 2026-01-04
**Purpose**: Add ai configuration columns
**Revises**: 036_add_po_documents

**Adds Columns**:

- `company_settings.ai_provider`
- `company_settings.ai_api_key`
- `company_settings.ai_ollama_url`
- `company_settings.ai_ollama_model`
- `company_settings.external_ai_blocked`

---

#### `037_add_anthropic_model_selection.py`

**Tier**: Core
**Date**: 2026-01-05
**Purpose**: Add anthropic model selection
**Revises**: 2940c6a93ea7

**Adds Columns**:

- `company_settings.ai_anthropic_model`

---

#### `038_add_missing_sales_order_columns.py`

**Tier**: Core
**Date**: 2026-01-07
**Purpose**: Add missing sales order columns
**Revises**: 037_add_anthropic_model

**Adds Columns**:

- `sales_orders.color`
- `sales_orders.customer_id`
- `sales_orders.customer_name`
- `sales_orders.customer_email`
- `sales_orders.customer_phone`

**Creates Indexes**:

- `ix_sales_orders_customer_id`

**Creates Foreign Keys**:

- `fk_sales_orders_customer_id_users`

---

#### `039_uom_cost_normalization.py`

**Tier**: Core
**Date**: 2025-01-08
**Purpose**: UOM Cost Normalization - Single Source of Truth for Transactions
**Revises**: 038_add_missing_so_cols

**Adds Columns**:

- `products.purchase_factor`
- `inventory_transactions.total_cost`
- `inventory_transactions.unit`

**Creates Indexes**:

- `ix_inventory_transactions_unit`

---

#### `040_update_material_item_types.py`

**Tier**: Core
**Date**: 2026-01-08
**Purpose**: Update material item_types - Migrate supply filaments to material type
**Revises**: 039_uom_cost_normalization

---

### Phase 4: Accounting & Customers (043-057)

#### `043_add_customer_name_fields.py`

**Tier**: Core
**Date**: 2026-01-10
**Purpose**: Create customers table with name fields
**Revises**: 040_update_material_item_types

**Creates Tables**:

- `customers` - Customer records

**Adds Columns**:

- `users.customer_id`

**Creates Indexes**:

- `ix_customers_id`
- `ix_customers_customer_number`
- `ix_customers_company_name`
- `ix_customers_email`
- `ix_customers_status`
- `ix_users_customer_id`

**Creates Foreign Keys**:

- `fk_users_customer_id`

---

#### `044_add_accounting_module_tables.py`

**Tier**: Core
**Date**: 2026-01-16
**Purpose**: Add accounting module tables (GL)
**Revises**: 043_add_customer_name_fields

**Creates Tables**:

- `gl_accounts` - Chart of Accounts
- `gl_fiscal_periods` - Fiscal period tracking
- `gl_journal_entries` - Journal entry headers
- `gl_journal_entry_lines` - Journal entry debit/credit lines

**Creates Indexes**:

- `ix_gl_accounts_account_type`
- `ix_gl_accounts_schedule_c_line`
- `ix_gl_accounts_active`
- `ix_gl_fiscal_periods_year`
- `ix_gl_fiscal_periods_status`
- `ix_gl_journal_entries_entry_date`
- `ix_gl_journal_entries_source`
- `ix_gl_journal_entries_status`
- `ix_gl_journal_entry_lines_entry_id`
- `ix_gl_journal_entry_lines_account_id`

---

#### `045_seed_default_chart_of_accounts.py`

**Tier**: Core
**Date**: 2026-01-16
**Purpose**: Seed default chart of accounts
**Revises**: 044_gl_tables

---

#### `046_add_business_type_to_company_settings.py`

**Tier**: Core
**Date**: 2026-01-16
**Purpose**: Add business_type column to company_settings
**Revises**: 045_seed_coa

**Adds Columns**:

- `company_settings.business_type`

---

#### `9056086f1897_add_order_type_to_production_order.py`

**Tier**: Core
**Date**: 2026-01-20
**Purpose**: Add order type to production order
**Revises**: 046_add_business_type

**Adds Columns**:

- `production_orders.order_type`

---

#### `052_add_inventory_accounts_and_je_link.py`

**Tier**: Core
**Date**: 2026-01-20
**Purpose**: Add inventory sub-accounts and journal_entry_id link
**Revises**: 9056086f1897

**Adds Columns**:

- `inventory_transactions.journal_entry_id`

**Creates Indexes**:

- `ix_inventory_transactions_journal_entry_id`

**Creates Foreign Keys**:

- `fk_inventory_transactions_journal_entry`

---

#### `053_create_scrap_records_table.py`

**Tier**: Core
**Date**: 2026-01-20
**Purpose**: Create scrap_records table
**Revises**: 052_inv_accounts_je_link

**Creates Tables**:

- `scrap_records` - Scrap/waste tracking records

**Creates Indexes**:

- `ix_scrap_records_created_at`
- `ix_scrap_records_scrap_reason_id`

---

#### `054_add_printer_id_to_operations.py`

**Tier**: Core
**Date**: 2026-01-20
**Purpose**: Add printer_id column to production_order_operations
**Revises**: 053_scrap_records

**Adds Columns**:

- `production_order_operations.printer_id`

**Creates Indexes**:

- `ix_production_order_operations_printer_id`

**Creates Foreign Keys**:

- `fk_production_order_operations_printer_id`

---

#### `055_add_product_image_url.py`

**Tier**: Core
**Date**: 2026-01-20
**Purpose**: Add image_url column to products
**Revises**: 054_add_printer_id

**Adds Columns**:

- `products.image_url`

---

#### `056_migrate_bom_to_operations.py`

**Tier**: Core
**Date**: 2025-01-21
**Purpose**: Migrate BOM lines to routing operation materials.
**Revises**: 055_add_product_image_url

---

#### `057_seed_scrap_reasons.py`

**Tier**: Core
**Date**: 2025-01-21
**Purpose**: Seed default scrap reasons for production operations.
**Revises**: 056_migrate_bom

---

### Phase 5: Adjustments & Precision (058-066)

#### `058_create_adjustment_reasons.py`

**Tier**: Core
**Date**: 2026-02-08
**Purpose**: Create adjustment_reasons table and seed default data.
**Revises**: 057_seed_scrap_reasons

---

#### `059_add_reason_code_to_transactions.py`

**Tier**: Core
**Date**: 2026-02-08
**Purpose**: Add reason_code column to inventory_transactions.
**Revises**: 058_adjustment_reasons

---

#### `060_add_missing_fk_indexes.py`

**Tier**: Core
**Date**: Initial
**Purpose**: Add missing foreign key indexes for query performance.
**Revises**: 059_reason_code

**Creates Indexes**:

- `ix_purchase_orders_vendor_id`
- `ix_purchase_order_lines_purchase_order_id`
- `ix_purchase_order_lines_product_id`
- `ix_resources_work_center_id`
- `ix_routing_operations_routing_id`
- `ix_routing_operations_work_center_id`

---

#### `061_fix_product_customer_fk.py`

**Tier**: Core
**Date**: Initial
**Purpose**: Fix product.customer_id FK to reference customers table instead of users.
**Revises**: 060

**Creates Foreign Keys**:

- `fk_products_customer`

---

#### `062_add_locale_to_company_settings.py`

**Tier**: Core
**Date**: Initial
**Purpose**: Add locale column for i18n support.
**Revises**: 061

**Adds Columns**:

- `company_settings.locale`

---

#### `063_create_tax_rates_table.py`

**Tier**: Core
**Date**: Initial
**Purpose**: Create tax_rates table and add tax_name to transactional tables.
**Revises**: 062

**Creates Tables**:

- `tax_rates` - Tax rate definitions

**Adds Columns**:

- `quotes.tax_name`
- `sales_orders.tax_name`
- `sales_order_lines.tax_name`

**Creates Indexes**:

- `ix_tax_rates_id`
- `ix_tax_rates_is_default`

---

#### `064_add_material_inventory_to_sales_order_lines.py`

**Tier**: Core
**Date**: Initial
**Purpose**: Add material_inventory_id to sales_order_lines.
**Revises**: 063

**Adds Columns**:

- `sales_order_lines.material_inventory_id`

**Alters Columns**:

- `sales_order_lines.product_id`

**Creates Indexes**:

- `ix_sales_order_lines_material_inventory_id`

**Creates Foreign Keys**:

- `fk_sol_material_inventory`

---

#### `065_increase_cost_column_precision.py`

**Tier**: Core
**Date**: Initial
**Purpose**: Increase cost column precision from Numeric(10,2) to Numeric(18,4).
**Revises**: 064

---

#### `066_add_default_margin_to_company_settings.py`

**Tier**: Core
**Date**: Initial
**Purpose**: Add default_margin_percent to company_settings.
**Revises**: 065

**Adds Columns**:

- `company_settings.default_margin_percent`

---

#### `067_add_variant_matrix.py`

**Tier**: Core
**Date**: Initial
**Purpose**: Add variant matrix support to products and routing_operation_materials.
**Revises**: 066

**Adds Columns**:

- `products.parent_product_id`
- `products.is_template`
- `products.variant_metadata`
- `routing_operation_materials.is_variable`

**Creates Indexes**:

- `ix_products_parent_product_id`

---

## Migration Dependencies

```text
baseline_001
    |
b1815de543ea (001_initial_postgres_schema)
    |
017_add_material_spool_tracking
    |
018_add_negative_inventory_approval_columns
    |
019_add_purchase_unit_to_po_lines
    |
020_add_business_hours_to_company_settings
    |
021_add_performance_indexes
    |
65be66a7c00f (add_production_order_materials_table)
  021_add_performance_indexes, 65be66a7c00f
    \ /
     905ef924f499 (merge_sprint1_migrations)  [merge]
    |
022_sprint3_cleanup_work_center
    |
023_sprint3_cleanup_product
    |
024_sprint3_add_fk_indexes
    |
025_add_maintenance_logs_table
    |
026_add_maintenance_tracking_fields
    |
027_backfill_po_received_date
    |
028_add_company_timezone
    |
029_add_transaction_date
    |
030_add_event_tables
    |
031_add_stocking_policy_to_products
    |
032_cleanup_machines_table
    |
033_add_operation_materials
    |
034_add_operation_scrap_reason
    |
035_add_purchase_uom_to_products
    |
036_add_po_documents_table
    |
2940c6a93ea7 (add_ai_configuration_columns)
    |
037_add_anthropic_model_selection
    |
038_add_missing_sales_order_columns
    |
039_uom_cost_normalization
    |
040_update_material_item_types
    |
043_add_customer_name_fields
    |
044_add_accounting_module_tables
    |
045_seed_default_chart_of_accounts
    |
046_add_business_type_to_company_settings
    |
9056086f1897 (add_order_type_to_production_order)
    |
052_add_inventory_accounts_and_je_link
    |
053_create_scrap_records_table
    |
054_add_printer_id_to_operations
    |
055_add_product_image_url
    |
056_migrate_bom_to_operations
    |
057_seed_scrap_reasons
    |
058_create_adjustment_reasons
    |
059_add_reason_code_to_transactions
    |
060_add_missing_fk_indexes
    |
061_fix_product_customer_fk
    |
062_add_locale_to_company_settings
    |
063_create_tax_rates_table
    |
064_add_material_inventory_to_sales_order_lines
    |
065_increase_cost_column_precision
    |
066_add_default_margin_to_company_settings
    |
067_add_variant_matrix
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

*Last updated: 2026-03-22*
*Generated for FilaOps Core v3.5.0*
