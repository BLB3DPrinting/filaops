# seed_demo — Deferred features checklist

Each entry here is a piece of spec intent the seed does NOT fully exercise
today, with the reason and the trigger to revisit. When a feature lands in
Core, find the entry here, update the matching seed module, and remove the
line from this file.

## Deferred

### [ ] Quality dashboard UI exercise
- **Spec ref:** acceptance criterion (v4.0.0 "quality dashboard" feature check)
- **Status:** `record_qc_inspection()` IS called for 5 of the 15 completed
  production orders, so QC rows exist in the DB. The dashboard page itself
  was not confirmed wired in v4.0.0 as of 2026-04-17.
- **Trigger to revisit:** a Quality dashboard page appears under
  `/admin/quality` (or similar) and consumes `qc_status / qc_inspected_*`.
- **Action:** no code change needed — data is already seeded. Just verify
  the dashboard renders correctly after re-seed.

### [ ] Month-end close
- **Spec ref:** §Accounting — "At least one month-end close performed (if
  the feature supports it in v4.0.0 — skip if not)".
- **Status:** no month-end close routine exists in Core. Skipped entirely.
- **Trigger to revisit:** a month-end close service / endpoint ships.
- **Action:** add an `accounting.py` seed module that calls the close
  routine for the month preceding `_time.now()`.

### [ ] Sales order 'draft' status
- **Spec ref:** §Sales Orders — Draft bucket.
- **Status:** `SalesOrder.status` accepts `{pending, confirmed, in_production,
  shipped, closed_short, cancelled}` — no literal `draft`. The 3 Draft rows
  remain at `status='pending'` (the default for newly-created orders).
- **Trigger to revisit:** a `draft` value is added to the status enum/column.
- **Action:** in `sales_orders.py`, add a transition loop that flips those
  3 order IDs from `pending` to `draft`.

### [ ] Quote 'draft' status
- **Spec ref:** §Quotes — 2 Draft.
- **Status:** `Quote.status` accepts `{pending, approved, accepted, rejected,
  converted, expired, cancelled}` — no `draft`. The 2 Draft quotes are
  stored with `status='pending'` + `admin_notes='DRAFT: internal -- not yet
  sent to customer'` so they're distinguishable in the admin view.
- **Trigger to revisit:** a `draft` status (or similar) lands in the quote
  model.
- **Action:** replace the `admin_notes` marker in `quotes.py` with a real
  status flip.

### [ ] Full close-short workflow
- **Spec ref:** §Sales Orders — "Closed Short: 5 | Exercises the Accept Short
  / Close Short workflow".
- **Status:** 3 sales orders get `status='closed_short'` + a minimal
  `CloseShortRecord` row (for audit-view population), but the full
  `close_short_sales_order()` service function is NOT called. That service
  needs reliable production-order quantities and linked PO states, which
  don't exist at the moment sales_orders.py runs (production.py runs later).
- **Trigger to revisit:** either (a) reorder the pipeline so production runs
  before sales_orders, or (b) build a second-pass 'finalize' step that runs
  after production.py and upgrades the closed_short rows with proper workflow
  state.
- **Action:** call `close_short_sales_order()` with realistic line_adjustments
  for the 3 orders.

### [ ] Close-short workflow for production orders
- **Spec ref:** §Production Orders — "accepted-short" mix entry.
- **Status:** 5 production orders are seeded with `status='completed'`,
  `qc_status='waived'`, `quantity_completed < quantity_ordered` — but the
  `accept_short_production_order()` service is NOT called (same runtime
  reasoning as above).
- **Trigger to revisit:** dedicated Accept-Short audit view renders and
  looks sparse.
- **Action:** in `production.py`, replace the direct accepted-short stamps
  with `accept_short_production_order()` calls.

### [ ] Ship date / payment date variance stress-testing
- **Spec ref:** implicit in §Sales Orders date spread.
- **Status:** current spread is uniformly random over 90 days with ship 3–14
  days after order and payment 1–10 days after ship. Good for most charts,
  but doesn't exercise edge cases like "invoice overdue >60 days" or
  "shipped same-day".
- **Trigger to revisit:** AR Aging dashboard or "overdue invoices" feature
  needs fixture data.
- **Action:** carve out ~5 orders with shifted date distributions.

### [ ] MRP run pre-seeded
- **Spec ref:** §MRP — "Do NOT pre-run MRP".
- **Status:** INTENTIONAL — the spec asks us NOT to run MRP so the screenshot
  operator can run it live and show the 'generated planned orders' output.
  Low-stock raws + demand from 50 sales orders + 40 production orders produce
  enough shortage signal for 4+ planned orders.
- **Trigger to revisit:** never (leave this one alone).

---

## How to use this file

- **When a deferral gets addressed:** remove its section entirely. Don't
  leave "DONE" markers — git history has that.
- **When a new deferral is identified during a re-seed:** add a section
  with the same shape (spec ref, status, trigger, action).
- **Before a release:** scan this file to decide which deferrals block the
  release vs which can ride through.
