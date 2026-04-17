"""
Seed users: 1 admin + 2 operators.

The admin account has a well-known password (printed at the end of the
seed run) for evaluator login. Operator accounts get random passwords —
they exist so that UI dropdowns and audit trails have more than one
user to choose from, not for real authentication.

Service-layer note: customer_service.create_customer() hardcodes
account_type='customer', so admin/operator rows are created directly.
There is no UserService for staff creation in Core.
"""
import secrets
from typing import Any

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User

from scripts.seed_data import _time


ADMIN_EMAIL = "admin@acme-demo.test"
ADMIN_PASSWORD = "demo1234"


def seed(db: Session, context: dict[str, Any]) -> None:
    now = _time.now()
    fake = _time.fake()

    admin = User(
        email=ADMIN_EMAIL,
        password_hash=hash_password(ADMIN_PASSWORD),
        email_verified=True,
        first_name="Demo",
        last_name="Admin",
        status="active",
        account_type="admin",
        created_at=now,
        updated_at=now,
    )
    db.add(admin)
    db.flush()  # populate admin.id for downstream modules

    operators = []
    for _ in range(2):
        op = User(
            email=fake.unique.email(),
            password_hash=hash_password(secrets.token_urlsafe(32)),
            email_verified=True,
            first_name=fake.first_name(),
            last_name=fake.last_name(),
            status="active",
            account_type="operator",
            created_at=now,
            updated_at=now,
        )
        db.add(op)
        operators.append(op)
    db.flush()

    context["admin_id"] = admin.id
    context["operator_ids"] = [op.id for op in operators]
    print(f"[seed]   admin id={admin.id}, operators={[op.id for op in operators]}")
