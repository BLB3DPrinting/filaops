# Report: bring #1093 into uom-rebuild

Permission mode: auto (cloud session, Claude Code). Kickoff:
`docs/kickoffs/2026-11-23-uom-rebuild-takes-1093.md`.

## What changed

- `main` (at `22b31a0`, the #1093 merge) merged into `uom-rebuild` (at
  `4386f16`, the #1092 merge). Git merged it with no conflicts.
- 16 files come in from #1093: the quote, invoice and sales order code, the
  quote form, `scripts/ci/check_audit_severity.py`, their tests, and the #1093
  kickoff and report.
- `docs/reports/2026-11-23-uom-s1-lock-and-unit-api.md`: its status checks now
  name the merged head `7fd7667`, and it says how the CodeRabbit run ended.

## Review

- No file is changed on both sides since the two branches split, so the merge
  takes each side as it is.
- #1093 adds no migration. `alembic heads` gives one head, `108`.
- The quote changes use `unit_price` (price for each item) and do not call any
  unit or conversion code that the UOM work changed. The UOM work does not
  touch quote, invoice or sales order code.
- Nothing found to fix.

## Tests

- Quote, invoice and unit tests (`tests/services/test_quote*`,
  `test_invoice*`, `tests/api/test_quote*`, `test_item_unit_service.py`,
  `test_stock_unit_lock.py`, `tests/api/test_units_api.py`) on PostgreSQL 16:
  218 passed.
- `scripts/ci/test_audit_severity.py`: 11 passed.
- `ruff check --select F,E9 backend/app`: 2 findings in
  `app/models/__init__.py` (unused `QualityPlan` imports). `main` has the same
  2, so they are not from this merge.
- The frontend quote tests were not run here (no `node_modules` in this
  session). CircleCI's `core-frontend-unit` runs them.

## Status checks

Not yet run. Filled in after the push.
