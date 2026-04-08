# Basic Accounting

> Track revenue, costs, taxes, and profitability without leaving FilaOps.

## What You'll Learn

- How FilaOps records financial data automatically from your orders
- How to review the accounting dashboard for a quick financial snapshot
- How to drill into the sales journal, payments, and COGS reports
- How to prepare tax information for filing
- How to export accounting data for your accountant or tax software

## Prerequisites

- Admin access to FilaOps
- At least a few shipped orders and recorded payments (see [Taking and Fulfilling Orders](orders.md))
- Tax settings configured if you collect sales tax (see [System Settings](system-settings.md))

---

## How Accounting Works in FilaOps

FilaOps uses **accrual-basis accounting** — revenue is recognized when an order ships, not when payment is received. This gives you a more accurate picture of your business because it matches income to the period when the work was actually done.

You don't need to enter journal entries or maintain a chart of accounts for day-to-day operations. FilaOps automatically records financial data as you work:

- **Ship an order** → Revenue and COGS are recorded
- **Record a payment** → Cash received is tracked
- **Collect sales tax** → Tax liability is calculated

The five accounting views organize this data into reports you can use for business decisions and tax preparation.

---

## The Accounting Dashboard

Navigate to **Accounting** in the sidebar. The dashboard loads by default and shows a snapshot of your current financial position.

<!-- TODO: screenshot of accounting dashboard -->

### Revenue and Payments

The left section shows four cards:

| Card | What It Shows |
|------|--------------|
| **Revenue MTD** | Total revenue from shipped orders this month, with order count |
| **Revenue YTD** | Total revenue from shipped orders this year, with order count |
| **Cash Received MTD** | Payments collected this month, with year-to-date total below |
| **Accounts Receivable** | Outstanding balance from unpaid invoices, with count of unpaid orders |

### Tax and Profitability

The right section shows three cards:

| Card | What It Shows |
|------|--------------|
| **Sales Tax Liability MTD** | Tax collected this month that you'll need to remit, with year-to-date total |
| **COGS MTD** | Cost of goods sold this month (materials, labor, packaging) |
| **Gross Profit MTD** | Revenue minus COGS, with gross margin percentage |

!!! tip "New to FilaOps?"
    If you see a blue hint banner about accrual accounting, it means you have confirmed orders that haven't shipped yet. Revenue won't appear until those orders are marked as shipped.

---

## Sales Journal

Click the **Sales Journal** tab to see a detailed record of every shipped order line item.

<!-- TODO: screenshot of sales journal -->

### Filtering by Date

Use the **Start Date** and **End Date** fields to narrow the report to a specific period. The default view shows the last 30 days.

### Reading the Sales Journal

The top of the page shows five summary cards:

| Card | What It Shows |
|------|--------------|
| **Orders** | Number of orders in the selected period |
| **Subtotal** | Total before tax and shipping |
| **Tax** | Total sales tax collected |
| **Shipping** | Total shipping charges |
| **Grand Total** | Subtotal + tax + shipping |

Below the summary, a table lists every line item:

| Column | What It Shows |
|--------|--------------|
| **Date** | When the order was shipped |
| **Order** | Order number (click to open the order) |
| **Product** | Item name |
| **Subtotal** | Line item amount before tax |
| **Tax** | Tax charged on this line |
| **Total** | Line total including tax |
| **Status** | Payment status — **Paid** (green), **Partial** (yellow), or **Unpaid** (gray) |

### Exporting

Click **Export CSV** to download the sales journal as a spreadsheet file. The file is named `sales-journal-{start}-to-{end}.csv` using your selected date range.

---

## Payments

Click the **Payments** tab to see all payments and refunds recorded against your orders.

<!-- TODO: screenshot of payments tab -->

### Summary Cards

| Card | What It Shows |
|------|--------------|
| **Payments** | Total amount received (green) |
| **Refunds** | Total amount refunded (red) |
| **Net** | Payments minus refunds |
| **Transactions** | Total number of payment and refund transactions |

### By Payment Method

Below the summary, a grid of cards breaks down totals by payment method (cash, check, credit card, etc.). This helps you reconcile each payment channel.

### Payment Details Table

| Column | What It Shows |
|--------|--------------|
| **Date** | When the payment was recorded |
| **Payment #** | Unique payment identifier |
| **Order** | The order this payment applies to |
| **Method** | Payment method used |
| **Amount** | Dollar amount (green for payments, red for refunds) |
| **Type** | **Payment** (green) or **Refund** (red) |

### Exporting

Click **Export CSV** to download as `payments-journal-{start}-to-{end}.csv`.

!!! info "Where do payments come from?"
    Payments are recorded on individual order detail pages, not in the Payments tab directly. Navigate to an order and use the payment section to record a payment. The Payments tab is a read-only report of all recorded payments.

---

## COGS and Materials

Click the **COGS** tab to understand your production costs and gross profitability.

<!-- TODO: screenshot of COGS tab -->

### Selecting a Period

