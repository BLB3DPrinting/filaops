# Manufacturing Guide

This guide covers FilaOps' manufacturing system for 3D print production, including production orders, BOMs, routings, work centers, and quality control.

## Overview

FilaOps manufacturing system manages the entire production workflow:

- **Production Orders** - Work orders to manufacture products
- **BOMs (Bill of Materials)** - What components/materials are needed
- **Routings** - How to make the product (process steps)
- **Work Centers** - Where production happens (printer pools, stations)
- **Resources** - Individual machines/printers
- **Operations** - Individual steps in the manufacturing process
- **Quality Control** - QC inspection and approval workflow

**Manufacturing Flow:**
```
Sales Order → Production Order → Allocate Materials →
Release to Production → Execute Operations → QC Inspection →
Receive Finished Goods → Ship to Customer
```

---

## Part 1: Production Orders

### What is a Production Order?

A **Production Order** (also called **Manufacturing Order** or **Work Order**) is an instruction to manufacture a specific quantity of a product.

**Production orders can be created from:**
- Sales orders (make-to-order)
- MRP planned orders (make-to-stock)
- Manual entry (ad-hoc production)

**Each production order tracks:**
- What to make (product)
- How much to make (quantity)
- When it's due (due date)
- How to make it (BOM + routing)
- Current status (draft → in_progress → completed)
- Material consumption
- Labor hours
- Costs

### Production Order Statuses

| Status | Meaning | Next Actions |
|--------|---------|--------------|
| **draft** | Created but not ready | Review and release |
| **released** | Materials allocated, ready to schedule | Assign to work center |
| **scheduled** | Assigned to printer/work center, queued | Start production |
| **in_progress** | Job actively running | Monitor, complete |
| **completed** | Manufacturing finished, awaiting QC | QC inspection |
| **qc_hold** | QC failed, needs decision | Scrap or rework |
| **closed** | Parts accepted, inventory updated | Archive |
| **cancelled** | Order terminated | No further action |
| **on_hold** | Production paused | Resume or cancel |

### Production Order Lifecycle

**Standard Flow:**
```
draft → released → scheduled → in_progress → completed → closed
```

**QC Flow (if required):**
```
completed → [QC pending] → [QC passed] → closed
          ↓
    [QC failed] → qc_hold → (scrap + remake) OR (rework)
```

### Creating Production Orders

**Navigation:** Manufacturing → Production Orders → **+ New Production Order**

**Step 1: Product Selection**

```
Product: Select from dropdown
  - Shows products with procurement_type = 'make'
  - Must have BOM and/or Routing

Quantity: 10 (units to produce)

Source: manual (options: manual, sales_order, mrp_planned)
Order Type: MAKE_TO_ORDER (options: MAKE_TO_ORDER, MAKE_TO_STOCK)
  - MTO: For specific customer order, ships when complete
  - MTS: For inventory stock, sits on shelf until sold
```

**Step 2: BOM Selection**

```
BOM: BOM-001 v1 (Bill of Materials)
  - Auto-selects active BOM for product
  - Shows material requirements
  - Example:
    Line 1: 450 G PLA Basic Black (filament)
    Line 2: 1 EA M3 Insert (hardware)
    Line 3: 1 EA Poly Bag (packaging)
```

**Step 3: Routing Selection**

```
Routing: ROUTING-001 v1 (Manufacturing Process)
  - Auto-selects active routing for product
  - Shows operations sequence
  - Example:
    OP-10: Print (FDM Pool, 2.5 hrs)
    OP-20: Insert Hardware (Assembly, 5 min)
    OP-30: QC Inspection (QC Station, 5 min)
    OP-40: Pack (Shipping, 3 min)
```

**Step 4: Scheduling**

```
Due Date: 2026-02-15 (when customer needs it)
Priority: 3 (1=highest, 5=lowest)

Assigned To: (operator name, optional)
```

**Step 5: Sales Order Link** (optional)

