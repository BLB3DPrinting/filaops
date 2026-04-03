"""
Pytest configuration and fixtures for the test suite.

Provides:
- Automatic filaops_test database targeting
- Session-scoped schema creation and seed data
- Transaction-isolated database sessions (services can commit without leaking)
- FastAPI TestClient with auth overrides
- Data factory fixtures for common domain objects
"""
import os
import uuid
import pytest
import sys
from decimal import Decimal
from pathlib import Path

# =============================================================================
# CRITICAL: Point to filaops_test BEFORE any app imports.
# Settings are loaded at import time from env vars / .env file.
# =============================================================================
os.environ["DB_NAME"] = "filaops_test"

# Add the backend directory to the path so imports work correctly
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


# =============================================================================
# Session-scoped: create schema + seed data (runs once per test session)
# =============================================================================

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Create tables and seed required data in filaops_test.

    Uses Base.metadata.create_all() which is idempotent — safe to run
    even if tables already exist.
    """
    from app.db.session import engine
    from app.db.base import Base

    # Import all models so Base.metadata knows about them
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Patch columns that create_all() won't add to pre-existing tables
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE inventory_transactions "
            "ADD COLUMN IF NOT EXISTS reason_code VARCHAR(50)"
        ))
        # i18n / multi-tax additions (migration 062, 063)
        # Payment terms columns on users (customer payment terms feature)
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_terms VARCHAR(20) DEFAULT 'cod'"
        ))
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS credit_limit NUMERIC(12,2)"
        ))
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS approved_for_terms BOOLEAN DEFAULT FALSE"
        ))
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS approved_for_terms_at TIMESTAMPTZ"
        ))
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS approved_for_terms_by INTEGER"
        ))
        conn.execute(text("ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS locale VARCHAR(20)"))
        conn.execute(text("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS tax_name VARCHAR(100)"))
        conn.execute(text("ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS tax_name VARCHAR(100)"))
        conn.execute(text("ALTER TABLE sales_order_lines ADD COLUMN IF NOT EXISTS tax_name VARCHAR(100)"))
        # Issue #362: material inventory on sales order lines
        # DROP NOT NULL is idempotent — safe to run if already nullable
        conn.execute(text(
            "ALTER TABLE sales_order_lines "
            "ALTER COLUMN product_id DROP NOT NULL"
        ))
        conn.execute(text(
            "ALTER TABLE sales_order_lines "
            "ADD COLUMN IF NOT EXISTS material_inventory_id INTEGER "
            "REFERENCES material_inventory(id)"
        ))
        # Migration 065: widen cost columns
        for col in ("standard_cost", "average_cost", "last_cost"):
            conn.execute(text(
                f"ALTER TABLE products ALTER COLUMN {col} TYPE NUMERIC(18,4)"
            ))
        # Migration 066: default margin for Suggest Prices tool
        conn.execute(text(
            "ALTER TABLE company_settings "
            "ADD COLUMN IF NOT EXISTS default_margin_percent NUMERIC(5,2)"
        ))
        # Migration 067: variant matrix
        conn.execute(text(
            "ALTER TABLE products "
            "ADD COLUMN IF NOT EXISTS parent_product_id INTEGER "
            "REFERENCES products(id) ON DELETE SET NULL"
        ))
        conn.execute(text(
            "ALTER TABLE products "
            "ADD COLUMN IF NOT EXISTS is_template BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        conn.execute(text(
            "ALTER TABLE products "
            "ADD COLUMN IF NOT EXISTS variant_metadata JSONB"
        ))
        conn.execute(text(
            "ALTER TABLE routing_operation_materials "
            "ADD COLUMN IF NOT EXISTS is_variable BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        # Add CHECK constraint if it doesn't already exist
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'ck_sol_product_or_material'
                ) THEN
                    ALTER TABLE sales_order_lines ADD CONSTRAINT ck_sol_product_or_material
                    CHECK (
                        (product_id IS NOT NULL AND material_inventory_id IS NULL) OR
                        (product_id IS NULL AND material_inventory_id IS NOT NULL)
                    );
                END IF;
            END
            $$;
        """))
        # Migration 069: customer payment terms
        conn.execute(text(
            "ALTER TABLE users "
            "ADD COLUMN IF NOT EXISTS payment_terms VARCHAR(20) DEFAULT 'cod'"
        ))
        conn.execute(text(
            "ALTER TABLE users "
            "ADD COLUMN IF NOT EXISTS credit_limit NUMERIC(12,2)"
        ))
        conn.execute(text(
            "ALTER TABLE users "
            "ADD COLUMN IF NOT EXISTS approved_for_terms BOOLEAN DEFAULT FALSE"
        ))
        conn.execute(text(
            "ALTER TABLE users "
            "ADD COLUMN IF NOT EXISTS approved_for_terms_at TIMESTAMPTZ"
        ))
        conn.execute(text(
            "ALTER TABLE users "
            "ADD COLUMN IF NOT EXISTS approved_for_terms_by INTEGER"
        ))
        # Migration 072: portal order ingestion
        conn.execute(text(
            "ALTER TABLE sales_orders "
            "ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ"
        ))
        # Migration 074: close short and line editing
        conn.execute(text(
            "ALTER TABLE sales_orders "
            "ADD COLUMN IF NOT EXISTS closed_short BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        conn.execute(text(
            "ALTER TABLE sales_orders "
            "ADD COLUMN IF NOT EXISTS closed_short_at TIMESTAMPTZ"
        ))
        conn.execute(text(
            "ALTER TABLE sales_orders "
            "ADD COLUMN IF NOT EXISTS close_short_reason TEXT"
        ))
        conn.execute(text(
            "ALTER TABLE sales_order_lines "
            "ADD COLUMN IF NOT EXISTS original_quantity NUMERIC(10,2)"
        ))
        conn.execute(text(
            "ALTER TABLE sales_order_lines "
            "ADD COLUMN IF NOT EXISTS fulfillment_status VARCHAR(20)"
        ))
        conn.commit()

    # Seed required data
    from sqlalchemy.orm import Session as SASession
    from app.models.inventory import InventoryLocation
    from app.models.user import User
    from app.models.work_center import WorkCenter
    from app.models.accounting import GLAccount

    with SASession(engine) as db:
        # Seed default inventory location
        if not db.query(InventoryLocation).filter(InventoryLocation.id == 1).first():
            db.add(InventoryLocation(
                id=1, name="Default Warehouse", code="DEFAULT",
                type="warehouse", active=True,
            ))

        # Seed default test user
        if not db.query(User).filter(User.id == 1).first():
            db.add(User(
                id=1, email="test@filaops.dev",
                password_hash="not-a-real-hash",
                first_name="Test", last_name="User",
                account_type="admin",
            ))

        # Seed default work center
        if not db.query(WorkCenter).filter(WorkCenter.id == 1).first():
            db.add(WorkCenter(
                id=1, code="TEST-WC", name="Test Work Center",
            ))

        # Seed core GL accounts (idempotent)
        # Format: (code, name, type, is_system, schedule_c_line)
        gl_accounts = [
            ("1000", "Cash", "asset", True, None),
            ("1200", "Accounts Receivable", "asset", True, None),
            ("1210", "WIP Inventory", "asset", True, None),
            ("1220", "Finished Goods Inventory", "asset", True, None),
            ("1230", "Packaging Inventory", "asset", True, None),
            ("1300", "Inventory Asset", "asset", True, None),
            ("1310", "WIP Inventory (Legacy)", "asset", True, None),
            ("2000", "Accounts Payable", "liability", True, None),
            ("3000", "Retained Earnings", "equity", True, None),
            ("4000", "Sales Revenue", "revenue", True, "1"),
            ("5000", "Cost of Goods Sold", "expense", True, None),
            ("5010", "Shipping Supplies", "expense", True, None),
            ("5020", "Scrap Expense (Production)", "expense", True, None),
            ("5100", "Material Cost", "expense", True, None),
            ("5200", "Scrap Expense", "expense", True, None),
            ("5500", "Inventory Adjustment", "expense", True, None),
        ]
        for code, name, acct_type, is_sys, sched_line in gl_accounts:
            if not db.query(GLAccount).filter(GLAccount.account_code == code).first():
                db.add(GLAccount(
                    account_code=code, name=name, account_type=acct_type,
                    is_system=is_sys, schedule_c_line=sched_line,
                ))

        db.commit()

        # Synchronize PostgreSQL sequences after explicit-ID inserts
        for table in ("users", "inventory_locations", "work_centers"):
            db.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
            ))
        db.commit()

    yield


