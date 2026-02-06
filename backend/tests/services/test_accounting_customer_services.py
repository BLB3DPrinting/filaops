"""
Tests for app/services/customer_service.py

Covers:
- _build_full_name: Display name construction
- _get_customer_stats: Order/quote/spend stats
- _get_customer_or_404: Fetch-or-404 helper
- generate_customer_number: Sequence-based code generation
- list_customers: Listing with search and status filters
- search_customers: Lightweight autocomplete search
- get_customer_detail: Full customer detail with stats
- create_customer: Customer creation with validation
- update_customer: Partial-update with duplicate email check
- delete_customer: Soft-delete vs hard-delete logic
- get_customer_orders: Recent orders for a customer
- normalize_column_name: CSV column normalization
- map_row_to_fields: CSV row mapping with combined name / address fallback
- _detect_csv_format: Platform detection from column headers
- preview_customer_import: CSV preview with validation
- import_customers: CSV import with savepoint handling
"""
import uuid

import pytest
from decimal import Decimal
from fastapi import HTTPException

from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.services import customer_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _make_user_customer(db, *, email=None, first_name=None, last_name=None,
                        company_name=None, phone=None, status="active",
                        customer_number=None, **kwargs):
    """Create a User record with account_type='customer' for testing."""
    uid = _uid()
    user = User(
        customer_number=customer_number or f"CUST-T-{uid}",
        email=email or f"cust-{uid}@test.com",
        password_hash="not-real-hash",
        first_name=first_name,
        last_name=last_name,
        company_name=company_name,
        phone=phone,
        status=status,
        account_type="customer",
        email_verified=False,
        **kwargs,
    )
    db.add(user)
    db.flush()
    return user


# ===========================================================================
# _build_full_name
# ===========================================================================


class TestBuildFullName:
    """Unit tests for _build_full_name helper."""

    def test_first_and_last(self, db):
        user = _make_user_customer(db, first_name="Jane", last_name="Doe")
        assert customer_service._build_full_name(user) == "Jane Doe"

    def test_first_only(self, db):
        user = _make_user_customer(db, first_name="Jane")
        assert customer_service._build_full_name(user) == "Jane"

    def test_last_only(self, db):
        user = _make_user_customer(db, last_name="Doe")
        assert customer_service._build_full_name(user) == "Doe"

    def test_neither(self, db):
        user = _make_user_customer(db)
        assert customer_service._build_full_name(user) is None


# ===========================================================================
# _get_customer_or_404
# ===========================================================================


class TestGetCustomerOr404:
    """Tests for _get_customer_or_404."""

    def test_existing_customer(self, db):
        user = _make_user_customer(db, first_name="Found")
        result = customer_service._get_customer_or_404(db, user.id)
        assert result.id == user.id

    def test_missing_customer_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            customer_service._get_customer_or_404(db, 999999)
        assert exc_info.value.status_code == 404

    def test_non_customer_user_raises_404(self, db):
        """A user with account_type != 'customer' should not be found."""
        admin = User(
            email=f"admin-{_uid()}@test.com",
            password_hash="not-real",
            account_type="admin",
        )
        db.add(admin)
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            customer_service._get_customer_or_404(db, admin.id)
        assert exc_info.value.status_code == 404


# ===========================================================================
# generate_customer_number
# ===========================================================================


class TestGenerateCustomerNumber:
    """Tests for generate_customer_number."""

    def test_generates_formatted_number(self, db):
        num = customer_service.generate_customer_number(db)
        assert num.startswith("CUST-")
        # Extract numeric part
        seq = int(num.replace("CUST-", ""))
        assert seq >= 1

    def test_increments_from_existing(self, db):
        # Create a customer with a known number
        _make_user_customer(db, customer_number="CUST-050")
        num = customer_service.generate_customer_number(db)
        seq = int(num.replace("CUST-", ""))
        assert seq >= 51


# ===========================================================================
# create_customer
# ===========================================================================