```
Sales Order: SO-2026-0042 (links to customer order)
  - Auto-fills when creating from sales order
  - Tracks which customer order this fulfills
```

**Step 6: Submit**

Click **Create Production Order** → PO number generated (e.g., `PO-2026-0001`)

**✅ Result:** Production order created with status "draft"

### Releasing Production Orders

**From "draft" → "released":**

When you release a production order:
1. System validates BOM and routing exist
2. **Inventory Allocated** - Materials reserved:
   ```
   450 G PLA Basic Black
   1 EA M3 Insert
   1 EA Poly Bag
   ```
   Available inventory reduced by allocated amounts
3. Operations copied from routing to production order
4. Production order ready for scheduling
5. Status changes to "released"

**Navigation:** Manufacturing → Production Orders → Select PO → **Release Order**

**⚠️ Cannot release if:**
- Insufficient inventory (shows shortage)
- No BOM or routing assigned
- Product inactive

**If insufficient inventory:**
- Option 1: Reduce quantity
- Option 2: Run MRP to generate purchase orders
- Option 3: Override (requires approval)

### Executing Production

**From "released" → "in_progress" → "completed":**

**Step 1: Start Production**

**Navigation:** Manufacturing → Production Orders → Select PO → **Start Production**

- Assign to specific resource (printer)
- Record actual start time
- Status → "in_progress"

**Step 2: Execute Operations**

Each operation tracks separately:
```
OP-10: Print
  Status: pending → running → complete
  Planned Time: 2.5 hrs
  Actual Time: 2.6 hrs (tracked)
  Materials Used: 450 G PLA (recorded)
  Spool Used: SPOOL-PLA-BLK-010 (traceability)

OP-20: Insert Hardware
  Status: pending → running → complete
  Planned Time: 5 min
  Actual Time: 4 min

OP-30: QC Inspection
  Status: pending → running → complete
  QC Result: Passed ✓

OP-40: Pack
  Status: pending → running → complete
  Materials Used: 1 EA Poly Bag
```

**Step 3: Complete Production**

**Navigation:** Manufacturing → Production Orders → Select PO → **Complete Order**

- Mark all operations complete
- Record actual end time
- Enter quantity completed: 10 EA
- Enter quantity scrapped: 0 EA
- Status → "completed"

### Quality Control

**QC Status values:**
- **not_required** - Auto-pass (trusted products, internal orders)
- **pending** - Awaiting QC assignment
- **in_progress** - Inspector reviewing parts
- **passed** - Parts accepted ✓
- **failed** - Parts rejected ✗
- **waived** - Failed but accepted anyway (document reason)

**QC Workflow:**

1. **Production Completes** → QC Status: "pending"
2. **Assign QC Inspector** → QC Status: "in_progress"
3. **Inspector Reviews Parts:**
   - Check dimensions, finish, strength
   - Test functionality
   - Document findings in notes
4. **Inspector Passes/Fails:**
   - **Pass** → QC Status: "passed", PO ready to close
   - **Fail** → QC Status: "failed", PO Status: "qc_hold"

**If QC Fails:**

**Option 1: Scrap and Remake**
```
1. Mark PO as "scrapped"
2. Enter scrap reason: "Poor layer adhesion"
3. Create remake order:
   - Links to original PO (remake_of_id)
   - Same quantity, same product
   - Starts as "draft"
```

**Option 2: Rework**
```
1. Keep PO in "qc_hold"
2. Add rework operation
3. Re-execute problematic step
4. Re-submit to QC
```

**Option 3: Waive (Accept as-is)**
```
1. QC Status → "waived"
2. Document reason in QC notes: "Cosmetic issue only, customer accepts"
3. PO ready to close
```

### Closing Production Orders

**From "completed" → "closed":**

**Requirements:**
- ✅ All operations complete
- ✅ QC passed (or not required/waived)
- ✅ Quantity completed ≥ Quantity ordered

**Closing process:**

**Navigation:** Manufacturing → Production Orders → Select PO → **Close Order**

