# Inventory Reconciliation

> Keep your system numbers trustworthy — find drift, count the shelf, and anchor the ledger to reality.

## What You'll Learn

- What "drift" and "uncounted" mean in FilaOps
- How to use the Reconciliation report as your counting work queue
- How to record a physical count for a single item
- What "Baseline to stored" does, and when (and when not) to use it
- How reconciliation counts relate to your regular cycle counts

## Prerequisites

- Admin access (the Reconciliation section is staff-only)
- At least one inventory location configured
- Products entered in your catalog

---

## How FilaOps Keeps Inventory Numbers

FilaOps inventory is **ledger-first**: every receipt, consumption, shipment, adjustment,
and count posts a signed transaction to the inventory ledger. The on-hand number you see
on the Items page is the running total of those transactions — it is always backed by
history you can scroll through.

Think of it this way: there is a **sticky note on the shelf** (the on-hand balance you see
on screen) and a **notebook by the door** (the transaction ledger). Every time stock moves,
an entry goes in the notebook and someone updates the sticky note. The system keeps both,
and they are supposed to agree. The **Reconciliation report** is the process of checking
that they still do.

---

## The Reconciliation Report

Navigate to **Inventory > Transactions**, then scroll down to the
**Reconciliation — items needing a count** section and click to expand it.

<!-- TODO: screenshot of the expanded reconciliation section -->

The report loads a table with one row per inventory item. It compares:

| Column | What It Shows |
|--------|---------------|
| **Stored** | The on-hand balance currently stored in FilaOps |
| **Ledger Sum** | What the transaction history actually adds up to for this item's epoch |
| **Drift** | `Stored − Ledger Sum` — how far apart the two numbers are |
| **Baseline** | When this item was last physically counted (or "—" if never) |
| **Status** | **counted** / **uncounted** and drift indicator |

The summary line at the top shows total items, how many are drifted, and how many are uncounted.

### What "Drift" Means

Drift is the gap between what the ledger says you should have and what the system actually
shows on-hand. A non-zero drift means some inventory movement happened outside the normal
transaction flow. Common causes:

- A spool was scrapped and remade but the scrap was never recorded
- A last-minute slicing change added or removed material but the BOM was not updated
- A manual on-hand edit was made directly, bypassing the ledger
- Data was imported from a previous system using a different convention

Drift direction matters:

- **Yellow (positive drift)** — stored is higher than the ledger says (phantom stock —
  you think you have more than the history supports)
- **Red (negative drift)** — stored is lower (material was consumed but not fully recorded)

### What "Uncounted" Means

An item is **uncounted** when it has never had a physical count recorded in FilaOps.
Without a count baseline, the report sums all transactions since the beginning of time.
For items that predate FilaOps or were imported from another system, that history may
use mixed conventions — so the ledger sum is not fully trustworthy until you count once.

**Uncounted items appear at the top of the report** so you can work through them first.

!!! tip "Drifted-only filter"
    Use the **Show drifted items only** checkbox to hide items that are in balance.
    This gives you a focused counting work queue.

---

## Counting an Item

When you find a row that is uncounted or drifted, the **Count** action lets you record
what is physically on the shelf and anchor the ledger to that number.

### How to Record a Count

**Step 1.** Find the item in the Reconciliation table. Click **Count** on that row.

**Step 2.** A dialog opens showing the current stored quantity. It pre-fills the
**Counted quantity** field with the stored value as a starting point.

**Step 3.** Walk to the shelf. Count the physical stock. Enter the number you actually
counted in the **Counted quantity** field.

**Step 4.** Optionally add a **Note** (e.g., "bin A3 shelf count 2026-06-10").

**Step 5.** Click **Post count**.

### What Happens After You Count

FilaOps does three things atomically when you post a count:

1. **Computes the delta** — `counted − stored_at_submit_time`. If your count matches
   what is stored, delta is zero.
2. **Posts a ledger transaction** — A `reconciliation_baseline` transaction is written
   with the signed delta. This is visible in the full transaction history, just like any
   receipt or adjustment. If delta is zero, no transaction is written (nothing changed),
   but the baseline is still stamped.
3. **Stamps the baseline timestamp** — The item is now "counted." From this moment
   forward, the Reconciliation report measures drift only from this count onward.
   Pre-count history is preserved read-only — it is never deleted or recalculated.

After a successful count, the item's row will show drift = 0 and a baseline date of today.

!!! info "Accounting impact"
    Counts with a non-zero delta post a journal entry identical to a cycle-count
    variance: debit Inventory (account 1200) and credit Inventory Adjustment (5030) for
    overages; reverse for shortages. The amount is `|delta| × unit cost`. This keeps
    your books in sync with the physical count, the same way a cycle count does.

---

## "Baseline to Stored" — The Confusing Button

At the top of the Reconciliation section there is an orange button labeled
**Baseline to stored — dev/test only**. Here is exactly what it does and when to use it.

### What It Does

"Baseline to stored" stamps the **current system on-hand as the starting point** for
every inventory row — without you counting anything. It tells FilaOps: "I accept the
numbers in the system right now as correct. Start measuring drift from this moment."

**No adjustment transaction is written.** Nothing changes in the ledger. Only the
baseline timestamp is set, so the report stops treating all items as "uncounted."

### Why the Confirmation is Required