Use the period dropdown to choose a time window: **7 days**, **30 days** (default), **90 days**, or **365 days**.

### Summary Cards

| Card | What It Shows |
|------|--------------|
| **Orders Shipped** | Number of orders that shipped in the period |
| **Revenue** | Total revenue from those orders (excludes tax) |
| **Total COGS** | Combined cost of materials, labor, and packaging |
| **Gross Profit** | Revenue minus COGS, with gross margin percentage |

### COGS Breakdown

Below the summary, a detailed breakdown shows each cost component:

- **Materials** — Raw material costs calculated from your Bills of Materials
- **Labor** — Labor costs from production routing operations
- **Packaging** — Packaging material costs
- **Total COGS** — Sum of all production costs (highlighted)
- **Shipping Expense** — Carrier costs (shown separately because shipping is an operating expense, not part of COGS)

!!! tip "Improving your margin"
    If your gross margin is lower than expected, check the COGS breakdown to see which cost component is the largest. For most print farms, materials dominate — review your product BOMs to make sure material quantities and costs are accurate.

---

## Tax Center

Click the **Tax Center** tab to prepare your sales tax information for filing.

<!-- TODO: screenshot of tax center -->

### Selecting a Period

Use the period dropdown to choose **Monthly**, **Quarterly** (default), or **Yearly** reporting.

### Summary Cards

| Card | What It Shows |
|------|--------------|
| **Total Sales** | Gross sales amount with order count |
| **Taxable Sales** | Sales subject to tax |
| **Non-Taxable** | Exempt or non-taxable sales (gray) |
| **Tax Collected** | Total tax collected — this is the amount you need to remit |
| **Pending Tax** | Tax on orders not yet shipped (yellow, if any exist) |

!!! warning "Pending tax"
    If you see a pending tax amount, those are orders that have been confirmed but not shipped. The tax is collected but not yet recognized. This number will move to "Tax Collected" when you ship the orders.

### By Tax Rate

A table breaks down your tax collection by rate, useful if you operate in multiple tax jurisdictions:

| Column | What It Shows |
|--------|--------------|
| **Rate** | Tax rate percentage |
| **Taxable Sales** | Sales at this rate |
| **Tax Collected** | Tax collected at this rate |
| **Orders** | Number of orders at this rate |

### Monthly Breakdown

A second table shows tax collection by month, making it easy to fill in monthly or quarterly tax returns:

| Column | What It Shows |
|--------|--------------|
| **Month** | Calendar month |
| **Taxable Sales** | Taxable sales for that month |
| **Tax Collected** | Tax collected that month |
| **Orders** | Order count for that month |

### Exporting

Click **Export CSV** to download as `tax-summary-{period}.csv`. Hand this file to your accountant or use it to file your sales tax return.

---

## Tips and Best Practices

- **Review the dashboard weekly** — A quick look at revenue, AR, and margin keeps you aware of your financial health without spending time on bookkeeping.
- **Export monthly** — At month-end, export the sales journal, payments, and tax summary for your records. These files are your audit trail.
- **Record payments promptly** — The Accounts Receivable figure on the dashboard is only accurate if you record payments as they come in. Don't let them pile up.
- **Ship orders to recognize revenue** — Until an order is marked as shipped, its revenue doesn't appear in your accounting reports. If your numbers look low, check for unshipped orders.
- **Set up tax correctly first** — Configure your tax rate and name in [System Settings](system-settings.md) before creating orders. Changing tax settings doesn't retroactively update existing orders.
- **COGS depends on BOMs** — Cost of goods sold is calculated from your Bills of Materials. If COGS looks wrong, check that your product BOMs have accurate material quantities and costs.

!!! info "Looking for more?"
    [FilaOps PRO](https://blb3dprinting.com) adds accounting periods, Schedule C tax preparation, advanced multi-jurisdiction tax, and a full chart of accounts. Core already records automatic double-entry journal entries on shipment (DR COGS / CR FG Inventory) — these feed the COGS and P&L views above.

## What's Next?

- [Taking and Fulfilling Orders](orders.md) — where payments and revenue originate
- [Managing Your Product Catalog](product-catalog.md) — maintaining accurate BOMs for COGS
- [System Settings](system-settings.md) — configuring tax rates
- [Month-End Close](workflows/month-end-close.md) — a checklist for closing your books each month

## Quick Reference

| Task | Where to Find It |
|------|-------------------|
| View financial snapshot | **Accounting** > **Dashboard** tab |
| Review shipped order revenue | **Accounting** > **Sales Journal** tab |
| Review payments and refunds | **Accounting** > **Payments** tab |
| Analyze production costs | **Accounting** > **COGS** tab |
| Prepare tax filing data | **Accounting** > **Tax Center** tab |
| Record a payment | **Sales** > **Orders** > open an order > Payment section |
| Export sales journal | **Accounting** > **Sales Journal** > **Export CSV** |
| Export tax summary | **Accounting** > **Tax Center** > **Export CSV** |
| Configure tax rate | **Settings** > **Company Settings** > Tax Settings |
