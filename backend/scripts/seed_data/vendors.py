"""
Seed 6 vendors (fake supplier names).

Uses vendor_service.create_vendor (dict-based) so VND-### code
generation + audit timestamps fire. Terms are varied (Net 30,
Net 15, COD) and lead times span 3-14 days so the Vendors list
page screenshots show a realistic spread.
"""
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.services import vendor_service

from scripts.seed_data import _time


VENDOR_COUNT = 6
PAYMENT_TERMS = ["Net 30", "Net 30", "Net 30", "Net 15", "Net 15", "COD"]


def seed(db: Session, context: dict[str, Any]) -> None:
    fake = _time.fake()
    rng = _time.rng()

    vendor_ids: list[int] = []
    for i in range(VENDOR_COUNT):
        company = f"{fake.last_name()} {rng.choice(['Supply', 'Materials', 'Industrial', 'Trading'])}"
        data = {
            "name": company,
            "contact_name": fake.name(),
            "email": fake.unique.company_email(),
            "phone": fake.phone_number()[:50],
            "website": f"https://www.{fake.domain_name()}",
            "address_line1": fake.street_address()[:200],
            "city": fake.city()[:100],
            "state": fake.state_abbr(),
            "postal_code": fake.postcode()[:20],
            "country": "USA",
            "payment_terms": PAYMENT_TERMS[i],
            "lead_time_days": rng.randint(3, 14),
            "rating": Decimal(f"{rng.uniform(3.5, 5.0):.2f}"),
            "is_active": True,
        }
        vendor = vendor_service.create_vendor(db, data=data)
        vendor_ids.append(vendor.id)

    context["vendor_ids"] = vendor_ids
    print(f"[seed]   {len(vendor_ids)} vendors")
