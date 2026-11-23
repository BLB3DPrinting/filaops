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
- `ruff check --select F,E9` on the changed and new files: clean in `app/`.
  `tests/services/test_item_service_extra.py` keeps three findings it already
  had on the base branch (two unused `datetime` imports, one unused local).
  The repo's full ruff rule set reports findings across `app/` on the base
  branch too.
- Variants are covered through `duplicate_item`, which `create_variant` calls;
  there is no separate variant test.

## Review in place of CodeRabbit

CodeRabbit was triggered on #1092 once it was ready for review and did not
run (its free review limit was reached). The diff was then read in full for
correctness, security, data integrity and missing tests. Two changes came out
of it:

- **The factor of a unit in use is now fixed.** `check_unit_update` allowed
  an install's own weight, length, area, volume or time unit to take a new
  factor while items were stocked or bought in it, or lines used it. Every
  amount stored in that unit would have quietly meant something else, and
  `purchase_factor` on those items would have gone stale. It is now refused
  with the list of uses, the same list that stops a unit being switched off.
  Sending the factor a unit already has is still accepted. Test:
  `TestUOMUpdate.test_the_factor_of_a_unit_in_use_is_fixed`.
- `tests/endpoints/test_admin_endpoints.py`: the `pytest` import this PR left
  unused is removed.

Looked at and left as they are:

- The lock is checked, then the change is written, with no row lock between.
  A stock movement that lands in that gap is not seen. Stock movements are
  written by many services that do not lock the product row, so a row lock
  here would not close the gap on its own.
- A standard unit's name and symbol can still be edited; its factor and its
  switch cannot. The plan's "a standard row cannot be edited" is read as its
  factor and kind.
- Two requests adding the same unit to one item at the same moment: the
  second fails on `uq_product_units_product_unit` with a 500 instead of a
  400.

## Status checks

On head `52f0215` (#1092):

CircleCI:

- ci/circleci: core-guardrails: success
- ci/circleci: core-pro-guard: success
- ci/circleci: core-version-parity: success
- ci/circleci: core-backend-static: success
- ci/circleci: core-diff: success
- ci/circleci: core-dependency-audit: success
- ci/circleci: core-frontend-build: success
- ci/circleci: core-frontend-unit: success
- ci/circleci: core-backend-tests: success

GitHub Actions, none of which started ("The job was not started because your
account is locked due to a billing issue"), the same as on main and #1091:

- core-guardrails, core-backend-static, core-version-parity,
  core-dependency-audit, core-diff, core-pro-guard, check-pro-code:
  failure (not started)
- Analyze (python), Analyze (javascript-typescript) (CodeQL): failure (not
  started)

CodeRabbit: did not run (draft pull request, and its base is not the default
branch).
