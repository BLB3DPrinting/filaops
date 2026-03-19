# FilaOps Versioning

How version numbers are managed, where they live, and what to update when cutting a release.

## Sources of Truth

There are **three** sources of truth for the current version. All three must agree.

| File | Used By | Format |
|------|---------|--------|
| `backend/VERSION` | Backend `VersionManager` (primary in Docker) | Plain text, e.g. `3.4.0` |
| `package.json` (root) | Root project metadata | `"version": "3.4.0"` |
| `frontend/package.json` | Frontend (imported at Vite build time) | `"version": "3.4.0"` |

## How Version Is Resolved

### Backend (`backend/app/core/version.py`)

The `VersionManager.get_current_version()` method resolves the version in this order:

1. **Git tag** (`git describe --tags --abbrev=0`) - works in dev and non-Docker deployments where `.git/` is present.
2. **`FILAOPS_VERSION` env var** - only used if explicitly set (e.g. via `FILAOPS_VERSION=` in your `.env` or docker-compose override). The Dockerfile no longer bakes in a default.
3. **`backend/VERSION` file** - read at module import time. This is the primary mechanism in Docker deployments.
4. **Hardcoded `"0.0.0"`** - last-resort sentinel. Should never be reached if the VERSION file exists; if you see this version, the VERSION file is missing.

### Frontend (`frontend/src/utils/version.js`)

- `getCurrentVersionSync()` returns the version from `package.json`, imported at build time via Vite's JSON import support. No network call required.
- `getCurrentVersion()` (async) tries the backend API (`/api/v1/system/version`) first, then falls back to the `package.json` value.

### Docker (`backend/Dockerfile`)

The Dockerfile does **not** set `FILAOPS_VERSION`. The `VERSION` file is copied into the container via `COPY . .` and is read at import time by `VersionManager`. If you need to override the version (e.g. for a custom build), set `FILAOPS_VERSION` in your `.env` or docker-compose override — but this should rarely be needed.

## Bumping the Version

When releasing a new version:

1. Update `backend/VERSION` to the new version
2. Update `package.json` (root) `"version"` field
3. Update `frontend/package.json` `"version"` field
4. Commit, tag (`git tag vX.Y.Z`), push with tags (`git push --tags`)

Steps 1-3 are the files. Step 4 creates the git tag that Docker-less deployments and the GitHub release checker both rely on.

## Common Pitfalls

| Problem | Cause | Fix |
|---------|-------|-----|
| UI shows wrong version | `package.json` not updated, or browser cache | Update `frontend/package.json`, hard-refresh |
| Backend API returns wrong version | No git tags in Docker, `VERSION` file stale, or stale `FILAOPS_VERSION` env var override | Update `backend/VERSION`; remove any `FILAOPS_VERSION` override from `.env` |
| "Update available" when already current | Frontend version comparison used a stale fallback | Fixed - now reads `package.json` at build time |
| Update checker never detects updates | `getCurrentVersion()` was called without `await` | Fixed in `useVersionCheck.js` |
