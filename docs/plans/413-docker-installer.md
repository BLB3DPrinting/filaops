# Plan: One-Click Docker Installer (#413)

## Context

FilaOps targets 3D printer operators and small businesses who shouldn't need git+Python+Node to run an ERP. Issue #413 defines three deliverables to enable a "download and run" experience. The user wants this designed with PRO/Enterprise OCI distribution in mind so we don't paint ourselves into a corner.

**Current state**: Docker images are built locally via `docker-compose.yml` using `build: context`. No images are published to any registry. PRO is distributed at runtime via wheel download from the license server in `docker-entrypoint.sh`.

---

## Architecture Decision: Parameterized Image References

The key design choice that keeps all tiers working with one compose file:

```yaml
backend:
  image: ${FILAOPS_BACKEND_IMAGE:-ghcr.io/blb3d/filaops-backend:latest}
frontend:
  image: ${FILAOPS_FRONTEND_IMAGE:-ghcr.io/blb3d/filaops-frontend:latest}
```

| Tier | How it works | What changes |
|------|-------------|--------------|
| **Community** | Default images (public ghcr.io) | Nothing — just `docker compose up` |
| **PRO (today)** | Default images + `FILAOPS_LICENSE_KEY` | Entrypoint downloads wheel at startup (current behavior) |
| **PRO (future OCI)** | `FILAOPS_BACKEND_IMAGE=ghcr.io/blb3d/filaops-backend-pro:3.4.0` | Pre-built image, no runtime download, requires `docker login` |
| **Enterprise** | Same pattern with enterprise image | Same compose file, different image ref |

The PRO/Enterprise images would be built in `filaops-ecosystem` (private repo) using `FROM ghcr.io/blb3d/filaops-backend:3.4.0` as the base layer + the wheel pre-installed. That work is out of scope for this issue but the design accommodates it cleanly.

---

## Implementation Steps

### Step 0: Prerequisites (housekeeping)

**0a. Create `backend/.dockerignore`**
- Currently missing — build context includes venv, tests, .env, __pycache__
- Model after frontend's `.dockerignore`
- Excludes: `.git/`, `.env*`, `__pycache__/`, `venv/`, `.venv/`, `tests/`, `*.log`, `logs/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`

**0b. Add OCI labels to both Dockerfiles**
- `backend/Dockerfile` — add after line 7:
  ```dockerfile
  LABEL org.opencontainers.image.source="https://github.com/Blb3D/filaops"
  LABEL org.opencontainers.image.description="FilaOps ERP Backend"
  LABEL org.opencontainers.image.licenses="BSL-1.1"
  ```
- `frontend/Dockerfile` — add in production stage after `FROM nginx:alpine`:
  ```dockerfile
  LABEL org.opencontainers.image.source="https://github.com/Blb3D/filaops"
  LABEL org.opencontainers.image.description="FilaOps ERP Frontend"
  LABEL org.opencontainers.image.licenses="BSL-1.1"
  ```

**0c. Fix stale version default in backend Dockerfile**
- `backend/Dockerfile:4`: `ARG FILAOPS_VERSION=3.2.0` -> `ARG FILAOPS_VERSION=3.4.0`
- CI workflow will override this from the git tag, but standalone builds shouldn't get stale `3.2.0`

---

### Step 1: Production Compose — `docker-compose.prod.yml`

**New file**: `docker-compose.prod.yml`

Key differences from dev compose (`docker-compose.yml`):

| Aspect | Dev | Prod |
|--------|-----|------|
| Images | `build: ./backend` | `image: ${FILAOPS_BACKEND_IMAGE:-ghcr.io/blb3d/filaops-backend:latest}` |
| DB port | Exposed (5432) | Internal only (security) |
| Backend port | Exposed (8000) | Internal only (nginx proxies) |
| Frontend port | 80:8080 | `${FILAOPS_PORT:-8080}:8080` (configurable) |
| Uploads | Host mount `./uploads` | Named volume `filaops_uploads` |
| Restart | none | `unless-stopped` |
| Frontend healthcheck | none | `wget --spider http://localhost:8080/` |
| Env defaults | Dev-safe (`changeme`) | No defaults for secrets (must set in `.env`) |