# =============================================================================
# Database session fixture — transaction-isolated
# =============================================================================

@pytest.fixture
def db():
    """Create a database session wrapped in a transaction that rolls back.

    Uses SQLAlchemy 2.0 join_transaction_mode pattern:
    - Opens a real connection and begins a transaction
    - Creates a Session joined to that transaction via a savepoint
    - Service code calling session.commit() releases/recreates the savepoint
      but does NOT commit the connection-level transaction
    - At teardown, the connection transaction is rolled back — all test
      data disappears regardless of how many commits the service made
    """
    from app.db.session import engine
    from sqlalchemy.orm import Session as SASession

    connection = engine.connect()
    transaction = connection.begin()
    session = SASession(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# =============================================================================
# FastAPI TestClient with authentication
# =============================================================================

@pytest.fixture
def auth_token():
    """Generate a valid JWT access token for user_id=1 (seeded test admin)."""
    from app.core.security import create_access_token
    return create_access_token(user_id=1)


@pytest.fixture
def client(db, auth_token):
    """FastAPI TestClient with DB session override and auth.

    Usage:
        def test_list_items(client):
            response = client.get("/api/v1/items/")
            assert response.status_code == 200

        def test_unauthed(unauthed_client):
            response = unauthed_client.get("/api/v1/items/")
            assert response.status_code == 401
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import get_db

    def _override_get_db():
        try:
            yield db
        finally:
            pass  # db fixture handles rollback

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers["Authorization"] = f"Bearer {auth_token}"
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def unauthed_client(db):
    """FastAPI TestClient without authentication (for 401 tests)."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import get_db

    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    app.dependency_overrides.clear()


# =============================================================================
# Data factories — reusable fixtures for domain objects
# =============================================================================

def _uid():
    """Short unique suffix for test data."""
    return uuid.uuid4().hex[:8]


@pytest.fixture
def make_product(db):
    """Factory fixture to create Product instances.

    Usage:
        product = make_product()  # defaults: finished_good, EA, average cost
        raw = make_product(item_type="supply", unit="G", purchase_uom="KG", purchase_factor=1000)
    """
    from app.models.product import Product

    created = []

    def _factory(
        sku=None,
        name=None,
        item_type="finished_good",
        unit="EA",
        purchase_uom="EA",
        purchase_factor=None,
        cost_method="average",
        standard_cost=None,
        average_cost=None,
        selling_price=None,
        is_raw_material=False,
        procurement_type="buy",
        **kwargs,
    ):
        uid = _uid()
        product = Product(
            sku=sku or f"TEST-{item_type[:3].upper()}-{uid}",
            name=name or f"Test {item_type} {uid}",
            item_type=item_type,
            unit=unit,
            purchase_uom=purchase_uom,
            purchase_factor=purchase_factor,
            cost_method=cost_method,
            standard_cost=standard_cost,
            average_cost=average_cost,
            selling_price=selling_price,
            is_raw_material=is_raw_material,
            procurement_type=procurement_type,
            **kwargs,
        )
        db.add(product)
        db.flush()
        created.append(product)
        return product

    yield _factory


@pytest.fixture
def make_vendor(db):
    """Factory fixture to create Vendor instances."""
    from app.models.vendor import Vendor

    def _factory(name=None, code=None, **kwargs):
        uid = _uid()
        vendor = Vendor(
            code=code or f"V-{uid}",
            name=name or f"Test Vendor {uid}",
            is_active=True,
            **kwargs,
        )
        db.add(vendor)
        db.flush()
        return vendor

    yield _factory


@pytest.fixture
def make_customer(db):
    """Factory fixture to create Customer instances."""
    from app.models.customer import Customer

    def _factory(company_name=None, email=None, **kwargs):
        uid = _uid()
        customer = Customer(
            company_name=company_name or f"Test Co {uid}",
            email=email or f"test-{uid}@example.com",
            status="active",
            **kwargs,
        )
        db.add(customer)
        db.flush()
        return customer

    yield _factory


@pytest.fixture
def make_sales_order(db):
    """Factory fixture to create SalesOrder instances.

    Usage:
        so = make_sales_order(product_id=product.id, quantity=10, unit_price=Decimal("5.00"))
    """
    from app.models.sales_order import SalesOrder

    _counter = [0]

    def _factory(
        product_id=None,
        quantity=1,
        unit_price=Decimal("10.00"),
        status="draft",
        material_type="PLA",
        **kwargs,
    ):
        uid = _uid()
        _counter[0] += 1
        total = unit_price * quantity
        so = SalesOrder(
            order_number=kwargs.pop("order_number", f"SO-TEST-{uid}"),
            user_id=kwargs.pop("user_id", 1),
            product_id=product_id,
            product_name=kwargs.pop("product_name", f"Test Product {uid}"),
            quantity=quantity,
            material_type=material_type,
            unit_price=unit_price,
            total_price=total,
            grand_total=total,
            status=status,
            **kwargs,
        )
        db.add(so)
        db.flush()
        return so

    yield _factory


@pytest.fixture
def make_purchase_order(db):
    """Factory fixture to create PurchaseOrder instances."""
    from app.models.purchase_order import PurchaseOrder

    def _factory(vendor_id=None, status="draft", **kwargs):
        uid = _uid()
        po = PurchaseOrder(
            po_number=kwargs.pop("po_number", f"PO-TEST-{uid}"),
            vendor_id=vendor_id,
            status=status,
            created_by=kwargs.pop("created_by", "1"),
            **kwargs,
        )
        db.add(po)
        db.flush()
        return po

    yield _factory


@pytest.fixture
def make_bom(db):
    """Factory fixture to create BOM with lines.

    Usage:
        bom = make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])
    """
    from app.models.bom import BOM, BOMLine

    def _factory(product_id, lines=None, **kwargs):
        uid = _uid()
        bom = BOM(
            product_id=product_id,
            name=kwargs.pop("name", f"BOM-{uid}"),
            active=kwargs.pop("active", True),
            **kwargs,
        )
        db.add(bom)
        db.flush()

        if lines:
            for i, line_data in enumerate(lines):
                line = BOMLine(
                    bom_id=bom.id,
                    component_id=line_data["component_id"],
                    quantity=line_data.get("quantity", Decimal("1")),
                    unit=line_data.get("unit", "EA"),
                    sequence=line_data.get("sequence", (i + 1) * 10),
                )
                db.add(line)
            db.flush()

        return bom

    yield _factory


@pytest.fixture
def make_production_order(db):
    """Factory fixture to create ProductionOrder instances."""
    from app.models.production_order import ProductionOrder

    _counter = [0]

    def _factory(product_id=None, status="draft", quantity=10, **kwargs):
        uid = _uid()
        _counter[0] += 1
        po = ProductionOrder(
            code=kwargs.pop("code", f"WO-TEST-{uid}"),
            product_id=product_id or 1,
            quantity_ordered=quantity,
            status=status,
            source=kwargs.pop("source", "manual"),
            **kwargs,
        )
        db.add(po)
        db.flush()
        return po

    yield _factory


@pytest.fixture
def make_work_center(db):
    """Factory fixture to create WorkCenter instances."""
    from app.models.work_center import WorkCenter

    def _factory(name=None, code=None, center_type="printer", **kwargs):
        uid = _uid()
        wc = WorkCenter(
            name=name or f"Test WC {uid}",
            code=code or f"WC-{uid}",
            center_type=center_type,
            is_active=kwargs.pop("is_active", True),
            **kwargs,
        )
        db.add(wc)
        db.flush()
        return wc

    yield _factory


# =============================================================================
# Convenience fixtures for common test scenarios
# =============================================================================

@pytest.fixture
def raw_material(make_product):
    """A filament raw material: unit=G, purchase_uom=KG, cost_method=average."""
    return make_product(
        item_type="supply",
        unit="G",
        purchase_uom="KG",
        purchase_factor=Decimal("1000"),
        cost_method="average",
        average_cost=Decimal("0.02"),
        is_raw_material=True,
        name="PLA Filament (Test)",
    )


@pytest.fixture
def finished_good(make_product):
    """A finished good product with standard costing."""
    return make_product(
        item_type="finished_good",
        unit="EA",
        cost_method="standard",
        standard_cost=Decimal("5.00"),
        selling_price=Decimal("15.00"),
        procurement_type="make",
        name="Test Widget (FG)",
    )
