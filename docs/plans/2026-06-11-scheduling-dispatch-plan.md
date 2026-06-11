# Production Scheduling & Dispatch Plan (Plan v3)

Date: 2026-06-11
Author: Claude (architect/PM session `claude-filaops-pm-20260610-uibatch`)
Status: APPROVED FOR EXECUTION (owner approved B→A→C order, maintenance woven through)
Source: read-only scheduling capability recon (2026-06-11) grounded in code, plus the
maintenance-subsystem audit. Companions: plan v1 (`2026-06-09-ux-gtm-readiness.md`,
complete except PR-14), plan v2 (`2026-06-10-core-integrity-hardening.md`, complete).

## What this plan is NOT

Spool/serial traceability (HARD-14 design doc, `2026-06-11-regulated-traceability-design.md`)
is explicitly DEFERRED to plan v4/v5 per owner decision. Nothing in this plan touches
MaterialSpool/ProductionOrderSpool or the regulated-mode setting.

## Grounding — what already exists (do not rebuild)

- **Scheduling engine**: `backend/app/services/resource_scheduling.py` — per-resource
  schedules, conflict detection, `find_next_available_slot`, predecessor validation
  (`check_predecessor_scheduling`), `schedule_operation`. WORKS.
- **Endpoints**: `backend/app/api/v1/endpoints/scheduling.py` — capacity check,
  available slots, machine availability, `POST /auto-schedule` (PRO-gated; includes
  material↔machine compatibility via `resource_compatibility_service.is_machine_compatible`
  — ABS/ASA blocked on open-frame printers), resource conflicts.
- **Data model complete**: ProductionOrder has due_date/scheduled_start/scheduled_end/
  priority; ProductionOrderOperation has printer_id/work_center_id/resource_id +
  scheduled times; WorkCenter has capacity fields; Resource has status incl.
  "maintenance" and `is_available`; Printer has live status via discovery (MQTT) +
  capabilities JSON; PrintJob tracks queued→printing.
- **UI**: `OperationSchedulerModal.jsx` — resource picker, live conflict check,
  next-slot suggestion, compatibility warning. AdminProduction queue + kanban.
  CommandCenter `MachineStatusGrid`.
- **Maintenance subsystem (freemium, backend mostly done)**: `MaintenanceLog` model
  (printer_id, maintenance_type, performed_at, **next_due_at**, cost,
  downtime_minutes, parts_used), full CRUD + maintenance-due endpoints
  (`endpoints/maintenance.py`), `MaintenanceModal.jsx` on the Printers page.
  What's missing is the marriage to scheduling.
- **E2E spec as design artifact**: `frontend/tests/e2e/pages/scheduling.spec.ts`
  describes a Gantt-style Scheduler view (day/week/month, machine rows,
  auto-schedule) that was never implemented — Phase A's acceptance source.

## Owner decisions baked into this plan

1. **Order: B (dispatch) → A (visibility/Gantt) → C (capacity realism).** Dispatch
   does the work; the Gantt is a window. For a small farm, jobs flowing to idle
   machines beats a wall chart.
2. **Suggest-and-confirm by default.** Dispatch computes automatically, commits with
   a human click. A company setting `auto_dispatch` (default OFF) flips it to fully
   automatic when the owner trusts it. Same philosophy as the buy list / MRP layers.
3. **Maintenance is a thread, not a phase.** Dispatch is maintenance-aware from day
   one; Phase C's "calendars" are de-scoped to maintenance windows only (no shift
   calendars/holidays until a customer pulls).
4. **Prerequisite**: issue #715's fix (WO release allocation sync) must be merged
   before SCHED-3 end-to-end testing — dispatch assigns RELEASED orders.

## How to use this document

Execution model unchanged from plans v1/v2: each item is a self-contained spec for one
session on its own isolated worktree. Sessions MUST: verify worktree isolation first;
register Aeonyx session + claim files; branch off CURRENT origin/main and re-verify
line refs; backend/.env from the canonical checkout (never print), DATABASE_URL =
local `filaops` only; full PR loop, stop at green-and-triaged, PM merges; check the
file-overlap table before parallel dispatch. PM applies `alembic upgrade head` to the
dev DB after merging any migration and re-checks single-head at merge time.
Conventions: ruff E712, Decimal-only for quantities, GL/ledger-adjacent code requires
an independent reader before merge.

---

## Phase B — dispatch first

### SCHED-1: Dispatch service (the brain)

A read-only ranking + a single explicit assign action. New
`backend/app/services/dispatch_service.py`:

- `get_dispatch_suggestions(db, printer_id=None)` — for each idle, available printer
  (Resource/Printer status checks; SKIP status="maintenance" — pin with a test):
  rank candidate work: released production orders' next pending printable operation
  (operation's work center/resource class matches the printer; predecessors satisfied
  per `check_predecessor_scheduling`), ordered by priority (1 first) → due_date
  (earliest) → created_at (FIFO). Filter by
  `resource_compatibility_service.is_machine_compatible`. Returns per-printer:
  top suggestion + next 2 runners-up, each with WHY (rank factors) so the operator
  trusts it.
- **Maintenance-aware**: if the printer's latest `MaintenanceLog.next_due_at` falls
  before now + the operation's estimated duration (routing operation time fields —
  verify what exists; fall back to a default if absent), the suggestion carries a
  `maintenance_warning` ("due for maintenance before this job would finish") — warn,
  never silently skip; the operator decides.
- `dispatch_operation(db, operation_id, printer_id, user)` — the commit action:
  validates compatibility + conflicts via the EXISTING engine, calls
  `schedule_operation` with now→now+duration, sets operation status appropriately.
  No new scheduling math — orchestration only.
- ZERO writes in the suggestion path. Staff-gated endpoints:
  `GET /api/v1/dispatch/suggestions` (+ `?printer_id=`),
  `POST /api/v1/dispatch/assign`.
- Tests: ranking order (priority beats due date beats FIFO); maintenance status
  skipped; maintenance-due warning present/absent; incompatible material excluded;
  predecessor-not-ready excluded; assign path validates conflicts.

Impact: HIGH — this is Phase B's engine. Effort: M. Files: new service + endpoint,
api/v1/__init__.py registration, tests. DEPENDS ON: #715 fix merged (for live
end-to-end verification only; unit tests don't need it).

### SCHED-2: Reschedule / move (dispatch's undo)

Scheduled operations are currently immovable (no endpoint). Add:
- `POST /production-orders/{id}/operations/{op_id}/reschedule` — new resource and/or
  new start; revalidates conflicts + predecessor rules via the existing engine
  (`exclude_operation_id` param already exists in `find_conflicts` for exactly this);
  clear 400s on violation; writes an audit trail (OrderEvent or equivalent — inspect
  what production events exist and reuse).
- `POST .../unschedule` — clear scheduled times + resource, return op to pending
  (only when not started).
- OperationSchedulerModal: when an op is already scheduled, the modal becomes
  edit-mode (prefilled, "Reschedule"/"Unschedule" actions).
- Tests: move validates conflicts excluding self; unschedule only pre-start; audit
  entries written.

Impact: HIGH (no dispatch without undo). Effort: S/M. Files:
resource_scheduling.py (small additions), production_orders endpoint, modal + tests.
COORDINATE: SCHED-1 also touches resource_scheduling.py lightly — serialize 1 → 2 or
keep 2's engine edits additive-only.

### SCHED-3: Dispatch UI (suggest-and-confirm)

