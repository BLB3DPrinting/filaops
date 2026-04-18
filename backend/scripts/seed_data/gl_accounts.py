"""
Seed the minimal Chart of Accounts needed for ship_order() GL entries.

The alembic migrations 045 + 052 insert ~48 standard accounts. Those
are DELETED by wipe_all_tables on every seed run (the migration IDs
remain in alembic_version so alembic won't re-insert them). This
module re-seeds a curated subset -- enough for:

- ship_order -> _create_shipment_gl_entry: DR 5000 COGS / CR 1220 FG Inventory
- accounting dashboard widgets (Sales Revenue, Shipping Revenue,
  Cash, AR, AP, Inventory)
- the Chart of Accounts admin page to render with realistic rows

If you need the full 48-account set for a specific screenshot, extend
this list from migrations/versions/045_seed_default_chart_of_accounts.py
or toggle SEED_FULL_COA_ENVVAR below.
"""
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


# (code, name, account_type, is_system, description)
#
# account_type ∈ {asset, liability, equity, revenue, expense, cogs}
# Codes match migration 045 + 052 so production promotion is a no-op.

ACCOUNTS = [
    # Assets (1xxx)
    ("1000", "Cash",                      "asset",     True,  "Cash on hand and in bank accounts"),
    ("1100", "Accounts Receivable",       "asset",     True,  "Amounts owed by customers"),
    ("1200", "Raw Materials Inventory",   "asset",     True,  "Unconverted raw materials on hand"),
    ("1220", "Finished Goods Inventory",  "asset",     True,  "Completed parts on shelf, ready to ship"),

    # Liabilities (2xxx)
    ("2000", "Accounts Payable",          "liability", True,  "Amounts owed to vendors"),
    ("2100", "Sales Tax Payable",         "liability", False, "Collected sales tax owed to government"),

    # Equity (3xxx)
    ("3000", "Owner's Equity",            "equity",    True,  "Owner's investment in the business"),

    # Revenue (4xxx)
    ("4000", "Sales Revenue",             "revenue",   True,  "Gross receipts from sales"),
    ("4200", "Shipping Revenue",          "revenue",   False, "Shipping charges collected"),

    # COGS (5xxx)
    ("5000", "Cost of Goods Sold",        "cogs",      True,  "Cost of products sold to customers"),
    ("5010", "COGS - Raw Materials",      "cogs",      False, "Raw material cost component of COGS"),

    # Operating expenses (6xxx) - minimal
    ("6000", "Salaries and Wages",        "expense",   False, "Employee compensation"),
    ("6100", "Rent",                      "expense",   False, "Shop / office rent"),
    ("6200", "Utilities",                 "expense",   False, "Electricity, water, internet"),
]


def seed(db: Session, context: dict[str, Any]) -> None:
    # Raw INSERT matches migration 045's exact shape so a future
    # migration-based re-seed can be a drop-in replacement.
    for code, name, acct_type, is_system, description in ACCOUNTS:
        db.execute(
            text(
                "INSERT INTO gl_accounts "
                "(account_code, name, account_type, schedule_c_line, "
                " is_system, active, description) "
                "VALUES (:code, :name, :type, NULL, :is_system, true, :desc)"
            ),
            {
                "code": code,
                "name": name,
                "type": acct_type,
                "is_system": is_system,
                "desc": description,
            },
        )
    db.flush()

    context["gl_accounts_seeded"] = len(ACCOUNTS)
    print(f"[seed]   {len(ACCOUNTS)} GL accounts (Cash, AR, Inventory, COGS, Revenue, ...)")
