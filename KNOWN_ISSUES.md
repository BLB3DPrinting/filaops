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

### ISSUE-011: Saving the item form clears an item's weight and dimensions

**Status:** Open
**Priority:** Medium
**Reported:** 2026-11-10
**Affects:** 4.4.0 and earlier

**Description:**
The item form does not load an item's weight, length, width and height when it opens, and it sends all four empty when it saves. Whatever was stored in them is cleared each time the item is edited on the form. For a packaging item nothing is cleared silently, because the form requires the four values, but they have to be typed in again on every edit.

**Workaround:**
When you edit an item on the form, enter its weight and dimensions again before saving (the Physical / Shipping section). To change one field and leave the rest alone, use the API: `PATCH /api/v1/items/{id}` with only that field.

---

### ISSUE-012: A second copy of FilaOps on the same computer uses the first copy's database

**Status:** Open
**Priority:** Medium
**Reported:** 2026-11-10
**Affects:** 4.4.0 and earlier (Docker installs)

**Description:**
`docker-compose.yml` gives the containers, the data volumes and the network fixed names, so a second copy of the `filaops` folder on the same computer is not a separate install. It uses the same containers and the same data volumes.

- A copy in a folder with the same name (for example a fresh clone into another directory, also called `filaops`): `docker compose up -d --build` there replaces the first copy's running containers, with no warning. What happens next depends on the database password in the second folder's `.env`:
    - The same password (a copied `.env`, or no password set in either folder): the second copy starts, and if it holds newer code its `migrate` service upgrades the database.
    - A different password (a fresh clone has no `.env`, so it uses the default one): the `migrate` step fails to sign in, the database is left alone, and FilaOps stays down until the first folder is started again.
- A copy in a folder with a different name: while the first copy's containers exist, it stops with a container-name conflict and the database is left alone. That conflict is the only warning. Once the first copy's containers have been removed (`docker compose down`), the second copy starts on the same database with only a notice that a volume `already exists but was created for project ...`, and upgrades it if it holds newer code.

To Docker, two folders with the same name are one install. They share the built images as well: after a second copy has been built, `docker compose up -d` in the first folder, without `--build`, starts the second copy's version. `docker compose down -v` in the second folder deletes the first copy's database and its `filaops_config` volume.

Uploaded files and settings are not shared. Each copy has its own `uploads` folder and its own `.env` next to its `docker-compose.yml`. While a second copy is running, files uploaded through the first (product pictures, for example) are missing, and anything uploaded through the second stays in the second folder. On 4.3.1 or older, product pictures are kept inside the backend container, and are lost when a second copy replaces it.

**Workaround:**
Run one copy per computer, and upgrade the folder you already run FilaOps from. To try a release before upgrading, use another computer.

Don't set up a second copy on a computer that holds live data. Giving it its own container, volume and network names is not enough: ports listed in a `docker-compose.override.yml` are added to the ones `docker-compose.yml` publishes rather than put in their place, the web app opened on `localhost` calls the backend on port 8000 whichever copy served the page, and the browser sends the same sign-in cookies to every copy on `localhost`.

**If it has already happened:**

These steps were run with a first copy on 4.3.2 and a second copy on 4.4.0. On 4.3.1 or older there is one more thing to protect: product pictures are kept inside the backend container, and steps 3 and 4 remove or rebuild containers. If either copy is on such a version, pick a time when nobody is adding pictures, and keep it that way until you have finished. Before step 3, copy the pictures out of the running backend with the command in step 2 of the upgrade guide, run in the folder whose copy is running. If the first folder is still on 4.3.1 or older at the end, step 6 below has one more command for it.

1. Take a backup of the database as it is now, before anything else. Use the commands in step 1 of the upgrade guide (`docs/UPGRADE.md`), in the first folder (the one you ran FilaOps from before). If a `filaops_before_upgrade.sql` is already there, rename it first and keep it. Do not delete it: it may be the only backup from before this happened.
2. In the second folder, run `docker compose logs migrate` and save what it prints. If the database was upgraded, that output lists what the upgrade changed and what it left for you to check (step 6 of the upgrade guide), and it is gone once the container is removed.
3. Still in the second folder, run `docker compose down`. Never add `-v`.
4. In the first folder, run `docker compose up -d --build`. `--build` matters: it rebuilds the first folder's own version.
5. If FilaOps starts, the database was not upgraded and you are back on your own version. If the `migrate` step stops with `DATABASE MIGRATION MISMATCH`, the second copy upgraded the database, and the older code can no longer run on it. Versions before 4.4.0 then tell you to delete the database volume. Don't: that deletes all your data. You then have two ways on:
    - Move the first folder to the exact code the second copy runs. `git rev-parse HEAD` in the second folder prints its commit. In the first folder, run `git fetch --tags`, then `git checkout` followed by that commit, then `docker compose up -d --build`. Use that commit, not a newer one, and not the number in `backend/VERSION`: a copy that follows `main` can hold migrations its version number does not show. Changes made in the second folder and never committed are not part of the commit. If `git checkout` cannot find the commit, it was never published: in the first folder, run `git fetch "<path to the second folder>" HEAD` with the second folder's path between the quotes, then check it out again.
    - Or restore a backup taken before it happened (`docs/ROLLBACK.md` section 3), which loses everything entered since.
6. Copy, don't move, the files in the second folder's `uploads` into the first folder's `uploads`. If the first folder is on 4.3.1 or older, then run the copy-back from step 6 of `docs/ROLLBACK.md` section 3, which puts the pictures into its backend container. Once the pictures show in the app, delete the second folder.

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

## How to Add Issues

When adding a new issue:

1. Use format `ISSUE-XXX` for the ID
2. Include: Status, Priority, Reported date, Affects
3. Document expected vs actual behavior
4. List files to investigate
5. Update status and add root cause / fix when resolved
