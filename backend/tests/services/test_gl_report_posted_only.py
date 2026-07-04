"""
Tests for GL report posted-only semantics (#880 PR-1).

Covers:
- get_trial_balance: draft/voided entries excluded; zero-activity accounts
  (including draft-only accounts) still listed; include_unposted=True restores
  the old include-everything behavior
- get_transaction_ledger: draft/voided entries excluded from the transaction
  list AND the opening balance; include_unposted=True restores old behavior

Deltas are measured against a pre-snapshot so accumulated data from other
tests/runs cannot skew the assertions.
"""
import uuid
from datetime import date
from decimal import Decimal

from app.models.accounting import GLAccount, GLJournalEntry, GLJournalEntryLine
from app.services import accounting_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _make_journal_entry(db, *, entry_date, status, lines):
    """Create a GLJournalEntry with lines.

    ``lines`` is a list of dicts: {"account_id": int, "debit": Decimal, "credit": Decimal}.
    """
    entry = GLJournalEntry(
        entry_number=f"JE-T-{_uid()}",
        entry_date=entry_date,
        description=f"Posted-only test JE ({status})",
        status=status,
    )
    db.add(entry)
    db.flush()

    for i, line in enumerate(lines):
        db.add(GLJournalEntryLine(
            journal_entry_id=entry.id,
            account_id=line["account_id"],
            debit_amount=line.get("debit", Decimal("0")),
            credit_amount=line.get("credit", Decimal("0")),
            line_order=i,
        ))
    db.flush()
    return entry


def _get_account(db, code: str) -> GLAccount:
    """Fetch a seeded GL account by code."""
    acct = db.query(GLAccount).filter(GLAccount.account_code == code).first()
    assert acct is not None, f"Seed account {code} missing"
    return acct


def _make_status_trio(db, *, cash_id, revenue_id, entry_date):
    """Create one posted (100), one draft (999), and one voided (555) JE."""
    for status, amount in (
        ("posted", Decimal("100")),
        ("draft", Decimal("999")),
        ("voided", Decimal("555")),
    ):
        _make_journal_entry(db, entry_date=entry_date, status=status, lines=[
            {"account_id": cash_id, "debit": amount, "credit": Decimal("0")},
            {"account_id": revenue_id, "debit": Decimal("0"), "credit": amount},
        ])


def _tb_account(result, code):
    return next(
        (a for a in result["accounts"] if a["account_code"] == code), None,
    )


def _tb_debit_balance(result, code) -> Decimal:
    row = _tb_account(result, code)
    return row["debit_balance"] if row else Decimal("0")


# ===========================================================================
# get_trial_balance — posted-only
# ===========================================================================


class TestTrialBalancePostedOnly:
    """Draft and voided journal entries must not move trial balance figures."""

    def test_draft_and_voided_excluded(self, db):
        cash = _get_account(db, "1000")
        revenue = _get_account(db, "4000")
        as_of = date(2060, 1, 31)

        before = accounting_service.get_trial_balance(db, as_of_date=as_of)
        before_cash = _tb_debit_balance(before, "1000")

        _make_status_trio(
            db, cash_id=cash.id, revenue_id=revenue.id, entry_date=date(2060, 1, 15),
        )

        after = accounting_service.get_trial_balance(db, as_of_date=as_of)
        after_cash = _tb_debit_balance(after, "1000")

        # Only the posted 100 counts — not the draft 999 or the voided 555
        assert after_cash - before_cash == Decimal("100")
        assert after["is_balanced"] is True

    def test_include_unposted_restores_old_behavior(self, db):
        cash = _get_account(db, "1000")
        revenue = _get_account(db, "4000")
        as_of = date(2060, 2, 28)

        before = accounting_service.get_trial_balance(
            db, as_of_date=as_of, include_unposted=True,
        )
        before_cash = _tb_debit_balance(before, "1000")

        _make_status_trio(
            db, cash_id=cash.id, revenue_id=revenue.id, entry_date=date(2060, 2, 15),
        )

        after = accounting_service.get_trial_balance(
            db, as_of_date=as_of, include_unposted=True,
        )
        after_cash = _tb_debit_balance(after, "1000")

        # Old behavior: every entry counts regardless of status
        assert after_cash - before_cash == Decimal("100") + Decimal("999") + Decimal("555")

    def test_zero_activity_account_still_listed(self, db):
        """The outerjoin must keep no-entry accounts in the trial balance."""
        code = f"ZT-{_uid()}"  # unique, cannot collide with seeded numeric codes
        acct = GLAccount(
            account_code=code,
            name=f"Zero Activity Test {code}",
            account_type="asset",
        )
        db.add(acct)
        db.flush()

        result = accounting_service.get_trial_balance(
            db, include_zero_balances=True,
        )
        row = _tb_account(result, code)
        assert row is not None
        assert row["debit_balance"] == Decimal("0")
        assert row["credit_balance"] == Decimal("0")

    def test_draft_only_account_still_listed_with_zero_balance(self, db):
        """An account whose ONLY activity is a draft JE must still appear
        (with zero balance) — the status filter lives in the case(), not a
        WHERE clause, so it must not drop the account row entirely."""
        code = f"ZD-{_uid()}"
        acct = GLAccount(
            account_code=code,
            name=f"Draft Only Test {code}",
            account_type="asset",
        )
        db.add(acct)
        db.flush()

        cash = _get_account(db, "1000")
        _make_journal_entry(db, entry_date=date(2060, 3, 15), status="draft", lines=[
            {"account_id": acct.id, "debit": Decimal("42"), "credit": Decimal("0")},
            {"account_id": cash.id, "debit": Decimal("0"), "credit": Decimal("42")},
        ])

        result = accounting_service.get_trial_balance(
            db, as_of_date=date(2060, 3, 31), include_zero_balances=True,
        )
        row = _tb_account(result, code)
        assert row is not None
        assert row["debit_balance"] == Decimal("0")
        assert row["credit_balance"] == Decimal("0")