class TestCreateCustomer:
    """Tests for create_customer."""

    def test_create_basic_customer(self, db):
        uid = _uid()
        data = CustomerCreate(
            email=f"new-{uid}@example.com",
            first_name="Alice",
            last_name="Smith",
        )
        result = customer_service.create_customer(db, data, admin_id=1)

        assert result["email"] == f"new-{uid}@example.com"
        assert result["first_name"] == "Alice"
        assert result["last_name"] == "Smith"
        assert result["customer_number"] is not None
        assert result["customer_number"].startswith("CUST-")
        assert result["order_count"] == 0
        assert result["total_spent"] == 0.0

    def test_create_with_full_address(self, db):
        uid = _uid()
        data = CustomerCreate(
            email=f"addr-{uid}@example.com",
            first_name="Bob",
            billing_address_line1="123 Main St",
            billing_city="Springfield",
            billing_state="IL",
            billing_zip="62701",
            shipping_address_line1="456 Oak Ave",
            shipping_city="Shelbyville",
            shipping_state="IL",
            shipping_zip="62565",
        )
        result = customer_service.create_customer(db, data, admin_id=1)

        assert result["billing_address_line1"] == "123 Main St"
        assert result["billing_city"] == "Springfield"
        assert result["shipping_address_line1"] == "456 Oak Ave"
        assert result["shipping_city"] == "Shelbyville"

    def test_create_duplicate_email_raises_400(self, db):
        uid = _uid()
        email = f"dup-{uid}@example.com"
        data = CustomerCreate(email=email, first_name="First")
        customer_service.create_customer(db, data, admin_id=1)

        data2 = CustomerCreate(email=email, first_name="Second")
        with pytest.raises(HTTPException) as exc_info:
            customer_service.create_customer(db, data2, admin_id=1)
        assert exc_info.value.status_code == 400
        assert "already registered" in exc_info.value.detail.lower()

    def test_create_defaults_to_active(self, db):
        uid = _uid()
        data = CustomerCreate(email=f"active-{uid}@example.com")
        result = customer_service.create_customer(db, data, admin_id=1)
        assert result["status"] == "active"


# ===========================================================================
# get_customer_detail
# ===========================================================================


class TestGetCustomerDetail:
    """Tests for get_customer_detail."""

    def test_returns_full_details(self, db):
        user = _make_user_customer(
            db, first_name="Detail", last_name="Test",
            company_name="Acme Corp",
        )
        result = customer_service.get_customer_detail(db, user.id)

        assert result["id"] == user.id
        assert result["first_name"] == "Detail"
        assert result["last_name"] == "Test"
        assert result["company_name"] == "Acme Corp"
        assert "order_count" in result
        assert "quote_count" in result
        assert "total_spent" in result

    def test_missing_customer_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            customer_service.get_customer_detail(db, 999999)
        assert exc_info.value.status_code == 404


# ===========================================================================
# update_customer
# ===========================================================================


class TestUpdateCustomer:
    """Tests for update_customer."""

    def test_partial_update(self, db):
        user = _make_user_customer(db, first_name="Old", last_name="Name")
        data = CustomerUpdate(first_name="New")
        result = customer_service.update_customer(db, user.id, data, admin_id=1)

        assert result["first_name"] == "New"
        assert result["last_name"] == "Name"  # unchanged

    def test_update_email(self, db):
        uid = _uid()
        user = _make_user_customer(db, email=f"old-{uid}@example.com")
        new_email = f"new-{uid}@example.com"
        data = CustomerUpdate(email=new_email)
        result = customer_service.update_customer(db, user.id, data, admin_id=1)

        assert result["email"] == new_email

    def test_update_email_duplicate_raises_400(self, db):
        uid = _uid()
        existing = _make_user_customer(db, email=f"taken-{uid}@example.com")
        target = _make_user_customer(db)

        data = CustomerUpdate(email=existing.email)
        with pytest.raises(HTTPException) as exc_info:
            customer_service.update_customer(db, target.id, data, admin_id=1)
        assert exc_info.value.status_code == 400
        assert "already in use" in exc_info.value.detail.lower()

    def test_update_missing_customer_raises_404(self, db):
        data = CustomerUpdate(first_name="Ghost")
        with pytest.raises(HTTPException) as exc_info:
            customer_service.update_customer(db, 999999, data, admin_id=1)
        assert exc_info.value.status_code == 404


# ===========================================================================
# delete_customer
# ===========================================================================


