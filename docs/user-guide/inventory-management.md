# Inventory Management Guide

This guide covers FilaOps' inventory management system, including stock tracking, adjustments, spool management, and the unique unit of measure (UOM) system for 3D printing materials.

## Overview

FilaOps tracks inventory for all physical items:

- **Filament / Materials** - Raw materials consumed in production (PLA, PETG, ABS, TPU, etc.)
- **Finished Goods** - Products you sell to customers
- **Components** - Parts used in assemblies (hardware, inserts, etc.)
- **Supplies** - Consumables (packaging, labels, etc.)

**Key Features:**
- ✅ Multi-location inventory tracking
- ✅ Unit of measure conversions (grams ↔ kilograms)
- ✅ Material spool tracking with weight management
- ✅ Cycle counting and physical inventory adjustments
- ✅ Automatic transactions from production and shipping
- ✅ Reorder points and safety stock
- ✅ Cost tracking (FIFO, average, standard)

---

## Part 1: Items (Products)

### What is an Item?

An **Item** (also called **Product**) represents anything tracked in inventory. Each item has:

- **SKU** (Stock Keeping Unit) - Unique identifier (e.g., `MAT-PLA-BASIC-BLK`)
- **Name** - Human-readable description
- **Category** - Organizational grouping (FILAMENT > PLA)
- **Item Type** - Classification (finished_good, component, supply, service)
- **Unit** - Storage/consumption unit (G for filament, EA for hardware)

### Item Types

| Type | Description | Examples |
|------|-------------|----------|
| **finished_good** | Products sold to customers | Phone Stand, Custom Bracket |
| **component** | Parts used in BOMs | M3 Inserts, Magnets, Screws |
| **supply** | Consumables not sold | Poly Bags, Shipping Boxes |
| **service** | Non-physical items | Machine Time, Labor |

### Creating Items

**Navigation:** Items → Products → **+ New Item**

**Step 1: Basic Information**

```
SKU: BRACKET-001 (auto-generated or manual)
Name: Desk Mounting Bracket
Description: "Adjustable bracket for monitor arms"

Item Type: finished_good
Procurement Type: make (options: make, buy, make_or_buy)
Category: FINISHED_GOODS > Standard Products

Active: ✓ (items can be deactivated without deletion)
```

**Step 2: Unit of Measure**

**For Standard Items (Hardware, Finished Goods):**
```
Unit: EA (each)
Purchase UOM: EA
Purchase Factor: 1
```

**For Materials (Filament):**
```
Unit: G (grams - storage/consumption)
Purchase UOM: KG (kilograms - how vendors sell)
Purchase Factor: 1000 (1 KG = 1000 G)
```

**⚠️ Critical: Material UOM System**

FilaOps uses a dual-unit system for materials:
- **Storage/Consumption:** Grams (G) for precision
- **Purchasing:** Kilograms (KG) for vendor pricing
- **Cost Basis:** $/KG (standard market pricing)

**Why this matters:**
- Inventory shows: 500 G on hand
- Purchase order shows: Buy 3 KG @ $25/KG
- Inventory transaction records: +3000 G @ $0.025/G = $75 total