**System actions:**
1. **Material Consumption** - Inventory transactions:
   ```
   -450 G PLA Basic Black ($11.25 COGS)
   -1 EA M3 Insert ($0.25 COGS)
   -1 EA Poly Bag ($0.10 COGS)
   ────────────────────────────────
   Total Material Cost: $11.60
   ```

2. **Finished Goods Receipt** - Inventory transaction:
   ```
   +10 EA Phone Stand
   Cost: $50.00 (material $11.60 + labor $3.40/unit)
   Value: $50.00
   ```

3. **Allocations Released** - Available inventory updated

4. **Sales Order Updated** (if linked):
   - SO Status → "ready_to_ship"
   - Customer notified (if configured)

5. **Cost Accounting** - COGS recorded to GL

**✅ Result:** Production order closed, finished goods in inventory

---

## Part 2: Bill of Materials (BOM)

### What is a BOM?

A **Bill of Materials** defines **what components** are needed to make a product.

**BOM contains:**
- List of components (materials, hardware, packaging)
- Quantities required per unit
- When to consume (production vs shipping)
- Cost estimates

**Example BOM:**
```
Product: Phone Stand
BOM: BOM-001 v1

Line 1: PLA Basic Black - 450 G (consume: production)
Line 2: M3 Heat Set Insert - 2 EA (consume: production)
Line 3: Poly Bag - 1 EA (consume: shipping)
Line 4: Instruction Card - 1 EA (consume: shipping)
────────────────────────────────────────────────
Total Cost: $12.25 per unit
```

### Creating BOMs

**Navigation:** Manufacturing → BOMs → **+ New BOM**

**Step 1: BOM Header**

```
Product: Phone Stand (select product)
Code: BOM-STAND-001 (optional identifier)
Name: Phone Stand Assembly (descriptive)

Version: 1 (auto-incremented)
Revision: 1.0 (engineering revision)
Active: ✓ (only one active BOM per product)

Assembly Time: 10 minutes (manual assembly time)
Effective Date: 2026-02-01 (when to start using)

Notes: "Updated to use stronger insert size"
```

**Step 2: Add BOM Lines**

Click **+ Add Line** for each component:

**Line 1 - Filament:**
```
Component: MAT-PLA-BASIC-BLK
Quantity: 450
Unit: G (grams)
Consume Stage: production (consumed during print)
Scrap Factor: 5% (waste/support material)
Notes: "Print with 0.2mm layer height"
```

**Line 2 - Hardware:**
```
Component: INSERT-M3
Quantity: 2
Unit: EA (each)
Consume Stage: production (installed during assembly)
Scrap Factor: 0% (no waste)
```

**Line 3 - Packaging:**
```
Component: BAG-POLY-4X6
Quantity: 1
Unit: EA
Consume Stage: shipping (consumed when packing order)
Scrap Factor: 0%
```

**Step 3: Review Costs**

System calculates total cost:
```
Line 1: 450 G × $0.025/G × 1.05 = $11.81 (with 5% scrap)
Line 2: 2 EA × $0.15/EA = $0.30
Line 3: 1 EA × $0.10/EA = $0.10
────────────────────────────────────────────────
Total Material Cost: $12.21
Assembly Time: 10 min × $24/hr = $4.00
────────────────────────────────────────────────
Total BOM Cost: $16.21 per unit
```

**Step 4: Save**

Click **Create BOM** → BOM is saved and can be assigned to production orders

### BOM Versions

**Multiple versions per product:**
- Version 1: Original design
- Version 2: Cost-reduced (cheaper material)
- Version 3: Strength-improved (thicker walls)

**Only one active BOM per product** - the active BOM is used for new production orders.

**Version control:**
- When editing BOM, option to "Create New Version"
- Previous versions archived (historical record)
- Production orders reference specific BOM version (locked)

### Consume Stages

**production** - Consumed during manufacturing:
- Filament/materials (used in print)
- Hardware (installed in assembly)
- Labels (applied to product)

