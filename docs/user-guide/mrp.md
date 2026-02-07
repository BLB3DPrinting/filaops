# MRP (Material Requirements Planning)

## Overview

Material Requirements Planning (MRP) is an automated planning system that ensures you have the right materials at the right time to fulfill your production and sales commitments. FilaOps' MRP system analyzes your production orders, explodes Bills of Materials (BOMs), and automatically generates planned purchase orders and production orders for any material shortages.

**What MRP Does:**
- **Demand Analysis** - Identifies all material requirements from production orders (and optionally sales orders)
- **BOM Explosion** - Recursively expands multi-level BOMs to calculate component needs
- **Inventory Netting** - Compares requirements against available inventory and incoming supply
- **Planned Order Generation** - Creates suggested purchase orders (for raw materials) or production orders (for sub-assemblies)
- **Supply/Demand Timeline** - Projects when shortages will occur

**MRP Formula:**
```
Net Requirement = Gross Requirement - On-Hand Inventory - Incoming Supply + Safety Stock
```

**When to Use MRP:**
- Weekly or daily to proactively identify material shortages
- After creating new production orders
- When planning for upcoming production
- To answer "what materials do I need to order?"

---

## Table of Contents

1. [Understanding MRP Concepts](#1-understanding-mrp-concepts)
2. [Running MRP](#2-running-mrp)
3. [Reviewing MRP Results](#3-reviewing-mrp-results)
4. [Managing Planned Orders](#4-managing-planned-orders)
5. [Firming Planned Orders](#5-firming-planned-orders)
6. [Releasing Planned Orders](#6-releasing-planned-orders)
7. [BOM Explosion and Requirements](#7-bom-explosion-and-requirements)
8. [Supply/Demand Timeline](#8-supplydemand-timeline)
9. [MRP Configuration](#9-mrp-configuration)
10. [Best Practices](#10-best-practices)
11. [Complete Workflows](#11-complete-workflows)
12. [Troubleshooting](#12-troubleshooting)
13. [Quick Reference](#13-quick-reference)

---

## 1. Understanding MRP Concepts

### 1.1 Core MRP Components

**MRP Run**
- A single execution of the MRP calculation
- Analyzes all open production orders within planning horizon
- Creates an audit trail with statistics
- Can be re-run to refresh planned orders

**Planned Order**
- MRP's suggestion to order material
- Two types: `purchase` (raw materials) or `production` (sub-assemblies)
- Lifecycle: `planned` → `firmed` → `released`
- Can be deleted automatically by next MRP run (unless firmed)

**Planning Horizon**
- How far ahead MRP looks (default: 30 days)
- Production orders with due dates within horizon are analyzed
- Balances planning visibility vs computational cost

**Gross Requirements**
- Total quantity of a component needed across all production orders
- Before considering inventory or supply

**Net Requirements**
- Actual shortage after inventory netting
- `Net = Gross - On-Hand - Incoming + Safety Stock`

### 1.2 Make vs. Buy Decision

MRP automatically determines whether to create a purchase order or production order:

| Condition | Order Type | Meaning |
|-----------|-----------|---------|
| `has_bom = False` | **Purchase** | Raw material or purchased part — buy it |
| `has_bom = True` | **Production** | Manufactured sub-assembly — make it |

**Example:**
- **Filament** (no BOM) → Purchase Order to vendor
- **Circuit Board Sub-Assembly** (has BOM with resistors, capacitors) → Production Order to manufacture
- **Custom 3D Printed Component** (has BOM with filament) → Production Order

### 1.3 BOM Explosion

**Single-Level BOM:**
```
Widget (Qty: 10)
├─ Component A (Qty: 2 each) → Need 20
├─ Component B (Qty: 1 each) → Need 10
└─ Component C (Qty: 3 each) → Need 30
```

**Multi-Level BOM (Recursive):**
```
Widget (Qty: 10)
├─ Sub-Assembly X (Qty: 2 each) → Need 20
│   ├─ Component A (Qty: 3 each) → Need 60 total
│   └─ Component B (Qty: 1 each) → Need 20 total
└─ Component C (Qty: 5 each) → Need 50
```

MRP recursively explodes BOMs to calculate ALL component requirements at all levels.

### 1.4 Material Sources

**Primary Source: Routing Operation Materials**
- Modern approach for 3D printing
- Materials defined at operation level (e.g., filament at Print operation, boxes at Ship operation)
- Takes precedence if defined

**Fallback Source: BOM Lines**
- Legacy BOM components table
- Used only if no routing materials exist
- Maintains backward compatibility

### 1.5 Planned Order Lifecycle

```
[MRP Run] → [PLANNED] → [FIRMED] → [RELEASED] → [Actual PO/MO Created]
              ↓           ↓           ↓
         Can be deleted  Locked in   Converted
         by next MRP    by MRP      to real order
```

**Status Meanings:**
- **Planned** - MRP suggestion, not committed, will be deleted on next MRP run
- **Firmed** - User confirmed, locked, won't be deleted by MRP
- **Released** - Converted to actual Purchase Order or Production Order
- **Cancelled** - No longer needed, user cancelled

---

## 2. Running MRP

### 2.1 Manual MRP Run

**Navigation:** MRP → **Run MRP**

**Configuration:**
1. **Planning Horizon** (default: 30 days)
   - How far ahead to look for production orders
   - Example: 30 days = analyze all POs due within next month

2. **Include Draft Orders** (default: Yes)
   - Include production orders with status `draft`
   - Recommended: Yes (plan for all upcoming work)

3. **Regenerate Planned Orders** (default: Yes)
   - Delete unfirmed planned orders before running
   - Creates fresh plan based on current data
   - Firmed orders are NOT deleted

**Click "Run MRP"**

### 2.2 MRP Run Results

After running, you'll see:

```
✅ MRP Run #42 Completed
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Orders Processed:        15 production orders
Components Analyzed:     47 unique components
Shortages Found:         8 materials below reorder point
Planned Orders Created:  8 (5 purchase, 3 production)
Run Time:               2024-02-07 14:32:15
Status:                 completed
```

**What This Means:**
- MRP analyzed 15 production orders within horizon
- Found 47 unique components needed
- 8 components have shortages (need to order)
- Created 8 planned orders to resolve shortages

### 2.3 Viewing MRP History

**Navigation:** MRP → **MRP Runs**

See all past MRP runs with:
- Run date and time
- Planning horizon used
- Components analyzed
- Shortages found
- Planned orders created
- Status (running, completed, failed)

**Click on a run** to see which planned orders it created.

---

## 3. Reviewing MRP Results

### 3.1 Understanding the Requirements View

After MRP runs, review **Requirements Summary**:

**Navigation:** MRP → **Requirements** (or results page after run)

**Columns:**
| Column | Meaning |
|--------|---------|
| **Product SKU/Name** | Component needed |
| **Gross Qty** | Total quantity needed across all orders |
| **On-Hand** | Current inventory |
| **Allocated** | Already reserved for other orders |
| **Available** | On-Hand - Allocated |
| **Incoming** | On open purchase orders |
| **Safety Stock** | Minimum buffer quantity |
| **Net Shortage** | How much to order (if > 0) |
| **Has BOM** | Make (production) or Buy (purchase) |

### 3.2 Example Requirements

**Scenario: 3 Production Orders Need PLA Filament**

| Component | Gross | On-Hand | Incoming | Safety Stock | Net Shortage | Action |
|-----------|-------|---------|----------|--------------|--------------|--------|
| PLA Black 1kg | 12000 G | 3000 G | 5000 G | 2000 G | **6000 G** | 🛒 Order 6 KG |
| PETG Red 1kg | 8000 G | 10000 G | 0 G | 2000 G | **0 G** | ✅ In stock |
| Poly Mailer 6x9 | 25 EA | 50 EA | 0 EA | 10 EA | **0 G** | ✅ In stock |

**Calculation for PLA Black:**
```
Net Shortage = Gross - On-Hand - Incoming + Safety Stock
             = 12000 - 3000 - 5000 + 2000
             = 6000 G (6 KG)
```

**MRP Action:** Create Planned Purchase Order for 6 KG of PLA Black

### 3.3 Identifying Shortages

**Color Coding (in UI):**
- 🔴 **Red** - Critical shortage (net shortage > 0)
- 🟡 **Yellow** - Below reorder point but still have stock
- 🟢 **Green** - Sufficient inventory

**Priority:**
1. Items with earliest due dates
2. Items with largest shortage quantities
3. Items with long lead times

---

## 4. Managing Planned Orders

### 4.1 Viewing Planned Orders

**Navigation:** MRP → **Planned Orders**

**List View Shows:**
- Order type (Purchase or Production)
- Product SKU and name
- Quantity to order
- Due date (when material is needed)
- Start date (when to start ordering, accounting for lead time)
- Status (planned, firmed, released, cancelled)
- Source demand (which production order triggered this)

**Filters:**
- Status (planned, firmed, released)
- Type (purchase, production)
- Product

### 4.2 Planned Order Details

**Click on a planned order** to see:

**General Info:**
- Order type (purchase or production)
- Product details (SKU, name, cost)
- Quantity to order

**Timing:**
- **Due Date** - When material must be available
- **Start Date** - When to initiate order (due date - lead time)
- Lead time days (from product master)

**Pegging (Demand Tracing):**
- What triggered this planned order?
- Source: production_order, sales_order, or mrp_calculation
- Source ID and code (e.g., PO-2026-0042)

**Status & Actions:**
- Current status
- Available actions (Firm, Release, Cancel)
- Conversion tracking (if released, shows actual PO/MO number)

### 4.3 Understanding Lead Times

**Lead Time** = Time between order initiation and receipt

**Example:**
- Product: PLA Black Filament
- Lead time: 7 days
- Due date: 2026-02-20 (when production order needs it)
- **Start date**: 2026-02-13 (due date - 7 days)

**Start Date Logic:**
- MRP calculates start date by subtracting lead time from due date
- If start date is in the past, it uses today (order ASAP)
- If due date is also in the past, preserves lead time by shifting both forward

### 4.4 Editing Planned Orders

You **cannot** directly edit planned orders. Instead:

1. **To change quantity/date:**
   - Cancel this planned order
   - Adjust the underlying production order
   - Re-run MRP

2. **To lock it in:**
   - Firm the order (see next section)

3. **To create the actual order:**
   - Release the order (converts to PO/MO)

---

## 5. Firming Planned Orders

### 5.1 What is Firming?

**Firming** = Locking a planned order so MRP won't delete it.

**When MRP runs with "Regenerate Planned Orders":**
- **Unfirmed (status: planned)** orders are deleted and recreated
- **Firmed orders** are preserved

**Use Cases:**
- You've reviewed and approved the order
- You're planning to create PO soon
- You want to lock in timing while you find a vendor
- You don't want next MRP run to change/delete it

### 5.2 How to Firm a Planned Order

**Method 1: From Planned Orders List**
1. Navigate to MRP → Planned Orders
2. Find the order
3. Click **Firm** button
4. Add optional notes
5. Click **Confirm**

**Method 2: From Planned Order Detail**
1. Open planned order details
2. Click **Firm Order** button
3. Add notes (optional)
4. Submit

**Result:**
- Status changes: `planned` → `firmed`
- `firmed_at` timestamp recorded
- Order appears in "Firmed Orders" filter
- Will NOT be deleted by next MRP run

### 5.3 When to Firm vs. Release

**Firm** when you:
- Approve the order but aren't ready to create PO yet
- Want to lock timing
- Need to find vendor or review pricing

**Release** when you:
- Ready to create actual Purchase Order or Production Order
- Have selected vendor (for purchase orders)
- Ready to commit

---

## 6. Releasing Planned Orders

### 6.1 What is Releasing?

**Releasing** = Converting a planned order into an actual Purchase Order or Production Order.

**Process:**
1. Planned order (suggestion) → Actual order (committed)
2. For **purchase** orders: Creates draft PO with selected vendor
3. For **production** orders: Creates draft manufacturing order

### 6.2 Releasing a Purchase Order

**Navigation:** MRP → Planned Orders → (select purchase order) → **Release**

**Steps:**
1. **Select Vendor** (required for purchase orders)
   - Choose from your vendor list
   - Vendor will receive this PO

2. **Review Details:**
   - Product, quantity, due date
   - Unit cost (from product's standard or last cost)

3. **Add Notes** (optional)
   - Any special instructions

4. **Click "Release Order"**

**Result:**
```
✅ Purchase Order Created: PO-2026-0123
   Vendor: Acme Filament Supply
   Product: PLA Black 1kg
   Quantity: 6.0 KG
   Unit Cost: $25.00/KG
   Total: $150.00
   Status: Draft
   Expected Date: 2026-02-20
```

**Next Steps:**
1. Go to Purchasing → Purchase Orders → PO-2026-0123
2. Review the PO
3. Mark as "Ordered" when you send it to vendor
4. Receive inventory when it arrives

### 6.3 Releasing a Production Order

**Navigation:** MRP → Planned Orders → (select production order) → **Release**

**Steps:**
1. **Review Details:**
   - Product to manufacture (must have BOM)
   - Quantity
   - Due date

2. **Add Notes** (optional)

3. **Click "Release Order"**

**Result:**
```
✅ Production Order Created: PO-2026-0042
   Product: Widget Sub-Assembly
   Quantity: 10 EA
   BOM: v2.0
   Status: Draft
   Due Date: 2026-02-18
```

**Next Steps:**
1. Go to Production → Production Orders → PO-2026-0042
2. Review components needed (BOM)
3. Release the production order
4. Schedule and manufacture

### 6.4 Bulk Releasing Orders

To release multiple planned orders:

**Option 1: Release Individually**
- Good when you need different vendors
- Good when you want to review each

**Option 2: Group by Vendor, Then Release**
1. Filter planned orders by vendor (use product's preferred vendor)
2. Release all orders for Vendor A
3. Release all orders for Vendor B
4. etc.

**Best Practice:** Release all orders for same vendor together so you can consolidate shipments and negotiate pricing.

---

## 7. BOM Explosion and Requirements

### 7.1 Understanding BOM Explosion

**What is BOM Explosion?**
- Recursively expanding a Bill of Materials to calculate ALL component requirements
- Handles multi-level BOMs (assemblies with sub-assemblies)
- Accounts for scrap factors and UOM conversions

**Example: Single-Level BOM**

Product: **3D Printed Phone Stand**
- Quantity Needed: 10 EA

BOM:
```
3D Printed Phone Stand (1 EA)
├─ PLA Black Filament: 35 G
├─ Rubber Feet (4-pack): 1 EA
└─ Poly Mailer 6x9: 1 EA
```

**Explosion for 10 EA:**
```
Gross Requirements:
- PLA Black Filament: 350 G (35 G × 10)
- Rubber Feet: 10 EA (1 × 10)
- Poly Mailer: 10 EA (1 × 10)
```

**Example: Multi-Level BOM**

Product: **Custom Enclosure Assembly**
- Quantity Needed: 5 EA

BOM (2 levels):
```
Custom Enclosure Assembly (1 EA)
├─ 3D Printed Enclosure Shell (1 EA)  [Has BOM - Level 1]
│   ├─ PETG Gray Filament: 120 G
│   └─ Threaded Inserts M3: 4 EA
├─ Circuit Board Sub-Assembly (1 EA)  [Has BOM - Level 1]
│   ├─ PCB: 1 EA
│   ├─ Resistor 10K: 3 EA
│   └─ Capacitor 100nF: 2 EA
└─ Screws M3x8: 4 EA
```

**Explosion for 5 EA:**
```
Gross Requirements (all levels):
- PETG Gray Filament: 600 G (120 × 5)
- Threaded Inserts M3: 20 EA (4 × 5)
- PCB: 5 EA (1 × 5)
- Resistor 10K: 15 EA (3 × 5)
- Capacitor 100nF: 10 EA (2 × 5)
- Screws M3x8: 20 EA (4 × 5)
```

### 7.2 Viewing BOM Explosion

**Manual BOM Explosion:**

**Navigation:** MRP → **Explode BOM**

**Steps:**
1. Select product (must have BOM)
2. Enter quantity to explode (e.g., 10)
3. Click **Explode**

**Result:**
```
BOM Explosion for: Widget Assembly (Qty: 10)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Level 0 (Direct Components):
  - Component A: 20 EA
  - Sub-Assembly X: 10 EA
  - Component C: 30 EA

Level 1 (Sub-Components of Sub-Assembly X):
  - Component B: 30 EA (from Sub-Assembly X)
  - Component D: 10 EA (from Sub-Assembly X)

Total Components: 5 unique items
```

**Use Cases:**
- Understand what materials a product needs
- Verify BOM accuracy before running MRP
- Estimate material costs for quotes
- Plan material purchases before creating production orders

### 7.3 Requirements Analysis

**Navigation:** MRP → **Requirements** → Filter by Production Order

**View Requirements for Specific Production Order:**

**Example: PO-2026-0042 (Widget, Qty: 10)**

```
Requirements for PO-2026-0042
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Component A
  Gross Required:  20 EA
  On-Hand:        15 EA
  Incoming:        0 EA
  Safety Stock:    5 EA
  Net Shortage:   10 EA  ⚠️ Need to order

Sub-Assembly X
  Gross Required:  10 EA
  On-Hand:         0 EA
  Incoming:        0 EA
  Safety Stock:    2 EA
  Net Shortage:   12 EA  ⚠️ Need to manufacture

Component C
  Gross Required:  30 EA
  On-Hand:        50 EA
  Incoming:        0 EA
  Safety Stock:    5 EA
  Net Shortage:    0 EA  ✅ In stock
```

---

## 8. Supply/Demand Timeline

### 8.1 What is Supply/Demand Timeline?

A **chronological view** of:
- **Supply Events** - When inventory arrives (POs, planned orders, production completions)
- **Demand Events** - When inventory is consumed (production orders, sales orders)
- **Running Balance** - Projected inventory level over time

**Purpose:**
- Identify **when** shortages will occur
- Calculate **days of supply** remaining
- Validate MRP planned order timing

### 8.2 Viewing Timeline

**Navigation:** MRP → **Supply/Demand** → Select Product

**Timeline Display:**

```
Supply/Demand Timeline: PLA Black Filament
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Current Status:
  On-Hand:          5000 G
  Available:        3000 G (allocated: 2000 G)
  Safety Stock:     2000 G
  Days of Supply:   8 days

Projected Events:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Date       Type    Source              Qty       Balance
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2026-02-07 On-Hand Current Inventory   +3000 G   3000 G  ✅
2026-02-10 Demand  PO-2026-0038        -1500 G   1500 G  ⚠️ Below reorder
2026-02-12 Demand  PO-2026-0039        -2000 G   -500 G  🔴 SHORTAGE
2026-02-14 Supply  PO-2026-0101        +5000 G   4500 G  ✅
2026-02-18 Demand  PO-2026-0041        -3000 G   1500 G  ⚠️
2026-02-20 Supply  Planned-Purchase-42 +6000 G   7500 G  ✅
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ Projected Shortage Date: 2026-02-12
```

**Insights:**
- Shortage will occur on 2026-02-12 (in 5 days)
- Incoming supply on 2026-02-14 will arrive too late
- MRP's planned purchase for 2026-02-20 will restore safety stock
- **Action:** Expedite PO-2026-0101 or release planned order earlier

### 8.3 Interpreting Timeline

**Event Types:**

| Type | Meaning | Impact |
|------|---------|--------|
| **On-Hand** | Starting inventory | Baseline |
| **Demand** | Material consumed by production | Decreases balance |
| **Supply** | Material received from PO | Increases balance |

**Balance Colors:**
- 🟢 **Green** (> Safety Stock) - Healthy inventory
- 🟡 **Yellow** (< Reorder Point) - Order soon
- 🔴 **Red** (< 0) - Shortage, production at risk

**Days of Supply:**
```
Days of Supply = Available Inventory / Average Daily Demand

Example:
  Available: 3000 G
  Demand next 30 days: 12000 G
  Average Daily: 400 G/day
  Days of Supply: 3000 / 400 = 7.5 days
```

---

## 9. MRP Configuration

### 9.1 MRP Settings

**Location:** `backend/.env`

**Key Settings:**

```ini
# Sales Order Integration
INCLUDE_SALES_ORDERS_IN_MRP=false
# Set to 'true' to include sales orders as demand
# Default: false (only production orders analyzed)

# Auto-MRP Triggers
AUTO_MRP_ON_ORDER_CREATE=false
AUTO_MRP_ON_CONFIRMATION=false
AUTO_MRP_ON_SHIPMENT=false
# Automatically run MRP when events occur
# Default: false (manual MRP runs only)

# Sub-Assembly Lead Time Cascading
MRP_ENABLE_SUB_ASSEMBLY_CASCADING=false
# Calculate sub-assembly due dates based on parent due dates
# Default: false (all orders due ASAP)

# Validation
MRP_VALIDATION_STRICT_MODE=true
# Strict validation of BOMs and product data
# Default: true (catch data issues)
```

### 9.2 Including Sales Orders in MRP

**Default Behavior:** MRP only analyzes production orders

**When to Enable:**
Enable `INCLUDE_SALES_ORDERS_IN_MRP=true` if you:
- Have sales orders NOT yet converted to production orders
- Want MRP to plan for confirmed sales
- Use make-to-order workflow where SOs drive production directly

**What Changes:**
- MRP analyzes sales orders within planning horizon
- Explodes BOMs for quoted products
- Includes shipping materials (packaging, labels) if consume_stage='shipping'

**Example:**
```
Sales Order: SO-2026-00042
  Customer: Acme Corp
  Product: Widget
  Quantity: 10
  Status: Confirmed
  Estimated Delivery: 2026-02-20

MRP will:
1. Explode BOM for Widget (qty: 10)
2. Calculate material requirements
3. Create planned orders if shortages exist
4. Account for packaging materials (boxes, mailers)
```

### 9.3 Sub-Assembly Lead Time Cascading

**Default Behavior:** All planned orders due ASAP (earliest safe date)

**With Cascading Enabled:**
- Sub-assembly due dates calculated backwards from parent due date
- Preserves lead time buffers between levels
- More realistic timeline

**Example Without Cascading:**
```
Parent Product: Custom Enclosure (Due: 2026-02-25)
  Sub-Assembly: 3D Printed Shell (Due: 2026-02-15) ← ASAP
    Material: PETG Filament (Due: 2026-02-08) ← ASAP
```

**Example With Cascading:**
```
Parent Product: Custom Enclosure (Due: 2026-02-25)
  Sub-Assembly: 3D Printed Shell (Due: 2026-02-23) ← 2 days before parent
    Material: PETG Filament (Due: 2026-02-16) ← 7 days before sub-assy
```

**Enable:** Set `MRP_ENABLE_SUB_ASSEMBLY_CASCADING=true`

**Use When:**
- You have multi-level BOMs with sub-assemblies
- You want realistic lead time offsets
- You're planning far ahead (30+ days)

---

## 10. Best Practices

### 10.1 MRP Run Frequency

**Recommended Schedule:**

| Business Size | Frequency | Why |
|--------------|-----------|-----|
| **Small** (1-5 production orders/week) | Weekly | Monday morning to plan week |
| **Medium** (5-20 orders/week) | 2-3x per week | Monday, Wednesday, Friday |
| **Large** (20+ orders/week) | Daily | Every morning before production meeting |

**Trigger MRP When:**
- ✅ New production orders created
- ✅ Production schedules change
- ✅ Large sales orders confirmed
- ✅ Inventory levels change significantly (after receiving shipments)

### 10.2 Maintaining Accurate Data

**MRP Quality = Data Quality**

**Critical Data to Maintain:**

1. **BOMs** ✅
   - Keep BOMs accurate and up-to-date
   - Include ALL components (filament, hardware, packaging)
   - Set correct quantities and units
   - Use routing operation materials for 3D printing

2. **Lead Times** ✅
   - Set realistic lead times on products
   - Update as vendor performance changes
   - Account for shipping time + receiving + inspection

3. **Safety Stock** ✅
   - Set safety stock for critical materials
   - Formula: `Safety Stock = Daily Usage × Lead Time × Buffer Factor`
   - Example: 100 G/day × 7 days × 1.5 = 1050 G safety stock

4. **Reorder Points** ✅
   - Set reorder points to trigger orders
   - Formula: `Reorder Point = (Daily Usage × Lead Time) + Safety Stock`
   - MRP will suggest orders when on-hand drops below reorder point

5. **Minimum Order Quantities** ✅
   - Set min order qty for bulk materials
   - Example: Filament vendor requires 5 KG minimum
   - MRP will round up to min qty

### 10.3 Firming Strategy

**When to Firm Planned Orders:**

✅ **Firm Immediately:**
- Critical materials with long lead times
- Items already approved by purchasing manager
- Orders matching existing PO consolidation opportunities

✅ **Firm After Review:**
- High-value items (review pricing first)
- New suppliers (verify vendor reliability)
- Large quantities (negotiate better pricing)

❌ **Don't Firm:**
- Uncertain demand (production order might cancel)
- Speculative orders (wait for confirmation)
- Short lead time items (can order quickly if needed)

### 10.4 Reviewing Planned Orders

**Weekly Review Checklist:**

1. **Planned Purchase Orders:**
   - [ ] Review quantities (reasonable based on usage?)
   - [ ] Check vendors (correct supplier selected?)
   - [ ] Verify due dates (timing makes sense?)
   - [ ] Consolidate orders (combine orders for same vendor?)
   - [ ] Firm or release approved orders

2. **Planned Production Orders:**
   - [ ] Verify product has BOM
   - [ ] Check sub-assembly quantities
   - [ ] Ensure materials available for sub-assemblies
   - [ ] Sequence production (dependencies?)
   - [ ] Release orders ready to manufacture

### 10.5 Handling Exceptions

**Material Substitutions:**
- MRP doesn't auto-substitute (uses exact BOM components)
- If substituting: Cancel planned order, adjust BOM, re-run MRP

**Expediting Orders:**
- Use Supply/Demand Timeline to identify urgent needs
- Release planned orders with shorter lead times
- Manually adjust due dates in released POs

**Cancelling Production Orders:**
- If a production order cancels, re-run MRP
- MRP will remove related planned orders

---

## 11. Complete Workflows

### Workflow 1: Weekly MRP Cycle

**Monday Morning Routine**

**Step 1: Prepare for MRP (5 minutes)**
```
1. Review upcoming production orders (next 30 days)
2. Confirm any new sales orders are converted to production orders
3. Update any BOM changes from last week
4. Receive any weekend deliveries into inventory
```

**Step 2: Run MRP (2 minutes)**
```
1. Navigate to MRP → Run MRP
2. Planning Horizon: 30 days
3. Include Draft Orders: Yes
4. Regenerate Planned Orders: Yes
5. Click "Run MRP"
```

**Step 3: Review Results (10 minutes)**
```
1. Check shortages found: 8 materials
2. Review requirements:
   - Critical shortages (negative on-hand)
   - Low stock warnings (below safety stock)
   - Items with long lead times
3. Check planned orders:
   - 5 purchase orders
   - 3 production orders (sub-assemblies)
```

**Step 4: Process Purchase Orders (15 minutes)**
```
For each planned purchase order:
1. Review quantity and vendor
2. Check pricing (standard cost reasonable?)
3. Consolidate orders (combine orders to same vendor)
4. Firm high-priority orders
5. Release orders ready to send:
   - Select vendor
   - Confirm quantity and due date
   - Release → Creates PO-2026-XXXX
```

**Step 5: Process Production Orders (10 minutes)**
```
For each planned production order:
1. Verify product has BOM
2. Check material availability for sub-assembly
3. Coordinate with production lead
4. Release orders to manufacturing
```

**Step 6: Send Purchase Orders (10 minutes)**
```
1. Go to Purchasing → Purchase Orders
2. Filter: Status = Draft, Created Today
3. For each PO:
   - Review and finalize
   - Mark as "Ordered"
   - Send to vendor (email, portal, EDI)
```

**Total Time: ~50 minutes per week**

---

### Workflow 2: Handling Rush Order

**Scenario:** Customer needs 50 widgets by Friday (4 days away)

**Step 1: Create Production Order (2 minutes)**
```
1. Navigate to Production → Production Orders → New
2. Product: Widget
3. Quantity: 50
4. Due Date: 2026-02-11 (Friday)
5. Priority: High
6. Save as Draft
```

**Step 2: Run MRP for This Order (1 minute)**
```
1. Navigate to MRP → Requirements
2. Select: Production Order PO-2026-0042
3. Click "Calculate Requirements"
4. View component needs
```

**Step 3: Check Results (2 minutes)**
```
Components Needed:
- PLA Black Filament: 1750 G
  On-Hand: 800 G
  Shortage: 950 G (need 1 KG spool)

- Rubber Feet: 50 EA
  On-Hand: 200 EA
  Shortage: 0 EA ✅

- Poly Mailers: 50 EA
  On-Hand: 25 EA
  Shortage: 25 EA
```

**Step 4: Expedite Materials (10 minutes)**
```
PLA Black Filament (Shortage: 1 KG):
  Option A: Order from fast vendor (1-day delivery) ← BEST
  Option B: Use different color in stock
  Action: Create manual PO to fast vendor, mark RUSH

Poly Mailers (Shortage: 25 EA):
  Option A: Order from Amazon (2-day Prime)
  Option B: Re-use existing mailers from returns
  Action: Order from Amazon, expedite shipping
```

**Step 5: Adjust Production Schedule (5 minutes)**
```
1. Release production order
2. Schedule for Friday morning
3. Ensure filament arrives Wednesday (buffer day)
4. Block printer capacity
5. Notify production team of rush order
```

**Total Time: ~20 minutes**

---

### Workflow 3: Month-End Planning

**Scenario:** Plan material needs for next month

**Step 1: Extended Horizon MRP (5 minutes)**
```
1. Navigate to MRP → Run MRP
2. Planning Horizon: 60 days (2 months)
3. Include Draft Orders: Yes
4. Regenerate: Yes
5. Run MRP
```

**Step 2: Analyze Long-Term Needs (15 minutes)**
```
1. Review planned orders for next month
2. Group by vendor:
   - Vendor A: 5 orders, $1,250 total
   - Vendor B: 3 orders, $450 total
   - Vendor C: 2 orders, $800 total

3. Identify opportunities:
   - Consolidate orders to reduce shipping
   - Negotiate volume discounts
   - Adjust timing to spread cash flow
```

**Step 3: Firm Strategic Orders (10 minutes)**
```
For critical materials:
1. Review lead times (8-15 days typical)
2. Firm all orders due >30 days out
3. Lock in timing for long-lead items
```

**Step 4: Budget Review (10 minutes)**
```
Calculate monthly material spend:
- Total planned purchases: $2,500
- Compare to budget: $3,000 budgeted
- Review variances and adjust plan
```

**Step 5: Supplier Communication (15 minutes)**
```
1. Email Vendor A with forecast: ~$5K next quarter
2. Negotiate better pricing for increased volume
3. Schedule vendor meeting for new products
```

**Total Time: ~55 minutes**

---

## 12. Troubleshooting

### Issue 1: MRP Found No Shortages (but you expect some)

**Symptoms:**
- MRP run shows "0 shortages found"
- You know you need materials

**Causes & Solutions:**

**Cause:** No production orders within planning horizon
```
Solution:
1. Check production orders exist
2. Verify due dates are within next 30 days
3. Include draft orders in MRP settings
```

**Cause:** Production orders have no BOMs
```
Solution:
1. Go to production order
2. Check if product has active BOM
3. Assign BOM if missing
4. Re-run MRP
```

**Cause:** Safety stock not set
```
Solution:
MRP only creates orders for shortages or safety stock needs
1. Set safety stock on critical materials
2. Re-run MRP
```

### Issue 2: Planned Order Quantity Seems Wrong

**Symptoms:**
- Planned order suggests 100 KG but you only need 10 KG

**Causes & Solutions:**

**Cause:** Minimum order quantity set too high
```
Solution:
1. Go to product master (e.g., Filament)
2. Check "Min Order Qty" field
3. Adjust to realistic minimum (e.g., 1 KG)
4. Re-run MRP
```

**Cause:** BOM quantities incorrect
```
Solution:
1. Review BOM for production order
2. Check component quantities
3. Fix BOM (e.g., 100 G not 100 KG)
4. Re-run MRP
```

**Cause:** UOM mismatch (grams vs kilograms)
```
Solution:
1. Check BOM line unit (should be G for filament)
2. Check product unit (should be G for inventory)
3. Verify purchase_uom (KG) and purchase_factor (1000)
4. See Inventory Management guide, Part 7 (UOM system)
```

### Issue 3: MRP Creating Duplicate Orders

**Symptoms:**
- Multiple planned orders for same product
- Dates are same or very close

**Causes & Solutions:**

**Cause:** Multiple production orders need same component
```
Solution:
This is NORMAL behavior.
MRP creates separate planned orders for each demand source.
Action: Consolidate when releasing:
  1. Select all planned orders for same product/vendor
  2. Release together
  3. Creates single PO with combined quantity
```

**Cause:** MRP run multiple times without "Regenerate"
```
Solution:
1. Run MRP with "Regenerate Planned Orders" = Yes
2. This deletes old unfirmed planned orders
3. Creates fresh plan
```

### Issue 4: Can't Release Planned Order

**Symptoms:**
- "Release" button disabled or fails

**Causes & Solutions:**

**Cause:** Order already released
```
Solution:
Check status - if "released", it's already converted
Find created PO/MO using the conversion tracking fields
```

**Cause:** Product doesn't exist
```
Solution:
1. Check product_id is valid
2. Verify product not deleted
3. Re-run MRP to refresh data
```

**Cause:** Missing vendor (for purchase orders)
```
Solution:
Release requires vendor selection
1. Click Release
2. Select vendor from dropdown
3. Confirm
```

**Cause:** Product has no BOM (for production orders)
```
Solution:
If product has has_bom=True but no active BOM:
1. Create BOM for product
2. Set as active
3. Try release again
```

### Issue 5: MRP Run Failed

**Symptoms:**
- MRP status shows "failed"
- Error message in results

**Causes & Solutions:**

**Cause:** Circular BOM reference
```
Error: "Circular BOM detected: Product A → Product B → Product A"
Solution:
1. Review BOMs for products mentioned
2. Remove circular reference
3. BOMs should be hierarchical (tree), not circular (loop)
```

**Cause:** Missing product data
```
Error: "Product 123 not found"
Solution:
1. Check production orders for invalid product_id
2. Fix or delete invalid orders
3. Re-run MRP
```

**Cause:** Database connection issue
```
Error: "Database timeout" or "Connection failed"
Solution:
1. Check database is running
2. Verify connection in backend logs
3. Retry MRP run
```

---

## 13. Quick Reference

### MRP Calculation Formula

```
Net Shortage = Gross Requirement - On-Hand - Incoming + Safety Stock

If Net Shortage > 0:
  - Create Planned Order (Purchase or Production)
  - Quantity = max(Net Shortage, Min Order Qty)
  - Due Date = When material needed
  - Start Date = Due Date - Lead Time
```

### Planned Order Lifecycle

```
[MRP Run] → PLANNED → FIRMED → RELEASED → CANCELLED
             ↓          ↓         ↓
        Auto-deleted  Locked   Converted to PO/MO
        by next MRP  by user
```

### Key Terminology

| Term | Definition |
|------|------------|
| **Planning Horizon** | How far ahead MRP looks (days) |
| **Gross Requirement** | Total component qty needed before netting |
| **Net Requirement** | Shortage after considering inventory |
| **Planned Order** | MRP's suggestion to order material |
| **Firmed Order** | User-approved planned order (locked) |
| **Released Order** | Converted to actual PO or MO |
| **BOM Explosion** | Recursive expansion of multi-level BOMs |
| **Pegging** | Tracing demand back to source order |
| **Lead Time** | Days from order to receipt |
| **Safety Stock** | Minimum buffer inventory |
| **Reorder Point** | Level that triggers new order |

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/mrp/run` | POST | Run MRP calculation |
| `/api/v1/mrp/runs` | GET | List MRP run history |
| `/api/v1/mrp/planned-orders` | GET | List planned orders |
| `/api/v1/mrp/planned-orders/{id}` | GET | Get planned order details |
| `/api/v1/mrp/planned-orders/{id}/firm` | POST | Firm a planned order |
| `/api/v1/mrp/planned-orders/{id}/release` | POST | Release to PO/MO |
| `/api/v1/mrp/planned-orders/{id}` | DELETE | Cancel planned order |
| `/api/v1/mrp/requirements` | GET | View material requirements |
| `/api/v1/mrp/supply-demand/{product_id}` | GET | Supply/demand timeline |
| `/api/v1/mrp/explode-bom/{product_id}` | GET | Explode BOM manually |

### Status Values

**MRP Run Status:**
- `running` - In progress
- `completed` - Successfully finished
- `failed` - Error occurred
- `cancelled` - User cancelled

**Planned Order Status:**
- `planned` - MRP suggestion, can be auto-deleted
- `firmed` - User confirmed, locked
- `released` - Converted to actual order
- `cancelled` - No longer needed

**Planned Order Type:**
- `purchase` - Raw material or purchased part (has_bom=False)
- `production` - Manufactured sub-assembly (has_bom=True)

### Common Calculations

**Days of Supply:**
```
Days of Supply = Available Inventory / Average Daily Demand
```

**Safety Stock:**
```
Safety Stock = Daily Usage × Lead Time × Buffer Factor (1.5-2.0)
```

**Reorder Point:**
```
Reorder Point = (Daily Usage × Lead Time) + Safety Stock
```

**Lead Time Offset:**
```
Start Date = Due Date - Lead Time Days
```

---

## Related Guides

- **[Inventory Management](inventory-management.md)** - Managing inventory levels, safety stock, and reorder points
- **[Manufacturing](manufacturing.md)** - Production orders, BOMs, and routing operation materials
- **[Purchasing](purchasing.md)** - Converting planned purchase orders to actual POs and receiving
- **[Sales & Quotes](sales-and-quotes.md)** - Understanding how sales orders drive production and MRP demand

---

**Need Help?**
- Consult the [API Reference](../API-REFERENCE.md) for integration details
- Report issues on [GitHub](https://github.com/Blb3D/filaops/issues)
- See [Getting Started](getting-started.md) for initial setup

---

*Last Updated: February 2026 | FilaOps v3.0.0*