class TestDeleteCustomer:
    """Tests for delete_customer."""

    def test_hard_delete_no_orders(self, db):
        user = _make_user_customer(db, first_name="ToDelete")
        result = customer_service.delete_customer(db, user.id, admin_id=1)

        assert result["action"] == "deleted"
        assert result["order_count"] == 0

        # Verify actually deleted
        found = db.query(User).filter(User.id == user.id).first()
        assert found is None

    def test_soft_delete_with_orders(self, db, make_sales_order):
        user = _make_user_customer(db, first_name="WithOrders")
        make_sales_order(user_id=user.id, product_id=None, status="draft")

        result = customer_service.delete_customer(db, user.id, admin_id=1)

        assert result["action"] == "deactivated"
        assert result["order_count"] >= 1

        db.refresh(user)
        assert user.status == "inactive"

    def test_delete_missing_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            customer_service.delete_customer(db, 999999, admin_id=1)
        assert exc_info.value.status_code == 404


# ===========================================================================
# list_customers
# ===========================================================================


class TestListCustomers:
    """Tests for list_customers."""

    def test_returns_active_customers(self, db):
        _make_user_customer(db, first_name="Active1", status="active")
        _make_user_customer(db, first_name="Inactive1", status="inactive")

        results = customer_service.list_customers(db)
        # All returned should be active (default filter)
        statuses = {r["status"] for r in results}
        assert "inactive" not in statuses

    def test_include_inactive(self, db):
        _make_user_customer(db, first_name="Inactive2", status="inactive")

        results = customer_service.list_customers(db, include_inactive=True)
        statuses = {r["status"] for r in results}
        assert "inactive" in statuses

    def test_search_by_email(self, db):
        uid = _uid()
        email = f"findme-{uid}@example.com"
        _make_user_customer(db, email=email, first_name="FindMe")

        results = customer_service.list_customers(db, search=f"findme-{uid}")
        assert len(results) >= 1
        assert any(r["email"] == email for r in results)

    def test_search_by_name(self, db):
        uid = _uid()
        _make_user_customer(db, first_name=f"UniqueSearch{uid}")

        results = customer_service.list_customers(db, search=f"UniqueSearch{uid}")
        assert len(results) >= 1

    def test_status_filter(self, db):
        uid = _uid()
        _make_user_customer(db, first_name=f"Susp{uid}", status="suspended")

        results = customer_service.list_customers(db, status_filter="suspended")
        assert any(r["first_name"] == f"Susp{uid}" for r in results)

    def test_pagination(self, db):
        for _ in range(3):
            _make_user_customer(db)

        page1 = customer_service.list_customers(db, skip=0, limit=2)
        page2 = customer_service.list_customers(db, skip=2, limit=2)
        assert len(page1) <= 2
        if page2:
            ids_p1 = {r["id"] for r in page1}
            ids_p2 = {r["id"] for r in page2}
            assert ids_p1.isdisjoint(ids_p2)

    def test_result_includes_stats(self, db):
        user = _make_user_customer(db, first_name="StatsCheck")
        results = customer_service.list_customers(db, search="StatsCheck")
        if results:
            r = results[0]
            assert "order_count" in r
            assert "total_spent" in r
            assert "full_name" in r


# ===========================================================================
# search_customers
# ===========================================================================


class TestSearchCustomers:
    """Tests for search_customers (autocomplete)."""

    def test_search_by_email(self, db):
        uid = _uid()
        email = f"autocomplete-{uid}@example.com"
        _make_user_customer(db, email=email, first_name="Auto")

        results = customer_service.search_customers(db, query=f"autocomplete-{uid}")
        assert len(results) >= 1
        assert results[0]["email"] == email

    def test_search_by_company(self, db):
        uid = _uid()
        _make_user_customer(db, company_name=f"UniCorp-{uid}")

        results = customer_service.search_customers(db, query=f"UniCorp-{uid}")
        assert len(results) >= 1
        assert results[0]["company_name"] == f"UniCorp-{uid}"

    def test_search_returns_limited_fields(self, db):
        _make_user_customer(db, first_name="LimitedFields", last_name="Test")
        results = customer_service.search_customers(db, query="LimitedFields")
        if results:
            r = results[0]
            assert "id" in r
            assert "email" in r
            assert "full_name" in r
            assert "customer_number" in r

    def test_search_respects_limit(self, db):
        for _ in range(5):
            _make_user_customer(db, company_name=f"LimitTest-{_uid()}")

        results = customer_service.search_customers(db, query="LimitTest", limit=2)
        assert len(results) <= 2

    def test_search_only_active(self, db):
        uid = _uid()
        _make_user_customer(db, first_name=f"InactiveSearch{uid}", status="inactive")

        results = customer_service.search_customers(db, query=f"InactiveSearch{uid}")
        assert len(results) == 0


