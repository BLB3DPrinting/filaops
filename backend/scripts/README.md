# backend/scripts/

Operational and seed scripts for FilaOps Core.

## seed_demo.py — deterministic rich demo dataset

Creates a full-shape demo dataset (users, printers, products, BOMs, inventory,
quotes, sales orders, production orders, purchase orders, maintenance logs) for
evaluators, screenshot generation, and first-install walk-throughs.

### Hard guarantees

- **DB-name guard.** Refuses to run unless the target database name contains
  `demo` or `test`. Bypass with `FILAOPS_DEMO_OVERRIDE=1` only if you really
  mean to seed a production-shaped DB.
- **Migration guard.** Refuses to run if the DB isn't at the latest Alembic
  head. The seed does NOT run migrations itself — run `alembic upgrade head`
  first (or use the Docker profile, which chains it automatically).
- **Deterministic.** Same seed value → byte-identical DB state. Default seed
  is 42 (`FILAOPS_DEMO_SEED`). Rows and IDs start at 1 each run because
  `wipe_all_tables` uses `TRUNCATE ... RESTART IDENTITY CASCADE`.
- **Wipes on every run.** Not a live-reset tool — it truncates everything
  except `alembic_version` and re-seeds from scratch. Prompts interactively
  unless `--yes` is passed.

### Local run

```bash
# One-time: install dev requirements (includes faker)
cd backend
pip install -r requirements-dev.txt

# Create a demo DB with 'demo' or 'test' in the name
createdb filaops_demo   # or via psql

# Migrate
DB_NAME=filaops_demo alembic upgrade head

# Seed (interactive — type 'yes' to confirm wipe)
DB_NAME=filaops_demo python -m scripts.seed_demo

# Or non-interactive
DB_NAME=filaops_demo python -m scripts.seed_demo --yes
```

Login after seed completes: `admin@acme-demo.test` / `demo1234` (printed at
the end of the run).

### Docker run — single command

The fastest path for evaluators:

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml \
    --profile demo up -d
```

The `demo` profile spins up an isolated Postgres volume
(`filaops_demo_data`), runs migrations, runs `seed_demo.py --yes`, and
starts the backend + frontend. Open `http://localhost` and log in with
the admin credentials above.

### CLI flags

| Flag             | Purpose                                                   |
|------------------|-----------------------------------------------------------|
| `--yes`          | Skip the interactive wipe confirmation (CI / Docker).     |
| `--dry-run`      | Run the pipeline but roll back at the end.                |
| `--seed N`       | Override the RNG seed (default: `$FILAOPS_DEMO_SEED` or 42). |

### Environment variables

| Variable                  | Purpose                                                     |
|---------------------------|-------------------------------------------------------------|
| `DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD` | Standard FilaOps DB config. |
| `FILAOPS_DEMO_SEED`       | Deterministic RNG seed (default 42).                        |
| `FILAOPS_DEMO_NOW_ISO`    | Override 'now' to a fixed timestamp for cross-day determinism tests. |
| `FILAOPS_DEMO_OVERRIDE=1` | Bypass the DB-name guard (USE WITH CARE).                   |

### Shape of what gets created

Current counts (v4.0.0):

- **Users:** 1 admin + 2 operators
- **Printers:** 4 (Alpha/Bravo/Charlie/Delta — mix of online/offline, overdue maintenance)
- **Maintenance logs:** 12 across 90 days
- **Price levels:** 4 tiers (A/B/C/D — customer assignment is a PRO feature)
- **Customers:** 25 (20 B2B + 5 retail)
- **Vendors:** 6
- **Item categories:** 4 (Signage, Display Hardware, Branded Keepsakes, Raw Components)
- **Work centers:** 3 (PRINT, QA, PACK)
- **Products:** 30 (25 finished goods + 5 raw filament spools)
- **BOMs:** 25 (3 multi-level)
- **Routings:** 25 (2–4 operations each)
- **Inventory rows:** 30 (2 below reorder point, 1 flagged for cycle count)
- **Quotes:** 20 (mixed statuses)
- **Sales orders:** 50 across 90 days (scaled from spec's 150 for runtime; same
  proportions — 8 linked to converted quotes)
- **Production orders:** 40 (mixed statuses — scrapped, completed, in-progress,
  accepted-short)
- **Purchase orders:** 25 (3 from the Low Stock workflow)

Runtime: ~12 s on a developer laptop, well under the 30 s target. Full
breakdown printed live by the seed as each module runs.

### Determinism check

After seeding, capture a checksum and compare across runs:

```sql
-- Run this same query after Seed Run #1 and Seed Run #2.
-- The values must be identical.
SELECT 'users'        AS tbl, COUNT(*)::text AS n, md5(string_agg(email, ',' ORDER BY id)) AS h FROM users
UNION ALL SELECT 'printers',    COUNT(*)::text, md5(string_agg(code||'|'||name, ',' ORDER BY id)) FROM printers
UNION ALL SELECT 'customers',   COUNT(*)::text, md5(string_agg(COALESCE(company_name,'')||'|'||COALESCE(email,''), ',' ORDER BY id)) FROM users WHERE account_type='customer'
UNION ALL SELECT 'price_levels', COUNT(*)::text, md5(string_agg(name||'|'||discount_percent::text, ',' ORDER BY id)) FROM price_levels;
```

### Known deferrals

See [`seed_data/SKIPPED.md`](seed_data/SKIPPED.md) for features the seed
doesn't fully exercise yet, the reason, and the trigger to re-visit (e.g.
"wire QC dashboard" or "ship_order GL journal path").

## Other scripts in this directory

Pre-existing one-off helpers (not part of the demo seed): `check_bom.py`,
`regenerate_po_materials.py`, `clean_for_e2e.py`, etc. See the individual
files for their purpose.
