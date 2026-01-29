"""
Smoke tests to verify test infrastructure (TestClient, factories, auth).
Run these first to confirm the test setup works.
"""
from decimal import Decimal


class TestDatabaseFixtures:
    """Verify DB session and seed data work."""

    def test_db_session_connects(self, db):
        from sqlalchemy import text
        result = db.execute(text("SELECT 1")).scalar()
        assert result == 1

    def test_seed_data_exists(self, db):
        from app.models.inventory import InventoryLocation
        from app.models.user import User
        from app.models.work_center import WorkCenter

        assert db.query(InventoryLocation).filter(InventoryLocation.id == 1).first() is not None
        assert db.query(User).filter(User.id == 1).first() is not None
        assert db.query(WorkCenter).filter(WorkCenter.id == 1).first() is not None

    def test_gl_accounts_seeded(self, db):
        from app.models.accounting import GLAccount

        for code in ["1300", "5000", "4000", "2000"]:
            acct = db.query(GLAccount).filter(GLAccount.account_code == code).first()
            assert acct is not None, f"GL account {code} not seeded"


class TestFactories:
    """Verify data factory fixtures create valid objects."""

    def test_make_product(self, make_product):
        product = make_product()
        assert product.id is not None
        assert product.sku.startswith("TEST-")

    def test_make_product_raw_material(self, make_product):
        raw = make_product(
            item_type="supply", unit="G",
            purchase_uom="KG", purchase_factor=Decimal("1000"),
            is_raw_material=True,
        )
        assert raw.unit == "G"
        assert raw.purchase_uom == "KG"
        assert raw.purchase_factor == Decimal("1000")

    def test_make_vendor(self, make_vendor):
        vendor = make_vendor()
        assert vendor.id is not None
        assert vendor.code.startswith("V-")

    def test_make_customer(self, make_customer):
        customer = make_customer()
        assert customer.id is not None
        assert customer.status == "active"

    def test_make_sales_order(self, make_sales_order, make_product):
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=5, unit_price=Decimal("10.00"))
        assert so.id is not None
        assert so.total_price == Decimal("50.00")
        assert so.grand_total == Decimal("50.00")

    def test_make_bom(self, make_product, make_bom):
        fg = make_product(item_type="finished_good", procurement_type="make")
        raw = make_product(item_type="supply", unit="G")
        bom = make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])
        assert bom.id is not None

    def test_convenience_fixtures(self, raw_material, finished_good):
        assert raw_material.unit == "G"
        assert raw_material.purchase_uom == "KG"
        assert finished_good.item_type == "finished_good"
        assert finished_good.standard_cost == Decimal("5.00")


class TestClientFixtures:
    """Verify FastAPI TestClient with auth works."""

    def test_authed_client_gets_200(self, client):
        response = client.get("/api/v1/system/health")
        assert response.status_code == 200

    def test_unauthed_client_gets_401(self, unauthed_client):
        # POST endpoints require auth — creating an item without token should fail
        response = unauthed_client.post("/api/v1/items", json={"sku": "TEST", "name": "Test"})
        assert response.status_code == 401
