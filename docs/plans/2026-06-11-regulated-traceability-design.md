# Regulated Traceability — Spool-Serial Consumption (HARD-14 Design)

> **Status: DRAFT — AWAITING OWNER REVIEW**
> Design proposal for the serial-traceability layer decided in
> `docs/plans/2026-06-10-core-integrity-hardening.md` (HARD-14). This document is the
> design step the owner asked for *before* implementation. Nothing here is built yet.

Date: 2026-06-11
Owner decision of record: HARD-14 in `2026-06-10-core-integrity-hardening.md`
(lines 309–354).

---

## 1. What this is, in one paragraph

Today FilaOps already has a **batch** traceability layer that works: when you receive a
purchase order, FilaOps creates a `MaterialLot` carrying the vendor, the PO, the received
quantity, and the unit cost. At consumption it FIFO-attributes those lots. This runs for
everybody and keeps running. What is *not* wired is the **serial** layer — the individual
physical spool. The `MaterialSpool` table and a `ProductionOrderSpool` junction exist, but
no production-completion path records "this work order ate from spool PLA-BLK-2026-014."
HARD-14 wires that serial layer in, **gated by a company setting that is off by default**,
so a regulated customer (medical-device, aerospace) can answer "which physical spool went
into this shipped part" while a hobby farm never sees the extra friction.

The owner's model: **spool = serial, PO/receipt = batch.** The two layers are hierarchical,
not rivals. A mill cert per filament lot is not a thing filament vendors give you, so
"lot-as-mill-cert" is dropped; `MaterialLot` simply *is* the batch record.

---

## 2. Where the code stands today (grounding)

### 2.1 The batch layer already works

Receiving creates the lot. In `backend/app/services/purchase_order_service.py`, the receive
flow builds a `MaterialLot` at `purchase_order_service.py:1060–1078`, carrying
`vendor_id`, `purchase_order_id`, `vendor_lot_number`, `quantity_received`, and `unit_cost`.

Consumption attributes lots. In `backend/app/services/production_execution.py`,
`explode_bom_and_reserve_materials` (`production_execution.py:108–264`) checks
`LotPolicyService.is_lot_required_for_product` (`:156`), and when a lot is selected it
records a `ProductionLotConsumption` row (`:245–251`) linking the production order to the
material lot and BOM line. This is the existing OFF-mode behavior and it does not change.

### 2.2 The serial layer is built but unwired

`MaterialSpool` (`backend/app/models/material_spool.py:14–74`) tracks one physical roll:
`spool_number` (unique), `product_id`, `initial_weight_kg` / `current_weight_kg` (note:
**these columns store grams despite the `_kg` name** — see `purchase_order_service.py:1143`
and `spools.py:566`), `status`, `location_id`, `supplier_lot_number`, `expiry_date`.

`ProductionOrderSpool` (`material_spool.py:77–98`) is the junction: `production_order_id`,
`spool_id`, `weight_consumed_kg` (also grams), `created_by`. **There is no
`material_lot_id` on `MaterialSpool`** — the spool's batch is only inferable today by
correlating `ProductionOrderSpool` and `ProductionLotConsumption` on the same PO.

Spools are created at receiving in the *same loop iteration* as the lot, when the operator
opts in via `create_spools` (`purchase_order_service.py:1086–1171`). The lot is already
flushed (has an id) at `:1077` before the spool block runs at `:1145` — so the FK can be
populated right there with zero extra queries.

### 2.3 The consumption recorder exists and is correct; the service-layer one is broken

`POST /api/v1/spools/{spool_id}/consume` (`backend/app/api/v1/endpoints/spools.py:517–589`)
already records consumption correctly: it validates spool status and PO status, upserts a
`ProductionOrderSpool` row, decrements `current_weight_kg`, and flips the spool to `empty`
under a 5g threshold. This is the path to build on.

