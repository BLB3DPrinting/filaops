---
name: regenerate-reference-docs
description: Use when reference docs (API-REFERENCE, SCHEMA-REFERENCE, MIGRATIONS-LOG) are stale, after adding endpoints/models/migrations, before releases, or when issue asks for doc regeneration
---

# Regenerate Reference Docs

## Overview

Three reference docs in `docs/` are generated from the codebase for AI and developer consumption. They go stale after every release. This skill scripts their regeneration.

| Doc | Source | Script |
|-----|--------|--------|
| `API-REFERENCE.md` | `backend/app/api/v1/endpoints/**/*.py` | `generate_api_reference.py` |
| `SCHEMA-REFERENCE.md` | `backend/app/models/*.py` | `generate_schema_reference.py` |
| `MIGRATIONS-LOG.md` | `backend/migrations/versions/*.py` | `generate_migrations_log.py` |

## When to Run

**At release time** — after all PRs for a version are merged to `main`, before tagging.

```
merge PRs → checkout main → run scripts → commit docs → tag release
```

The docs describe the released state of the codebase, not in-flight changes. The version stamp in each footer (`v3.5.0`) makes staleness obvious — if `VERSION` says `3.6.0` but the docs say `v3.5.0`, regenerate.

**Not per-PR.** Running on every PR adds review noise for docs most contributors don't read. The scripts are gitignored (local-only), so CI can't run them anyway.

**Other triggers:**
- Issue or PR explicitly asks for doc regeneration
- When doc metrics (endpoint/model/migration counts) visibly don't match codebase

## Quick Reference: Running the Scripts

```bash
cd backend
python scripts/generate_api_reference.py      # → docs/API-REFERENCE.md
python scripts/generate_schema_reference.py    # → docs/SCHEMA-REFERENCE.md
python scripts/generate_migrations_log.py      # → docs/MIGRATIONS-LOG.md
```

Each script is self-contained — reads the codebase via AST/regex, writes the doc. No dependencies beyond stdlib.

## Doc Formats

### API-REFERENCE.md

```markdown
# FilaOps API Reference
> Generated for AI consumption and developer reference.
> This document covers **Core (Open Source)** API endpoints only.

## Overview
| Metric | Count |
| Total Endpoints | ~N |
| Router Files | N |
...

## 1. Section Name (`/prefix`)
**Tier**: Core
**File**: `endpoints/filename.py`
**Endpoints**: N

| Method | Path | Description | Auth |
| GET | `/prefix` | Description | STAFF |
...
```

Key conventions:
- Sections numbered sequentially, grouped by router file
- Auth levels: PUBLIC, CUSTOMER, STAFF, ADMIN
- Admin endpoints nested under `## N. Admin` with sub-sections per module
- Ends with pagination/filtering/versioning reference sections

### SCHEMA-REFERENCE.md

```markdown
# FilaOps Database Schema Reference
**Generated:** YYYY-MM-DD
**Source:** FilaOps Core vX.Y.Z
**Total Models:** N (Core only)

## Table of Contents
1. [Category](#category) (N models)
...

## Category Name
### ModelName
**Table:** `table_name` | **Tier:** Core | **File:** `filename.py:line`

| Column | Type | Constraints | Description |
| id | Integer | PK | Primary key |
...

**Relationships:**
- `field` → TargetModel (cardinality)
```

Key conventions:
- Models grouped by category (Core ERP, Manufacturing, User & Auth, etc.)
- Every column documented with type, constraints, description
- Relationships section after columns
- Summary statistics table at end

### MIGRATIONS-LOG.md

```markdown
# FilaOps Migrations Log
> Chronological record of all database migrations.

## Overview
| Metric | Count |
| Total Migrations | N |
...

## Migration Categories
### By Feature Area
| Area | Count | Migrations |
...

## Chronological Migration List
### Phase N: Description
#### `filename.py`
**Tier**: Core
**Date**: YYYY-MM-DD
**Purpose**: Description

**Creates Tables** / **Adds Column** / **Alters Column**:
- details...
```

Key conventions:
- Grouped into Phases (Initial Schema, Core Features, etc.)
- Each migration: tier, date, purpose, tables/columns affected
- Dependency chain diagram at end
- Running Migrations section with common alembic commands

## Extraction Patterns

### Endpoints (AST-based)

```python
# Parse each .py file in endpoints/ and admin/
# Find: @router.get/post/put/patch/delete("path")
# Extract: method, path, function docstring or name
# Auth: check for Depends(get_current_admin_user) vs get_current_user vs get_current_staff_user
# Prefix: read from __init__.py router.include_router(..., prefix="/x")
```

### Models (AST-based)

```python
# Parse each .py file in models/
# Find: class X(Base): with __tablename__
# Extract: Column() definitions — name, type, constraints
# Extract: relationship() definitions — target, back_populates
# Line number: from AST node.lineno
```

### Migrations (regex-based)

```python
# Parse each .py file in migrations/versions/
# Extract: revision, down_revision, create_date from module-level assignments
# Parse upgrade() body for: op.create_table, op.add_column, op.alter_column, op.create_index
# Extract table names and column definitions from these calls
```

## Common Mistakes

- **Forgetting admin sub-modules**: `endpoints/admin/*.py` has 15+ files — include them
- **Model count**: Count model *classes*, not files (some files have 2-5 classes)
- **Migration filenames**: Some use hash prefixes (e.g., `905ef924f499_merge...`), not all are numbered
- **Stale metrics**: Header counts MUST match the actual generated content — compute from output, don't hardcode
- **Auth level inference**: If endpoint has `get_current_admin_user` → ADMIN; `get_current_staff_user` → STAFF; `get_current_user` → CUSTOMER; no auth dep → PUBLIC
