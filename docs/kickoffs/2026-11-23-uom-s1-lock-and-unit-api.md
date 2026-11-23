# Kickoff: UOM stage 1, PR 3. The lock, the unit rules, the endpoints

Asked for on 2026-11-23 in the "Continue the UOM rebuild" project thread:
pick up the unit-of-measure work and continue with the plan. This is pull
request 3 of the stage 1 build plan (`UOM_STAGE1_BUILD_PLAN.md`), built on the
branch that brings `main` into `uom-rebuild` (#1091).

## Scope, from the plan

- **R9, the stock unit lock.** An item's stock unit cannot change once it has
  stock on hand or allocated, inventory transactions, or units of its own. The
  old rescaling of stock on a unit change goes. Every writer of `Product.unit`
  goes through one check: item create and update, product create and update,
  the item CSV import, the product CSV import.
- **Departure 4.** An item's unit and purchase unit must be in the unit table.
  An item that already holds an unknown code can be saved with it unchanged.
- **Point 8.** A new item's purchase unit defaults to KG for a material stocked
  in G, and to its stock unit otherwise.
- **Point 9.** One helper writes `purchase_factor`, from the two units and the
  item's own units. Requests and imports no longer set it.
- **R4.** An item can have units of its own (`product_units`), read and written
  through `GET/PUT/DELETE /items/{id}/units[/{code}]`.
- **Point 17.** Duplicates and variants copy the item's own units.
- **Point 18.** A blank Unit cell in a CSV import means "not given".
- **Plan 4.6, the admin unit table.** A standard unit keeps its factor and
  cannot be switched off. A new unit is a pack with no factor, or a weight,
  length, area, volume or time unit with a factor of at most 15 places. A new
  counting unit, a new kind, and a code already in the table in any spelling
  are refused. A unit in use cannot be switched off.
- `GET /units` for any staff account.

## Out of scope

Moving the remaining backend converters onto `unit_conversion` (PR 4) and the
screens (PRs 5 and 6).

## Delivery

A branch off #1091's head, a draft pull request into `uom-rebuild`. Do not
merge.
