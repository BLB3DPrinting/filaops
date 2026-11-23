# Kickoff: stop "Failed to fetch dynamically imported module" after updates

Date: 2026-11-23
Requested by: Brandan (project thread)
Branch: `claude/project-thread-98mhit` (draft PR, not merged)

## Request

After the local test copy was rebuilt on new code, opening the app showed
"TypeError: Failed to fetch dynamically imported module:
.../assets/CommandCenter-CAG0geRE.js". The owner: "that happens all of the time
and users will run into that. anyway to have it automate in the update?"

## Cause

`frontend/nginx.conf` serves `index.html` with no `Cache-Control` header, so
browsers may reuse a stale copy. That copy names the previous build's hashed
chunks, which the new image no longer has (404). A tab left open across an
update has the same problem even with a fresh `index.html`.

## Plan

- nginx: `location = /index.html` with `Cache-Control: no-cache` (plus the
  repeated security headers). `/` and the SPA fallback both internally
  redirect to `/index.html`, so every route is covered. `/assets/` keeps its
  one-year immutable cache.
- Frontend: `lib/staleBuild.js` recognises a failed dynamic import and reloads
  the page at most once per build (the entry script's address is kept in
  sessionStorage), so it cannot loop. Hooked into `ErrorBoundary` and Vite's `vite:preloadError` event.
- Tests for the helper and the boundary; CHANGELOG entry under Unreleased.
