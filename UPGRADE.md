# Upgrading FilaOps

**The full guide is [Upgrading FilaOps](https://blb3dprinting.github.io/filaops/UPGRADE/)**
([same page in this repo](docs/UPGRADE.md)). This page is a short version for
anyone who arrived from the "Full Documentation" link in the app's update banner.

## Before you start

- **Back up your database first.** Rolling back means restoring that backup:

  ```bash
  docker exec filaops-db pg_dump -U postgres -d filaops --no-owner --no-privileges > filaops_before_upgrade.sql
  ```

- **Docker, coming from 4.3.1 or older: copy your product images onto the
  uploads volume.** Before 4.3.2, product images were saved inside the backend
  container, and the upgrade replaces that container. While the old version is
  still running:

  ```bash
  docker compose exec backend sh -c 'set -eu; src=/app/static/uploads/products; dst=/app/uploads/products; mkdir -p "$dst"; if [ -d "$src" ]; then cp -a "$src/." "$dst/"; fi; ls "$dst" | wc -l'
  ```

  It prints how many images are now on the volume (0 is fine if you never
  uploaded any). If it prints an error instead, don't upgrade until it
  succeeds: the images would be lost. Image links don't change.
- **Don't click "Update Now" in the app, and don't mount the Docker socket into
  the backend** to make it work. Doing that gives the web app control of your
  whole machine. Upgrade with the commands below instead.
- **On 4.1.x or older?** 4.2.0 was a security release, and some installs won't
  start or will behave differently until a few settings are changed: a real
  `SECRET_KEY`, a real database password, and `ADMIN_APPROVAL_EMAIL` if you send
  email. Make the changes in
  [Actions you must take](https://blb3dprinting.github.io/filaops/UPGRADE-4.2.0/#actions-you-must-take)
  first. You can then upgrade straight to the current release; there's no need
  to stop at 4.2.0.

## Upgrade (Docker)

From the `filaops` folder:

```bash
git fetch --tags
git checkout v4.3.2
docker compose up -d --build
```

`--build` is required: without it, Docker restarts the old version. Database
migrations run on their own before the backend starts. Then check the version:

```bash
curl -s http://localhost/api/v1/system/version
```

If `git checkout` says your local changes would be overwritten, you edited a
tracked file such as `docker-compose.yml`. Keep your changes, then put the file
back and try again:

1. Save a copy of what you changed: `git diff > my-local-changes.patch`
2. Move settings (lines like `ENABLE_PUBLIC_QUOTER: "true"`) into `.env` as
   `ENABLE_PUBLIC_QUOTER=true`.
3. Move other changes, such as extra ports, volumes or services, into a
   `docker-compose.override.yml` next to `docker-compose.yml`. Docker Compose
   reads it automatically, and FilaOps doesn't ship one, so upgrades leave it alone.
4. Put the original file back: `git checkout -- docker-compose.yml`
5. Run the upgrade commands again.

## If something goes wrong

Restore the backup you took and check out your previous version. **Don't run
`alembic downgrade` repeatedly** to go back, and don't use
`docker compose down -v`, which deletes your data volumes. See
[Rolling back](https://blb3dprinting.github.io/filaops/UPGRADE/#rolling-back).

What changed in each release is in the [CHANGELOG](CHANGELOG.md).
