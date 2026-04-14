# FilaOps Core — Open Source ERP

> Primary safety is enforced by PreToolUse hooks and T-REX protocol. If a gate conflicts with behavioral instructions, the gate wins.

## 🔴 SACRED RULE

**"NO Core Changes from PRO. PRO Must Not Break Core."**

- Never modify files in Core (`C:\repos\filaops`) from the ecosystem repo
- Never add Core dependencies on any PRO / `filaops-ecosystem` package
- Core must run identically with zero PRO code installed
- PRO integrates via `register(app)`; keep coupling behind extension interfaces

## Aeonyx Session Protocol

**register → claim → recall → work → end**

1. `rex_register_session(session_id, branch, task)` at start
2. `rex_claim_files(session_id, branch, files)` before editing
3. `mem_recall("<topic>")` before major work (gated — will block otherwise)
4. During work: `mem_remember` for decisions/incidents/patterns, `cortex_observe` for pre-existing bugs
5. `rex_end_session` or `rex_handoff` at end

Don't store: routine file edits, blame attribution, "started working on X".
Pre-existing issues: report via `cortex_observe`, investigate, fix if safe, or add `# TODO(pre-existing)`.

## Layer 0 — Mechanical Gates (Enforced)

Enforced by hooks and CI. If blocked, read the block message and comply — don't route around.

- **0.1 Session Registration** — no edits until `rex_register_session`
- **0.2 Memory Recall** — no edits until `mem_recall` runs
- **0.3 File Claim** — no edits until file is claimed (one agent per file, TTL)
- **0.4 Type Check** — `pytest tests/ -x -q`, `npx tsc --noEmit`, `npx vitest run` must pass; CI is authority
- **0.5 Database Safety** — confirm `DATABASE_URL`, state it explicitly. This repo → `filaops`, never `filaops_prod`
- **0.6 Lockfile** — `npm ci` / `pip install --require-hashes` only
- **0.7 Dependency Addition** — human approval for any new manifest entry; see `filaops-supply-chain` skill
- **0.8 Build Artifact Audit** — no `.map`, `.env`, `.key` in publish payload
- **0.9 Network Egress Logging** — report unexpected outbound connections via `cortex_observe`

## Layer 1 — Behavioral Guidelines

### Pre-Work
- **Step 0 Rule**: Before refactoring any file >300 LOC, remove dead code in a separate commit. One commit, one purpose.
- **Phased Execution**: Max 5 files per phase. Verify and get approval before continuing.

### Code Quality
- **Senior Dev Override**: Ask "what would a perfectionist reject in code review?" Fix structural issues. Changes touching >5 files need a plan first.
- **Sub-Agent Isolation**: For tasks across >5 independent files, split into parallel sub-agents — each registers own session, claims own files.

### Context Management
- **Decay Awareness**: After ~8-10 messages or focus change, re-read relevant files before editing.
- **File Read Budget**: 2000 line cap. For files >500 LOC, chunk with offset/limit.
- **Tool Result Blindness**: Outputs >50k chars get truncated. If grep returns suspiciously few hits, narrow scope.

### Edit Safety
- **Edit Integrity**: Re-read before editing, re-read after. Max 3 edits per file without verification.
- **Explicit Reference Hunting**: You have grep, not an AST. When renaming, search: direct calls, type refs, string literals, dynamic imports, re-exports, tests/mocks.

### Supply Chain & Observation
See skills: `filaops-supply-chain` (dependency hygiene, registry trust, attribution, anomaly reporting) and `filaops-safety-philosophy` (why gates exist, threat landscape).

All commits include AI attribution:
```
feat: short description

Co-authored-by: Claude <claude@anthropic.com>
Agent-Session: [session-id]
```

## Core vs PRO Architecture

```
┌─────────────────────────────────┐
│         FilaOps Core            │  ← This repo. Open source. Standalone.
│   FastAPI + React + PostgreSQL  │
└──────────────┬──────────────────┘
               │ pip install filaops-pro
               ▼
┌─────────────────────────────────┐
│       filaops-pro package       │  ← filaops-ecosystem repo. Private.
│   register(app, license_key)    │
└─────────────────────────────────┘
```

PRO imports FROM Core, never reverse. PRO adds new tables via FK to Core tables, never alters Core schema.

### What IS Core (add here ✅)
Inventory/MRP/production/sales/purchase orders · BOM · traceability (lots, serials) · UOM (costs $/KG, inventory grams — see `backend/app/core/uom_config.py`) · basic GL · i18n · dashboards · auth/RBAC · MQTT printer integration

### What is PRO (never add here ❌)
B2B Portal · quote engine · QuickBooks/Shopify integrations · advanced accounting · catalog access control · AI agents (Cortex) · FilaFarm automation · license management · anything subscription-gated

## Repo Map

| Repo | Purpose |
|------|---------|
| `C:\repos\filaops` | **THIS REPO** — Core, open source, public |
| `C:\repos\filaops-ecosystem` | PRO monorepo, private |

## Tech Stack

Backend: FastAPI + SQLAlchemy + PostgreSQL + Alembic
Frontend: React 19 + Vite + Tailwind
Testing: pytest (backend), Vitest (frontend)

**UOM Safety**: Costs stored $/KG, inventory in grams. Single source: `backend/app/core/uom_config.py`. Never hardcode conversions elsewhere.

## Git Workflow

Feature branches off `main`: `feature/description`, `fix/description`. PRs require passing CI. Commit prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`.