**shipping** - Consumed during packing/shipment:
- Boxes
- Poly bags
- Packing material
- Shipping labels

**Why separate?**
- Accurate COGS timing (production COGS vs shipping expense)
- Inventory allocation (production materials reserved, shipping materials allocated at ship time)
- GL accounting (different expense accounts)

### Cost-Only Lines

**For costing without inventory consumption:**

```
Line 5: Machine Time - 2.5 HR @ $10/HR = $25.00
  is_cost_only: ✓
  (Includes in BOM cost, doesn't allocate inventory)
```

**Use cases:**
- Machine depreciation
- Overhead allocation
- Energy costs
- Setup time

---

## Part 3: Routings

### What is a Routing?

A **Routing** defines **how to make** a product - the sequence of operations.

**Routing contains:**
- List of operations (Print, QC, Pack, etc.)
- Work center assignments
- Time estimates
- Material requirements per operation
- Operation dependencies

**Example Routing:**
```
Product: Phone Stand
Routing: ROUTING-001 v1

OP-10: Print (Work Center: FDM-POOL)
  Time: 2.5 hrs
  Material: 450 G PLA Basic Black

OP-20: Install Inserts (Work Center: ASSEMBLY)
  Time: 5 min
  Material: 2 EA M3 Inserts
  Dependency: After OP-10

OP-30: QC Inspection (Work Center: QC)
  Time: 5 min
  Dependency: After OP-20

OP-40: Pack (Work Center: SHIPPING)
  Time: 3 min
  Material: 1 EA Poly Bag
  Dependency: After OP-30
────────────────────────────────────────────────
Total Time: 2 hrs 43 min
Total Cost: $27.50 (material + labor)
```

### Creating Routings

**Navigation:** Manufacturing → Routings → **+ New Routing**

**Step 1: Routing Header**

```
Product: Phone Stand
Code: ROUTING-STAND-001
Name: Standard Phone Stand Process

Version: 1
Revision: 1.0
Active: ✓

Effective Date: 2026-02-01
Notes: "Optimized for Bambu X1C printers"
```

**Step 2: Add Operations**

Click **+ Add Operation** for each step:

**Operation 1 - Print:**
```
Sequence: 10
Operation Code: PRINT
Operation Name: 3D Print Base

Work Center: FDM-POOL (printer pool)

Setup Time: 5 min (bed prep, filament load)
Run Time: 150 min (2.5 hrs actual print)
Wait Time: 10 min (cool down)
Move Time: 5 min (remove from bed)

Units per Cycle: 1 (1 part per print)
Scrap Rate: 5% (expected failures)

Materials:
  - PLA Basic Black: 450 G per unit
```

**Operation 2 - Install Inserts:**
```
Sequence: 20
Operation Code: ASSEMBLE
Operation Name: Install Heat Set Inserts

Work Center: ASSEMBLY

Setup Time: 0 min
Run Time: 5 min
Wait Time: 0 min
Move Time: 0 min

Predecessor Operation: OP-10 (must complete print first)
Can Overlap: No

Materials:
  - M3 Insert: 2 EA per unit
```

**Operation 3 - QC:**
```
Sequence: 30
Operation Code: QC
Operation Name: Quality Inspection

Work Center: QC

Setup Time: 0 min
Run Time: 5 min

Predecessor Operation: OP-20
```

**Operation 4 - Pack:**
```
Sequence: 40
Operation Code: PACK
Operation Name: Package Product

Work Center: SHIPPING

Setup Time: 0 min
Run Time: 3 min

Predecessor Operation: OP-30

Materials:
  - Poly Bag: 1 EA per unit
```

**Step 3: Review Totals**

System calculates:
```
Total Setup Time: 5 min
Total Run Time: 163 min (2 hrs 43 min)
Total Cost: $27.50 (based on work center rates)
```

**Step 4: Save**

Click **Create Routing** → Routing saved and ready for production orders