- Production queue (AdminProduction) and/or CommandCenter MachineStatusGrid: idle
  printers show a "Next up" chip — suggested order, material, due date, the WHY, and
  any maintenance warning — with one-click Confirm (calls /dispatch/assign) and a
  "pick different" affordance opening the existing scheduler modal prefiltered.
  Choose the surface that fits each page's existing patterns; CommandCenter grid is
  the primary home (it's the landing page now).
- `auto_dispatch` company setting (default OFF) in company settings + Settings UI
  toggle: when ON, suggestions auto-commit on printer-idle detection. Gate the
  auto-path carefully: never auto-assign a suggestion carrying maintenance_warning.
- Printer-idle refresh: when printer status flips to idle (the discovery service
  already tracks status), the UI refreshes suggestions — signals, not regenerative
  computation (Layer-3 philosophy). Polling the suggestions endpoint on the existing
  status-poll cadence is acceptable; no new websocket infrastructure.
- Wire the EXISTING PRO `POST /auto-schedule` endpoint to a button in
  OperationSchedulerModal ("Auto-pick slot") — it's built and unused.
- Tests: chip renders suggestion + warning; confirm calls assign; auto_dispatch OFF
  by default; auto-path skips warned suggestions.

Impact: HIGH — where Phase B becomes visible. Effort: M. Files: CommandCenter
components, AdminProduction, OperationSchedulerModal, settings page + backend
setting, tests. DEPENDS ON: SCHED-1 (and SCHED-2 for the pick-different flow).

### SCHED-4: Maintenance visibility quick wins

- Due-soon badge on PrinterCard (existing maintenance-due endpoint; threshold: due
  within 7 days or overdue — constant, not a setting yet).
- Command Center action item: "N printers due for maintenance" (extend
  command_center.py's get_action_items; priority 3).
- Pin the dispatch-skips-maintenance-status behavior with an integration test if
  SCHED-1 didn't already.
Impact: MED, cheap. Effort: S. Files: PrinterCard, command_center.py + endpoint
schema, tests. Parallel-safe with everything except SCHED-3's CommandCenter edits —
coordinate or fold into SCHED-3's PR if the same agent.

---

## Phase A — visibility (after B ships)

### SCHED-5: Scheduler (Gantt) view

The view `scheduling.spec.ts` already describes: machine rows × time axis;
day/week/month modes; date navigation; renders scheduled operations (from
`get_resource_schedule`), currently-running operations, and printer maintenance
STATUS as blocks; click-through opens OperationSchedulerModal (edit-mode per
SCHED-2). READ-ONLY first — explicitly NO drag-and-drop in this item (the E2E spec
notes @dnd-kit as future; defer). Lives as the "Scheduler" tab/toggle on
AdminProduction the tests expect. Largest single UI build in this plan — budget a
full session; reuse machine-availability endpoint for utilization shading.
Acceptance: the relevant scheduling.spec.ts cases pass un-skipped.
Impact: HIGH visibility. Effort: L. DEPENDS ON: SCHED-2 (modal edit-mode).

### SCHED-6: Capacity context (optional, owner pull)

Utilization summary (per machine, % booked next 7 days) + "what's blocking this
slot" peek on conflicts. Skip unless the Gantt leaves the owner wanting it.
Impact: MED. Effort: M.

---

## Phase C — capacity realism (de-scoped to maintenance windows)

### SCHED-7: Maintenance windows (the only calendar we need yet)

- Model: `maintenance_windows` (printer_id/resource_id, starts_at, ends_at, reason,
  optional link to MaintenanceLog when completed) via Alembic migration.
- Engine: `find_conflicts`/`find_next_available_slot` treat windows as busy;
  dispatch suggestions exclude printers inside a window and warn when a job would
  overlap an upcoming one (upgrade SCHED-1's next_due_at heuristic to real windows).
- Status: printer status auto-flips to "maintenance" during an active window and
  back after (scheduler/poll hook — inspect discovery service for the right seam).
- UI: schedule-a-window from MaintenanceModal/PrinterCard; Gantt renders windows as
  blocks (SCHED-5 dependency).
- Completing a window writes the MaintenanceLog entry (closing the loop with
  next_due_at recalculation).
Impact: HIGH for trustworthy scheduling. Effort: M/L. DEPENDS ON: SCHED-1/5.

### SCHED-8: Backward scheduling from due date  [design-first, owner pull]

Schedule-latest-start = due_date − Σ remaining operation durations; propose slots
working backwards. Only on explicit owner pull; design note before code.

### SCHED-9: Dispatch heuristics v2  [post-GTM, owner pull]

Load balancing (best-fit vs first-idle), schedule stability/freeze windows,
multi-order campaign batching (same material → same printer runs). Explicitly out
of scope until real-farm feedback exists.

---

## Sequencing & file overlap

```
Wave 1 (after #715 fix merges):  SCHED-1  → then SCHED-2  (share resource_scheduling.py)
Wave 2:                          SCHED-3  + SCHED-4        (coordinate CommandCenter files
                                                            or same agent)
Wave 3:                          SCHED-5                   (solo — large)
Wave 4:                          SCHED-7;  SCHED-6/8/9 on owner pull
```

Overlap table:
- `resource_scheduling.py`: SCHED-1, 2, 7 — serialize.
- `OperationSchedulerModal.jsx`: SCHED-2, 3, 5 — serialize 2 → 3; 5 reads only.
- CommandCenter components: SCHED-3, 4 — coordinate or combine.
- `AdminProduction.jsx`: SCHED-3, 5 — serialize.
- `command_center.py`: SCHED-4 only.
- Migration in SCHED-7 only: PM checks single alembic head at merge, applies to dev DB.

## Relationship to other plans / open items

- Plan v1: complete except PR-14 (blocked on HARD-14 owner answers — deferred with
  traceability to v4/v5). Plan v2: complete.
- #715 fix (in flight at plan-writing time): prerequisite for Phase B live testing.
- Backlog NOT in this plan: buy-list Layer 2 (plan-and-firm), HARD-13 vendor catalog,
  HARD-15 small fixes, draft-PO-as-supply policy flip, #680 item 4, revenue
  recognition timing (obs #168). All remain dispatchable from their existing specs.