Services: `db`, `migrate`, `backend`, `frontend` — same structure as dev compose.

The `migrate` service reuses the backend image with `command: ["bash", "scripts/docker-migrate.sh"]` override — entrypoint still runs first (handles PRO wheel download if license key set), then the command runs migrations.

**Also create**: `.env.production` — minimal production env template with:
- `DB_PASSWORD=` (required, no default)
- `SECRET_KEY=` (required, no default)
- `ENVIRONMENT=production`
- `FILAOPS_PORT=8080`
- `# FILAOPS_LICENSE_KEY=` (commented, with purchase URL)
- `# FILAOPS_BACKEND_IMAGE=` (commented, "for PRO OCI — see docs")
- `# FILAOPS_FRONTEND_IMAGE=` (commented)

---

### Step 2: CI Workflow — `.github/workflows/docker-publish.yml`

**New file**: `.github/workflows/docker-publish.yml`

**Triggers**:
- `push: tags: ['v*']` — builds on release tags
- `workflow_dispatch` — manual trigger for testing

**Permissions**: `contents: read`, `packages: write`

**Jobs** (parallel):

**`build-backend`**:
1. `actions/checkout@v6`
2. `docker/metadata-action@v5` — generates tags: `{{version}}`, `{{major}}.{{minor}}`, `latest`
3. `docker/setup-qemu-action@v3` — cross-platform emulation
4. `docker/setup-buildx-action@v3`
5. `docker/login-action@v3` — `registry: ghcr.io`, `username: ${{ github.actor }}`, `password: ${{ secrets.GITHUB_TOKEN }}`
6. `docker/build-push-action@v6`:
   - `context: ./backend`
   - `platforms: linux/amd64,linux/arm64`
   - `push: true`
   - `build-args: FILAOPS_VERSION=${{ steps.meta.outputs.version }}, FILAOPS_BUILD_DATE=${{ github.event.head_commit.timestamp }}`
   - `tags: ${{ steps.meta.outputs.tags }}`
   - `labels: ${{ steps.meta.outputs.labels }}`
   - `cache-from: type=gha`, `cache-to: type=gha,mode=max`

**`build-frontend`**: Same pattern, `context: ./frontend`, no build-args needed (VITE_API_URL defaults to empty = relative URLs via nginx proxy).

**Image names**:
- `ghcr.io/blb3d/filaops-backend:3.4.0` / `:3.4` / `:latest`
- `ghcr.io/blb3d/filaops-frontend:3.4.0` / `:3.4` / `:latest`

**PRO extension point**: The `filaops-ecosystem` repo would have its own `docker-publish-pro.yml` that triggers on its own tags, does `FROM ghcr.io/blb3d/filaops-backend:3.4.0` + `COPY filaops_pro*.whl /tmp/ && pip install /tmp/*.whl`, and pushes to a private ghcr.io package. This is entirely in the ecosystem repo — Core never changes.

---

### Step 3: Installer Script — `scripts/install-filaops.ps1`

**New file**: `scripts/install-filaops.ps1`

PowerShell 5.1+ compatible (ships with Windows 10/11).

**Flow**:
1. Print banner with version
2. **Check Docker Desktop**: `docker version` — if fails, print download URL + exit
3. **Check Docker Compose v2**: `docker compose version` — if fails, instructions + exit
4. **Check Docker running**: `docker info` — if fails, prompt to start Docker Desktop
5. **Create install dir**: `$HOME\FilaOps` (or `$env:FILAOPS_INSTALL_DIR`)
6. **Check for existing install**: if `.env` exists, back it up as `.env.backup-<timestamp>`
7. **Download compose file**: from GitHub release (`https://github.com/Blb3D/filaops/releases/latest/download/docker-compose.prod.yml`)
8. **Generate `.env`**:
   - `SECRET_KEY` = 64 random hex chars via `[System.Security.Cryptography.RandomNumberGenerator]`
   - `DB_PASSWORD` = 32 random hex chars
   - `DB_NAME=filaops`, `DB_USER=postgres`, `ENVIRONMENT=production`
   - Prompt: "Enter FilaOps PRO license key (or press Enter to skip):"
   - If key provided -> add `FILAOPS_LICENSE_KEY=<key>`
