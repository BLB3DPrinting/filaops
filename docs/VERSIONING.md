# FilaOps Versioning

How version numbers are managed, where they live, and what to update when cutting a release.

## Sources of Truth

There are **three** sources of truth for the current version. All three must agree.
There is also a last-resort hardcoded fallback, which should never be reached in practice.

| File | Used By | Format |
|------|---------|--------|
| `backend/VERSION` | Backend `VersionManager` (fallback) | Plain text, e.g. `3.0.1` |
| `package.json` (root) | Root project metadata | `"version": "3.0.1"` |
| `frontend/package.json` | Frontend (imported at Vite build time) | `"version": "3.0.1"` |

## How Version Is Resolved

### Backend (`backend/app/core/version.py`)

The `VersionManager.get_current_version()` method resolves the version in this order:

1. **Git tag** (`git describe --tags --abbrev=0`) - works in dev and non-Docker deployments where `.git/` is present.
2. **`FILAOPS_VERSION` env var** - set by the Dockerfile `ARG` / `ENV`, or by docker-compose. This is the primary mechanism in Docker deployments.
3. **`backend/VERSION` file** - read at module import time. This is the fallback when git and env vars are unavailable.
4. **Hardcoded `"3.0.1"`** - last-resort constant. Should never be reached if the VERSION file exists.

### Frontend (`frontend/src/utils/version.js`)

- `getCurrentVersionSync()` returns the version from `package.json`, imported at build time via Vite's JSON import support. No network call required.
- `getCurrentVersion()` (async) tries the backend API (`/api/v1/system/version`) first, then falls back to the `package.json` value.

### Docker (`backend/Dockerfile`)

The Dockerfile declares:
```dockerfile
ARG FILAOPS_VERSION=3.0.1
ENV FILAOPS_VERSION=${FILAOPS_VERSION}
```

This default should be updated on release, but the `VERSION` file acts as a safety net if it's missed.

## Bumping the Version

When releasing a new version:

1. Update `backend/VERSION` to the new version
2. Update `package.json` (root) `"version"` field
3. Update `frontend/package.json` `"version"` field
4. Update `backend/Dockerfile` `ARG FILAOPS_VERSION=` default
5. Commit, tag (`git tag vX.Y.Z`), push with tags (`git push --tags`)

Steps 1-4 are the files. Step 5 creates the git tag that Docker-less deployments and the GitHub release checker both rely on.

## Common Pitfalls

| Problem | Cause | Fix |
|---------|-------|-----|
| UI shows wrong version | `package.json` not updated, or browser cache | Update `frontend/package.json`, hard-refresh |
| Backend API returns wrong version | No git tags in Docker, `FILAOPS_VERSION` env not set, `VERSION` file stale | Update `backend/VERSION` and Dockerfile ARG |
| "Update available" when already current | Frontend version comparison used a stale fallback | Fixed - now reads `package.json` at build time |
| Update checker never detects updates | `getCurrentVersion()` was called without `await` | Fixed in `useVersionCheck.js` |
