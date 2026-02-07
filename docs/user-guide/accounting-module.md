# Accounting Module Guide

This guide covers FilaOps' built-in accounting system, including the General Ledger, journal entries, fiscal periods, inventory valuation, tax reporting, and financial dashboards.

## Overview

FilaOps includes a **double-entry bookkeeping** system that automatically records financial transactions as your business operates. When you receive inventory, ship orders, or consume materials in production, the GL stays in sync.

**Key Features:**
- Double-entry General Ledger with balance verification
- Automatic journal entries from inventory transactions
- Fiscal period management (open/close)
- Trial Balance and Transaction Ledger reports
- Inventory valuation with GL reconciliation
- COGS tracking and gross margin analysis
- Tax collection and reporting
- Revenue recognition at shipment (GAAP accrual basis)
- Schedule C line mapping for sole proprietor tax filing
- Full audit trail (who created, posted, voided every entry)

**Accounting Flow:**
```
Purchase Receipt → GL Entry (DR Inventory, CR AP)
Production Consumption → GL Entry (DR WIP, CR Raw Materials)
Finished Goods Receipt → GL Entry (DR FG Inventory, CR WIP)
Customer Shipment → GL Entry (DR COGS, CR FG Inventory)
```

**Who Uses This Module:**
- **Administrators** - Full access to all accounting features
- **Operators** - No access to accounting

---

## Table of Contents

