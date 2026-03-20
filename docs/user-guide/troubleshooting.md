# Troubleshooting

> Common problems and how to fix them.

This page collects the most frequently encountered issues across FilaOps, organized by module. If you don't find your answer here, check the [GitHub Issues](https://github.com/Blb3D/filaops/issues) page for known bugs and feature requests.

---

## Installation & Startup

### Backend won't start

**Symptom:** Error messages when running `uvicorn` or `python -m app.main`.

| Check | Fix |
|-------|-----|
| Python version | FilaOps requires Python 3.11+. Run `python --version` to verify. |
| Virtual environment | Make sure your venv is activated. You should see `(venv)` in your terminal prompt. |
| Missing dependencies | Run `pip install -r requirements.txt` inside your venv. |
| Database not running | Verify PostgreSQL is running and accessible. Check with `pg_isready` or your OS service manager. |
| Wrong database URL | Check `backend/.env` — the `DATABASE_URL` must point to a running PostgreSQL instance with the correct username, password, and database name. |
| Port already in use | Another process is using port 8000. Either stop that process or start FilaOps on a different port: `uvicorn app.main:app --port 8001`. |

### Frontend won't start

**Symptom:** `npm run dev` fails or the page won't load.

| Check | Fix |
|-------|-----|
| Node version | FilaOps requires Node.js 18+. Run `node --version` to verify. |
| Missing packages | Run `npm install` in the `frontend/` directory. |
| Backend not running | The frontend proxies API calls to the backend. Start the backend first. |
| Wrong port | By default, the frontend runs on port 5173. If that port is busy, Vite will pick another and display it in the terminal. |

### Database migration errors

**Symptom:** Errors about missing tables or columns when the backend starts.

1. Make sure your database exists: `createdb filaops` (or whatever name is in your `.env`)
2. Run migrations: `alembic upgrade head` from the `backend/` directory
3. If migrations fail, check that `DATABASE_URL` in `.env` matches your PostgreSQL setup

---

## Login & Authentication

### Can't log in

| Check | Fix |
|-------|-----|
| Email vs. username | FilaOps uses your **email address** to log in, not a username. |
| Wrong password | Use the **Forgot Password** link, or ask an admin to reset your password from **Admin > Team**. |
| Account inactive | An admin may have deactivated your account. Check with your administrator. |
| Cookies blocked | FilaOps uses HTTP-only cookies for authentication. Make sure your browser isn't blocking cookies from the FilaOps domain. |

### Session expired unexpectedly

FilaOps sessions use refresh tokens. If you're being logged out frequently:

- Check that your system clock is accurate — large time differences can invalidate tokens
- Clear your browser cookies for the FilaOps domain and log in again
- If the problem persists, an admin may have reset your password (which invalidates all sessions)

### Password reset says "submitted for review" but no email arrives

This is expected behavior. The reset form intentionally does not reveal whether an email exists in the system (anti-enumeration, OWASP A07:2021 — Identification and Authentication Failures). If no account matches the email you entered, the response looks identical to a valid submission but no email is sent.

**To verify your admin email**, check the database: `SELECT email FROM users WHERE account_type = 'admin';`

### Password reset shows "Request validation failed"

The `email-validator` library rejects `.local` domains (RFC 6762 reserved). If your user account uses an email like `user@myserver.local`, the reset form will fail with a validation error.

**Fix:** Use a standard TLD for user emails. For development, `admin@example.com` or `admin@dev.test` work well.

### Forgot password but SMTP is not configured

