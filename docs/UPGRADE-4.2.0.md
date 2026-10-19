# Upgrading to FilaOps 4.2.0

!!! note "Upgrading today? Go straight to the latest release"
    This page describes what changed in 4.2.0 and the settings it needs. If you
    are on 4.1.x or older, make the changes in
    [Actions you must take](#actions-you-must-take) below, then follow
    [Upgrading FilaOps](UPGRADE.md) to go straight to the current release. Its
    upgrade steps replace the ones on this page, which check out `v4.2.0`.

4.2.0 is a security release. Every install should upgrade. Read this page
before you start: some installs need a setting changed first, and a few things
work differently afterwards.

Upgrading from 4.1.0 runs database migrations (new tables and columns for
quality control, operation types and invoice voids). On Docker, the `migrate`
service runs them when you rebuild and start the stack with
`docker compose up -d --build`. A plain `docker compose up -d` reuses the
4.1.0 images, so nothing is upgraded. A manual install runs
`alembic upgrade head`. **Back up your database before upgrading** (see
[Backup and Recovery](BACKUP-AND-RECOVERY.md)); you need that backup to roll
back.

First make the changes in [Actions you must take](#actions-you-must-take),
then follow [Upgrade](#upgrade).

## Before you upgrade: checklist

| Do this | Who needs to |
| --- | --- |
| Set a real `SECRET_KEY` | Everyone whose `SECRET_KEY` is empty, a placeholder, or copied from an example |
| Set a real database password | Docker installs still using the default `changeme` |
| Set `ENABLE_PUBLIC_QUOTER=true` in `.env` | Only installs that accept customer sign-ups or public quote requests (Docker: not by editing `docker-compose.yml`) |
| Set up email, with a real `ADMIN_APPROVAL_EMAIL` | Shops that send email, or that have customer accounts (customers can only reset a password by email) |
| Give integrations a staff account | Anyone with a script or integration that signs in as a customer account |
| Check for duplicate imported orders | Installs that import orders from a CSV file |
| Check scripts that change order, invoice or stock status | Anyone with a script or integration that does this through the API |

Where to put settings: the project `.env` file for a Docker install, or
`backend/.env` for a manual install. After changing them, run
`docker compose up -d` (Docker) or restart the backend (manual install).

## Actions you must take

### 1. Set a real `SECRET_KEY`

`SECRET_KEY` signs every login. It must be a long random value that only your
server knows.

Make one with either command:

```bash
openssl rand -hex 32
python -c "import secrets; print(secrets.token_hex(32))"
```

Add it as `SECRET_KEY=<the value>` and restart.

What happens if you don't:

- **Production** (`ENVIRONMENT=production`): FilaOps refuses to start if the
  key is empty, a placeholder, or one of the example keys that earlier FilaOps
  files and docs showed. If your production `.env` still has an example key,
  replace it **before** you upgrade or the upgraded backend will not start.
- **Any other environment**: FilaOps starts, but with a temporary random key
  that is thrown away on every restart. Everyone is signed out each time the
  backend restarts, and **Admin > Security Audit** reports "Temporary
  SECRET_KEY in use" until you set a real key.

A key shorter than 32 characters still works but logs a warning.

### 2. Set a real database password (Docker)

The stock `docker-compose.yml` uses `DB_PASSWORD`, which defaults to
`changeme`. 4.2.0 also stops publishing the database on your network (see
[Database port](#database-port)), but a default password should still be
replaced.

Make a password the same way as the key above (`openssl rand -hex 32`).

**New install** (no database yet): add it to the project `.env` **before** the
first `docker compose up -d`:

```
DB_PASSWORD=<the value>
```

The database takes its password from this setting only when it is created
for the first time, so setting it later works differently (below).

**Existing install** still on `changeme`: change the password inside the
database first, then tell FilaOps the new one. Changing `.env` alone stops the
backend from connecting.

1. Open a database prompt inside the container (use your own `DB_USER` and
   `DB_NAME` if you changed them). If it asks for a password, enter the
   current one.

    ```bash
    docker compose exec db psql -U postgres -d filaops
    ```

2. At the `filaops=#` prompt, type `\password` (it changes the password of
   the user you connected as, your `DB_USER`), enter the new password twice,
   then type `\q`. Typing it here keeps it out of your shell
   history.
3. Set `DB_PASSWORD=<the new password>` in the project `.env`.
4. Run `docker compose up -d`. The backend restarts with the new password.

If the backend can't connect afterwards, the two values differ: repeat step 2
with the value from `.env`.

A manual install uses your own PostgreSQL server: change the password there
and set the same value in `backend/.env`.

### 3. Decide whether to accept customer sign-ups and public quotes

Customer self-registration and public quote intake are off by default. This
setting turns them on:

```
ENABLE_PUBLIC_QUOTER=true
```

Before 4.2.0, customer self-registration was always on, whatever this setting
said. Leave it unset if you don't take customer sign-ups or quote requests.
Staff accounts are still created through first-run setup or **Admin > Team
Members**.

**Docker installs that already turned this on:** before 4.2.0 the stock
`docker-compose.yml` did not pass `ENABLE_PUBLIC_QUOTER` to the backend, so
the setting had to be added to the compose setup by hand.

- If you added it in a `docker-compose.override.yml`, it keeps working.
- If you added it by **editing `docker-compose.yml` itself**, taking the new
  4.2.0 file removes your edit, and customer sign-ups and public quote
  requests are then refused (403). Before you upgrade, put
  `ENABLE_PUBLIC_QUOTER=true` in the project `.env`. Copy across any other
  changes you made to `docker-compose.yml` too, into `.env` or an override
  file.

A manual install keeps reading the setting from `backend/.env` as before.

### 4. Set up email if customers reset their own passwords

Password reset approvals are emailed to `ADMIN_APPROVAL_EMAIL`. FilaOps now
treats email as **off** until `SMTP_USER`, `SMTP_PASSWORD` and a real
`ADMIN_APPROVAL_EMAIL` are all set. The default `admin@example.com`, and other
example or test addresses, count as not set.

**Customer accounts can only reset a password by email.** An admin can reset
a staff password from **Admin > Team Members**, but customer accounts are not
listed there. Until email is set up, a
customer who forgets their password has no way back in. If you have customer
accounts, set up email before you upgrade.

Before 4.2.0 the stock `docker-compose.yml` did not pass any `SMTP_*`
setting to the backend, so on a Docker install email was never on, even if
your `.env` has SMTP settings. Check them now: after the upgrade they take
effect.

Docker installs: the stock `docker-compose.yml` now passes the `SMTP_*`
settings, `ADMIN_APPROVAL_EMAIL`, `ENABLE_PUBLIC_QUOTER` and `ENVIRONMENT`
through to the containers. If you edited your own compose file, copy those
lines across.

### 5. Move integrations off customer accounts

Customer accounts can now only use the routes a customer needs: signing in,
the quotes they submitted, password reset and reading their own account
details. Everything
else returns **403 Forbidden** for a customer account. A few lookups that
previously answered without signing in now need a staff login too.

If a script, spreadsheet or integration signs in with a customer account to
read or change shop data, create a staff (operator or admin) account for it
in **Admin > Team Members**.

### 6. Check for duplicate imported orders

4.2.0 makes each imported order ID unique, so the same import can't create an
order twice. If two sales orders already share an imported order ID, the
upgrade stops at that step. Check before you upgrade. For a Docker install,
from the `filaops` folder:

```bash
docker exec filaops-db psql -U postgres -d filaops -c "SELECT source_order_id, string_agg(order_number, ', ' ORDER BY id) AS orders FROM sales_orders WHERE source_order_id IS NOT NULL GROUP BY source_order_id HAVING count(*) > 1;"
```

Use your own `DB_USER` and `DB_NAME` if you changed them. `(0 rows)` means
there is nothing to do.

If it lists any, each row shows an imported order ID and the orders that
share it. Decide which order is the real one, and cancel the others in
FilaOps if they shouldn't be fulfilled. Then clear the imported ID on the
extra orders, naming them by order number:

```bash
docker exec filaops-db psql -U postgres -d filaops -c "UPDATE sales_orders SET source_order_id = NULL WHERE order_number IN ('SO-2026-000123');"
```

Run the first command again; it should now return `(0 rows)`.

## Upgrade

Do these in order, after the actions above.

### 1. Back up the database

For a Docker install, from the `filaops` folder:

```bash
docker exec filaops-db pg_dump -U postgres -d filaops --no-owner --no-privileges > filaops_before_4.2.0.sql
```

Use your own `DB_USER` and `DB_NAME` if you changed them. Keep the file:
rolling back means restoring it. Other options are in
[Backup and Recovery](BACKUP-AND-RECOVERY.md).

### 2. Get the 4.2.0 code

These steps stop at 4.2.0. To upgrade to the current release instead, use
[Upgrading FilaOps](UPGRADE.md#3-get-the-new-code).

From the `filaops` folder, check out the 4.2.0 release:

```bash
git fetch --tags
git checkout v4.2.0
```

If your install follows the `main` branch instead, run `git pull`.

Check that you have the new code. This should print `4.2.0`:

```bash
cat backend/VERSION
```

### 3. Rebuild and start (Docker)

```bash
docker compose up -d --build
```

`--build` is required: it rebuilds the images from the new code. Without it,
Docker restarts the old 4.1.0 images and nothing is upgraded. The `migrate`
service then applies the database migrations before the backend starts.

**Manual install:** from `backend/`, with your virtual environment active, run
`pip install -r requirements.txt` and then `alembic upgrade head`. From
`frontend/`, using Node.js 24 or newer, run `npm ci` and `npm run build`. Then restart the backend and
the web server.

### 4. Confirm the upgrade

Check the version the running backend reports. This should print
`"version":"4.2.0"`:

```bash
curl -s http://localhost/api/v1/system/version
```

Check that the migrations are at the latest revision. Both commands should
print the same revision, and the first one should end in `(head)`:

```bash
docker compose exec backend alembic current
docker compose exec backend alembic heads
```

(Manual install: run `alembic current` and `alembic heads` in `backend/`, and
use your backend's address in the `curl` command.)

**If it still says 4.1.0:**

- If `cat backend/VERSION` prints `4.1.0`, the new code was not checked out.
  Repeat step 2.
- If `backend/VERSION` prints `4.2.0` but the running version is 4.1.0, the
  images were not rebuilt. Run `docker compose up -d --build`, then check
  again.

**If the migrations are not at head:** run `docker compose logs migrate` to
see why the `migrate` service stopped. Fix the cause and run
`docker compose up -d --build` again. If you can't, restore your backup (see
[Rolling back](#rolling-back)) rather than use FilaOps with a partly migrated
database.

## After you upgrade

### Who gets signed out

- If you **set or changed** `SECRET_KEY`, everyone is signed out once and
  must sign in again.
- If you left a placeholder key outside production, everyone is signed out on
  **every** restart until you set a real one.
- If you already had a real key and did not change it, nobody is signed out.

Customer accounts that try to use anything other than their own quotes and
account will start seeing "access denied" messages. That is expected.

### Review your accounts

As a precaution, review the customer accounts on your install and remove any
you don't recognise. This read-only query lists customer accounts that
registered themselves, newest first:

```sql
SELECT id, email, created_at
FROM users
WHERE account_type = 'customer' AND created_by IS NULL
ORDER BY created_at DESC;
```

For a Docker install, open a database prompt with
`docker compose exec db psql -U postgres -d filaops` (use your own `DB_USER`
and `DB_NAME` if you changed them).

The published security advisories for this release describe what else to
review.

## Things that work differently

### Password reset

- Every reset request now waits for an administrator. The reset page never
  shows a reset link.
- **Without email set up:** requests stay pending and can't be completed. An
  admin can reset a staff password directly from **Admin > Team Members >
  Reset PW**. Customer accounts can't be reset that way, so without email a
  customer can't reset a password at all.
- **With email set up:** the approve/deny email flow is unchanged. If an
  approval email fails to send, the user can request again after 15 minutes.
- Reset links issued by earlier versions without an administrator's approval
  no longer work. Ask the user to request a new reset.
- A slow or unreachable mail server no longer holds up the rest of FilaOps.

### Roles and permissions

- Only **admins** can create, edit or delete scrap reasons. Operators still
  choose from the list when scrapping work.
- Only **admins** can change the AI (Ollama) settings or use **Test
  connection**.
- When a user lacks the needed role, FilaOps now answers "Admin access
  required" or "Staff access required" straight away, even if the request
  was also malformed.

### AI settings (Ollama URL)

- The Ollama URL must be a plain `http://` or `https://` address with no
  username, password, query string or `#` fragment.
- Addresses on your own machine and local network (for example
  `http://localhost:11434` or `http://192.168.1.20:11434`) and Tailscale
  addresses still work.
- Some special-purpose addresses are refused, including link-local and cloud
  metadata addresses.
- FilaOps connects to the Ollama URL directly. It ignores `HTTP_PROXY`,
  `HTTPS_PROXY`, `ALL_PROXY` and `~/.netrc` for that connection, but still
  honours `REQUESTS_CA_BUNDLE` and `CURL_CA_BUNDLE`. If you reached Ollama
  through a proxy, point the URL at Ollama itself.

### Quotes

- When a customer accepts a quote they submitted, the server now works out
  the price and total itself and refuses quotes that can't be accepted any
  more (for example expired or already ordered).
- Approving a quote clears its "needs review" reason.
- Setting a quote back to pending keeps it on hold until staff approve it
  again.
- A note entered when changing a quote's status is **added** to the admin
  notes instead of replacing them. Notes are limited to 1,000 characters.
- The quote detail always shows the shipping line when there is a ship-to
  address, including `$0.00`. Check shipping before you approve a quote.

### Database port

The stock `docker-compose.yml` now publishes the database on `127.0.0.1`
only, instead of on every network interface. FilaOps itself is unaffected:
the backend reaches the database over Docker's internal network. Tools on the
same machine, such as `psql -h 127.0.0.1` or a backup script, still connect as
before. Other machines can no longer reach port 5432.

If you edited your own compose file, change the `db` service's port line to:

```yaml
    ports:
      - "127.0.0.1:5432:5432"
```

On Linux, a port Docker publishes on all interfaces is reachable even when a
firewall such as `ufw` blocks it, so don't rely on the firewall alone.

**If another machine genuinely needs the database** (for example a reporting
tool), prefer an SSH tunnel. It needs no change to FilaOps. From the other
machine:

```bash
ssh -L 5432:127.0.0.1:5432 you@your-filaops-server
```

then point the tool at `127.0.0.1:5432` on that machine.

If a tunnel isn't possible, publish the database on one private address only,
never on all interfaces. Put this in a `docker-compose.override.yml` next to
`docker-compose.yml`, so it survives upgrades (Compose adds it to the
loopback binding):

```yaml
services:
  db:
    ports:
      - "192.168.1.10:5432:5432"  # this server's address on your private network
```

Only do this with a strong `DB_PASSWORD` set, and allow only the machines that
need it on that network.

### Staff accounts

Without a licence, FilaOps 4.2.0 allows one staff (admin or operator) account.
Existing installs keep all their current users, and everyone can still sign
in, but you can't add or reactivate staff while you are over that number.
Customer accounts don't count. **4.3.1 removed this limit**: upgrade straight
to the current release (see [Upgrading FilaOps](UPGRADE.md)) and you can add
staff again.

### Orders, shipping and invoices

These steps can now only happen through their own actions, so stock and the
ledger always stay in step. Scripts that set the status directly get an
error.

- **Shipping:** only the **Ship** action marks an order shipped, and only once
  it is ready to ship. It checks stock first and records what shipped on each
  line.
- **Cancelling:** only the **Cancel** action cancels an order. It records when
  and why, and releases linked production orders and reserved material.
- **Releasing production:** an order's production is released only after
  billing has started: a payment is recorded or an invoice is sent. Net-terms
  customers don't have to pay first.
- **Invoices:** editing an invoice can only change its status from draft to
  sent. To void an invoice, use the new **Void** action and give a reason;
  void or refund its payments first.

### Inventory adjustments

A manual adjustment now adds or removes the quantity you enter: `+5` adds
five and `-5` removes five. Before 4.2.0 it set the on-hand quantity to that
number. It can't take stock below zero. To set an exact counted quantity, use
**Reconciliation**.

### Accounting figures

Figures in the accounting reports may change after the upgrade:

- The trial balance and account ledger count posted journal entries only.
  Draft and voided entries no longer change the totals.
- COGS on the dashboard and in the profit and COGS reports comes from the
  general ledger.
- Completing production now posts to the ledger. Production completed before
  4.2.0 has no ledger entries. `backend/scripts/backfill_production_completion_gl.py`
  can add them: it previews by default, and needs a recent backup before it
  writes anything. Read `--help` first.
- Closing a fiscal period marks it closed for reporting. It does not lock
  entries in that period.
- First-pass yield is worked out from each order's first inspection, so it may
  go down where orders were inspected again.

### `ENVIRONMENT` setting

`ENVIRONMENT` is now read the same way everywhere and ignores capitals and
spaces. `ENVIRONMENT=Production` now behaves exactly like
`ENVIRONMENT=production`: the API docs pages (`/docs`, `/redoc`) are turned
off and the production security header is sent. If you relied on those pages
with a capitalised value, they are now off.

## Rolling back

Because 4.2.0 changes the database, going back to 4.1.0 means restoring the
backup you took before upgrading and redeploying 4.1.0 (see
[Rollback](ROLLBACK.md)). Anything entered after the upgrade is lost.

Rolling back also brings back the problems this release fixes. If the
upgraded backend won't start, the usual cause is the `SECRET_KEY` check in
production: set a real key (step 1) instead of rolling back.
