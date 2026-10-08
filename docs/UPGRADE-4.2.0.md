# Upgrading to FilaOps 4.2.0

4.2.0 is a security release. Every install should upgrade. Read this page
before you start: some installs need a setting changed first, and a few things
work differently afterwards.

Upgrading from 4.1.0 runs database migrations (new tables and columns for
quality control, operation types and invoice voids). They run the same way as in earlier upgrades: the Docker `migrate`
service runs them on `docker compose up -d`, and a manual install runs
`alembic upgrade head`. **Back up your database before upgrading** (see
[Backup and Recovery](BACKUP-AND-RECOVERY.md)); you need that backup to roll
back.

## Before you upgrade: checklist

| Do this | Who needs to |
| --- | --- |
| Set a real `SECRET_KEY` | Everyone whose `SECRET_KEY` is empty, a placeholder, or copied from an example |
| Set `ENABLE_PUBLIC_QUOTER=true` | Only shops that run the public online Quoter |
| Set `ADMIN_APPROVAL_EMAIL` to a real address | Shops that send email (SMTP) |
| Give integrations a staff account | Anyone with a script or integration that signs in as a customer account |
| Install the matching FilaOps PRO update | FilaOps PRO users |

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

If you take payments through FilaOps PRO's Stripe checkout, a real key is
required for checkout to work reliably. Use the same key for every backend
process.

### 2. Decide whether customers may register themselves

Customer self-registration is now **off** unless the public Quoter is on. If
you run the public Quoter, set:

```
ENABLE_PUBLIC_QUOTER=true
```

If you don't run the Quoter, leave it unset. Staff accounts are still created
through first-run setup or **Admin > Team Members**.

### 3. If you use email, set `ADMIN_APPROVAL_EMAIL`

Password reset approvals are emailed to `ADMIN_APPROVAL_EMAIL`. FilaOps now
treats email as **off** until `SMTP_USER`, `SMTP_PASSWORD` and a real
`ADMIN_APPROVAL_EMAIL` are all set. The default `admin@example.com`, and other
example or test addresses, count as not set.

Docker installs: the stock `docker-compose.yml` now passes the `SMTP_*`
settings, `ADMIN_APPROVAL_EMAIL`, `ENABLE_PUBLIC_QUOTER` and `ENVIRONMENT`
through to the containers. If you edited your own compose file, copy those
lines across.

### 4. Move integrations off customer accounts

Customer accounts can now only use the routes a customer needs: signing in,
their own Quoter quotes, password reset and reading their own account
details. Everything
else returns **403 Forbidden** for a customer account. A few lookups that
previously answered without signing in now need a staff login too.

If a script, spreadsheet or integration signs in with a customer account to
read or change shop data, create a staff (operator or admin) account for it
in **Admin > Team Members**.

### 5. FilaOps PRO

Install the PRO update released alongside 4.2.0. B2B buyers keep using the
PRO portal as before.

## After you upgrade

### Who gets signed out

- If you **set or changed** `SECRET_KEY`, everyone is signed out once and
  must sign in again.
- If you left a placeholder key outside production, everyone is signed out on
  **every** restart until you set a real one.
- If you already had a real key and did not change it, nobody is signed out.

Customer accounts that are signed in to anything other than the Quoter will
start seeing "access denied" messages. That is expected.

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
  Reset PW**. Customer accounts need email set up to reset a password.
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

### Quotes (Quoter shops)

- When a customer accepts a Quoter quote, the server now works out the price
  and total itself and refuses quotes that can't be accepted any more (for
  example expired or already ordered).
- Approving a quote clears its "needs review" reason, so the customer can pay
  online.
- Setting a quote back to pending keeps it on hold until staff approve it
  again.
- A note entered when changing a quote's status is **added** to the admin
  notes instead of replacing them. Notes are limited to 1,000 characters.
- The quote detail always shows the shipping line when there is a ship-to
  address, including `$0.00`. Check shipping before you approve a quote.
- **PRO with Stripe:** if a payment is held for review, refund it in Stripe
  before approving the quote again, or approve it and convert it to an order
  straight away and record the payment on the order. Otherwise the customer
  could pay twice.

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