1. [Chart of Accounts](#1-chart-of-accounts)
2. [Journal Entries](#2-journal-entries)
3. [Trial Balance](#3-trial-balance)
4. [Inventory Valuation](#4-inventory-valuation)
5. [Transaction Ledger](#5-transaction-ledger)
6. [Fiscal Periods](#6-fiscal-periods)
7. [Accounting Dashboard](#7-accounting-dashboard)
8. [COGS and Gross Margin](#8-cogs-and-gross-margin)
9. [Tax Reporting](#9-tax-reporting)
10. [Revenue and Payments](#10-revenue-and-payments)
11. [Schedule C Integration](#11-schedule-c-integration)
12. [Data Export](#12-data-export)
13. [Common Workflows](#13-common-workflows)
14. [Best Practices](#14-best-practices)
15. [Troubleshooting](#15-troubleshooting)
16. [Quick Reference](#16-quick-reference)

---

## 1. Chart of Accounts

### 1.1 What is the Chart of Accounts?

The **Chart of Accounts** is the master list of all financial accounts used to categorize transactions. Every journal entry posts to one or more of these accounts.

FilaOps ships with a default chart of accounts designed for 3D print farm operations.

### 1.2 Default Accounts

**Assets (1xxx) - Normal Balance: Debit**

| Code | Name | Purpose |
|------|------|---------|
| 1000 | Cash | Bank account / cash on hand |
| 1100 | Accounts Receivable | Money owed by customers |
| 1200 | Raw Materials Inventory | Filament, components (unconsumed) |
| 1210 | Work in Process (WIP) | Materials allocated to production |
| 1220 | Finished Goods Inventory | Completed products ready to sell |
| 1230 | Packaging Inventory | Boxes, bags, labels |

**Liabilities (2xxx) - Normal Balance: Credit**

| Code | Name | Purpose |
|------|------|---------|
| 2000 | Accounts Payable | Money owed to vendors |
| 2100 | Sales Tax Payable | Tax collected, owed to government |

**Revenue (4xxx) - Normal Balance: Credit**

| Code | Name | Purpose |
|------|------|---------|
| 4000 | Sales Revenue | Income from product sales |
| 4010 | Shipping Revenue | Shipping charges collected |

**Expenses (5xxx) - Normal Balance: Debit**

| Code | Name | Purpose |
|------|------|---------|
| 5000 | Cost of Goods Sold (COGS) | Material + labor cost of sold items |
| 5010 | Shipping Expense | Cost of shipping to customers |
| 5020 | Scrap Expense | Cost of scrapped/failed production |
| 5030 | Inventory Adjustment | Cost of cycle count corrections |
| 5100 | COGS - Materials | Material portion of COGS |

### 1.3 Account Types

| Type | Normal Balance | Increases With | Decreases With |
|------|---------------|----------------|----------------|
| **Asset** | Debit | Debit | Credit |
| **Liability** | Credit | Credit | Debit |
| **Equity** | Credit | Credit | Debit |
| **Revenue** | Credit | Credit | Debit |
| **Expense** | Debit | Debit | Credit |

### 1.4 System Accounts

Accounts marked as **system accounts** cannot be deleted. These are the core accounts needed for automatic transaction posting. You can rename them or add sub-accounts, but the codes must remain.

### 1.5 Sub-Accounts

Accounts support **parent-child hierarchy** for detailed tracking:

```
5000 - Cost of Goods Sold (parent)
  5010 - Shipping Expense
  5020 - Scrap Expense
  5030 - Inventory Adjustment
  5100 - COGS - Materials
```

---

## 2. Journal Entries

### 2.1 What is a Journal Entry?

A **Journal Entry** records a financial transaction using double-entry bookkeeping. Every entry has:

- At least **two lines** (minimum one debit and one credit)
- **Total debits must equal total credits** (balanced)
- A **source reference** linking to the originating document (PO, SO, etc.)

**Entry Number Format:** `JE-2026-0001` (auto-generated)

### 2.2 Journal Entry Statuses

| Status | Meaning | Editable? | In Reports? |
|--------|---------|-----------|-------------|
| **draft** | Created, not yet finalized | Yes | No |
| **posted** | Finalized and locked | No | Yes |
| **voided** | Cancelled with reason | No | No |

### 2.3 How Entries Are Created

**Most journal entries are created automatically** by inventory transactions:

**Purchase Order Receipt:**
```
DR 1200 Raw Materials Inventory    $125.00
   CR 2000 Accounts Payable                $125.00
   (Received 5 KG PLA @ $25/KG)
```

**Material Issue to Production:**
```
DR 1210 Work in Process            $11.25
   CR 1200 Raw Materials Inventory          $11.25
   (450 G PLA consumed for PO-2026-0042)
```

**Finished Goods Receipt (QC Pass):**
```
DR 1220 Finished Goods Inventory   $50.00
   CR 1210 Work in Process                  $50.00
   (10 EA Phone Stands completed)
```

**Shipment to Customer:**
```
DR 5000 Cost of Goods Sold         $50.00
   CR 1220 Finished Goods Inventory         $50.00
DR 5010 Shipping Expense           $0.10
   CR 1230 Packaging Inventory              $0.10
   (Shipped SO-2026-0042)
```

**Scrap (QC Failure):**
```
DR 5020 Scrap Expense              $5.00
   CR 1210 Work in Process                  $5.00
   (2 units scrapped - adhesion failure)
```

**Inventory Adjustment:**
```
DR 5030 Inventory Adjustment       $1.25
   CR 1200 Raw Materials Inventory          $1.25
   (Cycle count correction: -50 G PLA)
```

### 2.4 Manual Journal Entries

For transactions not covered by automatic posting, create manual entries:

**Navigation:** Accounting → Journal Entries → **+ New Entry**

**Step 1: Entry Header**
```
Description: "Write-off damaged inventory"
Entry Date: 2026-02-07
```

**Step 2: Add Lines**
```
Line 1: DR 5030 Inventory Adjustment   $25.00
Line 2: CR 1200 Raw Materials                   $25.00
```

**Step 3: Verify Balance**
- System shows: Total Debits = $25.00, Total Credits = $25.00
- Status: Balanced

**Step 4: Save as Draft or Post**
- **Save Draft** - Can edit later
- **Post** - Locks entry, includes in reports

### 2.5 Posting Journal Entries

**From "draft" to "posted":**

1. Open the journal entry
2. Verify all lines are correct
3. Confirm the entry is balanced (debits = credits)
4. Click **Post Entry**
5. Entry is locked and included in financial reports

**What Happens:**
- `posted_by` and `posted_at` are recorded
- Entry becomes read-only
- Balances update in Trial Balance
- Entry visible in Transaction Ledger

### 2.6 Voiding Journal Entries

**For posted entries that need correction:**

1. Open the journal entry
2. Click **Void Entry**
3. Enter void reason: "Duplicate entry" or "Incorrect amount"
4. Confirm

**What Happens:**
- Entry status changes to "voided"
- `voided_by`, `voided_at`, and `void_reason` are recorded
- Entry excluded from reports
- To correct: create a new entry with the right amounts

**You cannot edit a posted entry** - void and recreate instead.

### 2.7 Source Tracking

Every journal entry can link to its source document:

| Source Type | Example | Auto-Created? |
|-------------|---------|---------------|
| Purchase Order | PO-2026-010 | Yes (on receipt) |
| Sales Order | SO-2026-042 | Yes (on shipment) |
| Production Order | PO-2026-005 | Yes (on completion) |
| Inventory Adjustment | ADJ-001 | Yes (on adjustment) |
| Payment | PAY-001 | Yes (on payment record) |
| Manual | - | No (manual entry) |

Click the source reference in any entry to navigate to the originating document.

---

## 3. Trial Balance

### 3.1 What is a Trial Balance?

The **Trial Balance** is the foundational accounting report. It lists all GL accounts with their debit and credit balances as of a specific date. If total debits equal total credits, the books are **balanced**.

### 3.2 Viewing the Trial Balance

**Navigation:** Accounting → **GL Reports** → **Trial Balance**

**Parameters:**
- **As of Date** - Report date (defaults to today)
- **Include Zero Balances** - Show accounts with no activity

**Report Output:**

```
Trial Balance as of 2026-02-07
═══════════════════════════════════════════════════════════
Account   Name                          Debit      Credit
═══════════════════════════════════════════════════════════
1000      Cash                       $12,450.00
1100      Accounts Receivable         $2,350.00
1200      Raw Materials Inventory     $3,128.50
1210      Work in Process               $450.00
1220      Finished Goods Inventory    $1,755.00
1230      Packaging Inventory           $425.00
2000      Accounts Payable                        $1,850.00
2100      Sales Tax Payable                         $312.50
4000      Sales Revenue                          $15,250.00
5000      Cost of Goods Sold          $6,854.00
═══════════════════════════════════════════════════════════
TOTAL                               $27,412.50  $27,412.50
                                     ✓ BALANCED
```

### 3.3 Understanding Normal Balances

Each account type has a **normal balance** side:

- **Assets** (1xxx) - Normally show a **debit** balance
- **Liabilities** (2xxx) - Normally show a **credit** balance
- **Revenue** (4xxx) - Normally show a **credit** balance
- **Expenses** (5xxx) - Normally show a **debit** balance

If an account shows the opposite of its normal balance, investigate (e.g., negative inventory value suggests over-consumption).

### 3.4 When to Review

- **Weekly** - Quick check that books are balanced
- **Month-end** - Before closing fiscal period
- **Quarter-end** - Before tax filing preparation
- **Year-end** - Before annual close and tax preparation

---

## 4. Inventory Valuation

### 4.1 What is Inventory Valuation?

The **Inventory Valuation** report compares the value of physical inventory (from the inventory module) against GL account balances. Any difference is a **variance** that needs investigation.

### 4.2 Viewing Inventory Valuation

**Navigation:** Accounting → **GL Reports** → **Inventory Valuation**

**Report Output:**

```
Inventory Valuation Report
═══════════════════════════════════════════════════════════════════
Category          GL Account   Physical Value   GL Balance   Variance
═══════════════════════════════════════════════════════════════════════
Raw Materials     1200         $3,128.50        $3,128.50    $0.00 ✓
Work in Process   1210           $450.00          $450.00    $0.00 ✓
Finished Goods    1220         $1,755.00        $1,755.00    $0.00 ✓
Packaging         1230           $425.00          $425.00    $0.00 ✓
═══════════════════════════════════════════════════════════════════════
TOTAL                          $5,758.50        $5,758.50    $0.00 ✓
```

### 4.3 Understanding Categories

| Category | GL Account | What It Includes |
|----------|-----------|-----------------|
| **Raw Materials** | 1200 | Filament, components, hardware not yet in production |
| **Work in Process** | 1210 | Materials allocated/consumed by active production orders |
| **Finished Goods** | 1220 | Completed products in inventory, ready to sell |
| **Packaging** | 1230 | Boxes, bags, labels, packing materials |

**SKU Mapping Logic:**
- SKUs starting with `MAT-` map to Raw Materials (1200)
- SKUs starting with `PRD-` or finished goods map to Finished Goods (1220)
- SKUs starting with `PKG-` map to Packaging (1230)
- Active production order materials map to WIP (1210)

### 4.4 Investigating Variances

**Common causes of variance:**

1. **Manual inventory adjustments** without corresponding GL entries
2. **Incomplete transactions** (receipt recorded but GL entry failed)
3. **Timing differences** (physical count at different time than GL snapshot)
4. **Pre-existing inventory** (stock existed before the GL system was configured)

**Resolution steps:**
1. Note the variance amount and category
2. Check recent inventory transactions for the category
3. Look for manual adjustments without GL postings
4. Create a correcting journal entry if needed
5. Document the cause for audit trail

---

## 5. Transaction Ledger

### 5.1 What is the Transaction Ledger?

The **Transaction Ledger** shows all journal entry lines for a specific GL account, with a **running balance** after each transaction. It's the detailed view of how an account balance was built up over time.

### 5.2 Viewing the Ledger

**Navigation:** Accounting → **GL Reports** → **Transaction Ledger**

**Parameters:**
- **Account Code** - The GL account to view (e.g., 1200)
- **Start Date** / **End Date** - Date range filter
- **Limit** / **Offset** - Pagination

**Report Output:**

```
Transaction Ledger: 1200 - Raw Materials Inventory
Period: 2026-02-01 to 2026-02-07
═══════════════════════════════════════════════════════════════════════════
Date       Entry #        Description                 Debit    Credit   Balance
═══════════════════════════════════════════════════════════════════════════
           Opening Balance                                              $2,500.00
2026-02-03 JE-2026-0021   PO-2026-010 Receipt       $125.00            $2,625.00
2026-02-05 JE-2026-0024   PO-2026-005 Consumption            $11.25    $2,613.75
2026-02-06 JE-2026-0025   PO-2026-008 Consumption            $8.50     $2,605.25
2026-02-07 JE-2026-0027   ADJ-001 Cycle Count                $1.25     $2,604.00
═══════════════════════════════════════════════════════════════════════════
                           Period Activity           $125.00  $21.00
                           Closing Balance                              $2,604.00
```

### 5.3 Using the Ledger

**Click any entry** to view the full journal entry details.

**Common uses:**
- Trace how inventory value changed over a period
- Find specific transactions by source reference
- Verify costs were recorded correctly
- Prepare for audits or tax filing
- Debug inventory valuation variances

---

## 6. Fiscal Periods

### 6.1 What is a Fiscal Period?

A **Fiscal Period** represents a month in your fiscal year. Periods control when journal entries can be posted:

- **Open period** - New entries allowed
- **Closed period** - No new entries (historical data locked)

### 6.2 Period Structure

```
Fiscal Year 2026
├── Period 1  (Jan 2026)  - Closed ✓
├── Period 2  (Feb 2026)  - Open (current)
├── Period 3  (Mar 2026)  - Open
├── ...
└── Period 12 (Dec 2026)  - Open
```

### 6.3 Viewing Fiscal Periods

**Navigation:** Accounting → **Periods**

**Columns:**
- Year and period number
- Start date and end date
- Status (open / closed)
- Entry count
- Total debits and credits
- Closed by / closed at (if closed)

### 6.4 Closing a Period

**Navigation:** Accounting → Periods → Select period → **Close**

**Pre-Close Validation:**
1. System checks all entries in the period are balanced
2. Displays summary: entry count, total debits/credits
3. Warns of any unposted draft entries
4. Requires confirmation

**Closing Process:**
1. Click **Close Period**
2. Review the summary
3. Confirm closure
4. Period status changes to "closed"
5. `closed_by` and `closed_at` recorded

**After Closing:**
- No new journal entries can be dated in this period
- Existing entries remain visible (read-only)
- Reports reflect final numbers
- Prevents accidental modification of historical data

### 6.5 Reopening a Period

**Use with caution** - only for correcting errors discovered after close.

**Navigation:** Accounting → Periods → Select closed period → **Reopen**

1. Click **Reopen Period**
2. Confirm the action
3. Period status changes back to "open"
4. New entries can now be posted to this period
5. **Remember to re-close** after making corrections

**When to Reopen:**
- Discovered a missed invoice from previous month
- Need to correct a posting error
- Auditor requires an adjustment

---

## 7. Accounting Dashboard

### 7.1 Dashboard Overview

**Navigation:** Accounting → **Dashboard** (or the summary widget on the main dashboard)

The accounting dashboard provides a real-time financial snapshot.

### 7.2 Key Metrics

**Inventory Value:**

| Category | Value | % of Total |
|----------|-------|------------|
| Raw Materials | $3,128.50 | 54% |
| Work in Process | $450.00 | 8% |
| Finished Goods | $1,755.00 | 30% |
| Packaging | $425.00 | 7% |
| **Total** | **$5,758.50** | **100%** |

**Current Period:**
- Period: February 2026
- Status: Open
- Entries this period: 42

**Activity Metrics:**
- Entries today: 5
- Entries this week: 18
- Entries this month: 42

**Books Status:**
- Balanced: Yes (DR = CR)

### 7.3 Revenue Metrics

**Month-to-Date (MTD):**
- Revenue: $4,250.00 (recognized at shipment)
- Payments Received: $3,800.00
- Outstanding: $450.00

**Year-to-Date (YTD):**
- Revenue: $15,250.00
- Payments Received: $14,100.00
- Outstanding: $1,150.00

### 7.4 Recent Entries

Shows the last 10 journal entries:
- Entry number
- Date
- Description
- Total amount
- Source reference

Click any entry to view full details.

---

## 8. COGS and Gross Margin

### 8.1 Understanding COGS

**Cost of Goods Sold (COGS)** includes only the direct costs of producing items that were shipped:

| Component | Included in COGS? | GL Account |
|-----------|-------------------|------------|
| Material cost | Yes | 5100 |
| Labor cost | Yes | 5000 |
| Packaging cost | Yes | 5000 |
| Shipping to customer | **No** (operating expense) | 5010 |
| Overhead | Depends on setup | 5000 |

**GAAP Rule:** COGS is recognized when goods are **shipped** to the customer, not when produced or ordered.

### 8.2 COGS Summary

**Navigation:** Accounting → **COGS Summary**

**Parameters:**
- Date range (defaults to last 30 days)

**Report Output:**

```
COGS Summary: Feb 1-7, 2026
═══════════════════════════════════════════════
Component                Amount      % of COGS
═══════════════════════════════════════════════
Materials               $1,825.00      67%
Labor                     $580.00      21%
Packaging                 $325.00      12%
───────────────────────────────────────────────
Total COGS              $2,730.00     100%

Revenue                 $4,250.00
Gross Profit            $1,520.00
Gross Margin               35.8%
═══════════════════════════════════════════════
```

### 8.3 Order-Level Cost Breakdown

**Navigation:** Accounting → **Order Cost Breakdown** → Select order

View COGS for a specific sales order:

```
Order: SO-2026-0042
═══════════════════════════════════════════════
Material Cost:          $112.50
  - PLA Black (450 G × 10): $112.50
Labor Cost:              $40.00
  - Print time (2.5 hrs × 10): $40.00
Packaging Cost:           $1.00
  - Poly bags (10 EA): $1.00
───────────────────────────────────────────────
Total COGS:             $153.50

Revenue:                $250.00
Shipping Charged:        $12.00
Tax Collected:           $20.63

Gross Profit:            $96.50
Gross Margin:             38.6%
═══════════════════════════════════════════════
```

**Note:** Shipping charges are operational revenue/expense, not part of COGS.

### 8.4 Monitoring Gross Margin

**Target margins for 3D printing:**

| Product Type | Target Margin | Typical Range |
|-------------|---------------|---------------|
| Standard products | 40-60% | Predictable cost, volume pricing |
| Custom orders | 30-50% | Variable print time, unique designs |
| Rush orders | 50-70% | Premium pricing offsets rush costs |

**If margin drops below target:**
1. Check material costs (vendor price increases?)
2. Review scrap rates (high failure = higher COGS)
3. Analyze labor costs (inefficient operations?)
4. Review pricing (selling too cheap?)

---

## 9. Tax Reporting

### 9.1 Tax Summary

**Navigation:** Accounting → **Tax Summary**

**Parameters:**
- Date range
- Export to CSV option

**Report Output:**

```
Tax Summary: January 2026
═══════════════════════════════════════════════
Taxable Sales:          $12,500.00
Non-Taxable Sales:       $2,750.00
  (Tax-exempt customers)
───────────────────────────────────────────────
Total Sales:            $15,250.00

Tax Collected:
  Sales Tax (8.25%):     $1,031.25

Pending (not yet shipped):
  Taxable Orders:        $3,200.00
  Estimated Tax:           $264.00
═══════════════════════════════════════════════
```

### 9.2 Monthly Tax Breakdown

The tax summary includes a monthly breakdown for quarterly filing:

```
Month        Taxable Sales    Tax Collected
───────────────────────────────────────────
January      $12,500.00       $1,031.25
February      $4,250.00         $350.63
March          (in progress)
───────────────────────────────────────────
Q1 Total     $16,750.00       $1,381.88
```

### 9.3 Tax-Exempt Customers

Customers marked as **Tax Exempt** in their profile are excluded from tax calculations. Their sales appear in the "Non-Taxable Sales" line.

**To mark a customer as tax-exempt:**
1. Navigate to Sales → Customers → Select customer
2. Enable **Tax Exempt**
3. All future orders for this customer skip tax

### 9.4 Tax Configuration

**Navigation:** Settings → Company → Tax

```
Tax Enabled: Yes
Tax Rate: 0.0825 (decimal = 8.25%)
Tax Name: "Sales Tax"
Tax Registration Number: XX-1234567
```

**Important:** The tax rate is a **decimal**, not a percentage. Enter 0.0825, not 8.25.

---

## 10. Revenue and Payments

### 10.1 Revenue Recognition

FilaOps follows **GAAP accrual accounting** for revenue recognition:

- **Revenue is recognized when goods are shipped** (not when ordered or paid)
- The `shipped_at` timestamp on the sales order drives recognition
- Tax is a **liability** (2100 Sales Tax Payable), not revenue

**Example Timeline:**
```
Feb 1: Customer places order (SO-2026-042)      → No revenue
Feb 3: Payment received ($250.00)               → No revenue (deposit)
Feb 5: Production completes                      → No revenue
Feb 7: Order shipped                             → Revenue: $250.00 ✓
```

### 10.2 Sales Journal

**Navigation:** Accounting → **Sales Journal**

**Parameters:**
- Date range
- Export to CSV option

**Shows all shipped orders with financial breakdown:**

```
Sales Journal: February 2026
═══════════════════════════════════════════════════════════════
Order #        Customer        Shipped    Subtotal  Tax     Total
═══════════════════════════════════════════════════════════════
SO-2026-038    Acme Corp      Feb 03     $150.00   $12.38  $162.38
SO-2026-039    Beta LLC       Feb 05     $320.00   $26.40  $346.40
SO-2026-042    Delta Inc      Feb 07     $250.00   $20.63  $270.63
═══════════════════════════════════════════════════════════════
TOTAL                                    $720.00   $59.41  $779.41
```

### 10.3 Payments Journal

**Navigation:** Accounting → **Payments Journal**

**Tracks all completed payments:**

```
Payments Journal: February 2026
═══════════════════════════════════════════════════════════════
Date       Order #        Customer     Method        Amount
═══════════════════════════════════════════════════════════════
Feb 01     SO-2026-038    Acme Corp   Credit Card   $162.38
Feb 03     SO-2026-039    Beta LLC    PayPal        $346.40
Feb 05     SO-2026-042    Delta Inc   Credit Card   $270.63
═══════════════════════════════════════════════════════════════
TOTAL                                               $779.41

By Payment Method:
  Credit Card:    $433.01  (55%)
  PayPal:         $346.40  (45%)
  Manual:           $0.00   (0%)
```

### 10.4 Outstanding Payments

**Dashboard widget shows:**
- Orders shipped but not paid
- Orders with partial payment
- Overdue payments (past due date)

---

## 11. Schedule C Integration

### 11.1 What is Schedule C?

**IRS Schedule C** (Profit or Loss From Business) is the tax form used by sole proprietors to report business income and expenses. FilaOps maps GL accounts to Schedule C lines to simplify tax preparation.

### 11.2 Account Mapping

Each GL account can be mapped to a Schedule C line:

| GL Account | Schedule C Line | Description |
|-----------|----------------|-------------|
| 4000 Sales Revenue | Line 1 | Gross receipts |
| 5000 COGS | Line 4 | Cost of goods sold |
| 5010 Shipping Expense | Line 27a | Other expenses |
| 5020 Scrap Expense | Part III | COGS detail |

### 11.3 Generating Schedule C Report

**Navigation:** Accounting → **Reports** → **Schedule C**

**Output:**
```
Schedule C Summary: Tax Year 2025
═══════════════════════════════════════
Line 1  - Gross Receipts:    $85,000
Line 4  - Cost of Goods Sold: $42,500
Line 5  - Gross Profit:      $42,500
Line 27 - Other Expenses:     $8,500
Line 31 - Net Profit:        $34,000
═══════════════════════════════════════
```

**Use this report** when preparing your annual tax return or handing data to your accountant.

---

## 12. Data Export

### 12.1 Available Exports

| Report | Format | Navigation |
|--------|--------|-----------|
| Sales Journal | CSV | Accounting → Sales Journal → Export |
| Tax Summary | CSV | Accounting → Tax Summary → Export |
| Payments Journal | CSV | Accounting → Payments → Export |
| Trial Balance | Screen | Accounting → GL Reports → Trial Balance |
| Transaction Ledger | Screen | Accounting → GL Reports → Ledger |

### 12.2 Sales Export for Tax

**Navigation:** Accounting → **Export** → **Sales**

Generates a CSV with all shipped sales orders:

```csv
order_number,customer,shipped_date,subtotal,tax,shipping,total
SO-2026-038,Acme Corp,2026-02-03,150.00,12.38,8.00,170.38
SO-2026-039,Beta LLC,2026-02-05,320.00,26.40,12.00,358.40
```

**Useful for:**
- Importing into QuickBooks or other accounting software
- Providing to your accountant at tax time
- Reconciling with bank statements

---

## 13. Common Workflows

### Workflow 1: Month-End Close

```
1. Review Trial Balance
   - Verify books are balanced (DR = CR)
   - Investigate any anomalies

2. Review Inventory Valuation
   - Compare physical to GL balances
   - Resolve any variances

3. Review COGS Summary
   - Verify gross margin is reasonable
   - Check for unusual cost entries

4. Post Draft Entries
   - Find any unposted draft entries
   - Review and post or void them

5. Generate Reports
   - Tax Summary (for quarterly filing)
   - Sales Journal (for records)
   - Payments Journal (reconcile with bank)

6. Close Period
   - Navigate to Periods
   - Close the current month
   - Confirm closure

7. Archive
   - Export reports to CSV for backup
   - File with monthly financial records
```

**Time estimate:** 30-60 minutes

### Workflow 2: Quarterly Tax Filing

```
1. Generate Tax Summary for the quarter
   - Set date range: Q1 (Jan 1 - Mar 31)
   - Note total taxable sales and tax collected

2. Export to CSV
   - Download sales journal CSV
   - Download tax summary CSV

3. Reconcile
   - Compare tax collected to bank deposits
   - Verify payment method totals

4. File
   - Submit quarterly sales tax return
   - Pay tax liability to state/local authority

5. Record Payment (optional manual JE)
   DR 2100 Sales Tax Payable    $1,381.88
      CR 1000 Cash                       $1,381.88
   (Quarterly tax payment)
```

### Workflow 3: Investigating a Variance

```
1. Run Inventory Valuation report
   - Notice: Raw Materials GL = $3,128.50, Physical = $3,078.50
   - Variance: $50.00

2. Check Transaction Ledger for account 1200
   - Review recent entries
   - Look for missing or duplicate entries

3. Cross-reference with Inventory Transactions
   - Compare GL entries to inventory transaction log
   - Find the discrepancy:
     "Manual adjustment of -50 G PLA on Feb 6
      did not create corresponding GL entry"

4. Create correcting entry
   DR 5030 Inventory Adjustment  $1.25
      CR 1200 Raw Materials               $1.25
   (Correct for missing GL entry from inventory adjustment)

5. Post the entry

6. Re-run Inventory Valuation
   - Verify variance is now $0.00
```

### Workflow 4: Year-End Close

```
1. Complete all month-end closes for the year
   - Close Periods 1-12

2. Generate annual reports
   - Full-year Trial Balance
   - Full-year COGS Summary
   - Full-year Tax Summary
   - Schedule C report

3. Reconcile
   - Compare to bank statements
   - Verify all payments accounted for
   - Check for outstanding receivables

4. Export everything
   - Sales Journal (full year)
   - Tax Summary (full year)
   - Payments Journal (full year)

5. Provide to accountant
   - CSV exports
   - Schedule C summary
   - Any notes on unusual transactions

6. Start new fiscal year
   - New periods auto-created
   - Opening balances carry forward
```

---

## 14. Best Practices

### General Accounting

- **Do:** Post entries promptly (don't let drafts accumulate)
- **Do:** Close periods monthly to protect historical data
- **Do:** Review Trial Balance weekly for balance verification
- **Do:** Investigate variances immediately (they get harder to trace over time)
- **Do:** Keep source references on all manual entries

- **Don't:** Leave periods open indefinitely
- **Don't:** Void entries without documenting the reason
- **Don't:** Ignore "books unbalanced" warnings
- **Don't:** Reopen closed periods without good reason

### Inventory Valuation

- **Do:** Run valuation report after each cycle count
- **Do:** Reconcile GL to physical inventory monthly
- **Do:** Create correcting entries for variances

- **Don't:** Adjust inventory without corresponding GL entries
- **Don't:** Ignore small variances (they compound)

### Tax Compliance

- **Do:** Export tax summary quarterly for filing
- **Do:** Keep CSV exports as backup records
- **Do:** Verify tax-exempt customer designations annually
- **Do:** Enter tax rate as a decimal (0.0825), not percentage (8.25)

- **Don't:** Mix up tax rate format (0.0825 vs 8.25)
- **Don't:** Forget to file quarterly returns
- **Don't:** Ignore the difference between tax collected and tax owed

---

## 15. Troubleshooting

### Books Not Balanced

**Symptom:** Trial Balance shows total debits != total credits

**Cause:** A journal entry was posted with unequal debits and credits, or a system error occurred.

**Solution:**
1. Note the variance amount from Trial Balance
2. Use Transaction Ledger to find recent entries
3. Look for entries with only one side (missing DR or CR)
4. Create a correcting entry to balance
5. Investigate root cause (software bug? manual entry error?)

### Inventory Valuation Variance

**Symptom:** Physical inventory value differs from GL balance

**Common Causes:**
- Manual inventory adjustments without GL entries
- Incomplete receiving transactions
- Timing differences between physical count and report
- Inventory that existed before the GL system was implemented

**Solution:**
1. Compare physical count to system on-hand quantities
2. Review recent inventory transactions
3. Check for manual adjustments in the inventory module
4. Create correcting journal entries for true variances
5. Note: Pre-existing inventory (before GL implementation) will always show as variance until a one-time correcting entry is made

### Cannot Post Entry to Closed Period

**Symptom:** "Cannot post to closed period" error

**Solution:**
1. Check Periods tab for period status
2. If you need to post to a closed period:
   - Reopen the period (admin only)
   - Post the entry
   - Re-close the period
3. Or post the entry to the current open period with a note

### COGS Showing $0

**Symptom:** COGS Summary shows zero even though orders were shipped

**Cause:** COGS is calculated from shipped orders only. Check:
- Are orders marked as "shipped"? (not just "completed")
- Do the products have standard_cost set?
- Were production orders properly closed (inventory consumed)?

**Solution:**
1. Verify sales orders have `shipped_at` timestamps
2. Check product cost fields are populated
3. Review production order closing process
4. COGS entries should auto-create when orders ship

### Tax Amount Shows $0

**Symptom:** Orders have no tax calculated

**Cause:**
- Tax not enabled in company settings
- Tax rate set to 0
- Customer marked as tax-exempt

**Solution:**
1. Settings → Company → Tax → Verify enabled and rate set
2. Check customer profile for tax-exempt flag
3. Rate must be decimal: 0.0825 (not 8.25)

---

## 16. Quick Reference

### Transaction Flow Diagram

```
Purchase Receipt:        DR 1200 Raw Materials    → CR 2000 AP
Material to Production:  DR 1210 WIP              → CR 1200 Raw Materials
Finished Goods:          DR 1220 FG Inventory     → CR 1210 WIP
Ship to Customer:        DR 5000 COGS             → CR 1220 FG Inventory
Packaging Used:          DR 5010 Shipping Expense  → CR 1230 Packaging
Scrap:                   DR 5020 Scrap Expense     → CR 1210 WIP
Inventory Adjustment:    DR 5030 Adj Expense       → CR 1200 Raw Materials
```

### Journal Entry Lifecycle

```
draft → posted → (voided if needed)
```

### Fiscal Period Lifecycle

```
open → closed → (reopened if needed) → closed
```

### Key Formulas

**Gross Profit:**
```
Gross Profit = Revenue - COGS
```

**Gross Margin:**
```
Gross Margin = (Gross Profit / Revenue) × 100%
```

**COGS (per order):**
```
COGS = Material Cost + Labor Cost + Packaging Cost
```

**Inventory Value:**
```
Total Value = Sum(On-Hand Qty × Unit Cost) for all items
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/accounting/trial-balance` | GET | Trial Balance report |
| `/api/v1/accounting/inventory-valuation` | GET | Inventory vs GL comparison |
| `/api/v1/accounting/ledger/{account_code}` | GET | Transaction Ledger |
| `/api/v1/accounting/periods` | GET | List fiscal periods |
| `/api/v1/accounting/periods/{id}/close` | POST | Close a period |
| `/api/v1/accounting/periods/{id}/reopen` | POST | Reopen a period |
| `/api/v1/accounting/summary` | GET | Dashboard summary |
| `/api/v1/accounting/recent-entries` | GET | Recent journal entries |
| `/api/v1/admin/accounting/dashboard` | GET | Full accounting dashboard |
| `/api/v1/admin/accounting/cogs-summary` | GET | COGS breakdown |
| `/api/v1/admin/accounting/sales-journal` | GET | Sales transaction journal |
| `/api/v1/admin/accounting/tax-summary` | GET | Tax reporting data |
| `/api/v1/admin/accounting/payments-journal` | GET | Payment tracking |
| `/api/v1/admin/accounting/export/sales` | GET | CSV export for tax |
| `/api/v1/admin/accounting/order-cost-breakdown/{id}` | GET | Per-order COGS |

### Account Type Quick Reference

| Code Range | Type | Normal Balance | Examples |
|-----------|------|---------------|----------|
| 1xxx | Asset | Debit | Cash, Inventory, AR |
| 2xxx | Liability | Credit | AP, Tax Payable |
| 3xxx | Equity | Credit | Owner's Equity |
| 4xxx | Revenue | Credit | Sales, Shipping Revenue |
| 5xxx | Expense | Debit | COGS, Shipping, Scrap |

---

## Related Guides

- **[Getting Started](getting-started.md)** - Initial setup and environment configuration
- **[Inventory Management](inventory-management.md)** - Physical inventory that feeds GL transactions
- **[Manufacturing](manufacturing.md)** - Production costs, COGS, and WIP tracking
- **[Purchasing](purchasing.md)** - Vendor payments and AP entries
- **[Sales & Quotes](sales-and-quotes.md)** - Revenue, tax, and payment tracking
- **[Settings & Admin](settings-and-admin.md)** - Tax rate and fiscal year configuration

---

**Need Help?**
- Consult the [API Reference](../API-REFERENCE.md) for integration details
- Report issues on [GitHub](https://github.com/Blb3D/filaops/issues)
- See [Getting Started](getting-started.md) for initial setup

---

*Last Updated: February 2026 | FilaOps v3.0.0*
