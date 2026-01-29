# BLB3D Production - Known Issues

This document tracks known bugs and issues in the production system.

---

## Critical Issues

### ISSUE-001: Production-to-Shipping Transaction Tracking (0 Records)

**Status:** Open
**Priority:** Critical
**Reported:** 2025-01-19
**Affects:** Transaction audit trail, accounting reconciliation

**Description:**
The system records 0 transactions from production to shipping. When items move through the fulfillment process (production complete → shipped), no transaction records are being created.

**Expected Behavior:**
- When production is completed, a transaction should record inventory movement
- When items are shipped, a shipping event should be recorded
- These should be queryable for audit/accounting purposes

**Actual Behavior:**
- No transaction records exist
- `SELECT * FROM transactions` returns 0 rows (or no shipping-related records)

**Files to Investigate:**
- `backend/app/services/shipping_service.py` - Shipping logic
- `backend/app/services/transaction_audit_service.py` - Transaction recording
- `backend/app/models/shipping_event.py` - Shipping event model
- `backend/app/api/v1/endpoints/admin/fulfillment.py` - Fulfillment endpoints
- `backend/app/api/v1/endpoints/admin/inventory_transactions.py` - Transaction endpoints

**Investigation Steps:**
1. Check if transaction table exists in schema
2. Trace the shipping flow: where should transactions be created?
3. Check if shipping_service.py calls transaction_audit_service
4. Look for missing database commits or exception swallowing

**Root Cause:** IDENTIFIED - Missing Shipment Transaction in Fulfillment Flow

After investigation, the issue is in [backend/app/api/v1/endpoints/admin/fulfillment.py](backend/app/api/v1/endpoints/admin/fulfillment.py):

**The Flow:**
1. `start_production()` - Creates `reservation` transactions for materials ✓
2. `complete_print()` - Creates `consumption` (materials) + `receipt` (finished goods) ✓
3. `pass_qc()` - Status update only (correct - no inventory change)
4. `buy_label()` - Consumes packaging BUT **does NOT create shipment transaction** ✗
5. `mark_order_shipped()` - **Does NOT create ANY inventory transactions** ✗

**The Bug:**
When finished goods are produced (`complete_print()`), they are added to inventory via a `receipt` transaction. But when they are shipped (`buy_label()` or `mark_order_shipped()`), no `shipment` transaction is created to remove them from inventory.

**Result:**
- Finished goods accumulate in inventory forever (never decremented)
- No audit trail for shipped items
- Inventory quantities become incorrect over time
- Accounting cannot reconcile sales vs inventory

**Code Locations:**
- `buy_label()` line 1756-1915: Consumes packaging, but missing finished goods shipment
- `mark_order_shipped()` line 1918-1968: No inventory transactions at all

**Fix:**
Add `shipment` type `InventoryTransaction` in both `buy_label()` and `mark_order_shipped()` to:
1. Decrement finished goods `on_hand_quantity` in `Inventory` table
2. Create `shipment` transaction with `reference_type='sales_order'`

**Example Fix (for buy_label, around line 1872):**
```python
# After packaging consumption, ALSO ship the finished goods
if order.quote_id:
    quote = db.query(Quote).filter(Quote.id == order.quote_id).first()
    if quote and quote.product_id:
        fg_inventory = db.query(Inventory).filter(
            Inventory.product_id == quote.product_id
        ).first()
        if fg_inventory:
            qty_shipped = order.quantity or 1
            fg_inventory.on_hand_quantity = Decimal(str(
                max(0, float(fg_inventory.on_hand_quantity) - qty_shipped)
            ))
            shipment_txn = InventoryTransaction(
                product_id=quote.product_id,
                location_id=fg_inventory.location_id,
                transaction_type="shipment",
                reference_type="sales_order",
                reference_id=sales_order_id,
                quantity=Decimal(str(-qty_shipped)),
                notes=f"Shipped {qty_shipped} units for {order.order_number}",
                created_by="system",
            )
            db.add(shipment_txn)
```

---

## Medium Priority Issues

*(None documented yet)*

---

## Low Priority Issues

*(None documented yet)*

---

## Resolved Issues

### ISSUE-002: Version Display Shows v2.0.1 After Updating to v3.0.1

**Status:** Resolved
**Priority:** Medium
**Reported:** 2026-01-29
**Affects:** Settings page "Current Version" display, update checker comparison

**Description:**
After running the built-in updater (which correctly pulls new code and rebuilds), the
Settings page continued to display "v2.0.1" as the current version. The "Latest Version"
showed the correct value from GitHub, but the comparison was also broken.

**Root Cause:**
Multiple hardcoded `"2.0.1"` fallback strings were never updated when the version bumped.
Additionally, `useVersionCheck.js` called an async function without `await`, making the
update-available comparison always use a Promise object instead of a version string.

**Fix (PR #110):**
- Created `backend/VERSION` file as a single source of truth for the backend fallback
- Frontend now imports version from `package.json` at Vite build time (no hardcoded strings)
- Fixed missing `await` in `useVersionCheck.js`
- Updated Dockerfile `ARG FILAOPS_VERSION` default
- Added `docs/VERSIONING.md` documenting the version bump process

---

## How to Add Issues

When adding a new issue:

1. Use format `ISSUE-XXX` for the ID
2. Include: Status, Priority, Reported date, Affects
3. Document expected vs actual behavior
4. List files to investigate
5. Update status and add root cause / fix when resolved