### Routing Templates

**Create reusable routing templates:**

```
Template: TRUE (no product assigned)
Code: TEMPLATE-STANDARD-PRINT
Name: Standard 3D Print Process

Operations:
  OP-10: Print (FDM-POOL)
  OP-20: QC (QC)
  OP-30: Pack (SHIPPING)

Use: Assign to multiple products with similar process
```

**Assign template to product:**
1. Navigate to product
2. Select "Copy from Template"
3. Choose template
4. Routing created with operations pre-filled
5. Customize as needed

---

## Part 4: Work Centers & Resources

### What is a Work Center?

A **Work Center** is a logical production area where operations are performed.

**Examples:**
- **FDM-POOL** - Pool of FDM 3D printers
- **POST-PRINT** - Post-processing station (sanding, painting)
- **ASSEMBLY** - Manual assembly station
- **QC** - Quality control inspection station
- **SHIPPING** - Packing and shipping area

**Work centers contain:**
- Resources (individual machines/printers)
- Capacity (hours per day)
- Hourly rates (for cost calculation)
- Scheduling priority

### Creating Work Centers

**Navigation:** Manufacturing → Work Centers → **+ New Work Center**

```
Code: FDM-POOL
Name: FDM 3D Printer Pool
Description: "Pool of Bambu Lab FDM printers"

Center Type: machine (options: machine, station, production)
  - machine: Has resources (printers)
  - station: Single workstation
  - production: Generic production area

Capacity: 160 hours/day (8 printers × 20 hrs/day each)

Costing:
  Machine Rate: $8.00/hr (depreciation, maintenance)
  Labor Rate: $16.00/hr (operator wages)
  Overhead Rate: $4.00/hr (facility, utilities)
  ──────────────────────────────────────────────
  Total Rate: $28.00/hr

Is Bottleneck: ✓ (constrains overall throughput)
Scheduling Priority: 1 (highest)

Active: ✓
```

### What is a Resource?

A **Resource** is an individual machine or printer within a work center.

**Example:**
```
Work Center: FDM-POOL
  Resource 1: Leonardo (X1C)
  Resource 2: Donatello (X1C)
  Resource 3: Michelangelo (P1S)
  Resource 4: Raphael (P1S)
```

### Creating Resources

**Navigation:** Manufacturing → Work Centers → Select WC → **+ Add Resource**

```
Code: LEONARDO
Name: Leonardo (X1C Printer)

Work Center: FDM-POOL

Machine Type: X1C
Serial Number: 01P00A123456789
Printer Class: enclosed (required for ABS/ASA/PC)

Bambu Integration:
  Device ID: 01P00A123456789
  IP Address: 192.168.1.100

Capacity Override: 20 hrs/day (from WC default)

Status: available (options: available, busy, maintenance, offline)
Active: ✓
```

**Printer Classes:**
- **open** - Open frame (A1, A1 Mini) - PLA, PETG, TPU only
- **enclosed** - Enclosed chamber (P1S, X1C) - ABS, ASA, PC capable

**Scheduling logic:**
- ABS/ASA/PC orders → Only assigned to enclosed printers
- PLA/PETG orders → Can use any printer

---

## Part 5: Production Scheduling

### Scheduling Overview

**FilaOps scheduling approach:**

1. **Work Center Assignment** - Operations assigned to work centers
2. **Resource Dispatch** - Work centers dispatch to specific resources
3. **Priority-Based** - Higher priority orders scheduled first
4. **Capacity-Aware** - Respects work center capacity limits

### Manual Scheduling

**Assign production order to printer:**

**Navigation:** Manufacturing → Production Orders → Select PO → **Assign to Printer**

```
Operation: OP-10 Print
Work Center: FDM-POOL
Resource: Leonardo (X1C)

Scheduled Start: 2026-02-08 10:00 AM
Scheduled End: 2026-02-08 12:30 PM (2.5 hrs)

Status: scheduled → ready to start
```

