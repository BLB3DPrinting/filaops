# Report: bring #1096 and #1098 into uom-rebuild

Permission mode: default (desktop session, Claude Code). Kickoff:
`docs/kickoffs/2026-11-28-uom-rebuild-takes-1098.md`.

## What changed

`main` at `e2652752` merged into `uom-rebuild` at `9fbbde56`, on the branch
`chore/uom-rebuild-takes-1098`. The merge had no conflicts. It brings two
pull requests:

- #1098: the CodeQL jobs on CircleCI (`.circleci/config.yml`, with its
  kickoff and report).
- #1096: the frontend reloads onto the new build after an update
  (`frontend/nginx.conf`, `ErrorBoundary.jsx`, `lib/staleBuild.js`,
  `main.jsx`, their tests, one `CHANGELOG.md` line, its kickoff and report).

Neither touches the backend or adds a migration, so the migration chain keeps
its one head, `108`. Neither touches a file the unit work has changed.

## Not verified

Nothing was run locally. The merge changes CI configuration and frontend
files only; CircleCI runs the full backend and frontend suites on the pull
request.

## Status checks

No checks had run when this was written: the branch had not been pushed.
