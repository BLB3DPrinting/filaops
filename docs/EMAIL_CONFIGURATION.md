# Email Configuration

FilaOps can send transactional emails for password resets and notifications.

## Environment Variables

Add to your `.env` file. For Docker, that is the `.env` in the project root. For a manual install, it is `backend/.env`.

```ini
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=noreply@yourcompany.com
SMTP_FROM_NAME=Your Company Name
SMTP_TLS=true
ADMIN_APPROVAL_EMAIL=admin@yourcompany.com
```

Set `ADMIN_APPROVAL_EMAIL` to a real administrator's address. Password reset approval requests are sent there.

Then restart the backend. With Docker, run `docker compose up -d`, which recreates the backend container with the new values. `docker compose restart` keeps the old values.

To check that the backend sees the settings, open **Admin > Settings**. The amber "Email (SMTP) Not Configured" banner disappears once `SMTP_USER` and `SMTP_PASSWORD` are set.

## Gmail Setup

1. Enable 2-Factor Authentication on your Google account
2. Generate an App Password: <https://myaccount.google.com/apppasswords>
3. Use the App Password (not your regular password) for SMTP_PASSWORD

## Disabling Email

If SMTP is not configured, FilaOps will:
- Keep password reset requests pending. No reset link is sent or shown. An administrator resets a staff (admin or operator) password from **Admin > Team Members > Reset PW** instead. Customer portal accounts are not on Team Members, so they cannot reset a password until SMTP is configured.
- Log the recipient and subject of each email instead of sending it. The email body is not logged, because it contains approval and reset links.

For a full description of how password resets work with and without SMTP, see [First-Run Setup and Password Reset](FIRST-RUN-SETUP.md#password-reset-flow).
