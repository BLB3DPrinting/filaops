# Report: two review findings on code already on main

Permission mode: default (desktop session, Claude Code). Kickoff:
`docs/kickoffs/2026-11-28-codeql-upload-cache-and-reload-check.md`.

## What changed

**1. The upload job no longer takes its program from a cache.**
`.circleci/config.yml`: the command `install_codeql` gains a parameter,
`use_cache` (default true). With it, an unpacked bundle saved by an earlier
run is used without a download or a checksum. A CircleCI cache is written by
whichever job saves its key first, on any branch of the repository, so a
branch could have saved another program under that key, and `codeql-upload`
would have run it while holding `CODEQL_UPLOAD_TOKEN`. That job now passes
`use_cache: false`: it downloads the pinned bundle and checks its SHA-256 on
every run, and neither restores nor saves the cache. The two analysis jobs,
which hold no secret, keep the cache.

Cost: the upload job downloads about 700 MB on every run.

**2. The page reloads only when the build is stale.**
`frontend/src/lib/staleBuild.js` gains `handlePreloadError(event, options)`,
and `frontend/src/main.jsx` calls it for `vite:preloadError`. Vite sends every
rejected dynamic import through that event, with the error as the payload,
so a screen whose own code throws while loading arrived there too and was
answered with a reload that hid the error. The handler now reloads only when
`isStaleBuildError(event.payload)` holds, and takes the event over only when
a reload was started.

## Tests

- `frontend/src/lib/__tests__/staleBuild.test.js`: four new tests of
  `handlePreloadError` (a missing file reloads; an error from the screen's
  own code does not; no payload does not; a build already reloaded once does
  not).
- Run locally: `npm run test:unit -- --run` on that file and
  `ErrorBoundary.staleBuild.test.jsx`: 18 tests, passed.

## Not verified

- The CircleCI change has not run: the config was parsed as YAML only.
- The reload handler was not exercised in a browser. That Vite sends module
  evaluation errors through `vite:preloadError` is taken from the review and
  from how Vite's preload helper is written; it was not reproduced.
- The full frontend suite and the lint were not run locally.

## Status checks

No checks had run when this was written: the branch had not been pushed.
