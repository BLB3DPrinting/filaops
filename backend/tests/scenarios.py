"""
E2E test data scenarios.

Used by the /api/v1/test/seed endpoint to populate the database
with predictable data for Playwright E2E tests.

Each scenario function receives a SQLAlchemy Session and returns
a dict of created object IDs for use in test assertions.
"""
from sqlalchemy.orm import Session
from app.models.user import User
from app.core.security import hash_password


# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, callable] = {}


def _register(name: str):
    """Decorator to register a scenario function."""
    def decorator(fn):
        SCENARIOS[name] = fn
        return fn
    return decorator


def seed_scenario(db: Session, name: str) -> dict:
    """Run a named scenario and return created IDs."""
    if name not in SCENARIOS:
        raise ValueError(
            f"Unknown scenario '{name}'. "
            f"Available: {', '.join(sorted(SCENARIOS.keys()))}"
        )
    return SCENARIOS[name](db)


def cleanup_test_data(db: Session) -> dict:
    """Remove test user created by E2E scenarios.

    Only removes the known E2E test user — does NOT truncate tables.
    Safe to call on dev databases.
    """
    test_email = "admin@filaops.test"
    deleted = db.query(User).filter(User.email == test_email).delete()
    db.commit()
    return {"cleaned": deleted > 0, "tables": ["users"] if deleted else []}


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

@_register("empty")
def _seed_empty(db: Session) -> dict:
    """Create only the E2E admin user (for login tests)."""
    user = _ensure_test_admin(db)
    return {"user_id": user.id, "email": user.email}


@_register("basic")
def _seed_basic(db: Session) -> dict:
    """Admin user + a handful of sample products/vendors."""
    user = _ensure_test_admin(db)
    # For now, basic is the same as empty — extend as needed
    return {"user_id": user.id, "email": user.email}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_test_admin(db: Session) -> User:
    """Create or return the E2E test admin user.

    Always refreshes the password hash to ensure it matches
    the expected password, regardless of how the user was created.
    """
    email = "admin@filaops.test"
    password = "TestPass123!"
    user = db.query(User).filter(User.email == email).first()
    if user:
        # Always update password to ensure it's valid
        user.password_hash = hash_password(password)
        user.account_type = "admin"
        user.status = "active"
        db.commit()
        db.refresh(user)
        return user

    user = User(
        email=email,
        password_hash=hash_password(password),
        first_name="Admin",
        last_name="User",
        account_type="admin",
        status="active",
        email_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
