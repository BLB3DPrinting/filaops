# Core Integrity Hardening Plan (Plan v2)

Date: 2026-06-10
Author: Claude (architect/PM session `claude-filaops-ux-review-20260609`)
Status: APPROVED FOR EXECUTION
Source: three-domain deep review (purchasing/procure-to-stock, MRP, inventory management),
grounded in code AND the live `filaops` dev DB. Companion to
`2026-06-09-ux-gtm-readiness.md` (plan v1 — UI/UX; its Phase 2/3 items remain valid).

## The disease this plan cures

Recurring pattern confirmed across both reviews: **good things get built twice and
neither gets wired consistently** — four inventory on-hand writers, two low-stock
modules, four requirement-explosion implementations, two traceability spines, an
unused vendor catalog, a dormant-but-real MRP engine. The fix philosophy throughout:
**consolidate before adding.** Pick the good implementation, delete the rival, route
everything through the survivor.

## How to use this document

Same execution model as plan v1: each item is a self-contained spec for one coding
session on its own isolated worktree. Sessions MUST:

1. Verify worktree isolation first (`git rev-parse --show-toplevel` must contain
   "agent-" or a dedicated worktree path — NOT the parent session's worktree).
2. Register an Aeonyx session, claim ONLY their item's files, branch off CURRENT
   `origin/main` (fetch first), re-verify all line references against the code.
3. Backend test runs need `backend/.env` (copy from `C:/repos/filaops/backend/.env`,
   never print it) and `DATABASE_URL` targeting local `filaops`, never `filaops_prod`.
4. Full PR loop per AGENT_POLICY.md; stop at green-and-triaged; PM merges.
5. Check the file-overlap table at the bottom before parallel dispatch.

Conventions: ruff E712 (`.is_(True)`), Decimal not float for quantities/money, one
atomic commit per logical change, UOM single source `backend/app/core/uom_config.py`
(costs $/kg, inventory grams).

---

## Phase A — P0: trust and security

### HARD-1: Require auth on all /mrp endpoints  [DISPATCHED 2026-06-10]

Only `POST /run` in `backend/app/api/v1/endpoints/mrp.py` has
`Depends(get_current_staff_user)`. The read endpoints (`/requirements`,
`/planned-orders`, `/supply-demand`, `/explode-bom`, `/runs`) are unauthenticated and
expose BOM structures, costs, and inventory. Fix: router-level dependency; test that
unauthenticated reads 401; PR body lists any sibling routers with the same gap
(audit-only, don't fix here). Impact: HIGH security. Effort: S.

### HARD-2: Block the inventory-bypassing PO status flip

`update_po_status` allows manually setting a purchase order to `received`
(`AdminPurchasing.jsx` status dropdown → `purchase_order_service.py` ~411) WITHOUT
creating inventory transactions — only the `/receive` endpoint receives stock. Status
says received; stock never arrived; silent drift.

Scope: backend — reject direct transition to `received` with a clear 400 ("Use the
Receive workflow so inventory is recorded") OR auto-route through receiving when all
lines have known quantities (prefer the reject — simpler, explicit). Frontend — remove
`received` from the manual status dropdown options; the Receive button is the path.
Test: status PATCH to received → 400; receive endpoint still works.
Impact: HIGH (inventory integrity). Effort: S.

### HARD-3: Make MRP triggers honest

`backend/app/services/mrp_trigger_service.py` is entirely stubs that log and return
success-shaped payloads (`{"status": "checked", "message": "MRP check completed"}`)
while doing nothing. `trigger_mrp_check` is wired live to sales-order creation via
`AUTO_MRP_ON_ORDER_CREATE` (`sales_orders.py` ~294); shipment calls
`trigger_mrp_recalculation` which only logs.

Scope (minimum honest fix, NOT full auto-MRP):
- Wire `trigger_mrp_check` to the real engine: call `MRPService.run_mrp` scoped to the
  order's products (the engine exists in `backend/app/services/mrp.py`; add a
  product-scope parameter if needed) — OR, if scoped runs are too invasive for one PR,
  change every stub to return `{"status": "not_implemented"}` and remove
  success-shaped messages, then file the wiring as follow-up.
- Either way: no function may claim completion for work it didn't do.
- Test asserting the trigger's contract (whichever path chosen).
Impact: HIGH (system honesty / buyer trust). Effort: M (wire) or S (honest stub).

### HARD-4: One canonical inventory posting function  [THE BIG ONE — serialize]

On-hand is stored and mutated by four writers with incompatible conventions:
- `inventory_service.py` ~481: `adjustment` ⇒ on_hand −= quantity (delta-subtract,
  positive qty means consumption)
- `inventory_transaction_service.py` ~462: `adjustment` ⇒ on_hand = quantity
  (SET-absolute), float math throughout (~406-460)
- `transaction_service.py` ~223: on_hand += signed delta (stores signed quantities)
- `api/v1/endpoints/inventory.py` ~353: SETs on_hand, writes delta-magnitude txn
- `api/v1/endpoints/items.py` ~363, ~431: SETs on_hand with NO transaction at all

Confirmed drift in dev DB: MAT-PLA_BASIC-BLK stored 0 vs ledger +1000; PKG-BUBBLE
stored 140 vs ledger −248; COMP-FRAME-001 has on-hand 50 with zero transactions.
Cycle-count overages are stored as positive `adjustment` rows that the
inventory_service convention would SUBTRACT on any re-derivation.

Scope (3 PRs, sequential):
- **4a — canonical poster.** One function (suggest `inventory_ledger.post()` in a new
  or existing service): signed-delta semantics, Decimal-only, writes the transaction
  AND mutates on_hand atomically, one documented sign convention (positive = stock
  increases). Route ALL five writers through it. `adjustment` becomes a signed delta
  everywhere; SET-style callers compute `delta = new − current` first. items.py
  create/update must emit an `initial`/`adjustment` transaction. Existing tests must
  pass with explicitly-documented sign migrations where they encoded the old chaos.
  `reconciliation_baseline` (introduced by 4c) is an ALIAS OF `adjustment` in posting
  semantics — signed delta `counted − stored-at-post-time` through this same poster —
  distinguished by its reason code, and it additionally stamps
  `Inventory.baseline_timestamp` (see 4c) in the same atomic operation.
- **4b — reconciliation.** A function + admin endpoint computing
  `stored on_hand vs Σ(ledger at-or-after Inventory.baseline_timestamp)` per item
  (items with NULL baseline_timestamp sum ALL transactions and report as
  "uncounted"), surfaced as a report (reuse an existing admin page section or a
  simple table); log/flag mismatches. Wire into CI-runnable test for the seed
  dataset. NOTE: epoch filtering depends on the 4c schema (baseline_timestamp) —
  add the column in 4b's migration so the report is epoch-aware from day one, even
  though baselines only start being written in 4c.
- **4c — data repair (REQUIRES HUMAN APPROVAL before executing against any DB).**
  STRATEGY DECIDED 2026-06-10 by the owner: **"system first, updated by cycle count."**
  The transaction ledger is the system of record going forward; physical cycle counts
  are the periodic correction for transactional variance (unrecorded scrap-remakes,
  BOM-vs-reality drift from slicing changes, etc.). Neither the drifted stored on-hand
  nor the pre-consolidation ledger sum is ground truth — the shelf is. Implementation:
  1. The 4b report's drifted-item list is the counting work queue.
  2. Each counted item posts a reason-coded `reconciliation_baseline` transaction
     through the 4a canonical poster (an honest event: a count happened), snapping
     stored AND ledger to the counted value. Posting semantics: alias of
     `adjustment` (signed delta `counted − stored`), per the 4a contract.
     GL TREATMENT: identical to cycle-count variance — the existing mapping in
     `transaction_service.py` (~600-675): DR/CR 1200 Inventory vs 5030 Inventory
     Adjustment, direction by sign of the delta. Rationale: a baseline IS a
     physical count; its variance is period expense like any count variance.
     Example: stored 140, counted 152 → delta +12 → DR 1200 Inventory $X /
     CR 5030 Inventory Adjustment $X (X = 12 × unit cost). (A true greenfield
     opening balance at first install — no prior books — MAY warrant an
     opening-balance equity account instead; out of scope here, note for the
     onboarding flow.)
  3. EPOCH LINE: per-item baseline timestamp stored as
     `Inventory.baseline_timestamp` (nullable timestamptz on the Inventory row —
     the same grain as on_hand; NULL = never baselined). All future reconciliation
     (4b job) sums ONLY transactions at-or-after the baseline
     (`transaction.created_at >= Inventory.baseline_timestamp`). Pre-epoch history
     is retained read-only as archaeology — never re-summed, never repaired
     row-by-row.
  4. Items not yet counted: stored on-hand stands as the interim baseline. The
     "uncounted" state is DERIVED (Inventory.baseline_timestamp IS NULL) — no
     separate flag column — and the 4b report displays it as such.
  5. Dev/demo/test databases: baseline to stored without counting (test data),
     via the explicit fallback command only.
  The tool ships as count-first with stored-as-fallback. EXECUTION GATE: requires
  explicit human (owner) approval before running against any real database —
  recorded via the Aeonyx `cortex_approve` MCP gate where the session has it,
  otherwise direct owner sign-off in the PR/session. The migration itself only adds
  baseline plumbing, which means exactly: (a) the `Inventory.baseline_timestamp`
  column, (b) registration of the `reconciliation_baseline` reason code, (c) the
  count-entry tool, and (d) the explicit stored-as-baseline fallback command. The
  migration creates ZERO baseline transactions; baselines are written only by
  counts or the explicitly-invoked fallback, never silently.

Impact: HIGHEST in this plan — valuation, MRP, and COGS all inherit this. Effort: L
(split as above). Files: the five writers + tests; expect wide test fallout — budget
for it.

### HARD-5: Reservation/allocation reconciliation

`allocated_quantity` is a lump-sum column that leaks: dev DB has two rows with
allocated > on-hand (available −500, −350); `get_or_create_inventory` ~316 only logs a
warning; releases only fire for `reservation`-typed rows tied to a production order —
deleted/skipped POs strand allocations forever, poisoning availability and MRP.

Scope: derive allocation from the reservation/reservation_release ledger (logic exists
in `get_allocations_by_production_order`); add a repair path for stranded allocations;
verify every production-order terminal state (complete, cancel, close-short) releases
reservations; guard against allocated > on_hand at write time.
DEPENDS ON: HARD-4a (same files — do not parallelize with it).
Impact: HIGH. Effort: M.

---

## Phase B — P1: GTM credibility

### HARD-6: Net on-order supply into every shortage number

Per-order surfaces display incoming POs but don't subtract them from shortages —
the double-order trap. `sales_order_service.get_material_requirements` (~2364-2378),
`blocking_issues.get_material_available` (~89-93),
`production_order_service.get_material_availability` (~1421-1428) all compute
`short = required − (on_hand − allocated)` and ignore incoming.
`item_demand.py` ~307 already does it right: `projected = available + incoming`.

Scope: base `quantity_short` / `materials_short` / `can_fulfill` on projected balance
in all three; keep the incoming detail for expedite-vs-create-PO UX (that part is
good); update BlockingIssuesPanel copy to distinguish "short now, covered by PO-X
arriving <date>" from "short, no supply on the way". Tests for both states.
Impact: HIGH. Effort: M.

### HARD-7: Consolidated buy list (the planner's view)

Nothing answers "across ALL open demand, what do I buy, how much, by when?" The
engine computes 90% of it (`mrp.py` `calculate_net_requirements`).

Scope: read-only aggregate endpoint — gross demand across open SOs + production
orders by component, netted against on-hand + on-order + safety stock, grouped by
preferred vendor, sorted by earliest need; frontend page/section under Purchasing
("Buy List" or "Requirements") with line-level "Create PO" that pre-fills vendor +
qty. Do NOT build time-phasing yet (Phase C candidate); single-bucket netting is the
honest MVP. DEPENDS ON: HARD-6 definitions (share the netting helper).
Impact: HIGH — this is what makes "MRP" a feature, not a claim. Effort: M/L.

### HARD-8: Landed cost capitalization

Receiving posts only Σ(qty × unit_cost) to GL 1200/2000; `po.tax_amount` and
`po.shipping_cost` never reach item cost or the inventory GL leg
(`transaction_service.py` ~562-591; `purchase_order_service.py` ~727, ~759).
Filament always ships with freight → systematic undercosting.

Scope: allocate shipping+tax across received lines pro-rata by line value; fold into
`cost_per_unit_for_inventory` BEFORE the weighted-average update; include in the
inventory GL debit. Partial receipts allocate proportionally. Tests with freight-bearing
PO fixtures.
Impact: HIGH (margin truth). Effort: M.

### HARD-9: Kill the broken duplicate low-stock module

`backend/app/api/v1/endpoints/low_stock.py` references `Product.is_active` (~74) and
`product.reorder_quantity` (~90, ~262) — neither column exists (model has `active`,
`reorder_point`, `min_order_qty`) → 500 on every call. It's router-wired but the UI
uses the healthy `items/low-stock` (`item_service.get_low_stock_items`).

Scope: DELETE the module + router registration (`api/v1/__init__.py` ~133) unless
something imports it (grep first). If any unique capability exists (quick-reorder),
port it onto item_service. Dead-code-only PR.
Impact: HIGH (latent 500 landmine). Effort: S.

### HARD-10: Sequence-generation hardening (PO numbers + MRP generators)

`purchase_order_service.py` ~40-54 uses LIKE + lexicographic `desc(po_number)` +
`:03d` padding; width drift already in data (`PO-2026-027` vs `PO-2026-0021..0026`).
`mrp.py` ~1087, ~1142 have the same LIKE pattern, and purchase POs share the
`PO-YYYY-NNNN` prefix with production orders across two tables.

Scope: apply the established repo pattern (regex filter `op('~')` + numeric cast +
max), pad `:04d` consistently; consider renaming MRP-generated production orders'
prefix if collision risk is real (check actual generator for production orders —
`WO-` codes exist; align). One-time data fix for `PO-2026-027` → decide whether to
leave (grandfathered, regex tolerates) or renumber (don't renumber if referenced).
Impact: HIGH (duplicate-key 500s). Effort: S.

### HARD-11: Consumption idempotency + approval-row resolution

`consume_operation_material` (per-op) and `consume_production_materials` (completion)
can both fire for one production order — dev DB shows WO-2026-0035 with consumption
2700 AND a never-applied `negative_adjustment` 2700 (`requires_approval=true`) sitting
unresolved; COGS sums consumption+scrap by PO (`accounting.py` ~471-477) → double-count
risk.

Scope: idempotency key per (production_order, operation/bom_line) on consumption
writes; an approve/reject resolution flow for `requires_approval` transactions
(approve→apply via the HARD-4a poster; reject→void with reason); exclude unapplied
rows from COGS aggregation. DEPENDS ON: HARD-4a.
Impact: HIGH (COGS truth). Effort: M.

---

## Phase C — P2: capability and convergence

### HARD-12: One requirement-explosion function

`mrp.py` explodes routing-first/BOM-fallback (~441, ~496); `item_demand.py` (~52-91),
`blocking_issues.py` (~64) read bom_lines only. 35 products have both → screens
disagree. Scope: extract canonical `explode_requirements(product_id, qty)` with the
mrp.py semantics; converge item_demand, blocking_issues, sales_order_service on it.
DEPENDS ON: HARD-6 (shared helper). Impact: HIGH, Effort: M.

### HARD-13: Wire the vendor catalog

`VendorItem` model + CRUD exist (vendor_sku, default_unit_cost, default_purchase_unit);
zero rows, zero callers. Reorder paths default to `product.last_cost`. Scope: reorder/
buy-list PO creation prefers `VendorItem.default_unit_cost` for the chosen vendor;
receiving optionally upserts VendorItem from actuals ("remember this price?"); simple
management UI on the vendor detail. Impact: MED. Effort: M.

### HARD-14: Traceability spine  [DECIDED 2026-06-10 — design doc next; gates plan-v1 PR-14]

OWNER DECISION (med-dev traceability model applied to printing): **spool = serial,
PO/receipt = batch; lot-as-mill-cert is not meaningful for filament sourcing** (you
don't get a mill cert from a filament vendor). The two existing spines are therefore
HIERARCHICAL, not rivals:

- **Batch layer = MaterialLot** (exists, wired, has data): created at PO receipt,
  carries PO + vendor identity. Keep as-is — it already IS the batch record.
- **Serial layer = MaterialSpool** (built, currently unwired): each spool belongs to
  a receipt/lot. Wire `ProductionOrderSpool` consumption into production completion.

**Enforcement is a COMPANY SETTING (off by default), not a global behavior:**
- Setting ON (regulated mode): spool assignment is MANDATORY at consumption —
  production completion blocks without it. Full chain answerable: SO → SKU →
  material item → spool serial → receiving PO → vendor.
- Setting OFF: current behavior stands (item-level backflush, lot-FIFO attribution,
  no spool requirement). Spools page remains available as an optional registry.

Rationale: full serial traceability is real up-front operator work; most farms don't
need it, regulated customers (med-dev, aerospace) MUST have it. The setting makes it
a sales feature instead of universal friction.

Scope: design doc first (consumption UX when ON — spool picker/auto-pick-by-printer,
partial-spool handling, weight reconciliation; setting placement in company settings;
what the traceability report renders for OFF-mode history). Then implementation.
Unblocks plan-v1 PR-14 (consumption visibility), whose Materials card should render
spool serials when the setting is ON and lot attribution when OFF.
Impact: strategic (GTM differentiator for regulated buyers). Effort: L.

### HARD-15: Small-fix batch (one PR)

- Over-receipt tolerance: hard reject at ~516 → configurable % or operator override.
- PO edit-after-`ordered` should emit an "amended after ordering" event.
- UOM constant dedupe: 453.592 (~677) vs 453.59237 (~848) vs frontend ReceiveModal
  copies — route through `uom_config.py`.
- `product.last_cost_date` written (~782) but column doesn't exist — add column or
  remove write.
- `ReceiveModal.jsx` ~40-43 material detection by SKU prefix → use backend
  `is_material` flag in the PO line payload.
- MaterialLot.inspection_status set to "pending" (~814) and never updated — remove or
  wire (removal fine for now).
Impact: MED aggregate. Effort: M total, each S.

### HARD-16: Cycle-count pre-apply review (carried from plan v1 PR-17)

Variance-preview/confirm BEFORE posting adjustments + GL ("N adjustments, $X total
variance — Confirm"), and move "Fill Current Qty" away from Submit. After HARD-4a so
the confirm step posts through the canonical poster.
Impact: MED. Effort: M.

---

## Sequencing and file overlap

```
Immediate:  HARD-1 (dispatched), HARD-9, HARD-10        — independent, small
Wave 2:     HARD-2, HARD-3                              — independent of each other
Wave 3:     HARD-4a → 4b → 4c (serial; 4c needs human approval)
Wave 4:     HARD-5, HARD-11, HARD-16                    — all depend on 4a; 5 and 11
                                                          share inventory_service.py:
                                                          serialize or coordinate
Wave 5:     HARD-6 → HARD-7 and HARD-12                 — share netting helper
Anytime:    HARD-8, HARD-13, HARD-15
Design:     HARD-14 (user decision; blocks plan-v1 PR-14)
```

File-overlap warnings (Phase 1 lesson — check before parallel dispatch):
- `inventory_service.py`: HARD-4a, 5, 11 — strictly serialize.
- `purchase_order_service.py`: HARD-2, 8, 10, 15 — pairwise small but coordinate.
- `mrp.py`: HARD-3, 7, 10, 12.
- `blocking_issues.py` / `item_demand.py`: HARD-6, 12.

## Relationship to plan v1

Plan v1 Phase 2 UI items (PR-10 EmptyState, PR-11 ConfirmDialog, PR-12 pagination,
PR-13 nav regroup) are frontend-only and can run in parallel with this plan at any
time. PR-8 (expanded, issue #680) is independent. PR-14 (consumption visibility) is
BLOCKED by HARD-14's spine decision. PR-18 (onboarding) is independent.

## Open observations folded in or deferred

- Revenue recognition timing (GL at invoicing vs Sales Journal at shipment) — Aeonyx
  obs #168 — DEFERRED to a Phase 3 accounting-polish decision; not in this plan.
- Issue #680 (workflow gating / close-short) — lives in plan v1 PR-8 (expanded).