### Automatic Scheduling (via MRP)

**MRP generates planned orders** with due dates:

1. MRP calculates requirements
2. Creates planned production orders
3. Assigns due dates based on lead time
4. User reviews and converts to production orders
5. Scheduler assigns to work centers/resources

**See:** [MRP Guide](mrp.md) for planning details

### Production Schedule View

**Navigation:** Manufacturing → Schedule

**Gantt chart showing:**
- All production orders
- Resource assignments
- Timeline (hourly/daily/weekly)
- Bottlenecks highlighted
- Late orders flagged

**Drag-and-drop rescheduling:**
- Move orders between resources
- Adjust start times
- Re-sequence priorities

---

## Part 6: Scrap and Rework

### Recording Scrap

**During production:**

**Navigation:** Manufacturing → Production Orders → Select PO → **Record Scrap**

```
Quantity Scrapped: 2 EA (out of 10 ordered)
Scrap Reason: adhesion (dropdown)
  - adhesion (bed adhesion failure)
  - layer_shift (layer misalignment)
  - stringing (excess material stringing)
  - warping (part warping/curling)
  - nozzle_clog (clogged nozzle)
  - other (describe in notes)

Notes: "First layer failed due to dirty bed"

Update Quantity Ordered:
  Option 1: Keep 10 EA ordered (make 8 good + 2 scrapped)
  Option 2: Increase to 12 EA ordered (make 10 good + 2 scrapped)
```

**Result:**
- Scrap recorded in quantity_scrapped
- Material cost written off
- Scrap reason tracked for analysis

### Creating Remake Orders

**After scrap:**

**Navigation:** Manufacturing → Production Orders → Select scrapped PO → **Create Remake**

```
Remake for: PO-2026-0005 (links to original)
Quantity: 2 EA (replace scrapped units)
Priority: 1 (urgent - customer waiting)

Same product, same BOM, same routing
Status: draft (ready to release)
```

**Result:**
- Remake order created
- Links to original PO (remake_of_id)
- Tracks replacement production

### Scrap Analysis

**Navigation:** Manufacturing → Reports → **Scrap Analysis**

**Shows:**
```
Scrap by Reason (Last 30 Days):

Adhesion:       15 units (35%) → Clean beds more often
Layer Shift:    10 units (23%) → Check belt tension
Warping:         8 units (19%) → Increase bed temp for ABS
Nozzle Clog:     6 units (14%) → Preventive maintenance
Stringing:       4 units (9%)  → Adjust retraction settings
────────────────────────────────────────────────
Total:          43 units (100%)

Scrap Rate: 4.3% (43 scrapped / 1000 completed)
Target: < 3%
```

---

## Part 7: Integration with Sales Orders

### Creating Production from Sales Order

**Method 1: Manual Creation**

**Navigation:** Sales → Sales Orders → Select SO → **Create Production Order**

```
Sales Order: SO-2026-0042
Product: Phone Stand
Quantity: 10 EA

Auto-fills:
  - Links sales_order_id
  - Sets order_type: MAKE_TO_ORDER
  - Sets due_date from SO due_date
  - Sets priority from SO rush_level
```

**Method 2: Automatic from MRP**

MRP analyzes sales orders → Creates planned production orders → User converts to production orders

### Production Status Updates Sales Order

**Automatic status sync:**

```
PO Status          →  SO Status
────────────────────────────────────────
released           →  confirmed
in_progress        →  in_production
completed (QC pass)→  ready_to_ship
closed             →  (no change - ready to ship)
cancelled          →  on_hold (with notification)
```

---

## Part 8: Manufacturing Reports

### Production Order List

**Navigation:** Manufacturing → Production Orders

**Filter by:**
- Status (all, draft, released, in_progress, completed, closed)
- Date range
- Product
- Work center
- Due date

**Columns:**
- PO Number
- Product
- Quantity (Ordered / Completed / Scrapped)
- Status
- Due Date
- Priority
- Assigned To