9. **Pull images**: `docker compose -f docker-compose.prod.yml pull`
10. **Start**: `docker compose -f docker-compose.prod.yml up -d`
11. **Wait for health**: poll `docker inspect` for healthy status, timeout 120s
12. **Open browser**: `Start-Process "http://localhost:8080"`
13. **Print success**: data location, stop/start commands, backup instructions

**Upgrade-safe**: The script detects existing installs, preserves `.env`, and only re-downloads the compose file. Running it again = upgrade.

**PRO OCI future path**: The installer could later add a `--pro` flag that:
1. Exchanges license key for a registry token via the license server
2. Runs `docker login ghcr.io -u token -p <token>`
3. Sets `FILAOPS_BACKEND_IMAGE=ghcr.io/blb3d/filaops-backend-pro:latest` in `.env`

This is NOT part of the initial implementation but the `.env` structure supports it.

---

### Step 4: Update release script

**Modify**: `scripts/generate-release.sh`

Add `docker-compose.prod.yml`, `.env.production`, and `scripts/install-filaops.ps1` to the release artifacts:
```bash
echo "[X/Y] Copying Docker deployment files..."
cp docker-compose.prod.yml "$DIST_DIR/"
cp .env.production "$DIST_DIR/"
cp scripts/install-filaops.ps1 "$DIST_DIR/"
```

Include these files in SHA256SUMS generation.

---

## File Summary

| File | Action | Purpose |
|------|--------|---------|
| `backend/.dockerignore` | **Create** | Exclude dev files from build context |
| `backend/Dockerfile` | **Edit** | OCI labels + fix version default |
| `frontend/Dockerfile` | **Edit** | OCI labels |
| `docker-compose.prod.yml` | **Create** | Production compose with parameterized images |
| `.env.production` | **Create** | Production env template |
| `.github/workflows/docker-publish.yml` | **Create** | CI to build + push images on tags |
| `scripts/install-filaops.ps1` | **Create** | Windows one-click installer |
| `scripts/generate-release.sh` | **Edit** | Include new files in release artifacts |

---

## PRO/Enterprise OCI Roadmap (out of scope, but designed for)

The architecture supports this future progression:

```
Phase 1 (this issue): Core images on public ghcr.io
                      PRO via runtime wheel injection (existing behavior)

Phase 2 (ecosystem):  PRO images on private ghcr.io
                      Built FROM Core image + wheel pre-installed
                      License server issues short-lived registry tokens
                      Installer --pro flag does docker login + sets image env var

Phase 3 (future):     Enterprise images (same pattern)
                      OCI artifact distribution for wheels (oras push/pull)
                      Signed images (cosign/notation)
```

Each phase is additive — no Core changes needed after Phase 1.

---

## Verification

1. **Dockerfile changes**: `docker build -t filaops-backend-test ./backend` — verify labels with `docker inspect`
2. **Production compose**: `docker compose -f docker-compose.prod.yml config` — validates YAML and variable substitution
3. **CI workflow**: Trigger manually via `workflow_dispatch` before first real tag push. Verify images appear at `ghcr.io/blb3d/filaops-backend` and `ghcr.io/blb3d/filaops-frontend`
4. **Installer**: Test on clean Windows machine — run `install-filaops.ps1`, verify browser opens to setup wizard
5. **PRO compatibility**: Set `FILAOPS_LICENSE_KEY` in `.env`, verify runtime injection still works with the prod compose (entrypoint downloads wheel, app starts with PRO features)
6. **Upgrade path**: Run installer twice — verify `.env` is preserved, compose file is updated, containers restart with new images