**Pre-existing bug to flag (not introduced here):**
`production_order_service.assign_spool_to_order` / `get_order_spools`
(`production_order_service.py:1782–1842`) reference `spool.code`, `spool.quantity_remaining`,
and `ProductionOrderSpool(assigned_by=...)` — none of which exist on the models
(`spool_number`, `current_weight_kg`, `created_by`). These functions are wired to endpoints
at `production_orders.py:1193–1210` but would raise `AttributeError` if called. They are
effectively dead. HARD-14 implementation should fix or remove them rather than build on top.

### 2.4 The traceability report already exists

`frontend/src/pages/admin/quality/MaterialTraceability.jsx` renders forward (spool →
products → customers) and backward (serial → material → vendor) chains with DHR JSON export.
The backend chain lives in `backend/app/services/traceability_service.py`
(`get_serial_traceability` at `:840+`, forward spool trace at `:710+`).

**Important accuracy gap the FK fixes:** `_get_purchase_info_for_spool`
(`traceability_service.py:81–110`) currently resolves a spool's PO/vendor by *"most recent
PO line for the same product"* (`order_by(desc(PurchaseOrderLine.created_at)).first()`).
That is a guess — it returns the latest PO for that material, **not the PO the spool was
actually received on.** For a regulated chain this is wrong. `MaterialSpool.material_lot_id`
makes the resolution deterministic: spool → its lot → the lot's PO → vendor.

### 2.5 No printer carries a "loaded spool" state

`backend/app/models/printer.py` stores AMS capability metadata
(`capabilities.ams_slots`, `printer.py:48,94–98`) but **no current/loaded-spool field**.
Auto-suggesting a spool from the printer's loaded filament therefore requires new state that
does not exist today. This is an open question, not a given (see §7).

---

## 3. Schema changes

### 3.1 `MaterialSpool.material_lot_id` (the spine)

```text
ALTER TABLE material_spools
  ADD COLUMN material_lot_id INTEGER NULL REFERENCES material_lots(id);
CREATE INDEX ix_material_spools_material_lot_id ON material_spools (material_lot_id);
```

- **Nullable on purpose.** Legacy spools and manually-registered spools predate any receipt
  and will have no lot. New spools created at receiving get it populated.
- **Populated at receiving.** In `purchase_order_service.py`, after the lot is flushed
  (`:1077`) and inside the spool-creation loop (`:1145`), set
  `spool.material_lot_id = material_lot.id`. Both already exist in scope; no extra query.
- **Read-side fallback for legacy rows only.** The correlation join
  (`ProductionOrderSpool` ↔ `ProductionLotConsumption` on the same PO) stays as a fallback
  for rows where `material_lot_id IS NULL`. New data must never rely on it.

Migration goes in `backend/migrations/versions/` (Alembic; latest heads under that dir).
Brownfield backfill of the FK is discussed in §6.

### 3.2 The company setting

`CompanySettings` (`backend/app/models/company_settings.py`) is the singleton settings table
and already holds boolean feature flags in exactly this shape — `tax_enabled`
(`:42`), `external_ai_blocked` (`:92`). Add one more:

```text
ALTER TABLE company_settings
  ADD COLUMN require_spool_traceability BOOLEAN NOT NULL DEFAULT FALSE;
```

Name: **`require_spool_traceability`**. Default **FALSE** (off). This single boolean is the
fork point for every behavior in this doc. Surface it in the existing Company Settings admin
screen next to the other operational toggles, with help text framed as a regulated-mode
switch (see §4.5 copy).

Rationale for living on `CompanySettings` and not a per-customer profile: the owner's
decision is that enforcement is a **company-wide mode**, not a per-order or per-customer
rule. (A per-customer `CustomerTraceabilityProfile` already exists for the *lot* layer via
`LotPolicyService`; the spool mode is deliberately coarser — it's a posture the whole shop
adopts, usually to satisfy one regulated account, and applying it shop-wide avoids a
half-traced shop.)

### 3.3 `ProductionOrderSpool` wiring

No column changes. The junction is used as-is. The implementation adds:
- a **batched assignment write** at production completion (one row per spool consumed),
  reusing the upsert logic already proven in `spools.py:560–586`;
- population of `weight_consumed_kg` (grams) from the backflush quantity (see §4.4).

---

## 4. Consumption UX when the setting is ON

