"""
Seed 20 quotes across mixed statuses.

Spec distribution:
- 10 Accepted  (status='accepted')
- 5 Sent       (status='pending' — default for newly-created manual quotes)
- 3 Rejected   (status='rejected')
- 2 Draft      (no 'draft' state in Core — mapped to status='pending' with
                recent created_at + a 'DRAFT:' admin note. See SKIPPED.md.)

Each quote has 1-3 line items drawn from the finished-goods catalog,
created via quote_service.create_quote (ManualQuoteCreate payload) so
quote-number generation, discount application, and tax resolution fire
through the real code path.

Conversion-from-quote linkage (spec: 8 of the 10 Accepted should appear
as 'Converted From' on sales orders) is handled in sales_orders.py,
not here. That module picks 8 of the 10 accepted quote ids from
context['accepted_quote_ids'] and links them via convert_quote_to_order.
"""
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.api.v1.endpoints.quotes import ManualQuoteCreate, QuoteLineCreate
from app.services import quote_service

from scripts.seed_data import _time


DIST = [
    ("accepted", 10),
    ("pending_sent", 5),      # real 'pending' — just "Sent & waiting"
    ("rejected", 3),
    ("pending_draft", 2),     # pending with DRAFT: admin_note (no draft state in Core)
]


def _build_lines(rng, finished_good_ids: dict[str, int], products_by_id: dict):
    n = rng.randint(1, 3)
    chosen_skus = rng.sample(list(finished_good_ids.keys()), k=n)
    lines = []
    for sku in chosen_skus:
        fg_id = finished_good_ids[sku]
        product = products_by_id[fg_id]
        lines.append(QuoteLineCreate(
            product_id=fg_id,
            product_name=product.name,
            quantity=rng.randint(5, 50),
            unit_price=Decimal(str(product.selling_price or 10)),
        ))
    return lines


def seed(db: Session, context: dict[str, Any]) -> None:
    rng = _time.rng()
    admin_id = context["admin_id"]
    customer_ids = context["customer_ids"]
    finished_good_ids = context["finished_good_ids"]

    from app.models.product import Product
    products = db.query(Product).filter(Product.id.in_(finished_good_ids.values())).all()
    products_by_id = {p.id: p for p in products}

    accepted_quote_ids: list[int] = []
    all_quote_ids: list[int] = []

    for kind, count in DIST:
        for _ in range(count):
            customer_id = rng.choice(customer_ids)
            is_draft = kind == "pending_draft"
            admin_note = "DRAFT: internal — not yet sent to customer" if is_draft else None

            request = ManualQuoteCreate(
                customer_id=customer_id,
                lines=_build_lines(rng, finished_good_ids, products_by_id),
                material_type="PLA",
                apply_tax=False,
                shipping_cost=Decimal(str(rng.choice([0, 5, 10, 15]))),
                customer_notes=None,
                admin_notes=admin_note,
                valid_days=30,
            )
            quote = quote_service.create_quote(db, request, admin_id)
            all_quote_ids.append(quote.id)

            target_status = "pending"
            if kind == "accepted":
                target_status = "accepted"
            elif kind == "rejected":
                target_status = "rejected"

            if target_status != "pending":
                quote.status = target_status
                db.add(quote)

            if target_status == "accepted":
                accepted_quote_ids.append(quote.id)

    db.flush()

    context["quote_ids"] = all_quote_ids
    context["accepted_quote_ids"] = accepted_quote_ids
    print(
        f"[seed]   {len(all_quote_ids)} quotes "
        f"({len(accepted_quote_ids)} accepted, 5 sent, 3 rejected, 2 draft)"
    )