### Work Center Utilization

**Navigation:** Manufacturing → Reports → **Work Center Utilization**

**Shows:**
```
Work Center: FDM-POOL
Period: Last 7 Days

Total Capacity: 1,120 hrs (160 hrs/day × 7 days)
Scheduled: 945 hrs (84%)
Actual: 920 hrs (82%)
Idle: 200 hrs (18%)

Efficiency: 97% (920 actual / 945 scheduled)
Utilization: 82% (920 actual / 1,120 capacity)

Target Utilization: 85%
Status: ✓ Good
```

### Production Costs

**Navigation:** Manufacturing → Reports → **Production Costs**

**Shows:**
```
Period: Last 30 Days

Total Production Orders: 125
Total Units Produced: 1,450 EA

Material Cost: $18,250 (avg $12.59/unit)
Labor Cost: $5,800 (avg $4.00/unit)
Overhead: $2,900 (avg $2.00/unit)
────────────────────────────────────────
Total Cost: $26,950 (avg $18.59/unit)

Scrap Cost: $1,150 (4.3% of material)
```

---

## Part 9: Best Practices

### BOM Management

✅ **Do:**
- Keep one active BOM per product
- Include all materials (filament, hardware, packaging)
- Set realistic scrap factors (5-10% for filament)
- Separate production vs shipping materials
- Update costs when vendor prices change

❌ **Don't:**
- Forget to include packaging in BOM
- Use outdated material costs
- Set scrap factor too low (causes shortages)
- Have multiple active BOMs per product

### Routing Design

✅ **Do:**
- Break down into logical operations
- Set realistic time estimates (add buffer)
- Define clear operation dependencies
- Assign correct work centers
- Include QC steps where needed

❌ **Don't:**
- Create overly detailed routings (too many ops)
- Forget setup and move time
- Skip QC for critical products
- Assign operations to wrong work centers

### Production Planning

✅ **Do:**
- Release orders in batches (not one-by-one)
- Schedule high-priority orders first
- Monitor bottleneck work centers
- Plan for material lead times
- Use MRP for make-to-stock items

❌ **Don't:**
- Release without checking inventory
- Ignore capacity constraints
- Schedule conflicting operations
- Forget to update due dates

### Quality Control

✅ **Do:**
- Require QC for customer-facing products
- Document QC failures with photos/notes
- Analyze scrap reasons monthly
- Train operators on quality standards
- Set clear pass/fail criteria

❌ **Don't:**
- Waive QC failures without documentation
- Ignore recurring scrap reasons
- Ship failed parts (even if "close enough")
- Skip QC to save time

---

## Part 10: Common Workflows

### Workflow 1: Simple Make-to-Order

```
1. Sales order received: 10 Phone Stands, due Feb 15
2. Create production order from SO
   - Product: Phone Stand
   - Quantity: 10
   - Due: Feb 15
   - Status: draft
3. Review BOM and routing (auto-assigned)
4. Release order:
   - Allocate materials (450 G PLA × 10 = 4500 G)
   - Status: released
5. Assign to printer Leonardo (X1C)
   - Status: scheduled
6. Start production:
   - Leonardo starts print
   - Status: in_progress
7. Complete operations:
   - OP-10 Print: Complete (2.5 hrs)
   - OP-20 Assembly: Complete (5 min)
   - OP-30 QC: Passed ✓
   - OP-40 Pack: Complete
   - Status: completed
8. Close production order:
   - Materials consumed
   - Finished goods received (+10 EA)
   - Status: closed
9. Ship to customer:
   - SO status: shipped
```

**Time estimate:** 3-4 hours (print time + operations)

### Workflow 2: Batch Production (Make-to-Stock)

