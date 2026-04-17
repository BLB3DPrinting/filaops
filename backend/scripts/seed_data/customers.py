"""
Seed 25 customers: 20 B2B (faker.company) + 5 retail individuals.

Uses customer_service.create_customer(db, data, admin_id) rather than
raw User inserts so customer_number generation, default status, and
the rest of the business rules fire. The service returns a dict —
we capture the 'id' field to thread into downstream orders/quotes.

Price-level assignment is a PRO feature and is intentionally NOT
performed here (see seed_data/price_levels.py).
"""
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.customer import CustomerCreate
from app.services import customer_service

from scripts.seed_data import _time


B2B_COUNT = 20
RETAIL_COUNT = 5


def seed(db: Session, context: dict[str, Any]) -> None:
    admin_id = context["admin_id"]
    fake = _time.fake()

    customer_ids: list[int] = []

    for _ in range(B2B_COUNT):
        first = fake.first_name()
        last = fake.last_name()
        data = CustomerCreate(
            email=fake.unique.company_email(),
            first_name=first,
            last_name=last,
            company_name=fake.company(),
            phone=fake.phone_number()[:20],
            billing_address_line1=fake.street_address()[:255],
            billing_city=fake.city()[:100],
            billing_state=fake.state_abbr(),
            billing_zip=fake.postcode()[:20],
            billing_country="USA",
            shipping_address_line1=fake.street_address()[:255],
            shipping_city=fake.city()[:100],
            shipping_state=fake.state_abbr(),
            shipping_zip=fake.postcode()[:20],
            shipping_country="USA",
            status="active",
            payment_terms="net30",
        )
        result = customer_service.create_customer(db, data, admin_id)
        customer_ids.append(result["id"])

    for _ in range(RETAIL_COUNT):
        first = fake.first_name()
        last = fake.last_name()
        data = CustomerCreate(
            email=fake.unique.email(),
            first_name=first,
            last_name=last,
            company_name=None,
            phone=fake.phone_number()[:20],
            billing_address_line1=fake.street_address()[:255],
            billing_city=fake.city()[:100],
            billing_state=fake.state_abbr(),
            billing_zip=fake.postcode()[:20],
            billing_country="USA",
            status="active",
            payment_terms="cod",
        )
        result = customer_service.create_customer(db, data, admin_id)
        customer_ids.append(result["id"])

    context["customer_ids"] = customer_ids
    print(f"[seed]   {len(customer_ids)} customers ({B2B_COUNT} B2B + {RETAIL_COUNT} retail)")
