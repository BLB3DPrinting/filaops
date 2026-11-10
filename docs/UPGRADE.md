# Upgrading FilaOps

The current release is **4.4.0**. Upgrade straight to it from any earlier
version. There is no need to stop at a release in between: the database
migrations run in order in one go.

What you need to do first depends on the version you are on now. To check it,
run `cat backend/VERSION` in the `filaops` folder, or open
`/api/v1/system/version` on your FilaOps address.

| You are on | Before you upgrade | Then |
| --- | --- | --- |
| **4.3.2** | Read [What changes in 4.4.0](#what-changes-in-440). | [Upgrade](#upgrade), then [refresh costs](#6-refresh-costs) (step 6) |
| **4.3.0 or 4.3.1** | Docker: [copy your product images](#2-docker-copy-product-images-onto-the-volume) (step 2). Read [What changes in 4.4.0](#what-changes-in-440) and [in 4.3.2](#what-changes-in-432). | [Upgrade](#upgrade), then [refresh costs](#6-refresh-costs) (step 6) |
| **4.2.x** | Docker: [copy your product images](#2-docker-copy-product-images-onto-the-volume) (step 2). Read [What changes in 4.4.0](#what-changes-in-440), [in 4.3.2](#what-changes-in-432), [in 4.3.1](#what-changes-in-431) and [in 4.3.0](#what-changes-in-430). | [Upgrade](#upgrade), then [refresh costs](#6-refresh-costs) (step 6) |
| **4.1.x or older** | Make the changes in [Actions you must take](UPGRADE-4.2.0.md#actions-you-must-take) on the 4.2.0 page. 4.2.0 was a security release, and some installs won't start or work as before without them. Also read [What changes in 4.4.0](#what-changes-in-440) and the sections below it. | [Upgrade](#upgrade) on this page, not the steps on the 4.2.0 page, then [refresh costs](#6-refresh-costs) (step 6). Afterwards, read [After you upgrade](UPGRADE-4.2.0.md#after-you-upgrade) and [Things that work differently](UPGRADE-4.2.0.md#things-that-work-differently) there. |

The [CHANGELOG](https://github.com/BLB3DPrinting/filaops/blob/main/CHANGELOG.md)
lists everything that changed in each release, with its upgrade notes.

## Upgrade

### 1. Back up

Do this just before you upgrade, at a time when nobody is using FilaOps:
anything entered after the backup is taken is not in it.

For a Docker install, from the `filaops` folder. If a
`filaops_before_upgrade.sql` from an earlier upgrade is still in the folder,
rename or delete it first, so that it cannot be mistaken for the new one.

```bash
docker exec filaops-db pg_dump -U postgres -d filaops --no-owner --no-privileges -f /tmp/filaops_before_upgrade.sql
docker cp filaops-db:/tmp/filaops_before_upgrade.sql ./filaops_before_upgrade.sql
```

Both commands must finish without an error. If `docker cp` fails, the dump is
still inside the container: fix the cause and run that command again.

The dump is written inside the database container and then copied out, so
the file does not depend on how your shell handles output. Don't send
`pg_dump` output to a file with `>` in Windows PowerShell: version 5.1 writes
it in an encoding that cannot be restored. On Windows, run these commands in
PowerShell or Command Prompt. Git Bash rewrites the `/tmp/...` paths, so they
fail there.

Use your own `DB_USER` and `DB_NAME` if you changed them. For a manual
install, run `pg_dump` with the same options against your own PostgreSQL
server, writing the file with `-f filaops_before_upgrade.sql`.

Check the backup before you go on. The last few lines of the file must include
`PostgreSQL database dump complete` (`tail -n 5 filaops_before_upgrade.sql`,
or in PowerShell `Get-Content filaops_before_upgrade.sql -Tail 5`; in Command
Prompt, open the file in a text editor and look at its end). A failed dump can
still leave an empty or partial file behind.

When the check has passed, remove the copy left inside the container:

```bash
docker exec filaops-db rm /tmp/filaops_before_upgrade.sql
```

Keep the file: rolling back means restoring it. If you are already on 4.3.0 or later, back up
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
Already on 4.3.2 or later? Skip this step too.

### 3. Get the new code

From the `filaops` folder, check out the 4.4.0 release:

```bash
git fetch --tags
git checkout v4.4.0
```

If your install follows the `main` branch instead, run `git pull`.

Check that you have the new code. This should print `4.4.0`:

```bash
cat backend/VERSION
```

**Upgrade the folder you run FilaOps from. Don't try the new version in a
second copy of it on the same computer.** `docker-compose.yml` gives the
containers and the data volumes fixed names, so a second copy is not a
separate install: it uses the same database, and starting it on newer code
upgrades your live data. A fresh clone into another folder called `filaops`
does this with no warning at all. To try a release first, use another
computer. ISSUE-012 in `KNOWN_ISSUES.md` has the details, and what a second
copy on the same computer needs.

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

This should print `"version":"4.4.0"`:

```bash
curl -s http://localhost/api/v1/system/version
```

In Windows PowerShell, type `curl.exe` in place of `curl`. There, `curl` is a
different command, and this line stops with an error about a missing `Uri`.

Both of these should print the same revision, and the first should end in
`(head)`:

```bash
docker compose exec backend alembic current
docker compose exec backend alembic heads
```

(Manual install: run `alembic current` and `alembic heads` in `backend/`, and
use your backend's address in the `curl` command.)

- **Still the old version?** If `cat backend/VERSION` prints the old version,
  repeat step 3. If it prints `4.4.0`, the images weren't rebuilt: run
  `docker compose up -d --build` again.
- **Migrations not at head?** Run `docker compose logs migrate` to see why the
  `migrate` service stopped, fix the cause, and run `docker compose up -d --build`
  again. If you can't, restore your backup (see [Rolling back](#rolling-back))
  rather than use FilaOps with a partly migrated database.
- **Coming from 4.1.x and the backend won't start in production?** The usual
  cause is the `SECRET_KEY` check: see
  [Set a real SECRET_KEY](UPGRADE-4.2.0.md#1-set-a-real-secret_key).

### 6. Refresh costs

4.4.0 corrects how costs are worked out, and some stored figures only change
when they are recalculated. Coming from 4.3.2 or older:

1. **Read what the upgrade reported, straight away.** Run
   `docker compose logs migrate` and look for the lines containing `105:`
   (manual install: they are in the output of `alembic upgrade head`). They
   list each standard cost that was repaired, each material whose purchase unit
   was changed from EA to KG, and each item that was left alone, with the
   reason. In a repaired line, `x1E+3` means the cost was multiplied by 1000.
   Lines marked `WARNI` are the ones left for you. Read them now:
   they go when the migrate container is next recreated, for example by the
   next upgrade.
2. **Correct the items it left alone.** For a bought item, a standard cost is
   edited on the item form. Saving that form clears any weight and dimensions
   stored on the item (ISSUE-011 in `KNOWN_ISSUES.md`), so enter them again
   before saving, or change the cost through the API instead:
   `PATCH /api/v1/items/{id}` with only `standard_cost`. For an item listed
   because it has an active BOM
   or routing, do not edit its standard cost: Recost All replaces it with the
   cost worked out from its BOM and routing. Check what it is costed from
   instead: its components' costs and quantities, and its routing's operation
   times and work-centre rates. Look at its standard cost again after step 3:
   an item whose cost works out to zero is skipped and keeps its old figure. A
   purchase unit is not on the form yet: change it through the API
   (`PATCH /api/v1/items/{id}` with `purchase_uom`). An item bought by a pack
   with no pack size recorded is not listed when its standard and average
   costs differ; check those yourself.
3. **Run Recost All.** On the **Items** page, click **All Items** in the
   category list, set the type dropdown to **All Types**, click **Recost All**
   and confirm. It covers the category and type chosen there; the search box
   and the status filter do not limit it. It refreshes the standard cost of
   made items and the stored total of the BOM each is costed from. One run settles every level of
   sub-assembly. Inactive items are skipped, and items built from themselves
   are named in the server log. If you correct a component's cost later, run
   it again.

## What changes in 4.4.0

- **Costs are worked out in the right unit.** A filament's standard cost is per
  KG and its average cost is per gram, and several places mixed the two up.
  Cycle counts, inventory valuation, routing material costs, MRP purchase
  lines and BOM costs could be 1000 times off, and receiving a purchase order
  could overwrite a filament's standard cost with a per-gram figure. All of
  these now go through one rule.
- **One database migration (105)** repairs standard costs already overwritten
  that way, changes the purchase unit of some filaments from EA to KG, and
  lists anything it is unsure of. `alembic downgrade` does not undo it. See
  [Refresh costs](#6-refresh-costs).
- **Recost All settles every level in one run.** It costs sub-assemblies
  before the items built from them.
- **Count variances** are valued by the item's cost method (average cost for
  average-cost items). They used to take standard cost first.
- **Deactivate and reactivate an item** from its edit form, and filter the
  Items list by Active, Inactive or All.
- **Items page:** the table stays on the page you move to. It used to go back
  to page 1 a moment after you clicked **Next**.
- **Going back a version:** if an older version is started on an upgraded
  database, the migrate step's message no longer tells you to delete the
  database volume. Versions before 4.4.0 still print the old message, so
  follow [Rolling back](#rolling-back).
- **Scheduling:** the scheduler board draws operations that share one machine
  and one window as a single block, and counts a lane's overlapping bookings
  once.
- **Production:** splitting an order no longer over-consumes material. A failed
  plate posts its scrap, and completing an operation is refused if its scrap
  cannot be posted. An order that made nothing can be closed as scrapped (API
  only for now: `POST /api/v1/production-orders/{id}/close-scrapped`).
  Materials are sized from the exact order quantity, so orders created or split
  from now on can reserve slightly more or less than before, and a quantity
  with more than four decimals is refused.
- **MRP** can plan routing-only parts as production (`MRP_ROUTING_MAKE_BUY`),
  count open production orders as supply (`MRP_OPEN_PO_SUPPLY`) and release a
  planned order as a full production order (`MRP_RELEASE_COPIES_ROUTING`). Each
  is off by default. Manual install: set them in `backend/.env` and restart
  the backend. Docker: `docker-compose.yml` passes a fixed list of settings to
  the backend, so add them under the backend service's `environment` in a
  `docker-compose.override.yml` (for example `MRP_OPEN_PO_SUPPLY: "true"`)
  and run `docker compose up -d`.

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
step 1 and redeploying the old version: follow
[section 3 of Rollback](ROLLBACK.md#3-emergency-database-restore). Anything
entered after the upgrade is not in the restored database. An older version
won't start against a database that has been migrated further, so always
restore the backup, and never delete the database volume to get it started.

Don't use `docker compose down -v` to roll back. On 4.3.0 and later it also
deletes the `filaops_config` volume, and without it stored secrets such as the
AI API key can't be read and have to be entered again. If you do lose the
volume, restore it from your config backup (see
[Backup and Recovery](BACKUP-AND-RECOVERY.md)) along with the database.
