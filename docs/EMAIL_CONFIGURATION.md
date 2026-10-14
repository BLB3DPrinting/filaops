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

Set `ADMIN_APPROVAL_EMAIL` to a real administrator's address. Password reset approval requests, with their Approve and Deny links, are sent there. FilaOps treats email as off until it is set: while it is empty or a placeholder, reset requests stay pending as if SMTP were not configured. Placeholders are the stock `admin@example.com`, any address at `example.com`, `example.org` or `example.net`, and addresses at `localhost` or a reserved test domain (`.example`, `.test`, `.invalid`, `.localhost`, `.localdomain`).

Then restart the backend. With Docker, run `docker compose up -d`, which recreates the backend container with the new values. `docker compose restart` keeps the old values.

To check that the backend sees the settings, open **Admin > Settings**. The amber "Email (SMTP) Not Configured" banner disappears once `SMTP_USER` and `SMTP_PASSWORD` are set and `ADMIN_APPROVAL_EMAIL` is a real address.

## Shop Name and Contact Address in Emails

Customer emails (password reset approved, denied and changed) name your shop and tell the customer where to get help. FilaOps picks each value in this order:

| Value | First choice | Fallback | Last resort |
|-------|--------------|----------|-------------|
| Shop name in the email | **Company Name** in **Admin > Settings > Company Information** | `BUSINESS_NAME` in `.env` | `FilaOps` |
| From name | **Company Name** | `SMTP_FROM_NAME`, then `BUSINESS_NAME` in `.env` | `FilaOps` |
| Contact address in the email | **Email** in **Admin > Settings > Company Information** | `BUSINESS_EMAIL` in `.env` | "contact your administrator" |

Blank values and the shipped placeholders (`Your Company Name`, `info@yourcompany.com`, `example.com` addresses) are skipped. The From address itself is always `SMTP_FROM_EMAIL`.

## Gmail Setup

1. Enable 2-Factor Authentication on your Google account
2. Generate an App Password: <https://myaccount.google.com/apppasswords>
3. Use the App Password (not your regular password) for SMTP_PASSWORD

## Disabling Email

If SMTP is not configured, or `ADMIN_APPROVAL_EMAIL` is empty or a placeholder, FilaOps will:
- Keep password reset requests pending. No reset link is sent or shown. An administrator resets a staff (admin or operator) password from **Admin > Team Members > Reset PW** instead. Customer accounts are not on Team Members, so they cannot reset a password until SMTP is configured.
- Log the recipient and subject of each email instead of sending it. The email body is not logged, because it contains approval and reset links.

For a full description of how password resets work with and without SMTP, see [First-Run Setup and Password Reset](FIRST-RUN-SETUP.md#password-reset-flow).
