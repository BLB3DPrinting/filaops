# Report: UOM stage 1, PR 3. The lock, the unit rules, the endpoints

Permission mode: auto (cloud session, Claude Code). Kickoff:
`docs/kickoffs/2026-11-23-uom-s1-lock-and-unit-api.md`.

## What changed

- `app/services/item_unit_service.py` (new): the one place an item's units are
  checked and written.
  - `stock_unit_lock` and `check_stock_unit_change`: R9. Locked by stock on
    hand or allocated, an inventory transaction, or a unit of the item's own.
    A spelling-only change is not a change.
  - `require_item_unit`: departure 4. An unknown or switched-off code is
    refused unless it is the value the item already holds.
  - `default_purchase_unit`: point 8.
  - `sync_purchase_factor`: point 9, the only writer of `purchase_factor`.
  - `set_item_unit`, `remove_item_unit`, `apply_item_units`,
    `copy_item_units`: R4 and point 17.
- `app/services/unit_table_rules.py` (new): plan 4.6, the admin unit table.
- `app/api/v1/endpoints/units.py` (new): `GET /units`, and
  `GET/PUT/DELETE /items/{id}/units[/{code}]`.
- Writers moved onto the service: `item_service` create and update (the old
  rescaling of stock on a unit change is gone), `product_service` create and
  update, `item_import_service`, `data_import_service` (a blank Unit cell is
  "not given", point 18), `item_duplicate_service` (variants go through it),
  and a vendor item's default purchase unit.
- `admin/uom.py`: create and update follow plan 4.6; get and update find a
  switched-off unit; convert uses the exact factors.
- `ItemBase.purchase_uom` has no default ("EA" before); the item response now
  carries the stored `purchase_uom`.
- `docs/API-REFERENCE.md` and `CHANGELOG.md` updated.

## Tests

- New: `tests/services/test_item_unit_service.py` (47),
  `tests/api/test_units_api.py` (17), `tests/services/test_stock_unit_lock.py`
  (11: product update, both CSV imports, duplicates).
- Rewritten for the new rules: the admin unit tests in
  `tests/endpoints/test_admin_endpoints.py` (they created counting units and
  changed arbitrary factors) and `TestUpdateItemUnitChange` in
  `tests/services/test_item_service_extra.py` (it tested the rescaling).
- `tests/schemas/test_schema_coverage.py`: `purchase_uom` defaults to None.
- Full backend suite, locally on PostgreSQL 16 with a test database built the
  way CI builds it: 8424 passed, 7 skipped.
- `ruff check --select F,E9` on the changed and new files: clean. The repo's
  full ruff rule set reports findings across `app/` on the base branch too.
- Variants are covered through `duplicate_item`, which `create_variant` calls;
  there is no separate variant test.

## Status checks

Filled in from the pull request once its checks have run.
