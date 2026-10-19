# Upgrading FilaOps

The current release is **4.3.2**. Upgrade straight to it from any earlier
version. There is no need to stop at a release in between: the database
migrations run in order in one go.

What you need to do first depends on the version you are on now. To check it,
run `cat backend/VERSION` in the `filaops` folder, or open
`/api/v1/system/version` on your FilaOps address.

| You are on | Before you upgrade | Then |
| --- | --- | --- |
| **4.3.0 or 4.3.1** | Docker: [copy your product images](#2-docker-copy-product-images-onto-the-volume) (step 2). Read [What changes in 4.3.2](#what-changes-in-432). | [Upgrade](#upgrade) |
| **4.2.x** | Docker: [copy your product images](#2-docker-copy-product-images-onto-the-volume) (step 2). Read [What changes in 4.3.2](#what-changes-in-432), [in 4.3.1](#what-changes-in-431) and [in 4.3.0](#what-changes-in-430). | [Upgrade](#upgrade) |
| **4.1.x or older** | Make the changes in [Actions you must take](UPGRADE-4.2.0.md#actions-you-must-take) on the 4.2.0 page. 4.2.0 was a security release, and some installs won't start or work as before without them. | [Upgrade](#upgrade) on this page, not the steps on the 4.2.0 page. Afterwards, read [After you upgrade](UPGRADE-4.2.0.md#after-you-upgrade) and [Things that work differently](UPGRADE-4.2.0.md#things-that-work-differently) there. |

The [CHANGELOG](https://github.com/BLB3DPrinting/filaops/blob/main/CHANGELOG.md)
lists everything that changed in each release, with its upgrade notes.

## Upgrade

### 1. Back up

For a Docker install, from the `filaops` folder:

```bash
docker exec filaops-db pg_dump -U postgres -d filaops --no-owner --no-privileges > filaops_before_upgrade.sql
```

Use your own `DB_USER` and `DB_NAME` if you changed them. Keep the file:
rolling back means restoring it. If you are already on 4.3.0 or later, back up
the `filaops_config` volume too (see [Backup and Recovery](BACKUP-AND-RECOVERY.md)).
Installs older than 4.3.0 don't have it yet.

### 2. Docker: copy product images onto the volume

Before 4.3.2, Docker installs saved product images inside the backend
container, and the upgrade replaces that container. Copy them onto the uploads
volume while the old version is still running:

```bash
docker compose exec backend sh -c 'set -eu; src=/app/static/uploads/products; dst=/app/uploads/products; mkdir -p "$dst"; if [ -d "$src" ]; then cp -a "$src/." "$dst/"; fi; ls "$dst" | wc -l'
```

It prints how many images are now on the volume. 0 is fine if you never
uploaded any. If it prints an error instead, don't upgrade until it
succeeds: the images would be lost. Image links don't change, so products keep their pictures. Skip
this step for a manual install, where images were never inside a container.

### 3. Get the new code

From the `filaops` folder, check out the 4.3.2 release:

```bash
git fetch --tags
git checkout v4.3.2
```

If your install follows the `main` branch instead, run `git pull`.

Check that you have the new code. This should print `4.3.2`:

```bash
cat backend/VERSION
```

### 4. Rebuild and start (Docker)

```bash
docker compose up -d --build
```

`--build` is required: it rebuilds the images from the new code. Without it,
Docker restarts the old images and nothing is upgraded. The `migrate` service
applies the database migrations before the backend starts.

**Manual install:** from `backend/`, with your virtual environment active, run
`pip install -r requirements.txt` and then `alembic upgrade head`. From
`frontend/`, using Node.js 24 or newer, run `npm ci` and `npm run build`. Then
restart the backend and the web server.

### 5. Confirm the upgrade

This should print `"version":"4.3.2"`:

```bash
curl -s http://localhost/api/v1/system/version
```

Both of these should print the same revision, and the first should end in
`(head)`:

```bash
docker compose exec backend alembic current
docker compose exec backend alembic heads
```

(Manual install: run `alembic current` and `alembic heads` in `backend/`, and
use your backend's address in the `curl` command.)

- **Still the old version?** If `cat backend/VERSION` prints the old version,
  repeat step 3. If it prints `4.3.2`, the images weren't rebuilt: run
  `docker compose up -d --build` again.
- **Migrations not at head?** Run `docker compose logs migrate` to see why the
  `migrate` service stopped, fix the cause, and run `docker compose up -d --build`
  again. If you can't, restore your backup (see [Rolling back](#rolling-back))
  rather than use FilaOps with a partly migrated database.
- **Coming from 4.1.x and the backend won't start in production?** The usual
  cause is the `SECRET_KEY` check: see
  [Set a real SECRET_KEY](UPGRADE-4.2.0.md#1-set-a-real-secret_key).

## What changes in 4.3.2

- **Product images survive upgrades.** In Docker, product images were saved
  inside the backend container, so every upgrade or container rebuild deleted
  them. They are now saved on the uploads volume (`./uploads/products` on the
  host). Images already lost in an earlier upgrade can't be recovered: upload
  them again.
- **License page.** With an active license it says so, instead of asking for a
  key. It no longer shows a "Restart Core" banner that never went away, or an
  activation date of Dec 31, 1969.
- No database migrations.

## What changes in 4.3.1

- **No staff account limit.** An install without a licence can add and
  reactivate as many staff (admin and operator) accounts as it needs. 4.2.0 and
  4.3.0 allowed one. 4.3.1 has no database migrations.

## What changes in 4.3.0

- **Serial number prefix.** New serials use the prefix in
  **Admin > Settings > Serial Numbers**. An install that already issued `BLB-`
  serials keeps `BLB-`, so numbering carries on. Every other install gets `SN-`.
  Existing serials are never renamed.
- **Customer emails use Company Settings.** The shop name and email in
  **Admin > Settings > Company Information** now win over `BUSINESS_NAME`,
  `BUSINESS_EMAIL` and `SMTP_FROM_NAME` in `.env`. See
  [Email Setup](EMAIL_CONFIGURATION.md#shop-name-and-contact-address-in-emails).
- **Your logo** replaces the FilaOps wordmark in the sidebar, and shows on the
  login page.
- **AI settings** list the Claude models your API key can use. Check the
  selected model in **Admin > Integrations > AI Assistant** after upgrading.
  A retired model is marked "not listed by Anthropic".
- **Docker: the backend runs as `appuser`, not root.** At startup it takes
  ownership of the uploads and config folders. On a Linux host, files in
  `./uploads` change owner to uid 100. If it can't make a folder writable, it
  logs a warning and keeps running as root.
- **Docker: a new `filaops_config` volume** keeps the backend's instance ID
  (`install_uuid`), so stored secrets survive rebuilding the container. If the
  AI API key shows as not set after this upgrade, enter it once more. From now
  on, back up this volume with the database. `docker compose down -v` deletes it.

## Rolling back

Upgrading changes the database, so going back means restoring the backup from
step 1 and redeploying the old version (see [Rollback](ROLLBACK.md)). Anything
entered after the upgrade is lost. An older version won't start against a
database that has been migrated further, so always restore the backup.

Don't use `docker compose down -v` to roll back. On 4.3.0 and later it also
deletes the `filaops_config` volume, and without it stored secrets such as the
AI API key can't be read and have to be entered again. If you do lose the
volume, restore it from your config backup (see
[Backup and Recovery](BACKUP-AND-RECOVERY.md)) along with the database.