When SMTP is not set up, the password reset flow auto-approves and displays the reset link directly on the Forgot Password page. No email is needed. See the [First-Run Setup Guide](../FIRST-RUN-SETUP.md#without-smtp-configured-development-mode) for details.

### Locked out of admin account on a dev database

If you cannot log in and the setup wizard does not appear (because users exist), see [Dev Environment: Resetting Admin Credentials](../FIRST-RUN-SETUP.md#dev-environment-resetting-admin-credentials) for multiple recovery options.

---

## Dashboard

### Dashboard shows all zeros

The dashboard displays data based on recent activity. If everything shows zero:

- **New installation?** — The dashboard needs orders, production, and inventory data to display metrics. Complete your [first day setup](first-day.md) and create some transactions.
- **Date range issue** — Some dashboard metrics use "Month to Date." If it's the first of the month, there may simply be no data yet.

### Command Center not responding

The Command Center search bar filters across multiple data types. If it seems unresponsive:

- Try a shorter search term (at least 2 characters)
- Make sure the backend is running — the Command Center queries the API
- Check your browser's developer console for network errors

---

## Orders & Quotes

### Quote won't convert to order

- The quote must be in **Sent** or **Accepted** status to convert
- Check that all line items have valid products and prices
- Make sure the customer record is complete

### Order stuck in "Confirmed" status

Orders don't advance automatically. You need to:

1. Create production orders for manufactured items
2. Complete production
3. Ship the order from the order detail page

See the [Quote to Cash](workflows/quote-to-cash.md) workflow for the complete process.

### Payment not showing in accounting

Payments only appear in accounting reports after they're recorded against a specific order. Check:

- Did you enter the payment in the order's Payment section (not just mark the order as shipped)?
- Is the payment date within the date range you're filtering in the Payments tab?

---

## Inventory

### Item shows wrong quantity

Inventory quantities are calculated from transaction history. If the number seems wrong:

1. Go to **Inventory > Transactions** and filter by the item
2. Review recent transactions — look for incorrect adjustments, duplicate receipts, or missing consumption records
3. Use a [cycle count](inventory.md) to correct the quantity if needed

### Spool tracking shows wrong weight

Spool quantities update when filament is consumed by production orders. Common issues:

- **BOM quantity wrong** — If the Bill of Materials specifies the wrong amount of filament per unit, every production order will consume the wrong amount
- **UOM mismatch** — Filament BOMs should specify quantities in grams. Check the BOM line's unit of measure.
- **Manual adjustment needed** — If a spool was used outside of FilaOps (test prints, waste), create a manual adjustment in Inventory Transactions

### Location not appearing in dropdowns

- Locations must be **Active** to appear in dropdowns. Check if the location was deactivated.
- Go to **Admin > Locations**, enable **Show Inactive**, and reactivate the location if needed.

---

## Production

### Can't start a production order

Production orders must be in **Draft** status to move to **In Progress**. Check:

- Is the production order in Draft status?
- Does it have a valid product with a Bill of Materials?
- Are the required materials in stock? (FilaOps warns but doesn't block if materials are short)

### Production order won't complete

To complete a production order, all operations in the routing must be finished. If the **Complete** button isn't available:

- Check that each operation is marked as done
- If there's no routing, the production order can be completed directly

### COGS not calculating correctly

Cost of Goods Sold depends on accurate BOMs. If COGS seems wrong:

- Verify the BOM has all materials listed with correct quantities
- Check that material costs (unit cost on each item) are up to date
- Remember that COGS uses the **cost at the time of production**, not the current cost

---

## Purchasing

### PO won't submit

Purchase orders need at minimum:

- A vendor selected
- At least one line item with a product and quantity
- A valid unit price

### Received quantities don't match inventory

When you receive a PO, the received quantity should add to inventory. If it doesn't:

- Check the **Receive** action on the PO — did you enter the correct quantity?
- Verify the item's inventory location — received goods go to the location specified on the PO line

---

## MRP

### MRP shows no results

MRP only generates suggestions when there's demand. Check:

- Do you have **Confirmed** sales orders with products that have BOMs?
- Is the planning horizon long enough to capture upcoming orders?
- Did you check the **Include Draft Orders** option if you want to plan for quotes?

### MRP suggests materials I already have

MRP considers both demand and on-hand inventory. If it's suggesting materials you have:

- Verify the on-hand quantity in **Inventory > Items** — is the system quantity accurate?
- Check if the materials are allocated to other orders
- Run a cycle count to correct any discrepancies

---

## Printers

### Printer shows "Offline"

| Check | Fix |
|-------|-----|
| Power | Is the printer powered on? |
| Network | Is the printer connected to the same network as FilaOps? Ping the printer's IP to verify. |
| IP changed | If using DHCP, the printer's IP may have changed after a restart. Update it in FilaOps or set a static IP. |
| API disabled | Some printer firmware requires explicitly enabling the API (e.g., OctoPrint requires an API key). |
| Firewall | Check that no firewall is blocking communication between FilaOps and the printer. |

### MQTT status not updating

If you're using MQTT monitoring and status isn't updating in real time:

- Verify your MQTT broker is running and accessible
- Check the MQTT topic configured for the printer matches what the printer is actually publishing to
- Review the MQTT broker logs for connection errors
- Test with an MQTT client (like MQTT Explorer) to verify the printer is publishing messages

---

## Accounting

### Revenue not appearing in reports

Revenue is recognized when orders are **shipped**, not when they're created or paid. To see revenue:

1. Make sure the order is marked as Shipped
2. Check the date range in the Sales Journal — the ship date must fall within your filter

### Tax calculations seem wrong

- Verify your tax rate in **Admin > Settings > Tax Settings**
- Check that tax is enabled (the **Enable Tax** checkbox must be on)
- Tax is calculated on the line item total (quantity x price). Verify your prices are correct.
- Tax only applies to shipped orders in the Tax Center reports

### CSV export is empty

CSV exports use the same date range filter shown on screen. If the export is empty:

- Check your date filter — are there actually transactions in that period?
- Try expanding the date range
- Make sure there's data in the tab you're exporting from

---

## Performance

### Pages loading slowly

- **Large datasets** — If you have thousands of items, orders, or transactions, pagination helps. Use filters to narrow results.
- **Backend resources** — Check that your server has adequate RAM and CPU. PostgreSQL performance degrades with insufficient memory.
- **Network** — If FilaOps is running on a remote server, check your network connection.

### Browser tab using too much memory

- Close FilaOps tabs you're not actively using
- If a specific page is slow, try refreshing the browser
- Clear browser cache if performance degrades over time

---

## Getting More Help

If you can't resolve your issue:

1. **Search existing issues** — [github.com/Blb3D/filaops/issues](https://github.com/Blb3D/filaops/issues)
2. **Report a bug** — Open a new issue with:
   - What you were trying to do
   - What happened instead
   - Steps to reproduce
   - Your FilaOps version (shown in **Admin > Settings**)
   - Browser and OS information
3. **Community support** — Check the repository's Discussions tab for community help
