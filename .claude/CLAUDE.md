# FilaOps Core — Open Source ERP (v3.2.x)

## 🧠 Aeonyx — READ INSTITUTIONAL MEMORY FIRST

Before starting work, check Aeonyx shared memory for context from prior sessions:
```
mem_recall("filaops portal")     # Portal GTM status, deployed features, known bugs
mem_recall("sacred rule")        # Entanglement findings, Core/PRO boundary violations
mem_recall("Track 3 sync")      # Order sync status, remaining bugs
mem_recall("pattern")           # Recurring patterns to watch for (duplicate filters, etc.)
```

If Aeonyx MCP is not connected, check `.mcp.json` in the repo root for config.
Before editing high-collision files, call `rex_claim_files` per memory #26.

## 🔴 SACRED RULE — READ FIRST, NEVER VIOLATE

**"NO Core Changes from PRO. PRO Must Not Break Core."**

This rule is absolute. It means:
- NEVER modify files in Core (`C:\repos\filaops`) from this repo
- NEVER add Core dependencies on any ecosystem package
- Core must run perfectly with zero PRO code installed
- If `filaops-pro` is uninstalled, Core runs identically
- PRO hooks into Core via `register(app)` — Core never knows PRO exists

The ONLY exception is if Brandan explicitly authorizes a specific change.

## Architecture: How Core and PRO Relate

```
┌─────────────────────────────────┐
│         FilaOps Core            │  ← This repo. Open source. Runs standalone.
│   FastAPI + React + PostgreSQL  │
└──────────────┬──────────────────┘
               │ pip install filaops-pro
               │ (optional, customer's choice)
               ▼
┌─────────────────────────────────┐
│       filaops-pro package       │  ← Separate repo (filaops-ecosystem)
│   register(app, license_key)    │
│   Adds PRO routes to Core app   │
└─────────────────────────────────┘
```

PRO is a pip-installable package that calls `register(app)` to inject routes into Core's FastAPI app at startup. If PRO is uninstalled, Core runs identically. This is the same pattern as Django's `INSTALLED_APPS` or Flask's `register_blueprint()`.

### Extension Hook Guidance

When adding new tables, APIs, or systems to Core:
- **Design for extensibility**: PRO should be able to add related tables (FK references) without modifying Core tables
- **Example**: Core's `tax_rates` table is self-contained. PRO can add a `tax_jurisdictions` table that references `tax_rates.id` — without altering Core's schema
- **Never add columns "for PRO later"** — that violates the sacred rule

## What IS Core (add here ✅)

- Inventory management, MRP, production orders, sales/purchase orders
- BOM management and cost calculations
- Traceability (lots, serials)
- UOM system (costs stored $/KG, inventory tracked in grams — see `backend/app/core/uom_config.py`)
- Basic GL accounting (journal entries, chart of accounts, periods)
- Internationalization: locale, currency formatting, multi-tax rates
- Basic reporting and dashboards
- User authentication and role-based access
- MQTT printer integration
- Bug fixes and improvements to any of the above

## What is PRO (never add here ❌)

- B2B Portal (customer-facing catalog, ordering, RFQ)
- Quote engine / public quoter with 3D preview
- Integrations: QuickBooks, Shopify, marketplace connectors
- Advanced accounting: jurisdiction-based tax, compound tax, cross-currency GL, Schedule C
- Catalog access control, price levels, customer tiers
- AI agents (Cortex: Otto, Sam, Ada)
- FilaFarm printer automation
- License management
- Any feature requiring a subscription/payment

## Repository Map

| Repo | Purpose | Status |
|------|---------|--------|
| `C:\repos\filaops` | **THIS REPO** — Open source Core | ✅ Active, GitHub public |
| `C:\repos\filaops-ecosystem` | PRO monorepo (filaops-pro, license-server, portal, quoter) | ✅ Active, private |
| `C:\repos\FilaOpsPRO-BLB3D_Production` | Legacy PRO fork | ⚠️ Being consolidated into ecosystem |
| `C:\BLB3D_Production` | Old production repo | 📦 Archived after extraction |

**All new PRO work goes into `filaops-ecosystem`. No exceptions.**

## Tech Stack

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL + Alembic
- **Frontend**: React 19 + Vite + Tailwind CSS
- **Testing**: pytest (backend), Vitest (frontend)
- See `.claude/skills/` for detailed patterns

## ⚠️ Database Safety Rule

**BEFORE any database operation (migrations, queries, schema changes):**

1. Read `backend/.env` to confirm `DATABASE_URL` or `DB_NAME`
2. Verify which DB the MCP postgres tool is connected to: `SELECT current_database();`
3. State explicitly: "Working against database `X`"
4. If there's ANY mismatch, **STOP and clarify with Brandan**

| Database | Purpose | Used By |
|----------|---------|---------|
| `filaops` | Dev/open-source testing | This repo |
| `filaops_prod` | Production + PRO dev | Legacy — being consolidated |
| `filaops_test` | Automated tests | pytest |
| `filaops_cortex` | Cortex agent memory | filaops-ecosystem/cortex |

**This repo uses `filaops`. Never run migrations against `filaops_prod` from here.**

## UOM Safety

Costs stored as $/KG, inventory tracked in grams. Single source of truth: `backend/app/core/uom_config.py`

**Never hardcode UOM conversion factors elsewhere.**

## Quick Start

```powershell
# Backend
cd backend && .\venv\Scripts\Activate && uvicorn app.main:app --reload

# Frontend
cd frontend && npm run dev

# Tests
cd backend && python -m pytest tests/ -v --tb=short -x
cd frontend && npx vitest run
```

## Testing Requirements

- All backend changes must have corresponding tests
- Run `python -m pytest tests/ -x -q` before committing
- Tests run against `filaops_test` database — NEVER against `filaops_prod`
- See `.claude/skills/testing.md` for coverage analysis workflow

### Test Failure Policy

**ALL tests must pass before committing. No exceptions.**

If a test was failing before you started:
1. Investigate it — read the test, trace the failure, understand why
2. Fix it if the fix is straightforward and safe
3. If it requires human judgment or a larger change, add a `# TODO(pre-existing): [description of failure and likely cause]` comment to the test AND note it in your commit message

"Pre-existing failure" is never an excuse to silently skip it. Broken is broken — at minimum, flag it so it doesn't get forgotten.

## Git Workflow

- Feature branches off `main`: `feature/description`, `fix/description`
- PRs require passing CI before merge
- Commit messages: `feat:`, `fix:`, `refactor:`, `test:`, `docs:` prefixes