# ===========================================================================
# get_customer_orders
# ===========================================================================


class TestGetCustomerOrders:
    """Tests for get_customer_orders."""

    def test_returns_orders(self, db, make_sales_order):
        user = _make_user_customer(db, first_name="OrderGuy")
        so = make_sales_order(user_id=user.id, product_id=None, status="confirmed")

        orders = customer_service.get_customer_orders(db, user.id)
        assert len(orders) >= 1
        assert orders[0]["order_number"] == so.order_number
        assert orders[0]["status"] == "confirmed"

    def test_missing_customer_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            customer_service.get_customer_orders(db, 999999)
        assert exc_info.value.status_code == 404

    def test_respects_limit(self, db, make_sales_order):
        user = _make_user_customer(db, first_name="ManyOrders")
        for _ in range(5):
            make_sales_order(user_id=user.id, product_id=None)

        orders = customer_service.get_customer_orders(db, user.id, limit=3)
        assert len(orders) <= 3


# ===========================================================================
# normalize_column_name
# ===========================================================================


class TestNormalizeColumnName:
    """Tests for normalize_column_name."""

    def test_standard_mapping(self):
        assert customer_service.normalize_column_name("email") == "email"
        assert customer_service.normalize_column_name("First Name") == "first_name"
        assert customer_service.normalize_column_name("Billing City") == "billing_city"

    def test_case_insensitive(self):
        assert customer_service.normalize_column_name("EMAIL") == "email"
        assert customer_service.normalize_column_name("Email_Address") == "email"

    def test_strip_whitespace(self):
        assert customer_service.normalize_column_name("  email  ") == "email"

    def test_unknown_column_passthrough(self):
        """Unknown columns should be returned normalized but not mapped."""
        result = customer_service.normalize_column_name("Custom Field")
        assert result == "custom_field"

    def test_dash_to_underscore(self):
        assert customer_service.normalize_column_name("billing-city") == "billing_city"


# ===========================================================================
# map_row_to_fields
# ===========================================================================


class TestMapRowToFields:
    """Tests for map_row_to_fields."""

    def test_standard_fields(self):
        row = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "555-1234",
        }
        result = customer_service.map_row_to_fields(row)
        assert result["email"] == "test@example.com"
        assert result["first_name"] == "John"
        assert result["last_name"] == "Doe"
        assert result["phone"] == "555-1234"

    def test_combined_name_fallback(self):
        """When first/last are empty, combined name field is split."""
        row = {
            "email": "test@example.com",
            "name": "Jane Smith",
        }
        result = customer_service.map_row_to_fields(row)
        assert result["first_name"] == "Jane"
        assert result["last_name"] == "Smith"

    def test_combined_name_single_word(self):
        row = {
            "email": "test@example.com",
            "buyer_name": "Madonna",
        }
        result = customer_service.map_row_to_fields(row)
        assert result["first_name"] == "Madonna"
        assert result["last_name"] == ""

    def test_billing_to_shipping_copy(self):
        """If shipping is empty, billing should be copied to shipping."""
        row = {
            "email": "test@example.com",
            "billing_address_1": "123 Main St",
            "billing_city": "Springfield",
            "billing_state": "IL",
            "billing_zip": "62701",
        }
        result = customer_service.map_row_to_fields(row)
        assert result["shipping_address_line1"] == "123 Main St"
        assert result["shipping_city"] == "Springfield"
        assert result["shipping_state"] == "IL"
        assert result["shipping_zip"] == "62701"

    def test_no_billing_copy_when_shipping_exists(self):
        """If shipping is already provided, billing should not overwrite."""
        row = {
            "email": "test@example.com",
            "billing_address_1": "123 Main St",
            "shipping_address_1": "456 Oak Ave",
        }
        result = customer_service.map_row_to_fields(row)
        assert result["shipping_address_line1"] == "456 Oak Ave"

    def test_default_country(self):
        row = {"email": "test@example.com"}
        result = customer_service.map_row_to_fields(row)
        assert result["billing_country"] == "USA"
        assert result["shipping_country"] == "USA"

    def test_empty_values_ignored(self):
        row = {
            "email": "test@example.com",
            "first_name": "",
            "last_name": "   ",
        }
        result = customer_service.map_row_to_fields(row)
        assert result["first_name"] == ""
        assert result["last_name"] == ""

    def test_woocommerce_style_columns(self):
        row = {
            "billing_email": "woo@shop.com",
            "billing_first_name": "Woo",
            "billing_last_name": "Customer",
            "billing_company": "WooShop",
        }
        result = customer_service.map_row_to_fields(row)
        assert result["email"] == "woo@shop.com"
        assert result["first_name"] == "Woo"
        assert result["last_name"] == "Customer"
        assert result["company_name"] == "WooShop"

    def test_etsy_style_columns(self):
        row = {
            "buyer_email": "etsy@buyer.com",
            "ship_name": "Etsy Buyer",
            "ship_address1": "789 Craft Lane",
            "ship_city": "Portland",
            "ship_state": "OR",
            "ship_zip": "97201",
        }
        result = customer_service.map_row_to_fields(row)
        assert result["email"] == "etsy@buyer.com"
        assert result["first_name"] == "Etsy Buyer"


