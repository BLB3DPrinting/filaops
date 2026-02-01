# FilaOps - Known Issues

This document tracks known bugs and issues in the production system.

---

## Critical Issues

*(None currently open)*

---

## Medium Priority Issues

*(None documented yet)*

---

## Low Priority Issues

*(None documented yet)*

---

## Resolved Issues

### ISSUE-001: Production-to-Shipping Transaction Tracking (0 Records)

**Status:** RESOLVED  
**Priority:** Critical  
**Reported:** 2025-01-19  
**Resolved:** 2026-01-31

**Description:**
The system recorded 0 transactions from production to shipping. When items moved through the fulfillment process (production complete → shipped), no transaction records were being created.

**Root Cause:** Missing Shipment Transaction in Fulfillment Flow

Both `buy_label()` and `mark_order_shipped()` in `fulfillment.py` were not creating shipment transactions when shipping finished goods.

**Fix Applied:**
- `buy_label()` now calls `TransactionService.ship_order()` which creates proper shipment transactions with GL entries (DR COGS, CR FG Inventory)
- `mark_order_shipped()` now creates `InventoryTransaction` with `transaction_type="shipment"` and decrements FG inventory

**Verification:**
- `TransactionService.ship_order()` creates linked inventory transactions + journal entries
- Both endpoints now return `finished_goods_shipped` in response confirming the transactions

---

### ISSUE-002: Version Display Shows v2.0.1 After Updating to v3.0.1

**Status:** Resolved
**Priority:** Medium
**Reported:** 2026-01-29
**Resolved:** 2026-01-31

**Description:**
After running the built-in updater (which correctly pulls new code and rebuilds), the Settings page continued to display "v2.0.1" as the current version.

**Root Cause:**
Multiple hardcoded `"2.0.1"` fallback strings were never updated when the version bumped. Additionally, `useVersionCheck.js` called an async function without `await`.

**Fix (PR #110):**
- Created `backend/VERSION` file as single source of truth
- Frontend imports version from `package.json` at Vite build time
- Fixed missing `await` in `useVersionCheck.js`
- Added `docs/VERSIONING.md` documenting the version bump process

---

## How to Add Issues

When adding a new issue:

1. Use format `ISSUE-XXX` for the ID
2. Include: Status, Priority, Reported date, Affects
3. Document expected vs actual behavior
4. List files to investigate
5. Update status and add root cause / fix when resolved