Voice note: this section is written for the operator who runs the floor, in the same
register as the Inventory Reconciliation guide.

### 4.1 Where the assignment happens — at completion, not at start

There are two candidate moments: when an operation *starts* (you reserve material) and when
it *completes* (you backflush what was actually used). **Assign at completion.**

Why completion is the least-friction point:
- Completion is where FilaOps already knows the real consumed quantity — the operator just
  told it how many good and bad units came off (`OperationCompletionModal.jsx:228–229`).
  The backflush quantity is the number we reconcile spool weight against. At *start* you
  only have an estimate.
- The print farm reality: a spool can run out mid-print and get swapped. If you forced the
  pick at start you'd capture the wrong spool half the time. Capturing it at completion lets
  the operator record "I actually finished this on PLA-BLK-015 after -012 ran dry."
- Completion is already a deliberate, single confirm step. Adding the picker there means one
  modal, not two.

The lot layer stays where it is (selected at material reservation/start via
`explode_bom_and_reserve_materials`). The spool layer is the completion-time addition. They
do not move each other.

### 4.2 The spool picker

The picker is a new section inside `OperationCompletionModal.jsx`, rendered **only when
`require_spool_traceability` is ON** (the modal fetches the setting, or it rides along on the
operation payload). It sits above the Complete button so the operator cannot finish without
addressing it.

Layout, plain version:

```
Material used for this operation
  [ PLA Black  •  spool picker ▼ ]   used: [ 248 ] g
  + Add another spool

  Backflush expects ~250 g for 50 good units.  ✓ within tolerance
```

- **Filtered list.** The dropdown shows only spools that match the operation's consumed
  material *and* are `status = active`, sorted by location then by lowest remaining weight
  (FIFO-friendly: burn the nearly-empty spool first). Filtering by material is non-negotiable
  — picking a spool of the wrong material is a traceability lie. Filtering by location is a
  strong default but overridable (a spool can physically move).
- **Auto-suggest.** If a printer "loaded spool" linkage exists (it does **not** today —
  see §2.5 and §7), pre-select the spool loaded on the work order's printer. Until that state
  exists, auto-suggest falls back to "the most-recently-consumed active spool of this
  material on this printer's recent orders," which is a heuristic, not ground truth. The
  honest v1 is: no auto-pick, a clean filtered list, FIFO-sorted.
- **Multi-spool.** "Add another spool" lets the operator split consumption across spools
  (the run spanned a swap). Each line is `{spool_id, grams}`. The lines must sum to the
  backflush quantity within tolerance.

### 4.3 Partial-spool handling

A spool is rarely consumed whole. The picker captures *grams used from this spool for this
operation*, not "consume the spool." On submit:
- decrement `current_weight_kg` (grams) by the entered amount, mirroring
  `spools.py:582–589`;
- if the result drops under the 5g empty threshold, flip `status = empty` (same rule as
  `spools.py:588`);
- the spool stays available for the next order until it's empty.

This is the existing partial-consume behavior; HARD-14 just drives it from completion instead
of a manual API call.

### 4.4 Weight reconciliation against the backflush

FilaOps computes the expected material from the BOM × completed quantity (the same math
`consume_production_stage_materials` already does at
`production_execution.py:319–326`). The operator's entered spool grams are reconciled against
that expected figure:

- **Within tolerance:** record the spool consumption at the *entered* grams, post the normal
  item-level backflush at the *BOM-derived* grams (the ledger stays BOM-driven so inventory
  valuation is unchanged), and link the `ProductionOrderSpool` row. Show a quiet ✓.
