# Kickoff: bring main into the UOM rebuild branch

Asked for on 2026-11-23 in the "Continue the UOM rebuild" project thread:
pick up the unit-of-measure work and continue with the plan.

## Required first step

- `main` has migration `106_quote_descriptions_discounts` (#1089), chained
  from `105`. `uom-rebuild` has its own `106` (unit table) and `107` (settle
  units), also chained from `105`.
- Merge `main` into the rebuild and renumber the unit migrations to `107` and
  `108`, the first chained from main's `106`.
- Do not break #1089 (quote descriptions, notes, discounts) or #1090 (portal
  quote-to-order totals).
- Work on a branch, open a pull request into `uom-rebuild`, do not merge.

## Then

Continue with pull request 3 of the stage 1 build plan (the stock unit lock,
the unit rules and the unit endpoints), on top of this.
