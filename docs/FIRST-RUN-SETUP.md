# First-Run Setup and Password Reset

This document covers two closely related topics: how FilaOps handles initial setup on a fresh database, and how password resets work.

## First-Run Setup

### What Happens on First Launch

When FilaOps starts with an empty user table, the frontend automatically detects this and redirects to the **Setup Wizard** at `/onboarding`. The backend exposes two endpoints that drive this flow:

- `GET /api/v1/setup/status` -- Returns `needs_setup: true` when zero users exist.
- `POST /api/v1/setup/initial-admin` -- Creates the first admin account. This endpoint is **permanently disabled** once any user exists (returns `403 Forbidden`).

The setup wizard walks through eight steps:

1. **Create Admin Account** -- email, name, password, optional company name and customer contact email (the address customers are told to contact in emails; blank uses the admin email)
2. **Load Example Data** -- optionally seed sample items, materials, colors, and UOMs
3. **Import Products** (CSV, optional)
4. **Import Customers** (CSV, optional)
5. **Import Orders** (CSV, optional)
6. **Import Inventory** (CSV, optional)
7. **Connect Your First Printer** (optional)
8. **Complete** -- redirects to the dashboard

After step 1, the user is immediately authenticated (via httpOnly cookie or bearer token depending on `AUTH_MODE`) and logged in. Steps 2-7 can all be skipped.

### Password Requirements

The initial admin password must meet these requirements:

- At least 8 characters
- At least one uppercase letter (A-Z)
- At least one lowercase letter (a-z)
- At least one number (0-9)
- At least one special character (`!@#$%^&*` etc.)

### Rate Limiting

The `initial-admin` endpoint is rate-limited to **3 requests per minute** per IP to prevent abuse.

---

## Password Reset Flow

FilaOps uses an **admin-approved** password reset flow. The reset link is only ever sent by email after an administrator approves. It is never returned by the API or shown on the Forgot Password page.

### With SMTP Configured

This is the production flow:

1. User clicks "Forgot Password" on the login page and submits their email.
2. The backend creates a `PasswordResetRequest` with `status=pending` (expires in 24 hours).
3. An email is sent to the admin (`ADMIN_APPROVAL_EMAIL` in `.env`) with Approve/Deny links.
4. **Admin approves:** The user receives an email with a reset link. The link expires in **1 hour** after approval.
5. **Admin denies:** The user receives a denial notification email.
6. User clicks the reset link, enters a new password, and all existing sessions are invalidated.

If the approval email cannot be sent (for example, the mail server is down), the request stays pending and nobody is emailed. A new request made at least 15 minutes later tries the email again.

### Without SMTP Configured

When `SMTP_USER` and `SMTP_PASSWORD` are not set in `.env`, or `ADMIN_APPROVAL_EMAIL` is empty or a placeholder such as `admin@example.com`:

1. User clicks "Forgot Password" and submits their email.
2. The backend records a `PasswordResetRequest` with `status=pending` and logs a warning. No email is sent.
3. The page shows the same generic message as always. No reset link is shown.
4. The request stays pending and expires after 24 hours. It cannot be used to set a password.

Requests recorded while email is off are not emailed later, even after email is turned on. Once email works, the user requests a reset again.

To get a staff user (admin or operator) back in, an administrator resets their password from **Admin > Team Members > Reset PW** (see [Option 1](#option-1-admin-resets-via-team-members-page) below) and gives them the new password. If the only administrator is locked out, use [Option 2](#option-2-reset-via-psql-when-locked-out).

Customer accounts are not listed on Team Members, so an administrator cannot reset them there. They can only reset a password by email. If you have customer accounts, configure SMTP.

To let users reset their own passwords with admin approval, configure SMTP — see [Email Setup](https://blb3dprinting.github.io/filaops/EMAIL_CONFIGURATION/).

### Anti-Enumeration (Security Note)

The password reset endpoint returns the **same response body** whether or not an email exists in the system:

- **With or without SMTP:** You see the same success message: "If an account exists with this email, a password reset request has been submitted for review." If the email does not exist, no email is sent.
- The body is also the same when a request for that account is already pending, and it does not say whether SMTP is configured.

This makes it harder to find out which accounts exist (OWASP A07:2021, Identification and Authentication Failures), but it does not rule it out. The response can take longer for an existing account, especially when SMTP is configured and an email is sent. If you are testing and unsure which email your admin account uses, check the database directly rather than relying on the reset form.

### The `.local` TLD Gotcha

FilaOps uses `pydantic.EmailStr` for email validation, which depends on the `email-validator` library. This library **rejects `.local` domains** (RFC 6762 reserved for mDNS). If you try to reset a password for `user@myserver.local`, you will get a `422 Request validation failed` error instead of the reset flow.

**Workaround:** Use a standard TLD for user email addresses, even in development (e.g., `admin@example.com` or `admin@dev.test`). The `.test` TLD is reserved for testing by RFC 2606 and is accepted by `email-validator`.

---

## Configuring SMTP

Add these variables to your `.env` to enable email-based password resets. For Docker, that is the `.env` in the project root; run `docker compose up -d` afterwards so the backend container picks them up (`docker compose restart` does not). For a manual install, it is `backend/.env`; restart the backend afterwards.

```ini
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=noreply@yourcompany.com
SMTP_FROM_NAME=Your Company Name
ADMIN_APPROVAL_EMAIL=admin@yourcompany.com
```

For Gmail, you must use an [App Password](https://myaccount.google.com/apppasswords) (requires 2FA enabled on the Google account).

Customer emails sign with the company name and contact email from **Admin > Settings > Company Information**; `SMTP_FROM_NAME` is only a fallback.

See [EMAIL_CONFIGURATION.md](EMAIL_CONFIGURATION.md) for full details.

---

## Resetting Admin Credentials

Once users exist, the setup wizard does not appear and the `/api/v1/setup/initial-admin` endpoint is disabled. Use one of these options instead.

### Option 1: Admin Resets via Team Members Page

If you have a working admin login, go to **Admin > Team Members**, find the user, and click **Reset PW**. This works for admin and operator accounts.

### Option 2: Reset via psql (When Locked Out)

If no administrator can log in, set a new password hash directly in the database. First generate the hash, then paste it into an `UPDATE`.

**Docker install.** Run these from the project folder. The first command asks for the new password (it is not echoed) and prints the hash:

```bash
docker compose exec backend python -c "import getpass; from app.core.security import hash_password; print(hash_password(getpass.getpass('New password: ')))"
docker compose exec db psql -U postgres -d filaops
```

If you changed `DB_USER` or `DB_NAME` in `.env`, use those values in the `psql` command. At the `filaops=#` prompt, run the `UPDATE` below, then type `\q` to leave.

**Manual install.** From the repository root, with the backend virtual environment active:

```bash
cd backend
python -c "import getpass; from app.core.security import hash_password; print(hash_password(getpass.getpass('New password: ')))"
psql -U postgres -d filaops
```

Then update the database, pasting the hash between the single quotes:

```sql
UPDATE users SET password_hash = '<paste hash here>' WHERE email = 'your-admin@example.com';
```

The hash contains `$` characters. Paste it inside the `psql` prompt as shown, not into a shell command, so the shell does not change it.

### Option 3: Delete All Users to Re-trigger Setup Wizard

As a last resort on a development database, you can delete all users to re-trigger the first-run setup:

```sql
-- WARNING: This deletes all users, sessions, and reset requests.
-- Only use on development databases.
DELETE FROM password_reset_requests;
DELETE FROM refresh_tokens;
DELETE FROM users;
```

Then refresh the browser -- the setup wizard will appear again.
