# Report: stop "Failed to fetch dynamically imported module" after updates

Permission mode: auto (Claude Code on the owner's PC, project thread).
Kickoff: `docs/kickoffs/2026-11-23-stale-build-reload.md`.

## Changes

- `frontend/nginx.conf`: `location = /index.html` sends `Cache-Control: no-cache`
  and the security headers.
- `frontend/src/lib/staleBuild.js` (new): `isStaleBuildError` and
  `reloadForNewBuild` (at most one reload per build, keyed on the entry
  script's address in sessionStorage; none when sessionStorage is blocked,
  including a throwing `sessionStorage` getter).
- `frontend/src/components/ErrorBoundary.jsx`: a stale-build error reloads once
  and shows "FilaOps was updated. Loading the new version..." meanwhile; any
  other error, or a second stale-build error on the same build, shows the
  existing error screen.
- `frontend/src/main.jsx`: `vite:preloadError` listener calls the same helper.
- Tests: `src/lib/__tests__/staleBuild.test.js`,
  `src/components/__tests__/ErrorBoundary.staleBuild.test.jsx`.

## Verification (local)

- `npx vitest run --config vitest.unit.config.js` on the two new files and the
  existing `ErrorBoundary.test.jsx`: 3 files, 18 tests passed.
- `npx eslint` on the changed and new files: no findings.
- After the CodeRabbit review (2 findings, both fixed): the guard is now one
  reload per build instead of per 30 seconds, and the `sessionStorage` read
  moved inside the `try`. Re-run: 3 files, 20 tests passed; eslint clean.
- `npx vite build`, then the built `dist/` served by `nginx:alpine` with this
  `nginx.conf`: `/`, `/index.html`, `/quotes` and `/admin/orders/5` return
  `Cache-Control: no-cache`; `/assets/index-*.js` still returns
  `max-age=31536000` and `public, immutable`.
- Not done: a browser test of the automatic reload across a real image
  rebuild. Covered by the unit tests only.

## Status checks

Recorded in the PR once CI has run.
