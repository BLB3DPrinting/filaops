# Report: main brought into the UOM rebuild, unit migrations renumbered

Permission mode: auto (cloud session, Claude Code). Kickoff:
`docs/kickoffs/2026-11-23-uom-rebuild-meets-main.md`.

## What changed

- `origin/main` at `1a90f8a` merged into `uom-rebuild` at `b15e4a1`. No
  conflicts. The one file both sides changed, `backend/tests/conftest.py`,
  merged on its own: main's block adds the quote discount columns, the
  rebuild's blocks widen the unit factor column and fill the standard units.
- `106_unit_table_and_item_units.py` is now `107_unit_table_and_item_units.py`,
  revision `107`, revising main's `106` (quote descriptions and discounts).
- `107_settle_item_and_line_units.py` is now `108_settle_item_and_line_units.py`,
  revision `108`, revising `107`.
- Their report lines (`107: ...`, `108: ...`), docstrings, the tests that load
  them by path and the comments that name them follow the new numbers.
- `scripts/uom_preflight.py`: it stopped at any pending migration without a
  unit report ahead of the unit migrations, so a 4.4.0 database (at 105) would
  have been told to upgrade to 106 first. Main's 106 only adds nullable
  columns to quotes, sales orders, invoices and their lines, which the unit
  migrations never read (they read units, items, BOM, routing, purchase order,
  production order material and vendor item rows). It goes on a short list,
  `_TOUCHES_NO_UNIT_ROWS`, of migrations that may still be pending ahead of the
  report. Any other pending migration still stops it, as before.

Nothing in #1089 (quote descriptions, notes, discounts) or #1090 (portal
quote-to-order totals) is changed. Main's `106_quote_descriptions_discounts.py`
is untouched.

## Checked

- `alembic upgrade head` on an empty PostgreSQL 16 database: one head, `108`;
  the chain runs 105, 106 (quotes), 107 (unit table), 108 (settle units).
- `alembic downgrade 105`, then `upgrade head` again: 106, 107 and 108 ran in
  order.
- The unit, migration, preflight, line check, BOM cost, schema coverage and
  routing test files: 746 passed, on a test database built the way CI builds
  it. New preflight tests: a database at 105 and one at 106 get the same unit
  report; one at 104 is still told to upgrade to 105 first.
- Full backend suite: see the pull request; CI is the authority.

## Status checks

Filled in from the pull request once its checks have run.
