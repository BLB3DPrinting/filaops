# Purchasing Guide

This guide covers FilaOps' purchasing system for managing vendors, purchase orders, and inventory receiving.

## Overview

FilaOps purchasing system handles the complete procurement workflow:

- **Vendors** - Manage supplier information and terms
- **Purchase Orders** - Create and track orders to vendors
- **Receiving** - Record incoming inventory and update stock levels
- **Documents** - Attach invoices, packing slips, receipts
- **MRP Integration** - Automatic PO generation from material requirements
- **Cost Tracking** - Update product costs from actual purchases

**Purchasing Flow:**
```
Reorder Point Triggered → Create Purchase Order → Send to Vendor →
Vendor Ships → Receive Inventory → Update Costs → Close PO
```

---

## Part 1: Vendors

### What is a Vendor?

A **Vendor** (also called **Supplier**) is a company you purchase materials, components, or supplies from.

**Vendor information includes:**
- Contact details (name, email, phone, website)
- Address (shipping/billing)
- Business terms (payment terms, lead time)
- Performance tracking (rating, lead time)
- Account information

### Creating Vendors

**Navigation:** Purchasing → Vendors → **+ New Vendor**

**Step 1: Basic Information**

```
Code: VND-001 (auto-generated or manual)
Name: 3D Filament Warehouse

Contact Name: John Smith
Email: orders@3dfilament.com
Phone: (555) 123-4567
Website: https://www.3dfilament.com
```

**Step 2: Address**

```
Address Line 1: 123 Industrial Pkwy
Address Line 2: Suite 200
City: Springfield
State: IL
Postal Code: 62701
Country: USA
```

**Step 3: Business Terms**

```
Payment Terms: Net 30 (options: COD, Net 30, Net 60, Upon Receipt)
Account Number: ACCT-12345 (your account with them)
Tax ID: 12-3456789 (vendor's tax ID)

Lead Time (days): 7 (average shipping time)
```

**Step 4: Performance Tracking**

```
Rating: 4.5 (1.0-5.0 scale)
  - 5.0 = Excellent (fast, reliable, quality)
  - 4.0 = Good
  - 3.0 = Average
  - 2.0 = Below Average
  - 1.0 = Poor (slow, unreliable)

Notes:
"Reliable vendor for PLA and PETG. Ships same-day if ordered before 2 PM EST.
Occasional backorders on specialty colors. Good customer service."
```

**Step 5: Save**

Click **Create Vendor** → Vendor is created and ready for purchase orders

**✅ Result:** Vendor code generated (e.g., `VND-001`)

### Vendor List View

**Navigation:** Purchasing → Vendors

**Columns:**
- Vendor Code (VND-001, VND-002, etc.)
- Name
- Contact Email
- Phone
- Lead Time
- Rating
- Active (✓ / ✗)

**Filter by:**
- Active/Inactive
- Search (name, email, code)