The button asks you to type `BASELINE_TO_STORED` exactly before it will proceed.
That is not bureaucracy — it is a deliberate speed bump. This action:

- Applies to **every inventory row at once** (unless you scope it to one item via the API)
- Cannot be undone by clicking anything — you would need to re-count affected items
- Silently discards the diagnostic value of pre-existing transaction history for the
  drift calculation

If you click it by accident, nothing harmful happens to your stock or your books —
the numbers do not change. But items that had real drift will now look clean, and
you will have missed the opportunity to find and fix the root cause.

### When to Use It

| Situation | Use it? |
|-----------|---------|
| Fresh FilaOps install, data imported from a spreadsheet, you trust the numbers | **Yes** |
| Dev or test database, cleaning up demo data | **Yes** |
| You want to skip counting and just make the report look clean | **No — count instead** |
| Some items show drift after a system upgrade | **No — count the drifted items** |
| Production database with live orders running | **No — count instead** |

The clearest rule: **if you care whether the numbers are actually right, count the
items instead.** "Baseline to stored" is for accepting numbers wholesale when you already
know they are correct (or when correctness does not matter, as in a dev environment).

!!! warning "Production databases"
    Do not use "Baseline to stored" against a production database unless you have
    verified the stored quantities are accurate. It will make drifted items appear clean
    without fixing the underlying variance, masking problems that would show up in your
    books.

### Step by Step

If you have decided "Baseline to stored" is appropriate:

**Step 1.** Click **Baseline to stored — dev/test only**.

**Step 2.** Read the warning in the dialog.

**Step 3.** Type `BASELINE_TO_STORED` exactly in the confirmation field.

**Step 4.** Click **Run baseline**.

**Step 5.** FilaOps reports how many rows were stamped. The table will reload showing
all items as "counted" with drift = 0.

---

## Reconciliation Counts vs. Cycle Counts

FilaOps has two ways to physically count inventory. They post the same kind of
ledger transaction and the same GL entry — they are just triggered from different places
and used for different workflows.

| | Cycle Count | Reconciliation Count |
|---|---|---|
| **Where** | Inventory > Cycle Count page | Inventory > Transactions > Reconciliation section |
| **Scope** | Batch — count many items at once | Single item — targeted correction |
| **Trigger** | Scheduled audit (weekly/monthly) | When you notice a specific item looks wrong |
| **GL entry** | DR Inventory / CR Inventory Adjustment | DR Inventory / CR Inventory Adjustment (same) |
| **Sets baseline** | No | Yes |
| **Best for** | Routine periodic audits | Investigating drift on a specific item |

**Rule of thumb:** run cycle counts on a schedule to keep quantities healthy overall.
Use the Reconciliation report and its Count action when a specific item's number looks
wrong and you want to investigate and fix just that item.

Both approaches anchor your books to physical reality the same way.

---

## Frequently Asked Questions

### Why does an item show huge drift right after an upgrade?

Before the HARD-4a/4b/4c changes, different parts of FilaOps used different sign
conventions when writing inventory transactions — some recorded positive quantities for
both stock-in and stock-out. The Reconciliation report assumes the modern signed
convention. An item whose history was written under the old convention may show
misleading drift numbers.

**Fix:** count the item (or use "Baseline to stored" for dev/test data). Once a
baseline is set, only transactions written after that point are included in the drift
calculation. The old history is preserved but no longer affects the drift math.

### Does counting change my books?

Yes, if the counted quantity differs from what is stored. A count with a non-zero
delta posts a journal entry to account **5030 Inventory Adjustment** — the same
account used by cycle-count variances. If you count 152 when the system shows 140,
the $X variance (12 × unit cost) is debited to Inventory and credited to Inventory
Adjustment. Zero-delta counts (where counted = stored) write no journal entry.

### Can I undo a baseline?

There is no "undo baseline" button. If you set a baseline incorrectly, the remedy is
to **count the item again** — the most recent count always wins. The previous baseline
timestamp is replaced by the new one, and the report starts measuring drift from the
new count forward.

### What does the Ledger Sum column show for an uncounted item?

For an uncounted item (no baseline timestamp), the Ledger Sum is the sum of all
transactions ever recorded for that item, from the beginning of time. If those
transactions used mixed conventions, the number may look wrong. Count the item once
to anchor the history — after that the Ledger Sum only looks at post-baseline
transactions.

### I see an item with drift = 0 but it is still marked "uncounted" — is that a problem?

No, it is fine. It means the transaction history happens to sum to the stored value,
even without a formal count. The "uncounted" label is informational — it means
FilaOps has never had a human physically verify the number. You can leave it or count
it; either is fine depending on how much you trust the history for that item.

---

## What's Next?

- [Tracking Inventory](inventory.md) — transaction types, transfers, and the full
  Transactions page
- [Cycle Counts](inventory.md#cycle-counts) — batch physical audits on a schedule
- [Material Planning (MRP)](mrp.md) — accurate on-hand numbers are the foundation
  of reliable MRP calculations

## Quick Reference

| Task | Where |
|------|-------|
| View the reconciliation report | **Inventory > Transactions** → expand Reconciliation section |
| Filter to drifted items only | Check **Show drifted items only** |
| Count a single item | Click **Count** on the item row |
| Set a baseline without counting | Click **Baseline to stored — dev/test only** (requires typed confirmation) |
| Run a batch cycle count | **Inventory > Cycle Count** |
