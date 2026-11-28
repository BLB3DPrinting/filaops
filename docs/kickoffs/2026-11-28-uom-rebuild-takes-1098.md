# Kickoff: bring #1096 and #1098 into uom-rebuild

The owner's instruction, 2026-11-28: "saved, 1098 is merged, bring main into
uom-rebuild".

The "Protect main" ruleset, which also covers `uom-rebuild`, now requires the
CircleCI checks and `CodeQL`. The CodeQL jobs were added to
`.circleci/config.yml` on `main` by #1098. Until `uom-rebuild` has them, no
pull request into it can meet the `CodeQL` requirement.

- Merge `main` into `uom-rebuild` on a branch, by pull request. Do not push to
  `uom-rebuild` directly.
- Keep the migration chain to one head.
