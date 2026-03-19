# First-Run Setup and Password Reset

This document covers two closely related topics: how FilaOps handles initial setup on a fresh database, and how password resets work.

## First-Run Setup

### What Happens on First Launch

When FilaOps starts with an empty user table, the frontend automatically detects this and redirects to the **Setup Wizard** at `/onboarding`. The backend exposes two endpoints that drive this flow:

- `GET /api/v1/setup/status` -- Returns `needs_setup: true` when zero users exist.
- `POST /api/v1/setup/initial-admin` -- Creates the first admin account. This endpoint is **permanently disabled** once any user exists (returns `403 Forbidden`).

The setup wizard walks through seven steps:

1. **Create Admin Account** -- email, name, password, optional company name
2. **Load Example Data** -- optionally seed sample items, materials, colors, and UOMs
3. **Import Products** (CSV, optional)
4. **Import Customers** (CSV, optional)
5. **Import Orders** (CSV, optional)
6. **Import Inventory** (CSV, optional)
7. **Complete** -- redirects to the dashboard

After step 1, the user is immediately authenticated (via httpOnly cookie or bearer token depending on `AUTH_MODE`) and logged in. Steps 2-6 can all be skipped.

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

FilaOps uses an **admin-approved** password reset flow by default. The behavior changes depending on whether SMTP email is configured.

### With SMTP Configured

This is the production flow:

1. User clicks "Forgot Password" on the login page and submits their email.
2. The backend creates a `PasswordResetRequest` with `status=pending` (expires in 24 hours).
3. An email is sent to the admin (`ADMIN_APPROVAL_EMAIL` in `.env`) with Approve/Deny links.
4. **Admin approves:** The user receives an email with a reset link. The link expires in **1 hour** after approval.
5. **Admin denies:** The user receives a denial notification email.
6. User clicks the reset link, enters a new password, and all existing sessions are invalidated.

### Without SMTP Configured

When `SMTP_USER` and `SMTP_PASSWORD` are not set in `.env`:

1. User clicks "Forgot Password" and submits their email.
2. The backend **auto-approves** the request immediately.
3. A reset link is returned directly in the API response and displayed on the page.
4. User clicks the link and sets a new password.

No email is sent. The Forgot Password page displays the reset link directly with a "Reset My Password" button.

> **Production warning:** If SMTP is not configured in production, auto-approval still works but a **SECURITY WARNING** is logged on every password reset. This bypasses admin approval, meaning anyone who knows a valid email address can reset that account's password without inbox verification. **Configure SMTP for production deployments** — see [Email Setup](https://blb3d.github.io/filaops/EMAIL_CONFIGURATION/).

### Anti-Enumeration (Security Note)

The password reset endpoint intentionally **does not reveal whether an email exists** in the system. If you submit a non-existent email:

- **With SMTP:** You see a green success message: "If an account exists with this email, a password reset request has been submitted for review." No email is sent, but the response is identical.
- **Without SMTP:** No reset link is generated (since no user was found), but the generic success message still appears.

This follows OWASP A07:2021 (Identification and Authentication Failures) best practices. If you are testing and unsure which email your admin account uses, check the database directly rather than relying on the reset form.

### The `.local` TLD Gotcha

FilaOps uses `pydantic.EmailStr` for email validation, which depends on the `email-validator` library. This library **rejects `.local` domains** (RFC 6762 reserved for mDNS). If you try to reset a password for `user@myserver.local`, you will get a `422 Request validation failed` error instead of the reset flow.

**Workaround:** Use a standard TLD for user email addresses, even in development (e.g., `admin@example.com` or `admin@dev.test`). The `.test` TLD is reserved for testing by RFC 2606 and is accepted by `email-validator`.

---

## Configuring SMTP

Add these variables to `backend/.env` to enable email-based password resets:

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

See [EMAIL_CONFIGURATION.md](EMAIL_CONFIGURATION.md) for full details.

---

## Dev Environment: Resetting Admin Credentials

On development databases with existing data, the setup wizard does not appear (since users already exist) and the `/api/v1/setup/initial-admin` endpoint is disabled.

### Option 1: Admin Resets via Team Members Page

If you have a working admin login, go to **Settings > Team Members**, find the user, and click **Reset Password**.

### Option 2: Reset via psql (When Locked Out)

If you cannot log in at all, update the password hash directly in the database.

Generate a new hash and update it:

```bash
cd backend
python -c "
from app.core.security import hash_password
print(hash_password('NewPassword1!'))
"
```

Then update the database:

```sql
UPDATE users SET password_hash = '<paste hash here>' WHERE email = 'your-admin@example.com';
```

### Option 3: Reset via the Forgot Password Flow (No SMTP)

If SMTP is not configured (typical for dev), use the Forgot Password page:

1. Go to `http://localhost:5173/forgot-password`
2. Enter the admin email address
3. The reset link appears directly on the page (no email needed)
4. Click the link and set a new password

### Option 4: Delete All Users to Re-trigger Setup Wizard

As a last resort on a development database, you can delete all users to re-trigger the first-run setup:

```sql
-- WARNING: This deletes all users, sessions, and reset requests.
-- Only use on development databases.
DELETE FROM password_reset_requests;
DELETE FROM refresh_tokens;
DELETE FROM users;
```

Then refresh the browser -- the setup wizard will appear again.