# ===========================================================================
# _detect_csv_format
# ===========================================================================


class TestDetectCsvFormat:
    """Tests for _detect_csv_format."""

    def test_woocommerce(self):
        headers = ["billing_first_name", "billing_last_name", "billing_email"]
        assert customer_service._detect_csv_format(headers) == "WooCommerce"

    def test_shopify(self):
        headers = ["First Name", "Last Name", "Email", "Company"]
        assert customer_service._detect_csv_format(headers) == "Shopify"

    def test_etsy(self):
        headers = ["buyer_email", "ship_name", "ship_address1"]
        assert customer_service._detect_csv_format(headers) == "Etsy/TikTok Shop"

    def test_tiktok(self):
        headers = ["email", "unit_price", "cost_price"]
        assert customer_service._detect_csv_format(headers) == "TikTok Shop"

    def test_generic(self):
        headers = ["email", "name", "phone"]
        assert customer_service._detect_csv_format(headers) == "Generic/Squarespace"

    def test_unknown(self):
        headers = ["foo", "bar", "baz"]
        assert customer_service._detect_csv_format(headers) == "Unknown"


# ===========================================================================
# preview_customer_import
# ===========================================================================


class TestPreviewCustomerImport:
    """Tests for preview_customer_import."""

    def test_valid_csv(self, db):
        csv_text = "email,first_name,last_name\njohn@example.com,John,Doe\njane@example.com,Jane,Smith\n"
        result = customer_service.preview_customer_import(db, csv_text)

        assert result["total_rows"] == 2
        assert result["valid_rows"] == 2
        assert result["error_rows"] == 0
        assert result["truncated"] is False

    def test_missing_email(self, db):
        csv_text = "email,first_name\n,John\njane@example.com,Jane\n"
        result = customer_service.preview_customer_import(db, csv_text)

        assert result["total_rows"] == 2
        assert result["error_rows"] >= 1
        # The row without email should have an error
        first_row = result["rows"][0]
        assert first_row["valid"] is False
        assert any("required" in e.lower() for e in first_row["errors"])

    def test_invalid_email(self, db):
        csv_text = "email,first_name\nbademail,John\n"
        result = customer_service.preview_customer_import(db, csv_text)

        assert result["error_rows"] >= 1
        row = result["rows"][0]
        assert row["valid"] is False
        assert any("invalid" in e.lower() for e in row["errors"])

    def test_duplicate_email_in_csv(self, db):
        csv_text = "email,first_name\ndup@example.com,First\ndup@example.com,Second\n"
        result = customer_service.preview_customer_import(db, csv_text)

        # First row valid, second row should be flagged as duplicate
        assert result["rows"][0]["valid"] is True
        assert result["rows"][1]["valid"] is False
        assert any("duplicate" in e.lower() for e in result["rows"][1]["errors"])

    def test_existing_email_in_db(self, db):
        uid = _uid()
        email = f"existing-{uid}@example.com"
        _make_user_customer(db, email=email)

        csv_text = f"email,first_name\n{email},Existing\n"
        result = customer_service.preview_customer_import(db, csv_text)

        assert result["error_rows"] >= 1
        assert any("already exists" in e.lower() for e in result["rows"][0]["errors"])

    def test_detected_format(self, db):
        csv_text = "billing_first_name,billing_last_name,billing_email\nJohn,Doe,john@shop.com\n"
        result = customer_service.preview_customer_import(db, csv_text)
        assert result["detected_format"] == "WooCommerce"

    def test_truncated_flag(self, db):
        # Create CSV with fewer than 100 rows
        csv_text = "email,first_name\n" + "".join(
            f"user{i}@example.com,User{i}\n" for i in range(5)
        )
        result = customer_service.preview_customer_import(db, csv_text)
        assert result["truncated"] is False


