# QMS Expansion Roadmap (#784)

FilaOps Core is growing a real Quality Management System on top of the
`qc_inspections` spine. This document is the sequenced plan. It is deliberately
**selectable** — see "The dial" below — so shops that do no formal QC are never
burdened, while regulated shops (medical / aerospace) get plan-driven inspection.

**Build split:** Core backend (this repo) builds the data + API; the UI is built
separately against these endpoints. NCR/CAPA, certificates (CoC/CoA/FAI), AQL
sampling, the SPC rule-violation engine, and plan approval/e-signature are **PRO**.

## The dial (selectable rigor)

A company-wide QC mode, stored in the `system_settings` KV store and resolved by
`app.services.quality_policy.get_quality_policy`:

| `quality_mode` | Meaning |
|----------------|---------|
| `off` | No QC surfaces at all. |
| `basic` (default) | Historical behavior: pass/fail + notes on a work order. |
| `full` | Plan-driven inspection: characteristics, measurements, defects, photos, and optional close-gating. |

Plus `quality_gate_close` (bool, default false): in `full` mode, whether a failed
inspection **hard-blocks** op/order close, or merely holds/flags it.

**The contract every QMS PR must honor:** when the mode is `off`/`basic`, the new
machinery is a graceful no-op — existing installs behave exactly as before. The
UI reads `GET /api/v1/quality/policy` to decide what to show.

## The end-to-end flow (target)

1. A product optionally carries a **quality plan**: which characteristics to
   measure (nominal + LSL/USL + unit) and which routing operations require
   inspection.
2. At order release, inspection-flagged operations are stamped.
3. An operator records a QC inspection **against a specific operation**, with the
   measurement form **pre-populated from the plan**.
4. Inspections capture measurements + defects + photos, attributed to
   printer / work-center / operator / inspector.
5. In `full` mode, a failed inspection gates op/order close (per the policy).
6. Grouped metrics + trend + SPC read the spine; a Quality lane appears in the
   command center.

## Sequenced Core PRs

| # | PR | Depends | Status |
|---|----|---------|--------|
| 1 | **QC policy/mode foundation** (the dial) | — | this PR |
| 2 | Inspection photos (upload/list/download/delete) | 1 | planned |
| 3 | Operation-targeted QC (+`requires_inspection` flag on routing ops) | — | planned |
| 4 | Denormalize grouping keys (printer/work-center/operator) onto `qc_inspections` | 3 | planned |
| 5 | Item Quality Plan (`quality_plans` + `quality_plan_characteristics` + CRUD) | 1 | planned |
| 6 | Plan-driven inspection (pre-fill + validate measurements vs plan) | 3, 5 | planned |
| 7 | Per-operation completion gating (`full` mode) | 3 | planned |
| 8 | Grouped metrics (by printer/work-center/operator/severity) | 4 | planned |
| 9 | Trend metrics (day/week time series) | 4 | planned |
| 10 | SPC characteristic stats (Cpk / %OOS + control-chart series) | 5 | planned |
| 11 | Quality lane in the command center | 1, 8 | planned |
| 12 | Consistency + cleanup (re-point recent-inspections at the spine, grouping indexes, docs, remove dead cert flags) | — | planned |

### Locked decisions
- **Plan shape**: a quality-plan header on the product; each characteristic
  optionally links to a routing operation/stage (mirrors BOM/Routing).
- **Full-mode gating**: configurable, defaults to *hold* (`quality_gate_close`
  off); regulated shops switch on hard-block.
- **Core owns all tables**; PRO references them via FK and never alters them.