```
1. MRP suggests: Make 100 Brackets for inventory
2. Create production order:
   - Product: Bracket
   - Quantity: 100
   - Order Type: MAKE_TO_STOCK
   - Due: End of week
3. Release order (allocate 45 KG filament)
4. Split into 10 batches:
   - PO-001-A: 10 units (Leonardo)
   - PO-001-B: 10 units (Donatello)
   - ...
   - PO-001-J: 10 units (Raphael)
5. Schedule across printer pool (parallel production)
6. Monitor progress:
   - 5 complete
   - 3 in progress
   - 2 queued
7. QC batch inspect (sample 10%)
8. Close all orders:
   - 100 units to inventory
   - Ready for sale
```

**Time estimate:** 1 day (parallel production)

### Workflow 3: Scrap and Remake

```
1. Production order in progress: 10 Phone Stands
2. Print completes, QC inspection finds issues:
   - 2 units: Poor layer adhesion (scrap)
   - 8 units: Pass ✓
3. Record scrap:
   - Quantity Scrapped: 2 EA
   - Reason: adhesion
   - Cost: $25 written off
4. Create remake order:
   - Quantity: 2 EA (replace scrapped)
   - Links to original PO
   - Priority: 1 (urgent)
5. Release and produce remake:
   - Clean bed thoroughly
   - Increase bed temp
   - Complete successfully
6. Close both orders:
   - Original: 8 good + 2 scrapped
   - Remake: 2 good
   - Total delivered: 10 EA
```

---

## Part 11: Advanced Features

### Multi-Operation Parallel Processing

**Operations can overlap:**

```
Operation 1: Print Part A (3 hrs)
Operation 2: Print Part B (2 hrs) [can start immediately]
Operation 3: Assemble A+B (10 min) [depends on Op1 and Op2]

Timeline:
0:00 - Start Op1 and Op2 simultaneously
2:00 - Op2 completes
3:00 - Op1 completes, start Op3
3:10 - Op3 completes, order done

Total Time: 3 hrs 10 min (vs 5 hrs 10 min sequential)
```

### Operation-Level Material Tracking

**Materials consumed per operation:**

```
OP-10: Print
  Material: 450 G PLA Basic Black
  Consumed: At operation complete
  Cost: $11.25

OP-40: Pack
  Material: 1 EA Poly Bag
  Consumed: At operation complete
  Cost: $0.10

Total Material Cost: $11.35
(Allocated at release, consumed at operation complete)
```

### Resource-Specific Routing

**Different routings for different resources:**

```
Product: Large Part

Routing A (X1C Printer - Large bed):
  OP-10: Print (1 unit per print)
  Time: 8 hrs

Routing B (P1S Printer - Standard bed):
  OP-10: Print Part 1 (4 hrs)
  OP-20: Print Part 2 (4 hrs)
  OP-30: Glue Assembly (10 min)
  Time: 8 hrs 10 min

Use Routing A for X1C, Routing B for P1S
```

---

## Next Steps

Now that you understand manufacturing, explore these related guides:

| Guide | Learn About |
|-------|-------------|
| **Inventory Management** | Material tracking, spool management, stock levels |
| **MRP** | Material requirements planning, automatic order generation |
| **Sales & Quotes** | How sales orders create production orders |
| **Accounting** | COGS calculation, production costing, variance analysis |

## Quick Reference

### Production Order Status Flow

```
draft → released → scheduled → in_progress → completed → closed
                                                ↓
                                           qc_hold → scrap + remake
```

### QC Status Values

- `not_required` - Auto-pass
- `pending` - Awaiting QC
- `in_progress` - Under inspection
- `passed` - Accepted ✓
- `failed` - Rejected ✗
- `waived` - Accepted with notes

### Common Scrap Reasons

- adhesion - Bed adhesion failure
- layer_shift - Layer misalignment
- stringing - Excess material
- warping - Part curling
- nozzle_clog - Nozzle blockage

### Keyboard Shortcuts

- `n` - New production order
- `r` - Release order
- `s` - Start production
- `c` - Complete order
- `/` - Search

---

**🎉 Congratulations!** You now understand the complete FilaOps manufacturing system. Create your first production order and see how BOMs, routings, and work centers come together!
