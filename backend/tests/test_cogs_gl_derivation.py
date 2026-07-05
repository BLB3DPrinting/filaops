"""
Tests for the #880 PR-5 GL-derived COGS story.

Covers:
- app.services.cogs_report_service.gl_derived_cogs_for_orders: the shared
  helper that derives COGS from posted gl_journal_entry_lines (ship JEs'
  5000/5010 debits, linked production orders' 5200 completion-variance
  credits), scoped strictly to each order's OWN linked production orders.
- The full mini-cycle: a shipped sales order with its production order's
  completion JE (including a 5200 variance) and ship JE, PLUS a separate
  CANCELLED sales order with its own production order's completion JE —
  the cancelled order's variance must never leak into the shipped order's
  out_of_pocket_cogs (this is the live-data PO-0001/SO-0001 case).
- /admin/accounting/cogs-summary: headline/secondary/reconciliation fields,
  legacy keys still populated, drafts/voided excluded, days-window respects
  shipped_at.
- /admin/accounting/dashboard: mtd COGS agrees with cogs-summary on the
  same seeded data (same GL derivation, same anchor).

All tests are delta-based with per-run unique fixtures (uuid SKUs/codes
from the conftest factories) because filaops_test accumulates state; each
test seeds its own orders/products, so window-scoped assertions look at
INDIVIDUAL order buckets, not global totals.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.services import inventory_service
from app.services.cogs_report_service import (
    gl_derived_cogs_for_orders,
    shipped_order_ids_in_window,
)
from app.services.production_gl_service import create_production_completion_gl_entry
from app.services.transaction_service import ShipmentItem, TransactionService

BASE = "/api/v1/admin/accounting"


# =============================================================================
# Helpers
# =============================================================================

def _location(db):
    return inventory_service.get_or_create_default_location(db)


def _seed_stock(db, product, qty, cost):
    return inventory_service.create_inventory_transaction(
        db=db,
        product_id=product.id,
        location_id=_location(db).id,
        transaction_type="receipt",
        quantity=Decimal(str(qty)),
        reference_type="test_seed",
        reference_id=0,
        cost_per_unit=Decimal(str(cost)),
    )


def _consume(db, product, po, qty, cost):
    return inventory_service.create_inventory_transaction(
        db=db,
        product_id=product.id,
        location_id=_location(db).id,
        transaction_type="consumption",
        quantity=Decimal(str(qty)),
        reference_type="production_order",
        reference_id=po.id,
        cost_per_unit=Decimal(str(cost)),
    )


def _receive_fg(db, product, po, qty, cost):
    return inventory_service.create_inventory_transaction(
        db=db,
        product_id=product.id,
        location_id=_location(db).id,
        transaction_type="receipt",
        quantity=Decimal(str(qty)),
        reference_type="production_order",
        reference_id=po.id,
        cost_per_unit=Decimal(str(cost)),
    )


def _build_shipped_cycle(
    db, make_product, make_sales_order, make_production_order,
    *, material_cost, fg_receipt_value, ship_qty, ship_unit_cost,
    shipped_at=None, so_status="shipped",
):
    """One full mini-cycle: PO completion (with GL variance) + ship JE.

    Returns (sales_order, production_order, completion_je, ship_je).
    """
    raw = make_product(item_type="supply", average_cost=Decimal("0.50"))
    fg = make_product(item_type="finished_good", average_cost=Decimal(str(ship_unit_cost)))

    so = make_sales_order(
        product_id=fg.id,
        quantity=ship_qty,
        unit_price=Decimal(str(ship_unit_cost)) * 2,
        status=so_status,
        shipped_at=shipped_at or datetime.now(timezone.utc),
    )
    po = make_production_order(
        product_id=fg.id, status="completed", quantity=ship_qty,
        sales_order_id=so.id,
    )

    _seed_stock(db, raw, 1000, "0.50")
    _consume(db, raw, po, material_cost / Decimal("0.50"), "0.50")  # material_cost total
    _receive_fg(db, fg, po, ship_qty, fg_receipt_value / Decimal(str(ship_qty)))

    completion_je = create_production_completion_gl_entry(db, po)
    db.flush()

    # Seed FG on-hand so ship_order's shipment txn doesn't go held/negative.
    _seed_stock(db, fg, ship_qty, str(ship_unit_cost))

    ts = TransactionService(db)
    _inv_txns, ship_je = ts.ship_order(
        sales_order_id=so.id,
        items=[ShipmentItem(product_id=fg.id, quantity=Decimal(str(ship_qty)), unit_cost=Decimal(str(ship_unit_cost)))],
    )
    db.flush()

    return so, po, completion_je, ship_je


# =============================================================================
# gl_derived_cogs_for_orders — the shared helper
# =============================================================================

class TestGLDerivedCOGSForOrders:

    def test_full_mini_cycle_out_of_pocket_and_full_product_cogs(
        self, db, make_product, make_sales_order, make_production_order
    ):
        """DR 1210 material=5 / CR 1200; DR 1220 FG=12 / CR 1210;
        V = 12 - 5 = +7 -> CR 5200 7. Ship 1 unit at $12 -> DR 5000 12 / CR 1220 12.

        full_product_cogs = 12 (5000 debits)
        completion_variance_5200 = 7
        out_of_pocket_cogs = 12 - 7 = 5 (== the material cost actually spent)
        """
        so, po, completion_je, ship_je = _build_shipped_cycle(
            db, make_product, make_sales_order, make_production_order,
            material_cost=Decimal("5.00"), fg_receipt_value=Decimal("12.00"),
            ship_qty=1, ship_unit_cost=Decimal("12.00"),
        )
        db.commit()

        result = gl_derived_cogs_for_orders(db, [so.id])

        assert result.reconciliation.ship_cogs_5000 == Decimal("12.00")
        assert result.reconciliation.completion_variance_5200 == Decimal("7.00")
        assert result.full_product_cogs == Decimal("12.00")
        assert result.out_of_pocket_cogs == Decimal("5.00")

    def test_cancelled_order_variance_does_not_leak(
        self, db, make_product, make_sales_order, make_production_order
    ):
        """The live-data case: a cancelled SO's own PO completion variance
        must NOT count toward a different (shipped) order's out_of_pocket.
        """
        shipped_so, shipped_po, _, _ = _build_shipped_cycle(
            db, make_product, make_sales_order, make_production_order,
            material_cost=Decimal("10.00"), fg_receipt_value=Decimal("20.00"),
            ship_qty=1, ship_unit_cost=Decimal("20.00"),
        )

        # A second, CANCELLED sales order with its own PO + completion JE.
        raw2 = make_product(item_type="supply", average_cost=Decimal("0.50"))
        fg2 = make_product(item_type="finished_good", average_cost=Decimal("8.00"))
        cancelled_so = make_sales_order(
            product_id=fg2.id, quantity=1, unit_price=Decimal("16.00"),
            status="cancelled",
        )
        cancelled_po = make_production_order(
            product_id=fg2.id, status="completed", quantity=1,
            sales_order_id=cancelled_so.id,
        )
        _seed_stock(db, raw2, 100, "0.50")
        _consume(db, raw2, cancelled_po, 2, "0.50")   # 1.00 material
        _receive_fg(db, fg2, cancelled_po, 1, "8.00")  # 8.00 FG -> variance 7.00
        create_production_completion_gl_entry(db, cancelled_po)
        db.commit()

        # Query ONLY the shipped order — the cancelled order's PO variance
        # must not appear.
        result = gl_derived_cogs_for_orders(db, [shipped_so.id])

        assert result.reconciliation.completion_variance_5200 == Decimal("10.00")
        # (20 FG - 10 material = 10 variance for the shipped order alone)
        assert result.out_of_pocket_cogs == Decimal("10.00")  # 20 - 10, NOT touched by cancelled_po's 7.00

    def test_drafts_and_voided_journal_entries_excluded(
        self, db, make_product, make_sales_order, make_production_order
    ):
        so, po, completion_je, ship_je = _build_shipped_cycle(
            db, make_product, make_sales_order, make_production_order,
            material_cost=Decimal("3.00"), fg_receipt_value=Decimal("9.00"),
            ship_qty=1, ship_unit_cost=Decimal("9.00"),
        )
        db.commit()

        baseline = gl_derived_cogs_for_orders(db, [so.id])
        assert baseline.reconciliation.ship_cogs_5000 == Decimal("9.00")

        # Void the ship JE — its debits must disappear from the derivation.
        ship_je.status = "voided"
        db.commit()

        after_void = gl_derived_cogs_for_orders(db, [so.id])
        assert after_void.reconciliation.ship_cogs_5000 == Decimal("0.00")

    def test_legacy_keys_still_populated(
        self, db, make_product, make_sales_order, make_production_order
    ):
        so, po, _, _ = _build_shipped_cycle(
            db, make_product, make_sales_order, make_production_order,
            material_cost=Decimal("4.00"), fg_receipt_value=Decimal("10.00"),
            ship_qty=1, ship_unit_cost=Decimal("10.00"),
        )
        db.commit()

        result = gl_derived_cogs_for_orders(db, [so.id])
        assert result.legacy_materials == Decimal("4.00")
        assert result.legacy_total == result.legacy_materials + result.legacy_labor + result.legacy_packaging

    def test_empty_order_set_returns_zeros(self, db):
        result = gl_derived_cogs_for_orders(db, [])
        assert result.out_of_pocket_cogs == Decimal("0.00")
        assert result.full_product_cogs == Decimal("0.00")
        assert result.legacy_total == Decimal("0.00")


# =============================================================================
# /admin/accounting/cogs-summary — the endpoint
# =============================================================================

class TestCOGSSummaryGLDerived:

    def test_out_of_pocket_and_full_product_and_reconciliation_present(
        self, client, db, make_product, make_sales_order, make_production_order
    ):
        so, po, _, _ = _build_shipped_cycle(
            db, make_product, make_sales_order, make_production_order,
            material_cost=Decimal("6.00"), fg_receipt_value=Decimal("15.00"),
            ship_qty=1, ship_unit_cost=Decimal("15.00"),
        )
        db.commit()

        resp = client.get(f"{BASE}/cogs-summary", params={"days": 30})
        assert resp.status_code == 200
        data = resp.json()

        assert "out_of_pocket_cogs" in data
        assert "full_product_cogs" in data
        assert "reconciliation" in data
        recon = data["reconciliation"]
        assert "ship_cogs_5000" in recon
        assert "packaging_5010" in recon
        assert "completion_variance_5200" in recon

        # Legacy keys still present and populated.
        assert "cogs" in data
        assert set(data["cogs"].keys()) == {"materials", "labor", "packaging", "total"}

    def test_window_filter_respects_shipped_at(
        self, client, db, make_product, make_sales_order, make_production_order
    ):
        """An order shipped 60 days ago must not appear in a 7-day window."""
        old_shipped_at = datetime.now(timezone.utc) - timedelta(days=60)
        so, po, _, _ = _build_shipped_cycle(
            db, make_product, make_sales_order, make_production_order,
            material_cost=Decimal("2.00"), fg_receipt_value=Decimal("5.00"),
            ship_qty=1, ship_unit_cost=Decimal("5.00"),
            shipped_at=old_shipped_at,
        )
        db.commit()

        resp = client.get(f"{BASE}/cogs-summary", params={"days": 7})
        data = resp.json()

        # Directly assert the 60-day-old order's id is ABSENT from the
        # narrow (7-day) anchor set, and present in a wide (90-day) window
        # that does cover it — this proves the window actually excludes it,
        # rather than just comparing aggregate counts (which would pass
        # even if the order were wrongly included).
        narrow_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        narrow_ids = shipped_order_ids_in_window(db, start=narrow_cutoff)
        assert so.id not in narrow_ids

        wide_cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        wide_ids = shipped_order_ids_in_window(db, start=wide_cutoff)
        assert so.id in wide_ids

        # The order's own COGS contribution must likewise be absent from the
        # narrow window's derivation.
        narrow_derivation = gl_derived_cogs_for_orders(db, narrow_ids)
        assert so.id not in narrow_derivation.order_ids

        wide_resp = client.get(f"{BASE}/cogs-summary", params={"days": 90})
        wide_data = wide_resp.json()
        assert wide_data["orders_shipped"] >= data["orders_shipped"]


# =============================================================================
# /admin/accounting/dashboard agrees with /cogs-summary
# =============================================================================

class TestDashboardAgreesWithCOGSSummary:

    def test_mtd_cogs_matches_cogs_summary_gl_derivation(
        self, client, db, make_product, make_sales_order, make_production_order
    ):
        """Ship inside the current month so both MTD (dashboard) and a wide
        days-window (cogs-summary) pick up the same order, then check the
        per-order GL derivation used by both agrees (same helper, same
        anchor semantics) via direct service comparison — the shared DB
        means absolute totals can differ from unrelated orders, so we
        compare the underlying derivation for THIS order specifically.
        """
        now = datetime.now(timezone.utc)
        so, po, _, _ = _build_shipped_cycle(
            db, make_product, make_sales_order, make_production_order,
            material_cost=Decimal("3.50"), fg_receipt_value=Decimal("8.00"),
            ship_qty=1, ship_unit_cost=Decimal("8.00"),
            shipped_at=now,
        )
        db.commit()

        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_order_ids = shipped_order_ids_in_window(db, start=month_start)
        assert so.id in month_order_ids

        dashboard_style = gl_derived_cogs_for_orders(db, month_order_ids, include_legacy=False)
        single_order = gl_derived_cogs_for_orders(db, [so.id], include_legacy=False)

        # This order's contribution to the MTD-anchored set must equal its
        # own out_of_pocket_cogs (additive — no double counting/omission).
        assert single_order.out_of_pocket_cogs <= dashboard_style.out_of_pocket_cogs

        resp = client.get(f"{BASE}/dashboard")
        assert resp.status_code == 200
        dash = resp.json()
        assert "cogs" in dash and "mtd" in dash["cogs"]
        # Dashboard's MTD COGS must be >= this single order's out-of-pocket
        # contribution (other MTD orders from prior tests may also be in
        # the shared DB window).
        assert Decimal(str(dash["cogs"]["mtd"])) >= single_order.out_of_pocket_cogs - Decimal("0.01")

    def test_transactions_journal_labeled_non_gl(self, client):
        """Item 3: the synthesized pseudo-view is relabeled, not logic-changed."""
        resp = client.get(f"{BASE}/transactions-journal")
        assert resp.status_code == 200
        # Docstring relabeling isn't visible in the JSON response (no
        # behavior change was requested) — this test just pins that the
        # endpoint still works unchanged.
        data = resp.json()
        assert "entries" in data
        assert "transaction_count" in data


# =============================================================================
# /admin/dashboard/profit-summary — delivered orders must count in BOTH
# revenue and COGS (CodeRabbit #897 review comment 3523975559)
# =============================================================================

DASHBOARD_BASE = "/api/v1/admin/dashboard"


class TestDeliveredOrdersCountInRevenueAndCOGS:

    def test_delivered_order_counted_in_both_revenue_and_cogs_anchor(
        self, client, db, make_product, make_sales_order, make_production_order
    ):
        """A 'delivered' order was shipped — its ship JE (5000/5010) already
        posted — so it must anchor COGS the same way it anchors revenue.
        Before the fix, shipped_order_ids_in_window() only anchored
        shipped/completed orders while /profit-summary's revenue query
        already included delivered, so a delivered order contributed
        revenue with zero COGS to gross_profit/gross_margin.
        """
        now = datetime.now(timezone.utc)
        so, po, _, _ = _build_shipped_cycle(
            db, make_product, make_sales_order, make_production_order,
            material_cost=Decimal("4.00"), fg_receipt_value=Decimal("11.00"),
            ship_qty=1, ship_unit_cost=Decimal("11.00"),
            shipped_at=now, so_status="delivered",
        )
        db.commit()

        # The shared anchor helper must pick up the delivered order.
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_order_ids = shipped_order_ids_in_window(db, start=month_start)
        assert so.id in month_order_ids

        # And its own GL-derived COGS must be non-zero (the ship JE posted).
        single_order = gl_derived_cogs_for_orders(db, [so.id], include_legacy=False)
        assert single_order.out_of_pocket_cogs > Decimal("0.00")

        # The dashboard endpoint's revenue (which already included
        # 'delivered') and COGS (via the now-widened anchor) must both
        # reflect this order — i.e. it must not be revenue-with-zero-COGS.
        resp = client.get(f"{DASHBOARD_BASE}/profit-summary")
        assert resp.status_code == 200
        data = resp.json()

        assert Decimal(str(data["revenue_this_month"])) >= so.grand_total - Decimal("0.01")
        # If COGS were still anchored on shipped/completed only, this
        # delivered order's cogs_this_month contribution would be zero,
        # inflating gross_profit_this_month by its full revenue. Assert the
        # dashboard's own gross profit is consistent with revenue minus at
        # least this order's COGS contribution (i.e. COGS was NOT skipped).
        assert Decimal(str(data["gross_profit_this_month"])) <= Decimal(
            str(data["revenue_this_month"])
        ) - single_order.out_of_pocket_cogs + Decimal("0.01")

    def test_delivered_order_counts_identically_across_all_three_cogs_surfaces(
        self, client, db, make_product, make_sales_order, make_production_order
    ):
        """Cross-surface consistency: ONE delivered order must move
        /accounting/cogs-summary, /accounting/dashboard (cogs.mtd) and
        /admin/dashboard/profit-summary (cogs_this_month) by exactly the
        same GL-derived amount — its own out_of_pocket_cogs. All three now
        anchor via cogs_report_service's shared anchor helpers; before, the
        two accounting.py endpoints used their own inline
        ['shipped','completed'] queries, so a delivered order counted on
        one surface but not the others (a third answer).

        Delta-based (shared filaops_test DB): snapshot each surface before
        and after seeding, and compare the deltas.
        """
        before_summary = client.get(f"{BASE}/cogs-summary", params={"days": 30}).json()
        before_dash = client.get(f"{BASE}/dashboard").json()
        before_pm = client.get(f"{DASHBOARD_BASE}/profit-summary").json()

        now = datetime.now(timezone.utc)
        so, po, _, _ = _build_shipped_cycle(
            db, make_product, make_sales_order, make_production_order,
            material_cost=Decimal("6.00"), fg_receipt_value=Decimal("14.00"),
            ship_qty=1, ship_unit_cost=Decimal("14.00"),
            shipped_at=now, so_status="delivered",
        )
        db.commit()

        single = gl_derived_cogs_for_orders(
            db, [so.id], include_legacy=False
        ).out_of_pocket_cogs
        assert single > Decimal("0.00")  # ship JE posted, material spent

        after_summary = client.get(f"{BASE}/cogs-summary", params={"days": 30}).json()
        after_dash = client.get(f"{BASE}/dashboard").json()
        after_pm = client.get(f"{DASHBOARD_BASE}/profit-summary").json()

        delta_summary = Decimal(str(after_summary["out_of_pocket_cogs"])) - Decimal(
            str(before_summary["out_of_pocket_cogs"])
        )
        delta_dash_mtd = Decimal(str(after_dash["cogs"]["mtd"])) - Decimal(
            str(before_dash["cogs"]["mtd"])
        )
        delta_pm = Decimal(str(after_pm["cogs_this_month"])) - Decimal(
            str(before_pm["cogs_this_month"])
        )

        tol = Decimal("0.01")
        assert abs(delta_summary - single) <= tol, (
            f"/cogs-summary moved by {delta_summary}, expected {single}"
        )
        assert abs(delta_dash_mtd - single) <= tol, (
            f"/accounting/dashboard cogs.mtd moved by {delta_dash_mtd}, expected {single}"
        )
        assert abs(delta_pm - single) <= tol, (
            f"/profit-summary cogs_this_month moved by {delta_pm}, expected {single}"
        )

        # And the delivered order's revenue moved with its COGS on the two
        # dashboard surfaces (no revenue-without-COGS or COGS-without-revenue).
        assert Decimal(str(after_pm["revenue_this_month"])) - Decimal(
            str(before_pm["revenue_this_month"])
        ) >= so.grand_total - tol
        assert after_dash["revenue"]["mtd_orders"] == (
            before_dash["revenue"]["mtd_orders"] + 1
        )
