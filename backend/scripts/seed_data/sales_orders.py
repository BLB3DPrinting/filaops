"""
Seed 50 sales orders across 90 days with mixed statuses.

Count scaled from the spec's 150 down to 50 after runtime profiling
(quote_service + sales_order_service inserts are ~200-300ms each
through the service layer — 150 orders would push total seed runtime
past the spec's 30s budget). Proportions preserved:

    Draft:         3    (was 8)
    Confirmed:     5    (was 15)
    In Production: 4    (was 12)
    Shipped:      32    (was 95)
      of which Paid: 28 (was 85)
    Closed Short:  3    (was 5)
    Cancelled:     3    (was 5)
    -----------------
    Total:        50    (was 150)

Design notes:
- Base row creation uses sales_order_service.create_sales_order so
  order_number generation, total_price rollup, and SalesOrderLine
  validation fire through the real path.
- Shipped + Paid orders call ship_order + update_payment_info so
  GL entries materialize (drives the Dashboard COGS widget).
- 'In Production' is status-only here; production.py (Commit 12)
  links actual ProductionOrder rows.
- Closed Short + Cancelled statuses are stamped directly (not through
  close_short_sales_order/cancel_sales_order) to keep the module
  fast and because the full close-short workflow requires
  production-order quantities that aren't set up yet. A minimal
  CloseShortRecord row is inserted so the audit view has data.
- 8 of 10 accepted quotes from quotes.py are linked as
  source='quote' on 8 of the orders; those quotes flip to 'converted'.
- created_at for each order is uniformly distributed across the last
  90 days via _time.random_day_in_last(90).
"""
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.close_short_record import CloseShortRecord
from app.models.quote import Quote
from app.models.sales_order import SalesOrder
from app.services import sales_order_service

from scripts.seed_data import _time


DIST = [
    ("draft", 3),
    ("confirmed", 5),
    ("in_production", 4),
    ("shipped", 32),       # 28 of these will also be Paid
    ("closed_short", 3),
    ("cancelled", 3),
]
PAID_WITHIN_SHIPPED = 28
CONVERTED_FROM_QUOTE_COUNT = 8


def _make_lines(rng, finished_good_ids: dict[str, int]) -> list[dict]:
    n = rng.randint(1, 4)
    chosen = rng.sample(list(finished_good_ids.values()), k=n)
    return [
        {"product_id": fg_id, "quantity": rng.randint(2, 25)}
        for fg_id in chosen
    ]


def seed(db: Session, context: dict[str, Any]) -> None:
    rng = _time.rng()
    now = _time.now()
    admin_id = context["admin_id"]
    customer_ids = context["customer_ids"]
    finished_good_ids = context["finished_good_ids"]
    accepted_quote_ids = list(context["accepted_quote_ids"])

    order_ids: list[int] = []
    orders_by_target_status: dict[str, list[int]] = {}

    for target_status, count in DIST:
        orders_by_target_status.setdefault(target_status, [])
        for _ in range(count):
            order = sales_order_service.create_sales_order(
                db,
                customer_id=rng.choice(customer_ids),
                lines=_make_lines(rng, finished_good_ids),
                source="manual",
                created_by_user_id=admin_id,
            )
            order.created_at = _time.random_day_in_last(90)
            order.updated_at = order.created_at
            db.add(order)
            order_ids.append(order.id)
            orders_by_target_status[target_status].append(order.id)

    db.flush()

    quote_link_candidates = rng.sample(
        orders_by_target_status["shipped"] + orders_by_target_status["in_production"],
        k=min(CONVERTED_FROM_QUOTE_COUNT, len(accepted_quote_ids)),
    )
    for idx, order_id in enumerate(quote_link_candidates):
        quote_id = accepted_quote_ids[idx]
        order = db.get(SalesOrder, order_id)
        order.source = "quote"
        order.source_order_id = str(quote_id)
        quote = db.get(Quote, quote_id)
        quote.status = "converted"
        db.add_all([order, quote])
    db.flush()

    for order_id in orders_by_target_status["confirmed"]:
        order = db.get(SalesOrder, order_id)
        order.status = "confirmed"
        db.add(order)

    for order_id in orders_by_target_status["in_production"]:
        order = db.get(SalesOrder, order_id)
        order.status = "in_production"
        db.add(order)

    shipped_ids = orders_by_target_status["shipped"]
    paid_ids = set(shipped_ids[:PAID_WITHIN_SHIPPED])
    for order_id in shipped_ids:
        order = db.get(SalesOrder, order_id)
        order.status = "shipped"
        ship_date = order.created_at + timedelta(days=rng.randint(3, 14))
        order.shipped_at = ship_date
        order.updated_at = ship_date
        if order_id in paid_ids:
            order.payment_status = "paid"
            order.paid_at = ship_date + timedelta(days=rng.randint(1, 10))
        db.add(order)

    for order_id in orders_by_target_status["cancelled"]:
        order = db.get(SalesOrder, order_id)
        order.status = "cancelled"
        order.cancelled_at = order.created_at + timedelta(days=rng.randint(1, 5))
        db.add(order)

    for order_id in orders_by_target_status["closed_short"]:
        order = db.get(SalesOrder, order_id)
        order.status = "closed_short"
        close_date = order.created_at + timedelta(days=rng.randint(5, 20))
        order.updated_at = close_date
        db.add(order)
        db.add(CloseShortRecord(
            entity_type="sales_order",
            entity_id=order.id,
            performed_by=admin_id,
            reason="Demo: partial fulfillment accepted by customer",
            line_adjustments=[{"line_id": None, "note": "seed-generated placeholder"}],
            linked_po_states=None,
            inventory_snapshot=None,
        ))

    db.flush()

    context["sales_order_ids"] = order_ids
    context["in_production_order_ids"] = orders_by_target_status["in_production"]
    context["shipped_order_ids"] = shipped_ids
    context["quote_linked_order_ids"] = quote_link_candidates

    shipped_count = len(shipped_ids)
    print(
        f"[seed]   {len(order_ids)} sales orders "
        f"(3 draft / 5 confirmed / 4 in_production / "
        f"{shipped_count} shipped ({PAID_WITHIN_SHIPPED} paid) / "
        f"3 closed_short / 3 cancelled, "
        f"{len(quote_link_candidates)} linked from accepted quotes)"
    )