**See:** [UOM System Deep Dive](#part-7-unit-of-measure-uom-system) below

**Step 3: Costs**

```
Cost Method: average (options: standard, average, fifo, last)

Standard Cost: $5.00 (fixed cost for manufactured items)
Average Cost: $4.85 (running average - system calculated)
Last Cost: $4.75 (most recent purchase)
Selling Price: $15.00 (customer price)
```

**Cost Methods:**
- **standard** - Fixed cost (for manufactured items with set costs)
- **average** - Weighted average (default, for purchased items)
- **fifo** - First in, first out (uses last_cost as approximation)
- **last** - Most recent purchase price

**Step 4: Inventory Settings**

```
Stocking Policy: on_demand (options: stocked, on_demand)
  - stocked: Keep minimum on hand, reorder proactively
  - on_demand: Only order when MRP shows demand

Reorder Point: 100 (when to trigger PO)
Safety Stock: 50 (buffer for demand variability)
Lead Time (days): 7 (supplier delivery time)

Min Order Qty: 10 (minimum purchase quantity)
Preferred Vendor: (select from dropdown)
```

**Step 5: Physical Properties** (optional)

```
Weight (oz): 2.5
Length (in): 4.0
Width (in): 2.0
Height (in): 1.0

UPC: 123456789012 (barcode)
```

**Step 6: Save**

Click **Create Item** → Item is saved and ready for inventory tracking

### Item Categories

**Hierarchical structure** for organization:

```
FILAMENT
  ├── PLA
  ├── PETG
  ├── ABS
  └── TPU

PACKAGING
  ├── Boxes
  └── Bags

HARDWARE
  ├── Fasteners
  └── Inserts

FINISHED_GOODS
  ├── Standard Products
  └── Custom Products
```

**Creating Categories:**

**Navigation:** Items → Categories → **+ New Category**

```
Code: PLA (unique identifier)
Name: PLA Filament
Parent: FILAMENT (optional - for subcategories)
Sort Order: 10 (display order)
Active: ✓
```

---

## Part 2: Inventory Locations

### What is a Location?

A **Location** is a physical or logical place where inventory is stored:

- Warehouse A
- Shelf B3
- Bin 5
- Main Production Floor
- Shipping Dock

**Locations enable:**
- Multi-site inventory tracking
- Warehouse management
- Transfer tracking between locations
- Location-specific cycle counts

### Creating Locations

**Navigation:** Settings → Locations → **+ New Location**

```
Code: WH-A-B3-05 (unique identifier)
Name: Warehouse A - Shelf B3 - Bin 5
Type: bin (options: warehouse, shelf, bin, zone, floor)

Parent Location: WH-A-B3 (hierarchical)
Active: ✓
```

**Example Hierarchy:**
```
Warehouse A (WH-A)
  ├── Shelf B1 (WH-A-B1)
  │   ├── Bin 01 (WH-A-B1-01)
  │   └── Bin 02 (WH-A-B1-02)
  └── Shelf B2 (WH-A-B2)
      ├── Bin 01 (WH-A-B2-01)
      └── Bin 02 (WH-A-B2-02)
```

### Default Location

When first setting up FilaOps:
1. One default location is created (e.g., "Main Warehouse")
2. All inventory defaults to this location
3. You can create additional locations as needed

---

## Part 3: Stock Levels

### Viewing Inventory

**Navigation:** Items → Inventory

**Columns:**
- **SKU** - Item identifier
- **Name** - Item description
- **Category** - Category path
- **Location** - Storage location
- **On Hand** - Physical quantity in stock
- **Allocated** - Quantity reserved for orders
- **Available** - On Hand - Allocated = Available for new orders
- **Unit** - Storage unit (G, EA, etc.)
- **Value** - Inventory value ($)

**Example:**
```
SKU: MAT-PLA-BASIC-BLK
Name: PLA Basic - Black
Location: Main Warehouse
On Hand: 5,000 G
Allocated: 450 G (reserved for active production orders)
Available: 4,550 G
Unit: G
Value: $125.00 (5000 G × $0.025/G)
```

### Understanding Quantities

**On Hand Quantity:**
- Physical stock in location
- Includes allocated items (they're still physically present)

**Allocated Quantity:**
- Reserved for production orders
- Cannot be used for new orders until released
- Automatically allocated when production order created
- Automatically released when production completed or cancelled

**Available Quantity:**
- Available = On Hand - Allocated
- What MRP sees as "available for new orders"
- Computed field (not stored, calculated on-the-fly)

**Example Flow:**
```
Starting: 1000 G on hand, 0 allocated, 1000 available

Create Production Order for 200 G:
  → 1000 G on hand, 200 G allocated, 800 G available

Complete Production Order:
  → 800 G on hand, 0 allocated, 800 G available
  (200 G consumed, allocation released)
```

---

## Part 4: Inventory Transactions

### What is a Transaction?

An **Inventory Transaction** records every inventory movement:

- **Receipt** - Receiving inventory from vendor
- **Issue** - Removing inventory (non-production)
- **Consumption** - Used in manufacturing
- **Adjustment** - Correcting discrepancies
- **Transfer** - Moving between locations
- **Reservation** - Allocating for production
- **Scrap** - Damaged/waste material

**All transactions are immutable** - once created, they cannot be edited (only reversed with a new transaction).

### Transaction Types

| Type | Direction | Use Case | Example |
|------|-----------|----------|---------|
| **receipt** | + | Receiving from vendor | PO received |
| **issue** | - | Non-production removal | Sample given away |
| **consumption** | - | Manufacturing usage | Filament used in print |
| **adjustment** | ± | Cycle count correction | Physical count shows 980 G vs 1000 G |
| **transfer** | ± | Moving between locations | WH-A → WH-B |
| **reservation** | (allocate) | Reserve for production | PO created |
| **scrap** | - | Damaged/waste | Failed print scrap |
| **shipment** | - | Customer shipment | SO shipped |

### Viewing Transaction History

**Navigation:** Items → Inventory → Select item → **Transaction History**

**Columns:**
- **Date** - When transaction occurred
- **Type** - Transaction type
- **Quantity** - Amount (+ or -)
- **Unit** - Unit of measure
- **Cost** - Cost per unit
- **Total Cost** - Quantity × Cost
- **Location** - Storage location
- **Reference** - Order/PO number
- **Notes** - Description

**Example History:**
```
Date       Type        Qty      Unit  Cost/Unit  Total   Reference    Notes
---------- ----------- -------- ----- ---------- ------- ------------ -----
2026-02-05 receipt     +3000 G  G     $0.025     $75.00  PO-2026-010  Received from Vendor A
2026-02-06 consumption -450 G   G     $0.025     $11.25  PO-2026-005  Production Order
2026-02-07 adjustment  -50 G    G     $0.025     $1.25   ADJ-001      Cycle count correction
```

---

## Part 5: Manual Inventory Adjustments

### When to Adjust Inventory

**Common scenarios:**
- 🔢 **Cycle counting** - Physical count differs from system
- 📦 **Lost/damaged inventory** - Items broken or misplaced
- 🔄 **Opening balances** - Setting up initial inventory
- ✏️ **Data entry errors** - Correcting past mistakes

### Creating Adjustments

**Navigation:** Items → Inventory → **Adjust Inventory**

**Method 1: Single Item Adjustment**

```
Select Item: MAT-PLA-BASIC-BLK
Location: Main Warehouse

Current Quantity: 5,000 G
New Quantity: 4,950 G (physical count)

Reason: Cycle count adjustment
Notes: "Physical count on 2026-02-07"

Cost per Unit: $0.025/G (auto-filled from item cost)
```

Click **Submit** → Transaction created:
- Type: `adjustment`
- Quantity: -50 G (difference)
- Total Cost: -$1.25 (inventory value reduction)

**Method 2: Batch Adjustment (Cycle Counting)**

For counting multiple items at once:

**Navigation:** Items → Inventory → **Batch Adjust**

Upload CSV or enter data:
```csv
sku,location_code,physical_count
MAT-PLA-BASIC-BLK,WH-A,4950
MAT-PETG-HF-WHT,WH-A,3200
BRACKET-001,WH-A,45
```

System compares to current quantities and creates adjustment transactions for all differences.

### Negative Inventory

**FilaOps allows negative inventory with approval:**

When a transaction would cause negative stock:
- Transaction flagged with `requires_approval: true`
- Reason required: "Emergency production order - PO on the way"
- Admin must approve
- Transaction recorded as `negative_adjustment` type

**View pending approvals:** Items → Inventory → **Pending Adjustments**

---

## Part 6: Material Spool Tracking

### What is a Spool?

A **Material Spool** represents a physical roll of filament with:

- **Spool Number** - Unique ID (e.g., `SPOOL-PLA-BLK-001`)
- **Material** - Link to material product (SKU)
- **Weight Tracking** - Initial weight → Current weight
- **Status** - active, empty, expired, damaged
- **Lot Number** - Vendor's lot/batch (for traceability)
- **Location** - Where stored

**Why track spools?**
- ✅ **Traceability** - Know which spool used in which order
- ✅ **Weight management** - Track remaining material accurately
- ✅ **Shelf life** - Monitor expiration dates (TPU, Nylon)
- ✅ **Quality control** - Identify problematic batches

### Creating Spools

**Navigation:** Items → Spools → **+ New Spool**

**When receiving filament:**

```
Spool Number: SPOOL-PLA-BLK-001 (auto-generated)
Material: MAT-PLA-BASIC-BLK

Initial Weight: 1.000 kg (full roll)
Current Weight: 1.000 kg (same at creation)

Status: active
Received Date: 2026-02-05
Expiry Date: (optional - for hygroscopic materials)

Location: WH-A-B1-03
Supplier Lot Number: LOT-2026-0205 (vendor's batch)

Notes: "Arrived sealed, good condition"
```

**Result:**
- Spool created and tracked
- Links to material SKU for cost/properties
- Available for production order assignment

### Spool Consumption Tracking

**During Production:**

When a production order uses material:
1. Assign spool to production order
2. Record weight consumed (e.g., 450 G)
3. Update spool current weight:
   - Initial: 1000 G
   - Consumed: 450 G
   - Current: 550 G (1000 - 450)
4. Link spool to production order for traceability

**Low Spool Alert:**
- When spool < 10% remaining → Status shows "Low"
- When spool < 50 G → Automatically marked "empty"

**View Spool History:**

**Navigation:** Items → Spools → Select spool → **History**

Shows all production orders that used this spool:
```
PO-2026-005 → 450 G consumed → Customer Order SO-2026-042
PO-2026-008 → 320 G consumed → Customer Order SO-2026-044
PO-2026-012 → 180 G consumed → Customer Order SO-2026-051
```

**Result:** Full traceability from raw material spool → production order → sales order → customer

---

## Part 7: Unit of Measure (UOM) System

### The Dual-Unit Challenge

**Problem:** Vendors sell filament in **kilograms**, but production consumes in **grams**.

**FilaOps Solution:** Dual-unit system with automatic conversion.

### How It Works

**Material Product Setup:**
```
Product: MAT-PLA-BASIC-BLK
  unit: G (grams - storage/consumption)
  purchase_uom: KG (kilograms - purchasing)
  purchase_factor: 1000 (1 KG = 1000 G)
  standard_cost: $25.00 (per KG)
```

**Purchase Order:**
```
PO Line: 3 KG @ $25/KG = $75.00
```

**Inventory Transaction (Receipt):**
```
Quantity: 3000 G (converted from 3 KG × 1000)
Cost per Unit: $0.025/G (converted from $25/KG ÷ 1000)
Total Cost: $75.00 (3000 G × $0.025/G)
Unit: G (stored for display)
```

**Inventory Display:**
```
On Hand: 3000 G
Value: $75.00 (3000 G × $0.025/G)
```

**Production Consumption:**
```
BOM requires: 450 G
Transaction: -450 G @ $0.025/G = $11.25 COGS
```

### Cost Storage Rule

**⚠️ CRITICAL: Costs are stored as $/KG (purchase UOM), not $/G**

**Product.standard_cost:** $25.00 (per KG)
**Product.average_cost:** $24.50 (per KG)
**Product.last_cost:** $24.75 (per KG)

**When calculating inventory value:**
```
Inventory Value = Quantity (G) × (Cost per KG ÷ 1000)
                = 3000 G × ($25/KG ÷ 1000)
                = 3000 × $0.025
                = $75.00
```

**System handles this automatically** - you never manually calculate.

### UOM for Non-Material Items

**Standard Items (Hardware, Finished Goods):**
```
unit: EA
purchase_uom: EA
purchase_factor: 1
```

**No conversion needed** - simple 1:1 relationship.

### UOM Best Practices

✅ **Do:**
- Let the system handle all UOM conversions
- Enter purchase orders in vendor's units (KG)
- Trust inventory displays in storage units (G)
- Use spool tracking for accurate weight management

❌ **Don't:**
- Manually convert units (system does this)
- Change purchase_factor after transactions exist
- Mix units within same material (always G/KG/1000)

---

## Part 8: Cycle Counting

### What is Cycle Counting?

**Cycle counting** is a periodic physical inventory check:
- Count subset of inventory regularly (daily/weekly)
- Compare physical count to system quantity
- Adjust discrepancies immediately
- Rotate through all items over time

**Benefits:**
- ✅ Maintain inventory accuracy without full shutdowns
- ✅ Identify shrinkage/theft
- ✅ Catch data entry errors early
- ✅ Improve trust in system data

### Cycle Count Workflow

**Step 1: Generate Count Sheet**

**Navigation:** Items → Inventory → **Cycle Count**

Select items to count:
```
Filter by:
  - Category: FILAMENT
  - Location: WH-A
  - Last Counted: > 30 days ago
  - Value: > $500 (ABC analysis - count high-value items more often)
```

**Generate Count Sheet** → Download CSV or print:
```csv
sku,name,location,expected_qty,unit,counted_qty
MAT-PLA-BASIC-BLK,PLA Basic - Black,WH-A,5000,G,
MAT-PETG-HF-WHT,PETG HF - White,WH-A,3500,G,
BRACKET-001,Desk Bracket,WH-A,48,EA,
```

**Step 2: Physical Count**

- Print count sheet
- Walk warehouse with sheet
- Count physical inventory
- Record counts in `counted_qty` column

**Step 3: Enter Counts**

**Navigation:** Items → Inventory → **Batch Adjust**

Upload completed count sheet:
```csv
sku,name,location,expected_qty,unit,counted_qty
MAT-PLA-BASIC-BLK,PLA Basic - Black,WH-A,5000,G,4950
MAT-PETG-HF-WHT,PETG HF - White,WH-A,3500,G,3500
BRACKET-001,Desk Bracket,WH-A,48,EA,47
```

**Step 4: Review Discrepancies**

System shows differences:
```
MAT-PLA-BASIC-BLK: Expected 5000 G, Counted 4950 G → Variance: -50 G (-1.0%)
BRACKET-001: Expected 48 EA, Counted 47 EA → Variance: -1 EA (-2.1%)
```

**Step 5: Approve Adjustments**

- Review variances
- Add notes (reason for discrepancy)
- Click **Submit Adjustments**

**Result:**
- Adjustment transactions created
- Inventory quantities updated
- `last_counted` field updated to today
- Inventory value recalculated

### ABC Analysis for Cycle Counting

**Prioritize high-value items:**

| Class | Criteria | Count Frequency |
|-------|----------|-----------------|
| **A** | Top 20% by value | Weekly |
| **B** | Next 30% by value | Monthly |
| **C** | Bottom 50% by value | Quarterly |

**Example:**
- Class A: Expensive materials (PAHT-CF, PC) → Count weekly
- Class B: Standard materials (PLA, PETG) → Count monthly
- Class C: Low-cost supplies (bags, labels) → Count quarterly

---

## Part 9: Reorder Points and MRP Integration

### Setting Reorder Points

**Reorder Point** = When to trigger purchase order

**Formula:**
```
Reorder Point = (Daily Usage × Lead Time) + Safety Stock
```

**Example:**
```
Material: PLA Basic Black
Daily Usage: 500 G/day (average)
Lead Time: 7 days
Safety Stock: 1000 G (buffer)

Reorder Point = (500 G/day × 7 days) + 1000 G
              = 3500 G + 1000 G
              = 4500 G

When inventory drops to 4500 G → Create PO
```

**Setting in System:**

**Navigation:** Items → Products → Select item → Edit

```
Stocking Policy: stocked
Reorder Point: 4500 G
Safety Stock: 1000 G
Lead Time: 7 days
Min Order Qty: 5 KG (5000 G)
```

### Automatic Reorder via MRP

**MRP (Material Requirements Planning) automates reordering:**

1. MRP runs daily (or on-demand)
2. Calculates net requirements:
   ```
   Net Required = Demand - On Hand + Safety Stock - On Order
   ```
3. Generates **Planned Orders** for items below reorder point
4. User reviews and converts to Purchase Orders

**See:** [MRP Guide](mrp.md) for full MRP workflow

---

## Part 10: Integration with Manufacturing

### Production Consumption

**When production order completes:**

1. **Material Consumption** - Automatic transactions:
   ```
   BOM Line: 450 G PLA Basic Black
   → Transaction: -450 G (consumption)
   → Cost: $11.25 (450 G × $0.025/G)
   → Reduce on_hand by 450 G
   → Release allocation (if reserved)
   ```

2. **Finished Goods Receipt** - Automatic transactions:
   ```
   Production Order Output: 10 EA Phone Stands
   → Transaction: +10 EA (receipt from production)
   → Cost: $50.00 (based on BOM + labor)
   → Add to finished goods inventory
   ```

**All automatic** - no manual inventory entries needed for production.

### Allocation System

**When production order created:**
```
BOM requires: 450 G PLA Basic Black
Current inventory: 5000 G on hand, 0 allocated

Action: Reserve 450 G
Result: 5000 G on hand, 450 G allocated, 4550 G available
```

**Available quantity drops** so MRP knows those 450 G are spoken for.

**When production completes/cancels:**
- Material consumed: -450 G from on_hand, -450 G from allocated
- Final: 4550 G on hand, 0 allocated, 4550 G available

---

## Part 11: Inventory Reports

### Stock Status Report

**Navigation:** Items → Inventory → **Reports** → Stock Status

**Columns:**
- SKU, Name, Category
- On Hand, Allocated, Available
- Unit, Unit Cost
- Inventory Value
- Reorder Point
- Days of Stock (on hand ÷ daily usage)

**Filters:**
- Location
- Category
- Item Type
- Below Reorder Point (alerts)
- Negative Inventory (issues)

### Inventory Valuation

**Total inventory value by category:**

```
Category            Items   Qty         Value      % of Total
FILAMENT            87      125,450 G   $3,128.50  62%
PACKAGING           12      850 EA      $425.00    8%
HARDWARE            34      2,340 EA    $585.00    12%
FINISHED_GOODS      45      234 EA      $1,755.00  35%
──────────────────────────────────────────────────────────
TOTAL               178                 $5,893.50  100%
```

### Transaction History Report

**View all transactions by date range:**

**Navigation:** Items → Inventory → **Reports** → Transaction History

**Filters:**
- Date Range
- Transaction Type
- Location
- SKU

**Export to CSV** for analysis in Excel/spreadsheet.

---

## Part 12: Best Practices

### Inventory Accuracy

✅ **Do:**
- Perform cycle counts regularly
- Investigate variances > 2%
- Update costs when purchasing
- Use spool tracking for materials
- Keep locations organized and labeled

❌ **Don't:**
- Ignore small discrepancies (they compound)
- Skip recording scrap/waste
- Manually adjust without reason/notes
- Change reorder points without data analysis

### Material Management

✅ **Do:**
- Track spools from receipt to consumption
- Rotate stock (FIFO) for materials with shelf life
- Store hygroscopic materials (Nylon, TPU) properly
- Label spools with received date and lot number
- Monitor low spool alerts

❌ **Don't:**
- Mix spools of same material without tracking
- Use expired materials (check expiry_date)
- Store materials in humid conditions
- Leave spools on printers when not in use

### Cost Management

✅ **Do:**
- Update standard costs when vendor prices change
- Review average costs quarterly
- Use standard costing for manufactured items
- Use average costing for purchased materials
- Track cost variances

❌ **Don't:**
- Leave cost fields blank (breaks valuation)
- Change cost method after many transactions
- Forget to update costs after price increases

---

## Part 13: Common Workflows

### Workflow 1: Receiving Filament

```
1. Vendor ships 5 KG of PLA Basic Black
2. Receive shipment
3. Create spool records:
   - SPOOL-PLA-BLK-010 (1 KG)
   - SPOOL-PLA-BLK-011 (1 KG)
   - SPOOL-PLA-BLK-012 (1 KG)
   - SPOOL-PLA-BLK-013 (1 KG)
   - SPOOL-PLA-BLK-014 (1 KG)
4. Each spool shows:
   - Initial Weight: 1.000 kg
   - Current Weight: 1.000 kg
   - Status: active
5. Inventory updated:
   - +5000 G (5 KG × 1000)
   - Cost: $125.00 (5000 G × $0.025/G)
```

### Workflow 2: Production Consumption

```
1. Production order created for 10 phone stands
2. BOM requires: 450 G PLA per unit = 4500 G total
3. System reserves 4500 G (allocated)
4. Production order assigned spool: SPOOL-PLA-BLK-010
5. Production completes
6. System records:
   - Material consumption: -4500 G
   - Spool updated: 1000 G → 550 G remaining
   - Finished goods receipt: +10 EA
7. Allocation released
```

### Workflow 3: Cycle Count Correction

```
1. Generate count sheet for FILAMENT category
2. Physical count shows: 4950 G (expected 5000 G)
3. Enter counted quantity: 4950 G
4. System creates adjustment: -50 G
5. Investigate:
   - Check scrap records
   - Review recent production
   - Ask operators
6. Document reason: "Unrecorded test prints"
7. Approve adjustment
8. Inventory updated to 4950 G
```

---

## Part 14: Troubleshooting

### Inventory Shows Negative Quantity

**Problem:** Item shows -50 G on hand

**Cause:**
- Consumption transaction recorded before receipt
- Manual adjustment error
- Production order consumed more than available

**Solution:**
1. Review transaction history for item
2. Identify incorrect transaction
3. Create correction adjustment to fix
4. Update processes to prevent recurrence

### Available Quantity Incorrect

**Problem:** Available = 500 G, but should be 1000 G

**Cause:**
- Allocated quantity not released after PO cancellation
- Reservation transaction orphaned

**Solution:**
1. Check allocated_quantity field
2. Find orphaned reservations:
   ```
   Items → Inventory → Item detail → Allocations
   ```
3. Release orphaned allocations manually
4. Verify production orders associated

### Spool Weight Tracking Off

**Problem:** Spool shows 800 G remaining, but scale shows 600 G

**Cause:**
- Manual consumption not recorded
- Production order didn't update spool
- Spool used for test prints

**Solution:**
1. Weigh spool physically
2. Adjust spool weight to match scale
3. Investigate missing transactions
4. Update production recording process

### Cost per Unit Shows $0.00

**Problem:** Transaction shows no cost

**Cause:**
- Product has no cost fields set
- Cost not entered on receipt
- New product without initial cost

**Solution:**
1. Edit product → Set standard_cost
2. Re-run inventory valuation
3. Future transactions will have cost
4. Past transactions remain $0 (historical)

---

## Part 15: Advanced Features

### Multi-Location Transfers

**Transfer inventory between locations:**

**Navigation:** Items → Inventory → **Transfer**

```
Item: MAT-PLA-BASIC-BLK
From Location: WH-A
To Location: WH-B
Quantity: 1000 G
Reason: "Rebalancing inventory"
```

**Result:**
- Transaction 1: -1000 G @ WH-A (issue)
- Transaction 2: +1000 G @ WH-B (receipt)
- Net inventory unchanged, location changed

### Lot/Serial Tracking

**Track batches for quality control:**

```
Lot Number: LOT-2026-0205 (vendor's batch)
Serial Number: SERIAL-001 (unique item)
```

**Used for:**
- Material lot traceability (which batch had defects?)
- Warranty tracking (which serial returned?)
- Recall management (which lots affected?)

**View items by lot:**

**Navigation:** Items → Inventory → **By Lot/Serial**

Shows all inventory quantities by lot number for recall scenarios.

### Inventory Alerts

**Automated notifications for:**

- ⚠️ **Below Reorder Point** - Time to purchase
- 🔴 **Negative Inventory** - Investigation needed
- 📉 **Low Spools** - < 10% remaining
- 📅 **Expiring Materials** - Nylon/TPU approaching expiry
- 💰 **High Value Variances** - Cycle count differences > $100

**Configure alerts:** Settings → Notifications → Inventory Alerts

---

## Next Steps

Now that you understand inventory management, explore these related guides:

| Guide | Learn About |
|-------|-------------|
| **Manufacturing** | How production consumes materials, BOMs, routings |
| **MRP** | Automatic reorder point calculations, planned orders |
| **Purchasing** | Creating POs, receiving inventory, vendor management |
| **Accounting** | COGS calculation, inventory valuation, financial reports |

## Quick Reference

### Transaction Types Quick Guide

| Type | On Hand | Allocated | Available | Use Case |
|------|---------|-----------|-----------|----------|
| **receipt** | + | - | + | Receiving from vendor |
| **consumption** | - | - (if released) | - | Manufacturing usage |
| **adjustment** | ± | - | ± | Cycle count correction |
| **reservation** | - | + | - | Allocate for production |
| **reservation_release** | - | - | + | Cancel allocation |

### UOM Conversion Quick Reference

```
Purchase: 3 KG @ $25/KG
  ↓ (× 1000 for quantity, ÷ 1000 for cost)
Inventory: 3000 G @ $0.025/G = $75.00
```

### Keyboard Shortcuts

- `n` - New item
- `a` - Adjust inventory
- `t` - Transfer
- `r` - Refresh list
- `/` - Search

---

**🎉 Congratulations!** You now understand FilaOps inventory management, including the critical UOM system for 3D printing materials. Set up your locations, create items, and start tracking inventory!