**Actions:**
- Click vendor to view details
- Edit vendor information
- Deactivate (don't delete - preserves history)
- Create PO for vendor

### Vendor Detail View

**Sections:**

1. **Vendor Information**
   - All contact/address/terms data
   - Edit button

2. **Purchase Orders**
   - List of all POs for this vendor
   - Filter by status (draft, ordered, received, closed)
   - Total spend

3. **Products Purchased**
   - List of products ordered from this vendor
   - Last purchase price
   - Last order date

4. **Performance Metrics**
   - Total POs
   - Total spend ($ amount)
   - Average lead time
   - On-time delivery rate

---

## Part 2: Purchase Orders

### What is a Purchase Order?

A **Purchase Order (PO)** is an official order document sent to a vendor to purchase items.

**PO contains:**
- Vendor information
- List of items to purchase
- Quantities and prices
- Expected delivery date
- Payment terms
- Shipping instructions

**PO number format:** `PO-2026-001` (auto-generated)

### Purchase Order Statuses

| Status | Meaning | Next Actions |
|--------|---------|--------------|
| **draft** | Being created/edited | Submit to vendor |
| **ordered** | Sent to vendor, awaiting shipment | Wait for shipment |
| **shipped** | Vendor has shipped | Receive inventory |
| **received** | Inventory received, pending close | Review and close |
| **closed** | Completed and archived | No further action |
| **cancelled** | Order cancelled | No further action |

### Purchase Order Lifecycle

**Standard Flow:**
```
draft → ordered → shipped → received → closed
```

**Can skip directly:**
```
draft → received → closed (for immediate purchases)
```

---

## Part 3: Creating Purchase Orders

### Manual PO Creation

**Navigation:** Purchasing → Purchase Orders → **+ New Purchase Order**

**Step 1: Vendor Selection**

```
Vendor: 3D Filament Warehouse (VND-001)
  - Auto-fills vendor details
  - Shows payment terms, lead time

Order Date: 2026-02-08 (today)
Expected Date: 2026-02-15 (order date + vendor lead time)
```

**Step 2: Add Line Items**

Click **+ Add Line** for each product:

**Line 1 - Filament:**
```
Product: MAT-PLA-BASIC-BLK (PLA Basic Black)

Quantity: 5
Purchase Unit: KG (how vendor sells it)
  - Shows product's purchase_uom
  - Can override if needed

Unit Cost: $25.00 ($/KG)
Line Total: $125.00 (5 KG × $25/KG)

Notes: "Request fresh batch, < 30 days old"
```

**Line 2 - Hardware:**
```
Product: INSERT-M3 (M3 Heat Set Inserts)

Quantity: 1000
Purchase Unit: EA
Unit Cost: $0.15
Line Total: $150.00

Notes: "Brass, M3×5mm"
```

**Line 3 - Packaging:**
```
Product: BAG-POLY-4X6 (4"×6" Poly Bags)

Quantity: 500
Purchase Unit: EA
Unit Cost: $0.08
Line Total: $40.00
```

**Step 3: Totals and Shipping**

```
Subtotal: $315.00 (sum of all line totals)

Tax Amount: $0.00 (if applicable)
Shipping Cost: $12.00
───────────────────────────
Total Amount: $327.00
```

**Step 4: Payment and Shipping**

```
Payment Method: Credit Card (options: Card, Check, Wire, COD)
Payment Reference: Last 4: 1234 (optional)

Tracking Number: (leave blank, fill when shipped)
Carrier: (leave blank, fill when shipped)
```

**Step 5: Notes and Documents**

```
Notes: "Rush order - need by Feb 15 for production schedule"

Document URL: (optional Google Drive link to quote/invoice)
```

**Step 6: Submit**

Click **Create Purchase Order** → PO number generated (e.g., `PO-2026-010`)

**✅ Result:** PO created with status "draft"

### Ordering (Sending to Vendor)

**From "draft" → "ordered":**

**Navigation:** Purchasing → Purchase Orders → Select PO → **Mark as Ordered**

**Actions:**
1. Review all line items and totals
2. Click **Mark as Ordered**
3. Enter order date (defaults to today)
4. Status changes to "ordered"

**Next steps:**
- Email PO to vendor (print or export PDF)
- Vendor confirms order
- Wait for shipment notification

**⚠️ Cannot edit after ordering** - must cancel and create new PO

### Vendor Ships Order

**From "ordered" → "shipped":**

**Navigation:** Purchasing → Purchase Orders → Select PO → **Mark as Shipped**

When vendor notifies you of shipment:

```
Shipped Date: 2026-02-10
Tracking Number: 1Z999AA10123456784
Carrier: UPS (options: UPS, FedEx, USPS, DHL, Other)
```

Click **Update** → Status changes to "shipped"

**System actions:**
- Expected date adjusted based on carrier (if tracking integration)
- Notification sent (if configured)

---

## Part 4: Receiving Inventory

### What is Receiving?

**Receiving** is the process of recording inventory when it arrives from the vendor.

**Receiving actions:**
1. Physical inspection of shipment
2. Count quantities received
3. Record receipt in system
4. Update inventory quantities
5. Update product costs
6. Create material spools (for filament)

### Receiving Process

**From "shipped" → "received":**

**Navigation:** Purchasing → Purchase Orders → Select PO → **Receive Inventory**

**Step 1: Verify Shipment**

```
PO Number: PO-2026-010
Vendor: 3D Filament Warehouse
Expected Date: 2026-02-15
Arrived Date: 2026-02-13 (✓ early!)

Carrier: UPS
Tracking: 1Z999AA10123456784

Shipment Condition:
☑ Boxes intact
☑ No damage
☑ All items present
```

**Step 2: Count and Record**

**Line 1: PLA Basic Black**
```
Ordered: 5 KG
Received: 5 KG ✓

Unit Cost: $25.00/KG
Total: $125.00

Create Spools:
  ☑ SPOOL-PLA-BLK-010 (1 KG)
  ☑ SPOOL-PLA-BLK-011 (1 KG)
  ☑ SPOOL-PLA-BLK-012 (1 KG)
  ☑ SPOOL-PLA-BLK-013 (1 KG)
  ☑ SPOOL-PLA-BLK-014 (1 KG)

Supplier Lot Number: LOT-2026-0210
Notes: "Sealed packages, good condition"
```

**Line 2: M3 Inserts**
```
Ordered: 1000 EA
Received: 1000 EA ✓

Count Verified: Yes (spot check of 100 pieces)
Quality: Good
```

**Line 3: Poly Bags**
```
Ordered: 500 EA
Received: 480 EA ⚠️ (short 20)

Reason: Damaged in shipping
Action: Contact vendor for credit or replacement
```

**Step 3: Location Assignment**

```
All items to: Main Warehouse (default location)

Or specify per line:
  - PLA Black → WH-A-B1-03
  - Inserts → WH-A-B2-05
  - Bags → WH-A-C3-01
```

**Step 4: Cost Update**

```
Update Product Costs: ✓ Yes (default)

System updates for each line:
  - Last Cost = Unit Cost from PO
  - Average Cost = Weighted average calculation
  - Updates inventory valuation
```

**Step 5: Submit Receipt**

Click **Receive Inventory** → System processes:

1. **Inventory Transactions Created:**
   ```
   +5000 G PLA Basic Black @ $0.025/G = $125.00
   +1000 EA M3 Inserts @ $0.15/EA = $150.00
   +480 EA Poly Bags @ $0.08/EA = $38.40
   ```

2. **Inventory Quantities Updated:**
   ```
   PLA Black: 2000 G → 7000 G (+5000 G)
   M3 Inserts: 500 EA → 1500 EA (+1000 EA)
   Poly Bags: 100 EA → 580 EA (+480 EA)
   ```

3. **Material Spools Created** (for filament):
   ```
   SPOOL-PLA-BLK-010: 1.000 kg, Active
   SPOOL-PLA-BLK-011: 1.000 kg, Active
   ... (5 spools total)
   ```

4. **Product Costs Updated:**
   ```
   PLA Black:
     Last Cost: $25.00/KG (from this PO)
     Average Cost: $24.50/KG (weighted average)

   M3 Inserts:
     Last Cost: $0.15/EA
     Average Cost: $0.155/EA
   ```

5. **PO Status Updated:**
   ```
   Status: received
   Received Date: 2026-02-13
   ```

**✅ Result:** Inventory received and ready for production!

### Partial Receipts

**If items arrive in multiple shipments:**

**First Shipment:**
```
Line 1: PLA Black - Receive 3 KG (of 5 ordered)
Line 2: Inserts - Receive 500 EA (of 1000 ordered)
Line 3: Bags - Not received yet

Status: partially_received (not shown, but recorded)
```

**Second Shipment:**
```
Line 1: PLA Black - Receive 2 KG (remaining)
Line 2: Inserts - Receive 500 EA (remaining)
Line 3: Bags - Receive 480 EA

Status: received (all lines complete)
```

**Each receipt creates separate inventory transactions** with different dates.

---

## Part 5: Closing Purchase Orders

**From "received" → "closed":**

**Navigation:** Purchasing → Purchase Orders → Select PO → **Close PO**

**Requirements:**
- ✅ All lines received (or documented short)
- ✅ Inventory transactions created
- ✅ Costs updated
- ✅ Any discrepancies resolved

**Closing actions:**

```
Review:
  - All items received: ✓
  - Costs updated: ✓
  - Documents attached: ✓

Final Notes: "20 bags short, vendor issued $1.60 credit"

Close Purchase Order: [Confirm]
```

**System actions:**
1. PO locked (no further edits)
2. Status → "closed"
3. PO archived and searchable
4. Accounting finalized

**✅ Result:** Purchase complete!

---

## Part 6: Document Management

### Document Types

**Attach documents to purchase orders:**

| Type | Description | When to Upload |
|------|-------------|----------------|
| **invoice** | Vendor invoice | After receiving |
| **packing_slip** | Packing list | When shipment arrives |
| **receipt** | Payment receipt | After payment |
| **quote** | Vendor quote | When creating PO |
| **shipping_label** | Shipping label | When vendor ships |
| **other** | Misc documents | As needed |

### Uploading Documents

**Navigation:** Purchasing → Purchase Orders → Select PO → **Documents** → **+ Upload**

```
Document Type: invoice
File: Browse (PDF, JPG, PNG)

Notes: "Invoice #INV-2026-0210"

Upload: [Confirm]
```

**Result:** Document attached and viewable

**Multiple documents allowed** - upload all related files

### Viewing Documents

**Navigation:** Purchasing → Purchase Orders → Select PO → **Documents**

**Shows:**
- Document type
- File name
- Upload date
- Uploaded by
- File size
- Actions: View, Download, Delete

**Click to view/download** - opens in browser or downloads file

---

## Part 7: Integration with MRP

### Automatic PO Generation

**MRP analyzes requirements** and suggests purchase orders:

1. **MRP Run** calculates material needs
2. **Planned Orders** created for items below reorder point
3. **User reviews** planned orders
4. **Convert to POs** - one click to create purchase order

**Example:**

```
MRP Output:

Item: PLA Basic Black
On Hand: 1000 G
Allocated: 4500 G (production orders)
Available: -3500 G (shortage!)

Reorder Point: 4500 G
Safety Stock: 1000 G
Lead Time: 7 days

Suggestion: Order 10 KG (10,000 G)
  → Covers shortage + safety stock + 1 week demand

Preferred Vendor: 3D Filament Warehouse (VND-001)
Unit Cost: $25.00/KG
Total: $250.00

Action: [Create Purchase Order]
```

**Click "Create Purchase Order":**
- Pre-fills vendor, product, quantity, cost
- User reviews and adjusts
- Submit to vendor

**See:** [MRP Guide](mrp.md) for full MRP workflow

### Low Stock Alerts

**Automatic notifications when:**

```
Reorder Point Trigger:
  Item: PLA Basic Black
  On Hand: 4400 G
  Reorder Point: 4500 G

  → Alert: "PLA Basic Black below reorder point"
  → Suggest: "Create PO for 10 KG from VND-001"
```

**Configure alerts:** Settings → Notifications → Inventory Alerts

---

## Part 8: Purchasing Reports

### Purchase Order List

**Navigation:** Purchasing → Purchase Orders

**Filter by:**
- Status (all, draft, ordered, shipped, received, closed, cancelled)
- Vendor
- Date range (order date, expected date, received date)
- Search (PO number, vendor name)

**Columns:**
- PO Number
- Vendor
- Order Date
- Expected Date
- Status
- Total Amount
- Items (count)

**Export to CSV** for analysis in Excel

### Vendor Performance Report

**Navigation:** Purchasing → Reports → **Vendor Performance**

**Shows:**

```
Vendor: 3D Filament Warehouse (VND-001)
Period: Last 6 Months

Total POs: 24
Total Spend: $6,850.00

On-Time Delivery:
  On Time: 22 POs (92%)
  Late: 2 POs (8%)
  Average Delay: 1.2 days

Lead Time:
  Average: 6.8 days
  Min: 5 days
  Max: 10 days

Quality:
  Perfect Orders: 21 (88%)
  Short Shipments: 2 (8%)
  Damaged: 1 (4%)

Rating: 4.5 / 5.0
Recommendation: ✓ Preferred Vendor
```

### Purchasing Costs Report

**Navigation:** Purchasing → Reports → **Purchasing Costs**

**Shows:**

```
Period: Last 30 Days

Total POs: 8
Total Spend: $2,450.00

By Category:
  Filament: $1,800.00 (73%)
  Hardware: $400.00 (16%)
  Packaging: $250.00 (11%)

By Vendor:
  VND-001: 3D Filament Warehouse: $1,800.00 (73%)
  VND-002: Hardware Supply Co: $400.00 (16%)
  VND-003: Packaging Inc: $250.00 (11%)

Average PO Value: $306.25
```

### Cost Variance Report

**Navigation:** Purchasing → Reports → **Cost Variance**

**Shows price changes over time:**

```
Product: PLA Basic Black (MAT-PLA-BASIC-BLK)

Last 6 Purchases:

Date       PO #         Vendor  Qty    Unit Cost  Change
────────── ──────────── ─────── ────── ────────── ──────
2026-02-13 PO-2026-010  VND-001 5 KG   $25.00/KG  +$2.00 (+8.7%)
2026-01-28 PO-2026-005  VND-001 10 KG  $23.00/KG  -$1.00 (-4.2%)
2025-12-15 PO-2025-085  VND-001 5 KG   $24.00/KG  +$1.00 (+4.3%)
2025-11-20 PO-2025-068  VND-001 10 KG  $23.00/KG  $0.00 (0%)
2025-10-15 PO-2025-042  VND-001 5 KG   $23.00/KG  -$2.00 (-8.0%)
2025-09-10 PO-2025-018  VND-001 10 KG  $25.00/KG  --

Average Cost: $23.83/KG
Current Cost: $25.00/KG (+5% above average)
Trend: ↗ Increasing
```

---

## Part 9: Best Practices

### Vendor Management

✅ **Do:**
- Maintain at least 2 vendors per critical item (backup supply)
- Update lead times based on actual performance
- Rate vendors after each order (honest feedback)
- Negotiate volume discounts for bulk purchases
- Build relationships with vendor reps

❌ **Don't:**
- Use single-source vendors for critical materials
- Forget to update contact information
- Keep inactive vendors cluttering the list
- Ignore vendor quality issues

### Purchase Order Creation

✅ **Do:**
- Check inventory before ordering (use MRP)
- Order in vendor's standard units (KG, BOX, etc.)
- Include clear notes for special requests
- Verify product SKUs match vendor's catalog
- Plan orders to minimize shipping costs

❌ **Don't:**
- Order without checking reorder points
- Create rush orders at premium prices unnecessarily
- Forget to include all needed items in PO
- Order quantities below minimum order qty
- Mix incompatible items in one PO

### Receiving Best Practices

✅ **Do:**
- Count all items upon receipt
- Inspect for damage immediately
- Document shortages/damages with photos
- Update costs from actual purchase prices
- Create spools for all filament received
- Record lot numbers for traceability

❌ **Don't:**
- Receive without counting (trust vendor)
- Delay receiving (inventory inaccurate)
- Skip quality inspection
- Forget to update product costs
- Lose packing slips/invoices

### Cost Management

✅ **Do:**
- Update product costs from actual purchases
- Review cost variance reports monthly
- Negotiate better prices with high-volume vendors
- Track price trends to plan purchases
- Use average costing for most items

❌ **Don't:**
- Leave product costs at $0.00
- Ignore price increases
- Accept price increases without negotiation
- Order premium rush shipments regularly

---

## Part 10: Common Workflows

### Workflow 1: Simple Purchase (One Vendor)

```
1. Check inventory: PLA Black at 1000 G
2. Reorder point: 4500 G → Need to order
3. Create PO:
   - Vendor: 3D Filament Warehouse
   - Product: PLA Basic Black
   - Quantity: 10 KG @ $25/KG = $250
   - Expected: 7 days
4. Mark as Ordered (send to vendor)
5. Vendor confirms order
6. Vendor ships (tracking: UPS 1Z999...)
7. Receive shipment:
   - Count: 10 KG ✓
   - Create 10 spools (1 KG each)
   - Update costs
8. Close PO
9. Inventory: 11,000 G → Ready for production
```

**Time estimate:** 7-10 days (vendor lead time)

### Workflow 2: Emergency Rush Order

```
1. Production order needs 5 KG PLA immediately
2. Inventory: 500 G (insufficient!)
3. Contact vendor for rush shipping:
   - Call vendor: "Need 5 KG overnight"
   - Vendor confirms: $150 + $50 rush = $200 total
4. Create PO:
   - Priority: Urgent
   - Shipping: $50 overnight
   - Notes: "RUSH - Production awaiting"
5. Order and pay immediately (credit card)
6. Vendor ships same day
7. Receive next morning:
   - Expedite receiving process
   - Immediately create spools
   - Release to production
8. Close PO
9. Production order continues
```

**Time estimate:** 1 day (overnight shipping)

### Workflow 3: Bulk Order (Multi-Vendor)

```
1. MRP run suggests:
   - 50 KG filament (various colors)
   - 5000 EA inserts
   - 2000 EA bags
2. Create 3 separate POs:

   PO-1: 3D Filament Warehouse
     - 10 KG PLA Black @ $25 = $250
     - 10 KG PLA White @ $25 = $250
     - 10 KG PETG Black @ $28 = $280
     - 10 KG PETG Clear @ $28 = $280
     - 10 KG TPU @ $35 = $350
     Total: $1,410

   PO-2: Hardware Supply Co
     - 5000 EA M3 Inserts @ $0.14 = $700
     Total: $700

   PO-3: Packaging Inc
     - 2000 EA Poly Bags @ $0.07 = $140
     Total: $140

3. Send all POs to vendors
4. Track shipments (different arrival dates)
5. Receive each shipment separately:
   - PO-1: Day 7 (filament)
   - PO-2: Day 10 (inserts)
   - PO-3: Day 5 (bags)
6. Close all POs
7. Inventory restocked for production
```

**Time estimate:** 10-14 days (staggered arrivals)

---

## Part 11: Advanced Features

### Vendor Item Mapping

**Map vendor SKUs to your products:**

**Navigation:** Purchasing → Vendors → Select vendor → **Vendor Items**

```
Add Vendor Item Mapping:

Vendor SKU: PLA-BLK-1KG
Vendor Description: "Black PLA Filament 1kg Spool"

Your Product: MAT-PLA-BASIC-BLK
Default Unit Cost: $25.00/KG
Default Purchase Unit: KG

Save: [Confirm]
```

**Use case:**
- Vendor invoice shows "PLA-BLK-1KG"
- System auto-maps to MAT-PLA-BASIC-BLK
- Faster PO creation (select from vendor's catalog)
- Consistent ordering

### Purchase Order Templates

**Create template POs for recurring orders:**

```
Template: Monthly Filament Restock

Vendor: 3D Filament Warehouse

Lines:
  - PLA Black: 10 KG @ $25/KG
  - PLA White: 10 KG @ $25/KG
  - PETG Black: 5 KG @ $28/KG
  - TPU 95A: 5 KG @ $35/KG

Total: $1,090

Use: Create PO from template, adjust quantities as needed
```

### Multi-Location Receiving

**Receive to different warehouse locations:**

```
PO-2026-010: Bulk Order

Line 1: PLA Black (10 KG)
  → Receive to: WH-A (5 KG)
  → Receive to: WH-B (5 KG)

Line 2: Inserts (5000 EA)
  → Receive to: WH-A (5000 EA)

Line 3: Bags (2000 EA)
  → Receive to: WH-C (2000 EA) [Shipping dept]
```

**System creates separate inventory transactions** per location.

### Partial Payments

**Track payments for large orders:**

```
PO Total: $5,000

Payment 1: $2,500 (Deposit, 2026-02-01)
Payment 2: $2,500 (Balance, 2026-02-15)

Payment Status: Fully Paid
```

---

## Part 12: Troubleshooting

### PO Won't Close

**Problem:** Cannot close PO, error message

**Possible causes:**
- Some lines not fully received
- Inventory transactions missing
- Status not "received"

**Solution:**
1. Check all line quantities: Ordered vs Received
2. Verify inventory transactions created
3. Ensure status is "received" (not "shipped")
4. If items short, document reason in notes
5. Retry close

### Cost Not Updating

**Problem:** Product cost shows old value after receiving

**Cause:** "Update Costs" option not checked during receiving

**Solution:**
1. Navigate to product
2. Edit product costs manually:
   - Last Cost: Enter from PO
   - Average Cost: Calculate weighted average
3. Or re-receive PO (if possible)

### Duplicate Inventory Receipt

**Problem:** Accidentally received same PO twice

**Cause:** Clicked "Receive" twice or received from multiple locations

**Solution:**
1. Check inventory transactions for duplicate entries
2. Create adjustment transaction to correct:
   - Adjustment: Negative quantity
   - Amount: Negative cost
   - Reason: "Duplicate receipt correction"
3. Document in PO notes

### Vendor Not Showing in Dropdown

**Problem:** Cannot select vendor when creating PO

**Cause:** Vendor is inactive

**Solution:**
1. Navigate to Purchasing → Vendors
2. Find vendor
3. Check "Active" status
4. Activate vendor
5. Retry PO creation

---

## Next Steps

Now that you understand purchasing, explore these related guides:

| Guide | Learn About |
|-------|-------------|
| **Inventory Management** | Stock levels, transactions, cycle counting |
| **MRP** | Automatic purchase order generation from material requirements |
| **Manufacturing** | How production consumes purchased materials |
| **Accounting** | COGS calculation, vendor payments, AP aging |

## Quick Reference

### Purchase Order Status Flow

```
draft → ordered → shipped → received → closed
```

### Document Types

- invoice - Vendor invoice
- packing_slip - Packing list
- receipt - Payment receipt
- quote - Vendor quote
- shipping_label - Tracking label
- other - Miscellaneous

### Keyboard Shortcuts

- `n` - New purchase order
- `r` - Receive inventory
- `c` - Close PO
- `/` - Search

---

**🎉 Congratulations!** You now understand the complete FilaOps purchasing system. Create your first purchase order and start managing vendor relationships!
