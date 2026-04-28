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
        # Migration 079: filament diameter for compatibility checks
        conn.execute(text(
            "ALTER TABLE material_types "
            "ADD COLUMN IF NOT EXISTS filament_diameter NUMERIC(4,2) DEFAULT 1.75"
        ))
        conn.execute(text(
            "UPDATE material_types "
            "SET filament_diameter = 1.75 "
            "WHERE filament_diameter IS NULL"
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


# =============================================================================
# Variant-axis fixtures (Task 2 — MaterialColorResolver)
# =============================================================================

@pytest.fixture
def material_type_pla(db):
    """A MaterialType with a unique test-only code to avoid seed-data collisions."""
    from app.models.material import MaterialType

    uid = _uid()
    mt = MaterialType(
        code=f"PLA_BASIC_TEST_{uid}",
        name="PLA Basic Test",
        base_material="PLA",
        process_type="FDM",
        density=1.24,
        base_price_per_kg=20.00,
    )
    db.add(mt)
    db.flush()
    return mt


@pytest.fixture
def color_black(db):
    """A Color with a unique test-only code to avoid seed-data collisions."""
    from app.models.material import Color

    uid = _uid()
    color = Color(
        code=f"BLK_TEST_{uid}",
        name="Black Test",
        hex_code="#000000",
    )
    db.add(color)
    db.flush()
    return color


@pytest.fixture
def supply_product_pla_black(db, make_product, material_type_pla, color_black):
    """Active supply Product linked to the PLA Basic Test material_type + Black Test color."""
    uid = _uid()
    return make_product(
        sku=f"SUP-PLA-BLK-TEST-{uid}",
        name=f"PLA Basic Black Filament Test {uid}",
        item_type="supply",
        unit="G",
        purchase_uom="KG",
        purchase_factor=Decimal("1000"),
        cost_method="average",
        average_cost=Decimal("0.02"),
        is_raw_material=True,
        active=True,
        material_type_id=material_type_pla.id,
        color_id=color_black.id,
    )


@pytest.fixture
def fg004_template_with_material_color_axis(db, make_product, make_work_center):
    """Fixture returning a dict used by test_list_options_returns_one_per_materialcolor_row.

    Creates:
      - 1 MaterialType (pla_for_fg) with a unique code
      - 3 Colors with unique codes
      - 3 MaterialColor rows (junction)
      - 3 supply Products (one per combo)
      - 1 finished-good template Product
      - 1 Routing → 1 RoutingOperation → 1 RoutingOperationMaterial (is_variable=True)
        whose component_id points at one of the supply products

    Returns:
      {
          "template": Product,
          "variable_material": RoutingOperationMaterial,
          "expected_combo_count": 3,
      }
    """
    from app.models.material import MaterialType, Color, MaterialColor
    from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial

    uid = _uid()

    # --- MaterialType ---
    pla_for_fg = MaterialType(
        code=f"PLA_FG_{uid}",
        name=f"PLA FG Test {uid}",
        base_material="PLA",
        process_type="FDM",
        density=1.24,
        base_price_per_kg=20.00,
    )
    db.add(pla_for_fg)
    db.flush()

    # --- Colors + MaterialColor rows + supply Products ---
    color_codes = [f"FG_C1_{uid}", f"FG_C2_{uid}", f"FG_C3_{uid}"]
    supply_products = []
    for i, code in enumerate(color_codes):
        c = Color(code=code, name=f"FG Color {i+1} {uid}", hex_code=f"#0{i}0{i}0{i}")
        db.add(c)
        db.flush()

        mc = MaterialColor(material_type_id=pla_for_fg.id, color_id=c.id)
        db.add(mc)
        db.flush()

        sp = make_product(
            sku=f"SUP-FG-{code}",
            name=f"Supply FG {code}",
            item_type="supply",
            unit="G",
            purchase_uom="KG",
            purchase_factor=Decimal("1000"),
            cost_method="average",
            average_cost=Decimal("0.02"),
            is_raw_material=True,
            active=True,
            material_type_id=pla_for_fg.id,
            color_id=c.id,
        )
        supply_products.append(sp)

    # --- Finished-good template ---
    template = make_product(
        sku=f"FG004-TMPL-{uid}",
        name=f"FG004 Template {uid}",
        item_type="finished_good",
        unit="EA",
        cost_method="standard",
        standard_cost=Decimal("5.00"),
        selling_price=Decimal("15.00"),
        procurement_type="make",
        is_template=True,
    )

    # --- Work center (required by RoutingOperation) ---
    wc = make_work_center(name=f"FDM Pool {uid}", code=f"WC-FDM-{uid}")

    # --- Routing ---
    routing = Routing(
        product_id=template.id,
        code=f"RT-FG004-{uid}",
        name=f"Routing FG004 {uid}",
        is_active=True,
    )
    db.add(routing)
    db.flush()

    # --- RoutingOperation ---
    op = RoutingOperation(
        routing_id=routing.id,
        work_center_id=wc.id,
        sequence=10,
        operation_code="PRINT",
        operation_name="Print",
        run_time_minutes=Decimal("150"),
        setup_time_minutes=Decimal("5"),
    )
    db.add(op)
    db.flush()

    # --- RoutingOperationMaterial (variable = True, component = first supply product) ---
    variable_material = RoutingOperationMaterial(
        routing_operation_id=op.id,
        component_id=supply_products[0].id,
        quantity=Decimal("37"),
        unit="G",
        is_variable=True,
    )
    db.add(variable_material)
    db.flush()

    return {
        "template": template,
        "variable_material": variable_material,
        "expected_combo_count": len(color_codes),  # 3
    }


# =============================================================================
# Variant-axis fixtures (Task 4 — ComponentTemplateResolver)
# =============================================================================

@pytest.fixture
def fg004_component_template_axis(db, make_product, make_work_center):
    """Fixture: FG template with a variable RoutingOperationMaterial whose
    component_id points at a COMP template that has 9 active children.

    Returns:
        {
            "template": Product (is_template=True, FG-style),
            "variable_material": RoutingOperationMaterial (is_variable=True),
            "children": list[Product],  # 9 active children of comp_template
        }
    """
    from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial

    uid = _uid()

    # --- COMP template: the parent whose children are the variant options ---
    comp_template = make_product(
        sku=f"COMP-005-TMPL-{uid}",
        name=f"Comp Template {uid}",
        item_type="component",
        unit="EA",
        is_template=True,
        active=True,
    )

    # --- 9 active children of the COMP template ---
    children = []
    for i in range(9):
        child = make_product(
            sku=f"COMP-005-V{i+1:02d}-{uid}",
            name=f"Comp Variant {i+1} {uid}",
            item_type="component",
            unit="EA",
            active=True,
            parent_product_id=comp_template.id,
        )
        children.append(child)

    # --- FG template ---
    template = make_product(
        sku=f"FG004-CT-TMPL-{uid}",
        name=f"FG004 Component Template {uid}",
        item_type="finished_good",
        unit="EA",
        cost_method="standard",
        standard_cost=Decimal("5.00"),
        selling_price=Decimal("15.00"),
        procurement_type="make",
        is_template=True,
        active=True,
    )

    # --- Work center ---
    wc = make_work_center(name=f"FDM Pool CT {uid}", code=f"WC-CT-{uid}")

    # --- Routing → RoutingOperation → RoutingOperationMaterial ---
    routing = Routing(
        product_id=template.id,
        code=f"RT-CT-{uid}",
        name=f"Routing CT {uid}",
        is_active=True,
    )
    db.add(routing)
    db.flush()

    op = RoutingOperation(
        routing_id=routing.id,
        work_center_id=wc.id,
        sequence=10,
        operation_code="ASSEMBLE",
        operation_name="Assemble",
        run_time_minutes=Decimal("30"),
        setup_time_minutes=Decimal("5"),
    )
    db.add(op)
    db.flush()

    variable_material = RoutingOperationMaterial(
        routing_operation_id=op.id,
        component_id=comp_template.id,
        quantity=Decimal("1"),
        unit="EA",
        is_variable=True,
    )
    db.add(variable_material)
    db.flush()

    return {
        "template": template,
        "variable_material": variable_material,
        "children": children,
    }


@pytest.fixture
def fg004_component_template_axis_with_inactive(db, make_product, make_work_center):
    """Fixture: same shape as fg004_component_template_axis but with 4 active
    children + 1 inactive child. Resolver must exclude the inactive one.

    Returns:
        {
            "template": Product,
            "variable_material": RoutingOperationMaterial,
            "active_count": 4,
            "inactive_child_id": int,
        }
    """
    from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial

    uid = _uid()

    # --- COMP template ---
    comp_template = make_product(
        sku=f"COMP-006-TMPL-{uid}",
        name=f"Comp Template Inactive {uid}",
        item_type="component",
        unit="EA",
        is_template=True,
        active=True,
    )

    # --- 4 active children ---
    for i in range(4):
        make_product(
            sku=f"COMP-006-V{i+1:02d}-{uid}",
            name=f"Comp Variant Active {i+1} {uid}",
            item_type="component",
            unit="EA",
            active=True,
            parent_product_id=comp_template.id,
        )

    # --- 1 inactive child ---
    inactive_child = make_product(
        sku=f"COMP-006-VOFF-{uid}",
        name=f"Comp Variant Inactive {uid}",
        item_type="component",
        unit="EA",
        active=False,
        parent_product_id=comp_template.id,
    )

    # --- FG template ---
    template = make_product(
        sku=f"FG004-CTI-TMPL-{uid}",
        name=f"FG004 Component Template Inactive {uid}",
        item_type="finished_good",
        unit="EA",
        cost_method="standard",
        standard_cost=Decimal("5.00"),
        selling_price=Decimal("15.00"),
        procurement_type="make",
        is_template=True,
        active=True,
    )

    # --- Work center ---
    wc = make_work_center(name=f"FDM Pool CTI {uid}", code=f"WC-CTI-{uid}")

    # --- Routing → RoutingOperation → RoutingOperationMaterial ---
    routing = Routing(
        product_id=template.id,
        code=f"RT-CTI-{uid}",
        name=f"Routing CTI {uid}",
        is_active=True,
    )
    db.add(routing)
    db.flush()

    op = RoutingOperation(
        routing_id=routing.id,
        work_center_id=wc.id,
        sequence=10,
        operation_code="ASSEMBLE",
        operation_name="Assemble",
        run_time_minutes=Decimal("30"),
        setup_time_minutes=Decimal("5"),
    )
    db.add(op)
    db.flush()

    variable_material = RoutingOperationMaterial(
        routing_operation_id=op.id,
        component_id=comp_template.id,
        quantity=Decimal("1"),
        unit="EA",
        is_variable=True,
    )
    db.add(variable_material)
    db.flush()

    return {
        "template": template,
        "variable_material": variable_material,
        "active_count": 4,
        "inactive_child_id": inactive_child.id,
    }


@pytest.fixture
def manufactured_template_with_children(db, make_product, make_work_center):
    """Fixture for Rule-1 test: COMP template with item_type='manufactured'
    (a sub-assembly) and 3 active children.

    Returns:
        {
            "template": Product (is_template=True, item_type='manufactured'),
            "variable_material": RoutingOperationMaterial (is_variable=True),
            "expected_count": 3,
        }
    """
    from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial

    uid = _uid()

    # --- COMP template: item_type='manufactured' (sub-assembly) ---
    comp_template = make_product(
        sku=f"SUB-MFG-TMPL-{uid}",
        name=f"Sub-Assembly Manufactured Template {uid}",
        item_type="manufactured",
        unit="EA",
        is_template=True,
        active=True,
    )

    # --- 3 active children ---
    for i in range(3):
        make_product(
            sku=f"SUB-MFG-V{i+1:02d}-{uid}",
            name=f"Sub-Assembly Variant {i+1} {uid}",
            item_type="manufactured",
            unit="EA",
            active=True,
            parent_product_id=comp_template.id,
        )

    # --- FG template ---
    template = make_product(
        sku=f"FG-MFG-TMPL-{uid}",
        name=f"FG Manufactured Template {uid}",
        item_type="finished_good",
        unit="EA",
        cost_method="standard",
        standard_cost=Decimal("5.00"),
        selling_price=Decimal("15.00"),
        procurement_type="make",
        is_template=True,
        active=True,
    )

    # --- Work center ---
    wc = make_work_center(name=f"Assembly WC MFG {uid}", code=f"WC-MFG-{uid}")

    # --- Routing → RoutingOperation → RoutingOperationMaterial ---
    routing = Routing(
        product_id=template.id,
        code=f"RT-MFG-{uid}",
        name=f"Routing MFG {uid}",
        is_active=True,
    )
    db.add(routing)
    db.flush()

    op = RoutingOperation(
        routing_id=routing.id,
        work_center_id=wc.id,
        sequence=10,
        operation_code="ASSEMBLE",
        operation_name="Assemble",
        run_time_minutes=Decimal("30"),
        setup_time_minutes=Decimal("5"),
    )
    db.add(op)
    db.flush()

    variable_material = RoutingOperationMaterial(
        routing_operation_id=op.id,
        component_id=comp_template.id,
        quantity=Decimal("1"),
        unit="EA",
        is_variable=True,
    )
    db.add(variable_material)
    db.flush()

    return {
        "template": template,
        "variable_material": variable_material,
        "expected_count": 3,
    }


@pytest.fixture
def supply_template_with_children(db, make_product, make_work_center):
    """Fixture for Rule-1 test: COMP template with item_type='supply'
    (purchased component) and 2 active children.

    Returns:
        {
            "template": Product (is_template=True, item_type='supply'),
            "variable_material": RoutingOperationMaterial (is_variable=True),
            "expected_count": 2,
        }
    """
    from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial

    uid = _uid()

    # --- COMP template: item_type='supply' (purchased component) ---
    comp_template = make_product(
        sku=f"SUP-TMPL-{uid}",
        name=f"Supply Component Template {uid}",
        item_type="supply",
        unit="EA",
        is_template=True,
        active=True,
    )

    # --- 2 active children ---
    for i in range(2):
        make_product(
            sku=f"SUP-V{i+1:02d}-{uid}",
            name=f"Supply Variant {i+1} {uid}",
            item_type="supply",
            unit="EA",
            active=True,
            parent_product_id=comp_template.id,
        )

    # --- FG template ---
    template = make_product(
        sku=f"FG-SUP-TMPL-{uid}",
        name=f"FG Supply Template {uid}",
        item_type="finished_good",
        unit="EA",
        cost_method="standard",
        standard_cost=Decimal("5.00"),
        selling_price=Decimal("15.00"),
        procurement_type="make",
        is_template=True,
        active=True,
    )

    # --- Work center ---
    wc = make_work_center(name=f"Assembly WC SUP {uid}", code=f"WC-SUP-{uid}")

    # --- Routing → RoutingOperation → RoutingOperationMaterial ---
    routing = Routing(
        product_id=template.id,
        code=f"RT-SUP-{uid}",
        name=f"Routing SUP {uid}",
        is_active=True,
    )
    db.add(routing)
    db.flush()

    op = RoutingOperation(
        routing_id=routing.id,
        work_center_id=wc.id,
        sequence=10,
        operation_code="ASSEMBLE",
        operation_name="Assemble",
        run_time_minutes=Decimal("30"),
        setup_time_minutes=Decimal("5"),
    )
    db.add(op)
    db.flush()

    variable_material = RoutingOperationMaterial(
        routing_operation_id=op.id,
        component_id=comp_template.id,
        quantity=Decimal("1"),
        unit="EA",
        is_variable=True,
    )
    db.add(variable_material)
    db.flush()

    return {
        "template": template,
        "variable_material": variable_material,
        "expected_count": 2,
    }


@pytest.fixture
def component_template_with_children(db, make_product, make_work_center):
    """Fixture for Rule-1 test: COMP template with item_type='component'
    (a discrete component / sub-part) and 2 active children.

    Used to pin Rule 1 for the 'component' item_type variant of the resolver.

    Returns:
        {
            "template": Product (is_template=True, item_type='component'),
            "variable_material": RoutingOperationMaterial (is_variable=True),
            "expected_count": 2,
        }
    """
    from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial

    uid = _uid()

    # --- COMP template: item_type='component' ---
    comp_template = make_product(
        sku=f"COMP-RULE1-{uid}",
        name=f"Rule1 Comp Template {uid}",
        item_type="component",
        unit="EA",
        is_template=True,
        active=True,
    )

    # --- 2 active children ---
    for i in range(2):
        make_product(
            sku=f"COMP-RULE1-{uid}-V{i}",
            name=f"Rule1 Comp Child {uid} {i}",
            item_type="component",
            unit="EA",
            active=True,
            parent_product_id=comp_template.id,
        )

    # --- FG template ---
    template = make_product(
        sku=f"FG-RULE1-{uid}",
        name=f"Rule1 FG {uid}",
        item_type="finished_good",
        unit="EA",
        cost_method="standard",
        standard_cost=Decimal("5.00"),
        selling_price=Decimal("15.00"),
        procurement_type="make",
        is_template=True,
        active=True,
    )

    # --- Work center ---
    wc = make_work_center(name=f"Assembly WC COMP {uid}", code=f"WC-COMP-{uid}")

    # --- Routing → RoutingOperation → RoutingOperationMaterial ---
    routing = Routing(
        product_id=template.id,
        code=f"RT-COMP-{uid}",
        name=f"Routing COMP {uid}",
        is_active=True,
    )
    db.add(routing)
    db.flush()

    op = RoutingOperation(
        routing_id=routing.id,
        work_center_id=wc.id,
        sequence=10,
        operation_code="ASSEMBLE",
        operation_name="Assemble",
        run_time_minutes=Decimal("30"),
        setup_time_minutes=Decimal("5"),
    )
    db.add(op)
    db.flush()

    variable_material = RoutingOperationMaterial(
        routing_operation_id=op.id,
        component_id=comp_template.id,
        quantity=Decimal("1"),
        unit="EA",
        is_variable=True,
    )
    db.add(variable_material)
    db.flush()

    return {
        "template": template,
        "variable_material": variable_material,
        "expected_count": 2,
    }


# =============================================================================
# Variant-axis fixtures (Task 8 -- mixed-axis sync_routing_to_variants)
# =============================================================================

@pytest.fixture
def mixed_axis_template_with_one_variant(db, make_product, make_work_center):
    """Fixture: FG template with 4 routing material lines (2 variable, 2 fixed)
    and one variant with v2 axis_selections metadata keyed by
    RoutingOperationMaterial.id.

    Line layout:
      rom_a  is_variable=True   component=pla_placeholder  axis=material_color
      rom_b  is_variable=True   component=comp_x template  axis=component_template
      rom_c  is_variable=False  component=fixed_1           preserved verbatim
      rom_d  is_variable=False  component=fixed_2           preserved verbatim

    Returns:
        {
            "template": Product,
            "variant": Product,
            "expected_color_target_id": int,     # pla_blk_supply.id
            "expected_component_target_id": int, # chosen_child.id
            "fixed_component_ids": [int, int],   # [fixed_1.id, fixed_2.id]
        }
    """
    from app.models.material import MaterialType, Color, MaterialColor
    from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial

    uid = _uid()

    # 1. Material+color setup
    pla_material_type = MaterialType(
        code=f"PLA_MX_{uid}",
        name=f"PLA Mixed-Axis Test {uid}",
        base_material="PLA",
        process_type="FDM",
        density=1.24,
        base_price_per_kg=20.00,
    )
    db.add(pla_material_type)
    db.flush()

    black_color = Color(
        code=f"BLK_MX_{uid}",
        name=f"Black Mixed-Axis Test {uid}",
        hex_code="#000000",
    )
    db.add(black_color)
    db.flush()

    mc_junction = MaterialColor(
        material_type_id=pla_material_type.id,
        color_id=black_color.id,
    )
    db.add(mc_junction)
    db.flush()

    # The supply product the material_color axis resolves to
    pla_blk_supply = make_product(
        sku=f"PLA-BLK-MX-{uid}",
        name=f"PLA Black Mixed-Axis Supply {uid}",
        item_type="supply",
        unit="G",
        purchase_uom="KG",
        purchase_factor=Decimal("1000"),
        cost_method="average",
        average_cost=Decimal("0.02"),
        is_raw_material=True,
        active=True,
        material_type_id=pla_material_type.id,
        color_id=black_color.id,
    )

    # Placeholder: template variable line points at this.
    # active=False so the material_color resolver's active=True filter excludes it,
    # leaving pla_blk_supply as the only valid match and eliminating fixture-order fragility.
    pla_placeholder = make_product(
        sku=f"PLA-PLACEHOLDER-MX-{uid}",
        name=f"PLA Placeholder Mixed-Axis {uid}",
        item_type="supply",
        unit="G",
        purchase_uom="KG",
        purchase_factor=Decimal("1000"),
        cost_method="average",
        average_cost=Decimal("0.02"),
        is_raw_material=True,
        active=False,
        material_type_id=pla_material_type.id,
        color_id=black_color.id,
    )

    # 2. Component-template setup
    comp_x_template = make_product(
        sku=f"COMP-X-TMPL-MX-{uid}",
        name=f"COMP-X Template Mixed-Axis {uid}",
        item_type="component",
        unit="EA",
        is_template=True,
        active=True,
    )

    children = []
    for i in range(3):
        child = make_product(
            sku=f"COMP-X-V{i+1:02d}-MX-{uid}",
            name=f"COMP-X Variant {i+1} Mixed-Axis {uid}",
            item_type="component",
            unit="EA",
            active=True,
            parent_product_id=comp_x_template.id,
        )
        children.append(child)
    chosen_child = children[1]  # deterministic pick

    # 3. Fixed-line products
    fixed_1 = make_product(
        sku=f"FIXED-1-MX-{uid}",
        name=f"Fixed Component 1 Mixed-Axis {uid}",
        item_type="supply",
        unit="EA",
        active=True,
    )
    fixed_2 = make_product(
        sku=f"FIXED-2-MX-{uid}",
        name=f"Fixed Component 2 Mixed-Axis {uid}",
        item_type="supply",
        unit="EA",
        active=True,
    )

    # 4. FG template
    template = make_product(
        sku=f"FG-MX-TMPL-{uid}",
        name=f"FG Mixed-Axis Template {uid}",
        item_type="finished_good",
        unit="EA",
        cost_method="standard",
        standard_cost=Decimal("5.00"),
        selling_price=Decimal("15.00"),
        procurement_type="make",
        is_template=True,
        active=True,
    )

    # 5. Routing: 1 operation, 4 material lines
    wc = make_work_center(name=f"Mixed-Axis WC {uid}", code=f"WC-MX-{uid}")

    routing = Routing(
        product_id=template.id,
        code=f"RT-MX-{uid}",
        name=f"Routing Mixed-Axis {uid}",
        is_active=True,
    )
    db.add(routing)
    db.flush()

    op = RoutingOperation(
        routing_id=routing.id,
        work_center_id=wc.id,
        sequence=10,
        operation_code="PRINT-MX",
        operation_name="Print Mixed-Axis",
        run_time_minutes=Decimal("150"),
        setup_time_minutes=Decimal("5"),
    )
    db.add(op)
    db.flush()

    # rom_a: material_color variable line
    rom_a = RoutingOperationMaterial(
        routing_operation_id=op.id,
        component_id=pla_placeholder.id,
        quantity=Decimal("37"),
        unit="G",
        is_variable=True,
    )
    db.add(rom_a)
    db.flush()

    # rom_b: component_template variable line
    rom_b = RoutingOperationMaterial(
        routing_operation_id=op.id,
        component_id=comp_x_template.id,
        quantity=Decimal("1"),
        unit="EA",
        is_variable=True,
    )
    db.add(rom_b)
    db.flush()

    # rom_c: fixed line
    rom_c = RoutingOperationMaterial(
        routing_operation_id=op.id,
        component_id=fixed_1.id,
        quantity=Decimal("2"),
        unit="EA",
        is_variable=False,
    )
    db.add(rom_c)
    db.flush()

    # rom_d: fixed line
    rom_d = RoutingOperationMaterial(
        routing_operation_id=op.id,
        component_id=fixed_2.id,
        quantity=Decimal("1"),
        unit="EA",
        is_variable=False,
    )
    db.add(rom_d)
    db.flush()

    # 6. Variant with v2 axis_selections metadata keyed by rom.id
    variant = make_product(
        sku=f"FG-MX-VAR-BLK-{uid}",
        name=f"FG Mixed-Axis Variant BLK {uid}",
        item_type="finished_good",
        unit="EA",
        cost_method="standard",
        standard_cost=Decimal("5.00"),
        selling_price=Decimal("15.00"),
        procurement_type="make",
        is_template=False,
        active=True,
        parent_product_id=template.id,
    )
    variant.variant_metadata = {
        "schema_version": 2,
        "axis_selections": {
            str(rom_a.id): {
                "type": "material_color",
                "label": "Color",
                "value": {
                    "material_type_id": pla_material_type.id,
                    "color_id": black_color.id,
                },
            },
            str(rom_b.id): {
                "type": "component_template",
                "label": "Variant",
                "value": {
                    "component_id": chosen_child.id,
                },
            },
        },
        "axis_count": 2,
    }
    db.flush()

    return {
        "template": template,
        "variant": variant,
        "expected_color_target_id": pla_blk_supply.id,
        "expected_component_target_id": chosen_child.id,
        "fixed_component_ids": [fixed_1.id, fixed_2.id],
    }
