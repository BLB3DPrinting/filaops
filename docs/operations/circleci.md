# CircleCI

Date: 2026-06-04

This repository uses CircleCI as the next primary CI entry point for Core
source validation. GitHub Actions workflows remain `workflow_dispatch` only so
they can be run manually without reintroducing automatic GitHub-hosted Actions
usage.

The starter CircleCI workflow intentionally has no deployment jobs, no
production secrets, and no production database access. Backend tests use a
disposable Postgres service container with explicit test environment values.

## Current Cloud Jobs

- `core-diff`: whitespace/conflict-marker diff check.
- `core-pro-guard`: public Core boundary check; rejects PRO-only paths such as
  `backend/app/pro/` and `license-server/`.
- `core-backend-static`: Python compile check for `backend/app` and
  `backend/tests`.
- `core-backend-tests`: backend pytest against disposable Postgres with JUnit
  stored under `test-results/core-backend`.
- `core-frontend-build`: frontend `npm ci` and `npm run build`.
- `core-frontend-unit`: frontend Vitest unit tests with JUnit stored under
  `test-results/core-frontend-unit`.

## Smarter Testing

Start with the full-suite CircleCI baseline. Do not enable dynamic splitting or
Test Impact Analysis for Core until this workflow has a green history on PRs and
`main`.

Recommended next steps:

1. Require the CircleCI contexts only after at least one clean PR run.
2. Keep the existing external CI statuses available as rollback until CircleCI
   is the trusted gate.
3. Pilot dynamic splitting on `core-backend-tests` only after backend JUnit
   timings are stable.
4. Treat Test Impact Analysis as advisory before it becomes a required Core
   gate.

## Rollback

If CircleCI setup fails, continue using the external runner documented in
`external-ci-statuses.md`. Reverting this setup should be a config-only PR that
removes `.circleci/config.yml` while leaving manual GitHub Actions workflows
unchanged.