# ===========================================================================
# get_transaction_ledger — posted-only
# ===========================================================================


class TestTransactionLedgerPostedOnly:
    """Draft and voided journal entries must not appear in the ledger."""

    def test_draft_and_voided_excluded_from_transactions(self, db):
        cash = _get_account(db, "1000")
        revenue = _get_account(db, "4000")

        _make_status_trio(
            db, cash_id=cash.id, revenue_id=revenue.id, entry_date=date(2061, 3, 15),
        )

        result = accounting_service.get_transaction_ledger(
            db, "1000",
            start_date=date(2061, 3, 1),
            end_date=date(2061, 3, 31),
        )
        debits = [t["debit"] for t in result["transactions"]]
        assert Decimal("100") in debits
        assert Decimal("999") not in debits
        assert Decimal("555") not in debits
        assert result["total_debits"] == Decimal("100")
        assert result["transaction_count"] == 1

    def test_opening_balance_excludes_draft_and_voided(self, db):
        cash = _get_account(db, "1000")
        revenue = _get_account(db, "4000")
        window = dict(start_date=date(2062, 2, 1), end_date=date(2062, 2, 28))

        before = accounting_service.get_transaction_ledger(db, "1000", **window)

        # All three entries fall BEFORE the queried window
        _make_status_trio(
            db, cash_id=cash.id, revenue_id=revenue.id, entry_date=date(2062, 1, 10),
        )

        after = accounting_service.get_transaction_ledger(db, "1000", **window)
        # Only the posted 100 rolls into the opening balance
        assert after["opening_balance"] - before["opening_balance"] == Decimal("100")

    def test_include_unposted_restores_old_behavior(self, db):
        cash = _get_account(db, "1000")
        revenue = _get_account(db, "4000")

        _make_status_trio(
            db, cash_id=cash.id, revenue_id=revenue.id, entry_date=date(2063, 5, 15),
        )

        result = accounting_service.get_transaction_ledger(
            db, "1000",
            start_date=date(2063, 5, 1),
            end_date=date(2063, 5, 31),
            include_unposted=True,
        )
        debits = [t["debit"] for t in result["transactions"]]
        assert Decimal("100") in debits
        assert Decimal("999") in debits
        assert Decimal("555") in debits
        assert result["total_debits"] == Decimal("100") + Decimal("999") + Decimal("555")
        assert result["transaction_count"] == 3

    def test_include_unposted_opening_balance(self, db):
        cash = _get_account(db, "1000")
        revenue = _get_account(db, "4000")
        window = dict(start_date=date(2064, 2, 1), end_date=date(2064, 2, 28))

        before = accounting_service.get_transaction_ledger(
            db, "1000", include_unposted=True, **window,
        )

        _make_status_trio(
            db, cash_id=cash.id, revenue_id=revenue.id, entry_date=date(2064, 1, 10),
        )

        after = accounting_service.get_transaction_ledger(
            db, "1000", include_unposted=True, **window,
        )
        assert after["opening_balance"] - before["opening_balance"] == (
            Decimal("100") + Decimal("999") + Decimal("555")
        )