- **Outside tolerance:** warn inline ("Backflush expects ~250 g, you entered 310 g — that's
  24% over"). Do **not** hard-block on a weight mismatch by default — a mismatch is a data-
  quality signal, not a safety stop, and blocking would strand a finished part. Surface it,
  let the operator confirm with a reason, and record the variance so it shows up in
  reconciliation (the same drift story the reconciliation guide already tells). The tolerance
  percentage is an owner decision (§7).

What ON-mode **does** hard-block on is a *missing* spool assignment, not a weight mismatch —
see §4.5.

### 4.5 What blocks when assignment is missing

When `require_spool_traceability` is ON and the operator tries to complete without assigning
a spool to traced material, the completion endpoint (`POST
/production-orders/{order_id}/operations/{id}/complete`, served via
`production_orders.py:637` → `production_order_service.complete_production_order` →
`consume_production_materials`) returns **400** with operator-readable copy:

> **Spool assignment required.** This shop runs in regulated traceability mode, so every
> consumed material needs a physical spool on record before an operation can complete.
> Pick the spool(s) you used for **PLA Black** above, then complete again.

The block lives server-side (the modal also disables the button client-side, but the 400 is
the real gate so the rule can't be bypassed by a direct API call). The fork is a single
`if settings.require_spool_traceability:` branch in the consume path.

The setting's own help text in Company Settings:

> **Require spool traceability (regulated mode).** When on, operators must record the
> physical spool(s) consumed before completing a production operation. Use this when a
> customer (medical, aerospace) requires you to prove which physical material went into their
> parts. Most farms leave this off. Turning it on adds a required step to every completion —
> read the brownfield notes before flipping it on a shop with work already in progress.

---

## 5. OFF-mode behavior is unchanged

When `require_spool_traceability` is FALSE (the default), nothing about consumption changes:

- Material reservation and lot selection run exactly as today via
  `explode_bom_and_reserve_materials` (`production_execution.py:108–264`), including
  `LotPolicyService` lot-required checks and `ProductionLotConsumption` recording.
- Completion backflushes item-level via `consume_production_stage_materials`
  (`production_execution.py:266–376`). No spool picker renders. No spool assignment is
  required. No 400 on missing spool.
- The Spools page and `POST /spools/{id}/consume` remain available as an *optional* registry
  for shops that want to track spools without enforcement.

**The exact code paths that fork on the setting:**
1. `OperationCompletionModal.jsx` — renders the §4.2 picker section only when ON.
2. The completion service path (`complete_production_order` /
   `consume_production_materials`) — the §4.5 missing-assignment 400 and the
   `ProductionOrderSpool` write only execute when ON.
3. The Materials card in plan-v1 PR-14 (§6.4 of plan-v1; see §6 below) — renders spool
   serials when ON, lot attribution when OFF.

Everything else (lot layer, ledger, GL, valuation) is mode-independent and runs in both.

---

## 6. Brownfield first-enablement

Regulated customers are conversions, not fresh installs. A shop runs OFF for months, lands a
medical account, and flips ON with live work orders and a year of un-spooled history. This is
the moment most likely to generate a support ticket, so it gets first-class design.

The mental model borrows directly from the Inventory Reconciliation guide's **baseline /
epoch** language: flipping the setting ON stamps an **enablement moment**. History before it
is the **pre-traceability epoch**; work after it is the **traced epoch**. Pre-epoch records
are preserved read-only and are never back-filled with fake spool data — same principle as
"pre-count history is preserved read-only" in reconciliation.

### 6.1 In-progress work orders — the grace rule

Work orders that were already `released` / `in_progress` when the setting flipped did their
material reservation under OFF rules and have no spool selections. **Do not retroactively
block them.** The grace rule:

- An operation is subject to the spool requirement only if its production order was
  **created (or released) at/after the enablement moment.** Store the enablement timestamp
  (alongside the setting, or derive it from the setting's `updated_at`) and compare against
  the production order's `created_at` / release event.
- Pre-existing in-progress orders complete under OFF rules (no 400), but the completion modal
  shows a soft banner: *"This order started before regulated mode — spool assignment is
  optional here. New orders will require it."* The operator may still assign a spool
  voluntarily, and if they do it's recorded normally.
- New orders created after enablement are fully gated.

This avoids the failure mode where flipping the switch freezes the floor because twenty
in-flight jobs suddenly can't be completed.

### 6.2 Historical consumption in the report

Pre-epoch production orders consumed material with lot attribution (or item-level only) and
no `ProductionOrderSpool` rows. In the traceability report
(`MaterialTraceability.jsx`), these render with an explicit epoch label rather than an empty
or misleading section:

- Forward and backward results gain an epoch banner per production order:
  **"Pre-traceability epoch — recorded before regulated mode was enabled (2026-xx-xx).
  Material is traced to lot/vendor; physical spool serial was not captured."**
- The material lineage block still shows what *is* known for that epoch: the `MaterialLot`,
  the vendor, the PO (now resolved deterministically via `material_lot_id` where the lot
  exists, or via the legacy `_get_purchase_info_for_spool` guess where it doesn't). It simply
  has no spool serial, and says so plainly instead of rendering a blank.
- DHR export carries the epoch label so an auditor reading the JSON sees the distinction
  rather than assuming a missing serial is a gap in a traced record.

### 6.3 The chain report, per epoch

The full chain the owner wants — **SO → SKU → material item → spool serial → receiving PO →
vendor** — renders differently per epoch:

| Hop | Traced epoch (ON) | Pre-traceability epoch (OFF history) |
|-----|-------------------|--------------------------------------|
| SO → SKU | Yes (sales order → finished product) | Yes |
| SKU → material item | Yes (BOM component) | Yes |
| material → **spool serial** | **Yes** (`ProductionOrderSpool` → `MaterialSpool.spool_number`) | **No** — labeled "not captured (pre-epoch)" |
| spool → receiving PO | Yes, deterministic via `MaterialSpool.material_lot_id` → `MaterialLot.purchase_order_id` | Falls back to lot/PO via `MaterialLot` where present; "—" otherwise |
| PO → vendor | Yes (`MaterialLot.vendor_id` / `PurchaseOrder.vendor`) | Yes where a lot exists |

The point: a regulated auditor gets a complete serial chain for traced-epoch parts, and an
honest, clearly-labeled partial chain (down to lot/vendor) for anything made before the shop
went regulated — never a silent blank that reads as a broken record.

### 6.4 Relationship to plan-v1 PR-14 (consumption visibility)

Plan-v1 PR-14 adds a Materials consumption card to the production-order view. HARD-14 is its
blocker because the card's content depends on the mode:
- **ON:** the card lists each consumed material with its **spool serial(s)** and grams,
  pulled from `ProductionOrderSpool`.
- **OFF:** the card lists each consumed material with its **lot attribution** (lot number,
  vendor) pulled from `ProductionLotConsumption` — the data that already exists today.

PR-14 should read the setting and render the matching column set. It does not need its own
fork beyond "spool column vs lot column."

---

## 7. Open questions for the owner

These are the genuinely undecidable points — everything else above is a proposal that can
proceed once these are settled.

1. **Weight-mismatch tolerance.** What percentage gap between entered spool grams and
   BOM-backflush grams is "within tolerance" (quiet ✓) vs. "warn and require a reason"?
   Proposal: ±10% warn threshold, no hard block. Owner to set the number, and confirm
   mismatch never hard-blocks completion (only missing assignment does).
2. **Printer "loaded spool" state.** Should printers carry a current-loaded-spool field so
   the picker can auto-select ground truth (and so a spool swap is a first-class event)? This
   is real new state and arguably its own feature. Without it, v1 ships with a FIFO-sorted
   filtered picker and no auto-pick. Build the loaded-spool state now, or ship the manual
   picker first and add auto-pick later?
3. **Enablement granularity.** Is `require_spool_traceability` correctly a single
   company-wide boolean, or should it be selectable per-customer (reusing
   `CustomerTraceabilityProfile`) so a shop can run regulated mode only for the one account
   that needs it? The doc assumes company-wide per the HARD-14 decision; flagging it because
   per-customer is the more granular alternative and changes the fork from "shop mode" to
   "does this order's customer require it."
4. **Grace-rule anchor.** Should the grace boundary key off production-order `created_at`,
   the release event, or a separately stored enablement timestamp? Proposal: a stored
   enablement timestamp compared against PO `created_at`, because deriving it from the
   setting's `updated_at` breaks if the setting is ever toggled twice.

---

## 8. Implementation slicing

Four PR-sized work items. Each is independently reviewable; later slices depend on earlier.

### PR-A — Schema spine (no behavior change)
- **Adds:** `MaterialSpool.material_lot_id` FK + index; `CompanySettings.require_spool_traceability`
  boolean (default FALSE); Alembic migration in `backend/migrations/versions/`.
- **Wires:** populate `material_lot_id` at receiving in
  `purchase_order_service.py:1145–1164` (set from the already-flushed `material_lot.id`).
- **Fixes:** the deterministic spool→PO resolution in
  `traceability_service._get_purchase_info_for_spool` to prefer `material_lot_id` and fall
  back to the legacy product-guess only when null.
- **Also:** repair or remove the broken `assign_spool_to_order` / `get_order_spools` in
  `production_order_service.py:1782–1842` (and their endpoints) so they stop referencing
  non-existent fields.
- **Tests:** receiving populates the FK; chain resolves via FK; legacy null-FK rows still
  resolve via fallback. Setting defaults FALSE.
- **Files:** `backend/app/models/material_spool.py`, `company_settings.py`,
  `migrations/versions/<new>.py`, `purchase_order_service.py`, `traceability_service.py`,
  `production_order_service.py`, `backend/app/api/v1/endpoints/production_orders.py`,
  tests under `backend/tests/`.
- **Depends on:** nothing.

### PR-B — ON-mode consumption gate (backend)
- **Adds:** the §4.5 missing-assignment 400 and the `ProductionOrderSpool` write inside the
  completion/consume path, forked on `require_spool_traceability`. Reuses the upsert/decrement
  logic from `spools.py:560–589`.
- **Adds:** weight reconciliation (§4.4) against the BOM-backflush figure with the §7.1
  tolerance; mismatch warns + records variance, does not block.
- **Adds:** grace-rule check (§6.1) keyed on the enablement anchor (§7.4).
- **Tests:** OFF mode unchanged (no 400, no spool rows); ON mode blocks on missing
  assignment; ON mode records spool consumption + decrements weight; pre-epoch in-progress
  order completes without block.
- **Files:** `backend/app/services/production_order_service.py`,
  `backend/app/services/production_execution.py`,
  `backend/app/api/v1/endpoints/production_orders.py`, tests.
- **Depends on:** PR-A.

### PR-C — Spool picker UX (frontend)
- **Adds:** the §4.2 picker section in
  `frontend/src/components/production/OperationCompletionModal.jsx`, rendered only when ON;
  multi-spool lines; inline reconciliation feedback; the 400 surfaced as a toast.
- **Adds:** the Company Settings toggle + help copy (§4.5) on the existing settings screen.
- **Adds:** the grace-rule soft banner (§6.1) on pre-epoch in-progress orders.
- **Tests:** picker hidden when OFF; required when ON; multi-spool sum validation; setting
  toggle persists.
- **Files:** `OperationCompletionModal.jsx`, the Company Settings admin component, settings
  API hook, frontend tests.
- **Depends on:** PR-B (needs the endpoint contract).

### PR-D — Report epochs + PR-14 alignment
- **Adds:** epoch labeling (§6.2/§6.3) in
  `frontend/src/pages/admin/quality/MaterialTraceability.jsx` and the backend chain payloads
  in `traceability_service.py` (epoch flag per production order, carried into DHR export).
- **Aligns:** plan-v1 PR-14 Materials card to render spool serials (ON) vs lot attribution
  (OFF) (§6.4).
- **Tests:** traced-epoch chain shows spool serial; pre-epoch chain shows labeled partial
  chain to lot/vendor; DHR carries epoch label.
- **Files:** `traceability_service.py`, `MaterialTraceability.jsx`, the PR-14 Materials card
  component, tests.
- **Depends on:** PR-A (FK), PR-B (spool rows to display). Can land alongside PR-C.

```
PR-A (schema spine) ──┬── PR-B (ON-mode gate) ──┬── PR-C (picker UX)
                      │                          └── PR-D (report epochs + PR-14)
                      └── PR-D also reads FK directly
```

---

## 9. Sacred Rule check

All changes are in Core (`C:\repos\filaops`). No Core dependency on any PRO package is
introduced. The setting is a Core company setting; removing any future PRO module leaves the
serial-traceability feature running identically. Compliant.