# ===========================================================================
# import_customers
# ===========================================================================


class TestImportCustomers:
    """Tests for import_customers."""

    def test_basic_import(self, db):
        uid = _uid()
        csv_text = f"email,first_name,last_name\nimport-{uid}@example.com,Import,Test\n"
        result = customer_service.import_customers(db, csv_text, admin_id=1)

        assert result["imported"] == 1
        assert result["skipped"] == 0
        assert "successfully imported 1" in result["message"].lower()

        # Verify the user was created in the DB
        user = db.query(User).filter(User.email == f"import-{uid}@example.com").first()
        assert user is not None
        assert user.account_type == "customer"
        assert user.first_name == "Import"
        assert user.last_name == "Test"

    def test_import_skips_invalid_email(self, db):
        csv_text = "email,first_name\nbademail,BadGuy\n"
        result = customer_service.import_customers(db, csv_text, admin_id=1)

        assert result["imported"] == 0
        assert result["skipped"] == 1
        assert len(result["errors"]) >= 1

    def test_import_skips_existing_email(self, db):
        uid = _uid()
        email = f"preexist-{uid}@example.com"
        _make_user_customer(db, email=email)

        csv_text = f"email,first_name\n{email},Existing\n"
        result = customer_service.import_customers(db, csv_text, admin_id=1)

        assert result["imported"] == 0
        assert result["skipped"] == 1

    def test_import_multiple_rows(self, db):
        uid = _uid()
        csv_text = (
            "email,first_name,last_name\n"
            f"multi1-{uid}@example.com,Alice,One\n"
            f"multi2-{uid}@example.com,Bob,Two\n"
            f"multi3-{uid}@example.com,Carol,Three\n"
        )
        result = customer_service.import_customers(db, csv_text, admin_id=1)

        assert result["imported"] == 3
        assert result["skipped"] == 0

    def test_import_mixed_valid_invalid(self, db):
        uid = _uid()
        csv_text = (
            "email,first_name\n"
            f"good-{uid}@example.com,Good\n"
            "noemail,Bad\n"
            f"also-good-{uid}@example.com,AlsoGood\n"
        )
        result = customer_service.import_customers(db, csv_text, admin_id=1)

        assert result["imported"] == 2
        assert result["skipped"] == 1

    def test_import_message_with_errors(self, db):
        csv_text = "email,first_name\nbademail,Bad\n"
        result = customer_service.import_customers(db, csv_text, admin_id=1)

        assert "skipped" in result["message"].lower()

    def test_import_assigns_customer_number(self, db):
        uid = _uid()
        csv_text = f"email,first_name\nimportnum-{uid}@example.com,NumCheck\n"
        customer_service.import_customers(db, csv_text, admin_id=1)

        user = db.query(User).filter(User.email == f"importnum-{uid}@example.com").first()
        assert user is not None
        assert user.customer_number is not None
        assert user.customer_number.startswith("CUST-")

    def test_import_with_woocommerce_columns(self, db):
        uid = _uid()
        csv_text = (
            "billing_email,billing_first_name,billing_last_name,billing_company\n"
            f"woo-{uid}@shop.com,Woo,Customer,WooShop\n"
        )
        result = customer_service.import_customers(db, csv_text, admin_id=1)
        assert result["imported"] == 1

        user = db.query(User).filter(User.email == f"woo-{uid}@shop.com").first()
        assert user is not None
        assert user.first_name == "Woo"
        assert user.last_name == "Customer"
        assert user.company_name == "WooShop"
