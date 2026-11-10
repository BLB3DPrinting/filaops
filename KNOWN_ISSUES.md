# FilaOps - Known Issues

This document tracks known bugs and issues in the production system.

---

## Critical Issues

*(None currently open)*

---

## Medium Priority Issues

### ISSUE-003: Pickers and tables stop at a fixed number of rows

**Status:** Open
**Priority:** Medium
**Reported:** 2026-11-10
**Affects:** 4.4.0 and earlier

**Description:**
Several screens load a fixed number of rows and have no paging, and their search boxes search only the rows already loaded. Product pickers (Create BOM, BOM components, the routing editor, new production order, the sales order wizard) load the first 500 active products. Item pickers load the first 500 items by SKU, or the first 2000 on the Purchasing page and in the inventory transactions item filter. The Routings tab shows the newest 50 routings and the inventory transactions page the newest 100. Other tables and pickers stop at a fixed number of rows, from 50 to 2000 depending on the screen. The Items page's table is not one of these: it pages through every item and its search box searches the server. Its Cards view is covered by ISSUE-010.

**Workaround:**
Narrow the list with the screen's filters where it has them. A routing that is not listed on the Routings tab can be opened from the Items page in Table view: find the item and click **Route/BOM** (shown on items whose procurement type is Make or Make or Buy). That opens the item's active routing with the highest version number; an older or inactive routing cannot be opened this way.

---

### ISSUE-004: Dashboard "Pending Purchases" panel is always empty

**Status:** Open
**Priority:** Medium
**Reported:** 2026-11-10
**Affects:** 4.4.0 and earlier

**Description:**
The panel asks for purchase orders with the status `draft,ordered` as one value, which matches none.

**Workaround:**
Use the Purchasing page.

---

### ISSUE-005: Orders page: "Highest Value First" fails

**Status:** Open
**Priority:** Medium
**Reported:** 2026-11-10
**Affects:** 4.4.0 and earlier

**Description:**
Choosing that sort order sends a sort field the server rejects, so the list fails to load.

**Workaround:**
Choose another sort order.

---

### ISSUE-006: CSV imports read a decimal comma as a thousands separator

**Status:** Open
**Priority:** Medium
**Reported:** 2026-11-10
**Affects:** 4.4.0 and earlier

**Description:**
The item, order and material imports remove every comma from a number, so a price written `12,34` is imported as 1234.

**Workaround:**
Write numbers in import files with a decimal point and no thousands separator.

---

### ISSUE-007: Cost and unit limits

**Status:** Open
**Priority:** Medium
**Reported:** 2026-11-10
**Affects:** 4.4.0 and earlier

**Description:**
- An item bought by a pack with no pack size recorded is costed at its standard cost unconverted. There is no field for a pack size yet.
- The item form has no purchase-unit field. Change it with `PATCH /api/v1/items/{id}` (`purchase_uom`).
- A material stocked by the KG, LB or OZ, not by the gram, is not costed correctly. Receiving records its stock and its average and last cost in grams whatever its stock unit says, and then writes that per-gram figure as its standard cost: $20.00 a KG becomes $0.0200. Recost does the same for such a material that has no standard cost. The 4.4.0 cost fix covers materials stocked by the gram, which is how the material form creates them. Check the standard cost of any other material after each receipt. Migration 105 neither repairs nor lists a material whose stock and purchase unit are the same.
- Materials bought by the LB or OZ are not handled correctly. Where the material is stocked in another unit (grams, for example), the receipt is refused unless both the purchase unit and G are active in the unit table. The setup wizard's example data adds G, LB and OZ; an install set up without the example data does not have them, and there is no screen for adding them afterwards. Where it is also stocked by the LB or OZ, the receipt is accepted, but the stock movement and the item's average and last cost are recorded in grams (1 LB as 453.592 G) although the item's stock unit says LB or OZ. BOM costs read such a material's standard cost as per KG.
- A material stocked by the each is costed correctly on a BOM only when it has just an average or last cost, and its unit cost is then shown 1000 times too high, labelled /KG.

---

### ISSUE-008: A currency other than US dollars is not shown on every screen

**Status:** Open
**Priority:** Medium
**Reported:** 2026-11-10
**Affects:** 4.4.0 and earlier

**Description:**
The currency and locale settings are not applied everywhere. A number of screens still show a `$` and a decimal point whatever the setting, among them the quote form and the sales order wizard. The amounts are right; the symbol and number format are not.

---

### ISSUE-010: Items page: Cards view has no page controls

**Status:** Open
**Priority:** Medium
**Reported:** 2026-11-10
**Affects:** 4.4.0 and earlier

**Description:**
Cards view shows one page of items and has no controls to change the page or the page size. The **Needs Reorder** card filters only the rows on the current page, in either view, so it can miss items that are on other pages. (Before 4.4.0 the table also went back to page 1 a moment after **Next** was clicked. That is fixed in 4.4.0.)

**Workaround:**
Change the page and the page size in Table view: Cards view shows the page the table is on. Raising the page size to 200 brings more items under the **Needs Reorder** card. To find one item, search by SKU or name.

---

## Low Priority Issues

### ISSUE-009: The MRP settings cannot be set from `.env` in a Docker install

**Status:** Open
**Priority:** Low
**Reported:** 2026-11-10
**Affects:** 4.4.0

**Description:**
`docker-compose.yml` passes a fixed list of settings to the backend, and `MRP_ROUTING_MAKE_BUY`, `MRP_OPEN_PO_SUPPLY` and `MRP_RELEASE_COPIES_ROUTING` are not on it.

**Workaround:**
Add them under the backend service's `environment` in a `docker-compose.override.yml`, for example `MRP_OPEN_PO_SUPPLY: "true"`, then run `docker compose up -d` so the backend container is recreated with them.

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

### ISSUE-011: Saving the item form clears an item's weight and dimensions

**Status:** Resolved
**Priority:** Medium
**Reported:** 2026-11-10
**Resolved:** 2026-11-10
**Affects:** 4.4.0 and earlier. Fixed in the first release after 4.4.0.

**Description:**
The item form did not load an item's weight, length, width and height when it opened, and it sent all four empty when it saved. Whatever was stored in them was cleared each time the item was edited on the form. For a packaging item nothing was cleared silently, because the form requires the four values, but they had to be typed in again on every edit. The same form also showed a stocked material's reorder point in grams (1000 times the stored value) and saved that figure back, so every save of a stocked material multiplied its reorder point by 1000.

**Root Cause:**
The form was built from a row of the Items list. That row has no weight or dimensions and reports a material's reorder point in grams, and the update stores every field it is sent.

**Fix:**
The form loads the full item (`GET /api/v1/items/{id}`) each time it opens for an edit, shows "Loading item…" until it arrives, and cannot be saved if the load fails. The weight, dimensions and reorder point come from that response. Values that were already cleared or multiplied are not repaired.

**Workaround (4.4.0 and earlier):**
When you edit an item on the form, enter its weight and dimensions again before saving (the Physical / Shipping section). To change one field and leave the rest alone, use the API: `PATCH /api/v1/items/{id}` with only that field. Do not save a stocked material on the form: change its reorder point with `PATCH /api/v1/items/{id}` and only `reorder_point` (kilograms, the unit it is stored in).

---

## How to Add Issues

When adding a new issue:

1. Use format `ISSUE-XXX` for the ID
2. Include: Status, Priority, Reported date, Affects
3. Document expected vs actual behavior
4. List files to investigate
5. Update status and add root cause / fix when resolved
