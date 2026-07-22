"""
Tests for Routings API endpoints.

Covers:
- Routing CRUD (list, create, get, get-by-product, update, delete)
- Template seeding and application
- Routing operations CRUD (list, create, update, delete)
- Routing operation materials CRUD (list, create, update, delete)
- Manufacturing BOM view
- Authentication requirements for write endpoints
- 404 and 422 error handling
"""
import threading
import pytest
from decimal import Decimal

from tests.services._operation_type_seed import seed_operation_types as _seed_operation_types


BASE_URL = "/api/v1/routings"


# =============================================================================
# Helpers
# =============================================================================

def _create_routing(client, product_id=None, **overrides):
    """Create a routing via the API and assert success."""
    payload = {
        "product_id": product_id,
        "description": "Test routing",
        "is_active": True,
    }
    payload.update(overrides)
    response = client.post(BASE_URL, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_operation(client, routing_id, **overrides):
    """Create a routing operation via the API and assert success."""
    payload = {
        "work_center_id": 1,
        "sequence": 10,
        "operation_code": "OP10",
        "operation_name": "Test Operation",
        "setup_time_minutes": "5.0",
        "run_time_minutes": "2.0",
    }
    payload.update(overrides)
    response = client.post(f"{BASE_URL}/{routing_id}/operations", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_material(client, operation_id, component_id, **overrides):
    """Create a routing operation material via the API and assert success."""
    payload = {
        "component_id": component_id,
        "quantity": "10.0",
        "unit": "G",
    }
    payload.update(overrides)
    response = client.post(
        f"{BASE_URL}/operations/{operation_id}/materials", json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


# =============================================================================
# Authentication — write endpoints require auth
# =============================================================================

class TestRoutingAuthRequired:
    """Verify write endpoints return 401 without authentication."""

    def test_create_routing_requires_auth(self, unauthed_client):
        response = unauthed_client.post(BASE_URL, json={
            "product_id": 1, "is_active": True,
        })
        assert response.status_code == 401

    def test_update_routing_requires_auth(self, unauthed_client):
        response = unauthed_client.put(f"{BASE_URL}/1", json={"notes": "x"})
        assert response.status_code == 401

    def test_delete_routing_requires_auth(self, unauthed_client):
        response = unauthed_client.delete(f"{BASE_URL}/1")
        assert response.status_code == 401

    def test_seed_templates_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/seed-templates")
        assert response.status_code == 401

    def test_apply_template_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/apply-template", json={
            "template_id": 1, "product_id": 1,
        })
        assert response.status_code == 401

    def test_create_operation_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/1/operations", json={
            "work_center_id": 1, "sequence": 10, "run_time_minutes": "5.0",
        })
        assert response.status_code == 401

    def test_update_operation_requires_auth(self, unauthed_client):
        response = unauthed_client.put(
            f"{BASE_URL}/operations/1", json={"sequence": 20}
        )
        assert response.status_code == 401

    def test_delete_operation_requires_auth(self, unauthed_client):
        response = unauthed_client.delete(f"{BASE_URL}/operations/1")
        assert response.status_code == 401

    def test_create_material_requires_auth(self, unauthed_client):
        response = unauthed_client.post(
            f"{BASE_URL}/operations/1/materials",
            json={"component_id": 1, "quantity": "5", "unit": "EA"},
        )
        assert response.status_code == 401

    def test_update_material_requires_auth(self, unauthed_client):
        response = unauthed_client.put(
            f"{BASE_URL}/materials/1", json={"quantity": "10"}
        )
        assert response.status_code == 401

    def test_delete_material_requires_auth(self, unauthed_client):
        response = unauthed_client.delete(f"{BASE_URL}/materials/1")
        assert response.status_code == 401


# =============================================================================
# List Routings — GET /api/v1/routings/
# =============================================================================

class TestListRoutings:
    """Tests for listing routings with filters."""

    def test_list_routings_returns_200(self, client):
        response = client.get(f"{BASE_URL}/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_routings_includes_created(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        response = client.get(f"{BASE_URL}/")
        assert response.status_code == 200

        ids = [r["id"] for r in response.json()]
        assert routing["id"] in ids

    def test_list_routings_filter_by_product_id(self, client, make_product):
        p1 = make_product(item_type="finished_good", procurement_type="make")
        p2 = make_product(item_type="finished_good", procurement_type="make")

        r1 = _create_routing(client, product_id=p1.id)
        _create_routing(client, product_id=p2.id)

        response = client.get(f"{BASE_URL}/", params={"product_id": p1.id})
        assert response.status_code == 200

        data = response.json()
        assert len(data) >= 1
        for r in data:
            assert r["product_id"] == p1.id

    def test_list_routings_templates_only(self, client):
        _create_routing(
            client,
            is_template=True,
            code="TPL-TEST-FILTER",
            name="Template Filter Test",
        )

        response = client.get(f"{BASE_URL}/", params={"templates_only": True})
        assert response.status_code == 200

        data = response.json()
        for r in data:
            assert r["is_template"] is True

    def test_list_routings_active_only_default(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        # Deactivate routing
        client.delete(f"{BASE_URL}/{routing['id']}")

        response = client.get(f"{BASE_URL}/")
        assert response.status_code == 200

        ids = [r["id"] for r in response.json()]
        assert routing["id"] not in ids

    def test_list_routings_include_inactive(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        client.delete(f"{BASE_URL}/{routing['id']}")

        response = client.get(f"{BASE_URL}/", params={"active_only": False})
        assert response.status_code == 200

        ids = [r["id"] for r in response.json()]
        assert routing["id"] in ids

    def test_list_routings_search_by_code(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(
            client, product_id=product.id, code="RTG-SEARCHABLE-XYZ"
        )

        response = client.get(
            f"{BASE_URL}/", params={"search": "SEARCHABLE-XYZ"}
        )
        assert response.status_code == 200

        ids = [r["id"] for r in response.json()]
        assert routing["id"] in ids

    def test_list_routings_skip_and_limit(self, client, make_product):
        products = [
            make_product(item_type="finished_good", procurement_type="make")
            for _ in range(3)
        ]
        for p in products:
            _create_routing(client, product_id=p.id)

        response = client.get(f"{BASE_URL}/", params={"skip": 0, "limit": 1})
        assert response.status_code == 200
        assert len(response.json()) <= 1


# =============================================================================
# Create Routing — POST /api/v1/routings/
# =============================================================================

class TestCreateRouting:
    """Tests for creating routings."""

    def test_create_product_routing(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")

        data = _create_routing(client, product_id=product.id)

        assert data["product_id"] == product.id
        assert data["is_active"] is True
        assert data["is_template"] is False
        assert data["code"] is not None

    def test_create_routing_auto_generates_code(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")

        data = _create_routing(client, product_id=product.id)

        assert product.sku in data["code"]

    def test_create_routing_with_explicit_code(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")

        data = _create_routing(
            client, product_id=product.id, code="CUSTOM-RTG-001"
        )

        assert data["code"] == "CUSTOM-RTG-001"

    def test_create_template_routing(self, client):
        data = _create_routing(
            client,
            is_template=True,
            code="TPL-UNIT-TEST",
            name="Unit Test Template",
        )

        assert data["is_template"] is True
        assert data["product_id"] is None
        assert data["code"] == "TPL-UNIT-TEST"

    def test_create_template_requires_code(self, client):
        response = client.post(BASE_URL, json={
            "is_template": True,
            "name": "Missing Code Template",
        })
        assert response.status_code == 400

    def test_create_template_requires_name(self, client):
        response = client.post(BASE_URL, json={
            "is_template": True,
            "code": "TPL-NONAME",
        })
        assert response.status_code == 400

    def test_create_non_template_requires_product_id(self, client):
        response = client.post(BASE_URL, json={
            "is_template": False,
            "is_active": True,
        })
        assert response.status_code == 400

    def test_create_routing_product_not_found(self, client):
        response = client.post(BASE_URL, json={
            "product_id": 999999,
            "is_active": True,
        })
        assert response.status_code == 404

    def test_create_routing_with_inline_operations(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")

        data = _create_routing(
            client,
            product_id=product.id,
            operations=[
                {
                    "work_center_id": 1,
                    "sequence": 10,
                    "operation_code": "OP10",
                    "operation_name": "Print",
                    "run_time_minutes": "60.0",
                    "setup_time_minutes": "5.0",
                },
            ],
        )

        assert len(data["operations"]) == 1
        assert data["operations"][0]["operation_code"] == "OP10"

    def test_create_routing_invalid_work_center_in_operations(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")

        response = client.post(BASE_URL, json={
            "product_id": product.id,
            "is_active": True,
            "operations": [
                {
                    "work_center_id": 999999,
                    "sequence": 10,
                    "run_time_minutes": "5.0",
                },
            ],
        })
        assert response.status_code == 400

    def test_create_routing_missing_run_time_returns_422(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")

        response = client.post(BASE_URL, json={
            "product_id": product.id,
            "is_active": True,
            "operations": [
                {
                    "work_center_id": 1,
                    "sequence": 10,
                    # run_time_minutes is required
                },
            ],
        })
        assert response.status_code == 422


# =============================================================================
# Get Routing — GET /api/v1/routings/{routing_id}
# =============================================================================

class TestGetRouting:
    """Tests for retrieving a single routing."""

    def test_get_routing_success(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        response = client.get(f"{BASE_URL}/{routing['id']}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == routing["id"]
        assert data["product_id"] == product.id
        assert data["product_sku"] == product.sku

    def test_get_routing_not_found(self, client):
        response = client.get(f"{BASE_URL}/999999")
        assert response.status_code == 404

    def test_get_routing_includes_operations(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)
        _create_operation(client, routing["id"])

        response = client.get(f"{BASE_URL}/{routing['id']}")
        assert response.status_code == 200

        data = response.json()
        assert len(data["operations"]) == 1
        assert data["operations"][0]["operation_code"] == "OP10"


# =============================================================================
# Get Routing by Product — GET /api/v1/routings/product/{product_id}
# =============================================================================

class TestGetRoutingByProduct:
    """Tests for retrieving routing by product ID."""

    def test_get_routing_by_product_success(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        response = client.get(f"{BASE_URL}/product/{product.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == routing["id"]
        assert data["product_id"] == product.id

    def test_get_routing_by_product_not_found(self, client):
        response = client.get(f"{BASE_URL}/product/999999")
        assert response.status_code == 404

    def test_get_routing_by_product_no_active_routing(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        # Soft delete (deactivate) the routing
        client.delete(f"{BASE_URL}/{routing['id']}")

        response = client.get(f"{BASE_URL}/product/{product.id}")
        assert response.status_code == 404


# =============================================================================
# Update Routing — PUT /api/v1/routings/{routing_id}
# =============================================================================

class TestUpdateRouting:
    """Tests for updating a routing."""

    def test_update_routing_notes(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        response = client.put(
            f"{BASE_URL}/{routing['id']}", json={"notes": "Updated notes"}
        )
        assert response.status_code == 200
        assert response.json()["notes"] == "Updated notes"

    def test_update_routing_revision(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        response = client.put(
            f"{BASE_URL}/{routing['id']}", json={"revision": "2.0"}
        )
        assert response.status_code == 200
        assert response.json()["revision"] == "2.0"

    def test_update_routing_not_found(self, client):
        response = client.put(f"{BASE_URL}/999999", json={"notes": "nope"})
        assert response.status_code == 404

    def test_update_routing_deactivate(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        response = client.put(
            f"{BASE_URL}/{routing['id']}", json={"is_active": False}
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False


# =============================================================================
# Delete Routing — DELETE /api/v1/routings/{routing_id}
# =============================================================================

class TestDeleteRouting:
    """Tests for routing deletion (soft delete)."""

    def test_delete_routing_returns_204(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        response = client.delete(f"{BASE_URL}/{routing['id']}")
        assert response.status_code == 204

    def test_delete_routing_soft_deletes(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        client.delete(f"{BASE_URL}/{routing['id']}")

        # Should still exist but inactive
        response = client.get(f"{BASE_URL}/{routing['id']}")
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_delete_routing_not_found(self, client):
        response = client.delete(f"{BASE_URL}/999999")
        assert response.status_code == 404


# =============================================================================
# Seed Templates — POST /api/v1/routings/seed-templates
# =============================================================================

class TestSeedTemplates:
    """Tests for seeding default routing templates.

    Note: This endpoint requires specific work centers (FDM-POOL, QC,
    ASSEMBLY, SHIPPING) to be present. The default test database only
    seeds TEST-WC (id=1), so these tests verify the expected 400 error
    when work centers are missing.
    """

    def test_seed_templates_missing_work_centers(self, client):
        response = client.post(f"{BASE_URL}/seed-templates")
        assert response.status_code == 400
        assert "Missing required work centers" in response.json()["detail"]


# =============================================================================
# Apply Template — POST /api/v1/routings/apply-template
# =============================================================================

class TestApplyTemplate:
    """Tests for applying a routing template to a product."""

    def test_apply_template_not_found(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")

        response = client.post(f"{BASE_URL}/apply-template", json={
            "template_id": 999999,
            "product_id": product.id,
        })
        assert response.status_code == 404

    def test_apply_template_product_not_found(self, client, make_product):
        # Create a template routing first
        template = _create_routing(
            client,
            is_template=True,
            code="TPL-APPLY-TEST",
            name="Apply Test Template",
        )
        _create_operation(client, template["id"])

        response = client.post(f"{BASE_URL}/apply-template", json={
            "template_id": template["id"],
            "product_id": 999999,
        })
        assert response.status_code == 404

    def test_apply_template_success(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")

        # Create template with an operation
        template = _create_routing(
            client,
            is_template=True,
            code="TPL-APPLY-OK",
            name="Apply OK Template",
        )
        _create_operation(
            client,
            template["id"],
            operation_code="PRINT",
            operation_name="3D Print",
            run_time_minutes="60.0",
        )

        response = client.post(f"{BASE_URL}/apply-template", json={
            "template_id": template["id"],
            "product_id": product.id,
        })
        assert response.status_code == 200

        data = response.json()
        assert data["product_sku"] == product.sku
        assert data["routing_id"] is not None
        assert len(data["operations"]) == 1
        assert data["operations"][0]["operation_code"] == "PRINT"

    def test_apply_template_with_overrides(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")

        template = _create_routing(
            client,
            is_template=True,
            code="TPL-OVERRIDE",
            name="Override Template",
        )
        _create_operation(
            client,
            template["id"],
            operation_code="PRINT",
            operation_name="3D Print",
            run_time_minutes="60.0",
            setup_time_minutes="7.0",
        )

        response = client.post(f"{BASE_URL}/apply-template", json={
            "template_id": template["id"],
            "product_id": product.id,
            "overrides": [
                {
                    "operation_code": "PRINT",
                    "run_time_minutes": "45.0",
                },
            ],
        })
        assert response.status_code == 200

        data = response.json()
        print_op = data["operations"][0]
        assert Decimal(str(print_op["run_time_minutes"])) == Decimal("45.0")

    def test_apply_template_creates_routing_for_product(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")

        template = _create_routing(
            client,
            is_template=True,
            code="TPL-CREATE-CHECK",
            name="Create Check Template",
        )
        _create_operation(client, template["id"], run_time_minutes="30.0")

        client.post(f"{BASE_URL}/apply-template", json={
            "template_id": template["id"],
            "product_id": product.id,
        })

        # Verify routing exists for the product
        response = client.get(f"{BASE_URL}/product/{product.id}")
        assert response.status_code == 200
        assert response.json()["product_id"] == product.id

    def test_apply_template_missing_fields_returns_422(self, client):
        response = client.post(f"{BASE_URL}/apply-template", json={})
        assert response.status_code == 422


class TestApplyTemplateIdempotency:
    """Regression coverage for #904 — apply-template must never silently
    append a second generation of operations onto an already-populated
    routing. Root cause: apply_template_to_product's "does this product
    already have an active routing?" check-then-act (deactivate old ops,
    then insert new ones) was not atomic, so two overlapping calls for the
    same product could each pass the check against the same pre-mutation
    state and each insert their own active operation set — reproducing the
    exact COMP-005 data shape (two interleaved active generations on one
    routing; see #904 and the #876 classifier session).
    """

    def test_repeated_apply_template_does_not_double_active_ops(self, client, make_product):
        """Applying the same template twice must leave the active op count
        unchanged (replace semantics), not doubled."""
        product = make_product(item_type="finished_good", procurement_type="make")

        template = _create_routing(
            client, is_template=True, code="TPL-IDEMPOTENT", name="Idempotent Template",
        )
        _create_operation(
            client, template["id"], operation_code="PRINT", operation_name="3D Print",
            sequence=10, run_time_minutes="60.0",
        )
        _create_operation(
            client, template["id"], operation_code="QC", operation_name="QC",
            sequence=20, run_time_minutes="2.0",
        )

        r1 = client.post(f"{BASE_URL}/apply-template", json={
            "template_id": template["id"], "product_id": product.id,
        })
        assert r1.status_code == 200, r1.text
        assert len(r1.json()["operations"]) == 2

        r2 = client.post(f"{BASE_URL}/apply-template", json={
            "template_id": template["id"], "product_id": product.id,
        })
        assert r2.status_code == 200, r2.text
        assert len(r2.json()["operations"]) == 2

        routing_id = r2.json()["routing_id"]
        active_ops = client.get(f"{BASE_URL}/{routing_id}/operations").json()
        assert len(active_ops) == 2, (
            f"expected 2 active ops after repeated apply-template, got {len(active_ops)}"
        )

    def test_apply_template_replaces_manually_built_operations(self, client, make_product):
        """Applying a template onto a routing that already has operations
        (built by any other origin — manual add, an older process, etc.)
        must deactivate the old ones, not leave them active alongside the
        new set."""
        product = make_product(item_type="finished_good", procurement_type="make")

        routing = _create_routing(client, product_id=product.id)
        _create_operation(client, routing["id"], operation_code="QC", operation_name="QC", sequence=1)
        _create_operation(client, routing["id"], operation_code="PRINT", operation_name="3D Print", sequence=2)

        template = _create_routing(
            client, is_template=True, code="TPL-REPLACE", name="Replace Template",
        )
        _create_operation(
            client, template["id"], operation_code="PRINT", operation_name="3D Print",
            run_time_minutes="60.0",
        )
        _create_operation(
            client, template["id"], operation_code="ASSEMBLE", operation_name="Assembly",
            sequence=20, run_time_minutes="5.0",
        )

        response = client.post(f"{BASE_URL}/apply-template", json={
            "template_id": template["id"], "product_id": product.id,
        })
        assert response.status_code == 200, response.text

        active_ops = client.get(f"{BASE_URL}/{routing['id']}/operations").json()
        assert len(active_ops) == 2, (
            f"expected the manually-built ops to be replaced (2 active), got {len(active_ops)}"
        )
        assert {op["operation_code"] for op in active_ops} == {"PRINT", "ASSEMBLE"}

    def test_apply_template_concurrent_double_submit_no_duplicate_active_ops(self):
        """Two overlapping 'apply template' calls for the same product must
        not both leave their operation set active — this is the literal
        #904 reproduction (double-click / retry-after-timeout on
        POST /apply-template). Uses two independent, really-committing
        sessions (the transactional `db`/`client` fixtures share a single
        connection and can't model real concurrency) synchronized with a
        barrier planted at the actual check-then-act boundary (the SQL read
        of the existing routing, immediately before the deactivate
        mutation) rather than at the earlier Product lookup — see the
        comment block at the barrier definition for why placement matters
        and how the FOR UPDATE fix changes which worker ever reaches it.
        """
        from sqlalchemy import event

        from app.db.session import SessionLocal, engine
        from app.models.manufacturing import Routing, RoutingOperation
        from app.models.product import Product
        from app.services import routing_service as rs

        setup_db = SessionLocal()
        try:
            product = Product(
                sku="TEST-904-RACE-PROD", name="904 Race Product",
                item_type="finished_good", procurement_type="make", unit="EA",
                active=True,
            )
            setup_db.add(product)
            setup_db.flush()

            template = Routing(
                code="TPL-904-RACE", name="904 Race Template", is_template=True,
                version=1, revision="1.0", is_active=True,
            )
            setup_db.add(template)
            setup_db.flush()

            setup_db.add_all([
                RoutingOperation(
                    routing_id=template.id, work_center_id=1, sequence=10,
                    operation_code="PRINT", operation_name="3D Print",
                    run_time_minutes=Decimal("60"), setup_time_minutes=Decimal("0"),
                ),
                RoutingOperation(
                    routing_id=template.id, work_center_id=1, sequence=20,
                    operation_code="QC", operation_name="QC",
                    run_time_minutes=Decimal("2"), setup_time_minutes=Decimal("0"),
                ),
            ])
            setup_db.flush()
            setup_db.commit()

            product_id = product.id
            template_id = template.id
        finally:
            setup_db.close()

        try:
            # Generation 1 — establishes the "already has an active routing"
            # precondition the race needs (non-racy, sequential call).
            db1 = SessionLocal()
            try:
                rs.apply_template_to_product(db1, template_id=template_id, product_id=product_id)
            finally:
                db1.close()

            # Race: two overlapping "apply template again" calls.
            #
            # SYNCHRONIZATION POINT: the barrier fires on the SQL that reads
            # the *existing* active routing for this product — the
            # check-then-act read, immediately before the "deactivate old
            # ops" mutation. This is deliberately NOT the earlier Product
            # lookup: a barrier planted before the #904 FOR UPDATE row lock
            # only guarantees both threads *start* together, and then lets
            # the OS scheduler decide how far each gets before the other is
            # scheduled again. One worker can legitimately run all the way
            # through read -> deactivate -> insert -> commit before the
            # other thread is even scheduled, which would let a broken
            # (unlocked) implementation pass this test by luck rather than
            # by having its race genuinely exercised. Hooking the SQL
            # emission for the "existing routing" read (via
            # before_cursor_execute, matched by table + absence of the
            # is_template filter that's unique to the earlier template
            # lookup) forces both threads to reach the actual vulnerable
            # window together.
            #
            # CRITICAL SUBTLETY: with the #904 FOR UPDATE fix in place, the
            # second worker blocks *at the row lock itself* — a statement
            # that runs BEFORE the one this barrier watches — while the
            # first worker holds it through its whole transaction. So under
            # FIXED code the second worker can never reach this barrier
            # while the first is still inside its transaction: the first
            # worker's barrier.wait() times out / raises
            # BrokenBarrierError (expected — the assertions below, not the
            # barrier, are the real oracle), the first worker proceeds and
            # commits, the lock releases, and only then does the second
            # worker reach its own (now-broken, so non-blocking) barrier
            # call and run serialized against the first's already-committed
            # state. Under UNFIXED (unlocked) code there's no lock to
            # stall on, so both workers reach the barrier together, both
            # proceed to deactivate+insert concurrently, and the final
            # active-op-count assertion below catches the duplication.
            barrier = threading.Barrier(2)
            thread_state = threading.local()

            def sync_on_existing_routing_read(conn, cursor, statement, parameters, context, executemany):
                upper = statement.upper()
                if "ROUTINGS" not in upper or "IS_TEMPLATE" in upper:
                    return
                if getattr(thread_state, "fired", False):
                    return
                thread_state.fired = True
                try:
                    barrier.wait(timeout=5)
                except threading.BrokenBarrierError:
                    pass  # expected under FIXED code — see comment block above

            errors = []

            def worker():
                db = SessionLocal()
                try:
                    rs.apply_template_to_product(
                        db, template_id=template_id, product_id=product_id,
                    )
                except Exception as e:  # noqa: BLE001
                    errors.append(repr(e))
                finally:
                    db.close()

            event.listen(engine, "before_cursor_execute", sync_on_existing_routing_read)
            try:
                t1 = threading.Thread(target=worker)
                t2 = threading.Thread(target=worker)
                t1.start()
                t2.start()
                t1.join(timeout=30)
                t2.join(timeout=30)
            finally:
                event.remove(engine, "before_cursor_execute", sync_on_existing_routing_read)

            assert not t1.is_alive(), "worker thread 1 did not complete within timeout (hung)"
            assert not t2.is_alive(), "worker thread 2 did not complete within timeout (hung)"
            assert not errors, f"apply_template_to_product raised under race: {errors}"

            verify_db = SessionLocal()
            try:
                routing = verify_db.query(Routing).filter(
                    Routing.product_id == product_id, Routing.is_active.is_(True)
                ).first()
                active_ops = verify_db.query(RoutingOperation).filter(
                    RoutingOperation.routing_id == routing.id,
                    RoutingOperation.is_active.is_(True),
                ).count()
                assert active_ops == 2, (
                    f"expected 2 active ops after concurrent double-submit, got {active_ops} "
                    f"(#904 regression: two generations left active)"
                )
            finally:
                verify_db.close()
        finally:
            cleanup_db = SessionLocal()
            try:
                routing_ids = [
                    r.id for r in cleanup_db.query(Routing).filter(
                        (Routing.product_id == product_id) | (Routing.id == template_id)
                    ).all()
                ]
                if routing_ids:
                    cleanup_db.query(RoutingOperation).filter(
                        RoutingOperation.routing_id.in_(routing_ids)
                    ).delete(synchronize_session=False)
                    cleanup_db.query(Routing).filter(
                        Routing.id.in_(routing_ids)
                    ).delete(synchronize_session=False)
                cleanup_db.query(Product).filter(Product.id == product_id).delete(synchronize_session=False)
                cleanup_db.commit()
            finally:
                cleanup_db.close()


# =============================================================================
# List Operations — GET /api/v1/routings/{routing_id}/operations
# =============================================================================

class TestListOperations:
    """Tests for listing operations on a routing."""

    def test_list_operations_empty(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        response = client.get(f"{BASE_URL}/{routing['id']}/operations")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_operations_returns_created(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])

        response = client.get(f"{BASE_URL}/{routing['id']}/operations")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == op["id"]

    def test_list_operations_routing_not_found(self, client):
        response = client.get(f"{BASE_URL}/999999/operations")
        assert response.status_code == 404

    def test_list_operations_ordered_by_sequence(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        _create_operation(
            client, routing["id"],
            sequence=20, operation_code="OP20", run_time_minutes="3.0",
        )
        _create_operation(
            client, routing["id"],
            sequence=10, operation_code="OP10", run_time_minutes="5.0",
        )

        response = client.get(f"{BASE_URL}/{routing['id']}/operations")
        assert response.status_code == 200

        data = response.json()
        assert data[0]["sequence"] <= data[1]["sequence"]

    def test_list_operations_excludes_inactive_by_default(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])

        # Soft-delete the operation
        client.delete(f"{BASE_URL}/operations/{op['id']}")

        response = client.get(f"{BASE_URL}/{routing['id']}/operations")
        assert response.status_code == 200

        ids = [o["id"] for o in response.json()]
        assert op["id"] not in ids

    def test_list_operations_include_inactive(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])

        client.delete(f"{BASE_URL}/operations/{op['id']}")

        response = client.get(
            f"{BASE_URL}/{routing['id']}/operations",
            params={"active_only": False},
        )
        assert response.status_code == 200

        ids = [o["id"] for o in response.json()]
        assert op["id"] in ids


# =============================================================================
# Create Operation — POST /api/v1/routings/{routing_id}/operations
# =============================================================================

class TestCreateOperation:
    """Tests for adding operations to a routing."""

    def test_create_operation_success(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(client, routing["id"])

        assert op["routing_id"] == routing["id"]
        assert op["work_center_id"] == 1
        assert op["operation_code"] == "OP10"
        assert op["is_active"] is True

    def test_create_operation_routing_not_found(self, client):
        response = client.post(f"{BASE_URL}/999999/operations", json={
            "work_center_id": 1,
            "sequence": 10,
            "run_time_minutes": "5.0",
        })
        assert response.status_code == 404

    def test_create_operation_invalid_work_center(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        response = client.post(f"{BASE_URL}/{routing['id']}/operations", json={
            "work_center_id": 999999,
            "sequence": 10,
            "run_time_minutes": "5.0",
        })
        assert response.status_code == 400

    def test_create_operation_includes_work_center_info(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(client, routing["id"])

        assert op["work_center_code"] == "TEST-WC"
        assert op["work_center_name"] == "Test Work Center"

    def test_create_operation_calculates_total_time(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(
            client, routing["id"],
            setup_time_minutes="5.0",
            run_time_minutes="10.0",
            wait_time_minutes="2.0",
            move_time_minutes="1.0",
        )

        total = Decimal(str(op["total_time_minutes"]))
        assert total == Decimal("18.0")

    def test_create_operation_missing_sequence_returns_422(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        response = client.post(f"{BASE_URL}/{routing['id']}/operations", json={
            "work_center_id": 1,
            "run_time_minutes": "5.0",
            # sequence is required
        })
        assert response.status_code == 422


# =============================================================================
# Update Operation — PUT /api/v1/routings/operations/{operation_id}
# =============================================================================

class TestUpdateOperation:
    """Tests for updating a routing operation."""

    def test_update_operation_name(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])

        response = client.put(
            f"{BASE_URL}/operations/{op['id']}",
            json={"operation_name": "Updated Name"},
        )
        assert response.status_code == 200
        assert response.json()["operation_name"] == "Updated Name"

    def test_update_operation_run_time(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])

        response = client.put(
            f"{BASE_URL}/operations/{op['id']}",
            json={"run_time_minutes": "30.0"},
        )
        assert response.status_code == 200
        assert Decimal(str(response.json()["run_time_minutes"])) == Decimal("30.0")

    def test_update_operation_not_found(self, client):
        response = client.put(
            f"{BASE_URL}/operations/999999", json={"sequence": 20}
        )
        assert response.status_code == 404

    def test_update_operation_invalid_work_center(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])

        response = client.put(
            f"{BASE_URL}/operations/{op['id']}",
            json={"work_center_id": 999999},
        )
        assert response.status_code == 400


# =============================================================================
# Delete Operation — DELETE /api/v1/routings/operations/{operation_id}
# =============================================================================

class TestDeleteOperation:
    """Tests for operation deletion (soft delete)."""

    def test_delete_operation_returns_204(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])

        response = client.delete(f"{BASE_URL}/operations/{op['id']}")
        assert response.status_code == 204

    def test_delete_operation_not_found(self, client):
        response = client.delete(f"{BASE_URL}/operations/999999")
        assert response.status_code == 404

    def test_delete_operation_soft_deletes(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])

        client.delete(f"{BASE_URL}/operations/{op['id']}")

        # Verify inactive via include_inactive
        response = client.get(
            f"{BASE_URL}/{routing['id']}/operations",
            params={"active_only": False},
        )
        assert response.status_code == 200

        found = [o for o in response.json() if o["id"] == op["id"]]
        assert len(found) == 1
        assert found[0]["is_active"] is False


# =============================================================================
# List Operation Materials — GET /api/v1/routings/operations/{op_id}/materials
# =============================================================================

class TestListOperationMaterials:
    """Tests for listing materials on an operation."""

    def test_list_materials_empty(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])

        response = client.get(f"{BASE_URL}/operations/{op['id']}/materials")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_materials_returns_created(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        component = make_product(
            item_type="supply", unit="G", is_raw_material=True
        )
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])
        mat = _create_material(client, op["id"], component.id)

        response = client.get(f"{BASE_URL}/operations/{op['id']}/materials")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == mat["id"]
        assert data[0]["component_id"] == component.id

    def test_list_materials_operation_not_found(self, client):
        response = client.get(f"{BASE_URL}/operations/999999/materials")
        assert response.status_code == 404


# =============================================================================
# Create Operation Material — POST /api/v1/routings/operations/{op_id}/materials
# =============================================================================

class TestCreateOperationMaterial:
    """Tests for adding materials to an operation."""

    def test_create_material_success(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        component = make_product(
            item_type="supply", unit="G", is_raw_material=True
        )
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])

        mat = _create_material(client, op["id"], component.id)

        assert mat["component_id"] == component.id
        assert mat["routing_operation_id"] == op["id"]
        assert mat["unit"] == "G"

    def test_create_material_includes_component_info(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        component = make_product(
            item_type="supply", unit="EA", name="Bolt M5"
        )
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])

        mat = _create_material(client, op["id"], component.id, unit="EA")

        assert mat["component_sku"] == component.sku
        assert mat["component_name"] == "Bolt M5"

    def test_create_material_operation_not_found(self, client, make_product):
        component = make_product(item_type="supply", unit="EA")

        response = client.post(
            f"{BASE_URL}/operations/999999/materials",
            json={"component_id": component.id, "quantity": "5", "unit": "EA"},
        )
        assert response.status_code == 404

    def test_create_material_component_not_found(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])

        response = client.post(
            f"{BASE_URL}/operations/{op['id']}/materials",
            json={"component_id": 999999, "quantity": "5", "unit": "EA"},
        )
        assert response.status_code == 400

    def test_create_material_invalid_unit_returns_422(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        component = make_product(item_type="supply", unit="EA")
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])

        response = client.post(
            f"{BASE_URL}/operations/{op['id']}/materials",
            json={
                "component_id": component.id,
                "quantity": "5",
                "unit": "INVALID_UNIT",
            },
        )
        assert response.status_code == 422

    def test_create_material_missing_quantity_returns_422(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        component = make_product(item_type="supply", unit="EA")
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])

        response = client.post(
            f"{BASE_URL}/operations/{op['id']}/materials",
            json={"component_id": component.id, "unit": "EA"},
        )
        assert response.status_code == 422


# =============================================================================
# Update Operation Material — PUT /api/v1/routings/materials/{material_id}
# =============================================================================

class TestUpdateOperationMaterial:
    """Tests for updating a routing operation material."""

    def test_update_material_quantity(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        component = make_product(
            item_type="supply", unit="G", is_raw_material=True
        )
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])
        mat = _create_material(client, op["id"], component.id)

        response = client.put(
            f"{BASE_URL}/materials/{mat['id']}",
            json={"quantity": "25.0"},
        )
        assert response.status_code == 200
        assert Decimal(str(response.json()["quantity"])) == Decimal("25.0")

    def test_update_material_notes(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        component = make_product(
            item_type="supply", unit="G", is_raw_material=True
        )
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])
        mat = _create_material(client, op["id"], component.id)

        response = client.put(
            f"{BASE_URL}/materials/{mat['id']}",
            json={"notes": "Use red variant"},
        )
        assert response.status_code == 200
        assert response.json()["notes"] == "Use red variant"

    def test_update_material_not_found(self, client):
        response = client.put(
            f"{BASE_URL}/materials/999999", json={"quantity": "10"}
        )
        assert response.status_code == 404

    def test_update_material_invalid_component(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        component = make_product(
            item_type="supply", unit="G", is_raw_material=True
        )
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])
        mat = _create_material(client, op["id"], component.id)

        response = client.put(
            f"{BASE_URL}/materials/{mat['id']}",
            json={"component_id": 999999},
        )
        assert response.status_code == 400


# =============================================================================
# Delete Operation Material — DELETE /api/v1/routings/materials/{material_id}
# =============================================================================

class TestDeleteOperationMaterial:
    """Tests for deleting a routing operation material (hard delete)."""

    def test_delete_material_returns_204(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        component = make_product(
            item_type="supply", unit="G", is_raw_material=True
        )
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])
        mat = _create_material(client, op["id"], component.id)

        response = client.delete(f"{BASE_URL}/materials/{mat['id']}")
        assert response.status_code == 204

    def test_delete_material_removes_from_list(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        component = make_product(
            item_type="supply", unit="G", is_raw_material=True
        )
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])
        mat = _create_material(client, op["id"], component.id)

        client.delete(f"{BASE_URL}/materials/{mat['id']}")

        response = client.get(f"{BASE_URL}/operations/{op['id']}/materials")
        assert response.status_code == 200
        assert len(response.json()) == 0

    def test_delete_material_not_found(self, client):
        response = client.delete(f"{BASE_URL}/materials/999999")
        assert response.status_code == 404


# =============================================================================
# Manufacturing BOM — GET /api/v1/routings/manufacturing-bom/{product_id}
# =============================================================================

class TestManufacturingBOM:
    """Tests for the manufacturing BOM view."""

    def test_get_manufacturing_bom_success(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        component = make_product(
            item_type="supply", unit="G", is_raw_material=True,
            average_cost=Decimal("0.02"),
        )
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"])
        _create_material(client, op["id"], component.id)

        response = client.get(f"{BASE_URL}/manufacturing-bom/{product.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["product_id"] == product.id
        assert data["product_sku"] == product.sku
        assert data["routing_id"] == routing["id"]
        assert data["is_active"] is True
        assert len(data["operations"]) == 1
        assert len(data["operations"][0]["materials"]) == 1

    def test_get_manufacturing_bom_product_not_found(self, client):
        response = client.get(f"{BASE_URL}/manufacturing-bom/999999")
        assert response.status_code == 404

    def test_get_manufacturing_bom_no_routing(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")

        response = client.get(f"{BASE_URL}/manufacturing-bom/{product.id}")
        assert response.status_code == 404

    def test_get_manufacturing_bom_includes_costs(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)
        _create_operation(client, routing["id"], run_time_minutes="60.0")

        response = client.get(f"{BASE_URL}/manufacturing-bom/{product.id}")
        assert response.status_code == 200

        data = response.json()
        assert "total_labor_cost" in data
        assert "total_material_cost" in data
        assert "total_cost" in data

    def test_get_manufacturing_bom_multiple_operations(self, client, make_product):
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        _create_operation(
            client, routing["id"],
            sequence=10, operation_code="OP10",
            operation_name="Print", run_time_minutes="60.0",
        )
        _create_operation(
            client, routing["id"],
            sequence=20, operation_code="OP20",
            operation_name="QC", run_time_minutes="5.0",
        )

        response = client.get(f"{BASE_URL}/manufacturing-bom/{product.id}")
        assert response.status_code == 200

        data = response.json()
        assert len(data["operations"]) == 2
        assert data["operations"][0]["sequence"] < data["operations"][1]["sequence"]


# =============================================================================
# #876 PR-2 — operation_type write-time alias assist + validation
# =============================================================================

class TestOperationTypeAliasAssist:
    """Write-time alias assist (#876 PR-2 design §3): when operation_type is
    absent but operation_code matches one of the 18 legacy canonical codes,
    the server auto-assigns the type. FINISH/POST get NO alias."""

    def test_print_code_gets_fdm_print_alias(self, db, client, make_product):
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(client, routing["id"], operation_code="PRINT")
        assert op["operation_type"] == "FDM_PRINT"

    def test_pack_code_gets_pack_ship_alias(self, db, client, make_product):
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(client, routing["id"], operation_code="PACK")
        assert op["operation_type"] == "PACK_SHIP"

    def test_qc_code_gets_quality_control_alias(self, db, client, make_product):
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(client, routing["id"], operation_code="QC")
        assert op["operation_type"] == "QUALITY_CONTROL"

    def test_assemble_code_gets_assembly_alias(self, db, client, make_product):
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(client, routing["id"], operation_code="ASSEMBLE")
        assert op["operation_type"] == "ASSEMBLY"

    def test_finish_code_gets_no_alias(self, db, client, make_product):
        """FINISH is deliberately excluded from the alias map — the live
        census shows it spans shipping/quality/blank names."""
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(client, routing["id"], operation_code="FINISH")
        assert op["operation_type"] is None

    def test_post_code_gets_no_alias(self, db, client, make_product):
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(client, routing["id"], operation_code="POST")
        assert op["operation_type"] is None

    def test_unrecognized_code_gets_no_alias(self, db, client, make_product):
        """OP10/OP20-style autofilled codes (not in the legacy 18) get no
        alias — they stay untyped, exactly like today, until a human or the
        classifier (#876 PR-3) types them."""
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(client, routing["id"], operation_code="OP10")
        assert op["operation_type"] is None

    def test_alias_target_deactivated_gets_no_alias(self, db, client, make_product):
        """CodeRabbit #4630789865 finding 4: the shared catalog-existence
        check used by alias assist excludes deactivated types, exactly like
        write-time validation — a code that would normally alias to a now-
        deactivated type degrades to a no-op instead of assigning a type
        that write-time validation would then reject."""
        _seed_operation_types(db)
        from app.models.manufacturing import OperationType

        deactivated_type = db.query(OperationType).filter(
            OperationType.code == "FDM_PRINT"
        ).first()
        deactivated_type.is_active = False
        db.flush()

        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(client, routing["id"], operation_code="PRINT")
        assert op["operation_type"] is None, (
            "PRINT would normally alias to FDM_PRINT, but that type is "
            "deactivated — alias assist must degrade to a no-op"
        )

    def test_explicit_type_is_never_overridden_by_alias(self, db, client, make_product):
        """An explicitly-provided operation_type always wins, even when the
        code would alias to something else."""
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(
            client, routing["id"],
            operation_code="PRINT", operation_type="QUALITY_CONTROL",
        )
        assert op["operation_type"] == "QUALITY_CONTROL"

    def test_explicit_type_is_case_normalized_upper(self, db, client, make_product):
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(
            client, routing["id"],
            operation_code="PRINT", operation_type="fdm_print",
        )
        assert op["operation_type"] == "FDM_PRINT"

    def test_update_operation_alias_assist_on_code_change(self, db, client, make_product):
        """Changing operation_code on an untyped op via PUT also gets the
        alias-assist treatment (op CRUD path, not just create)."""
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"], operation_code="OP10")
        assert op["operation_type"] is None

        response = client.put(
            f"{BASE_URL}/operations/{op['id']}",
            json={"operation_code": "PACK"},
        )
        assert response.status_code == 200
        assert response.json()["operation_type"] == "PACK_SHIP"

    def test_update_operation_alias_assist_never_overwrites_existing_type(
        self, db, client, make_product
    ):
        """If the operation already has a type, changing operation_code
        alone must NOT silently retype it via alias assist."""
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(
            client, routing["id"], operation_code="OP10", operation_type="QUALITY_CONTROL",
        )
        assert op["operation_type"] == "QUALITY_CONTROL"

        response = client.put(
            f"{BASE_URL}/operations/{op['id']}",
            json={"operation_code": "PACK"},
        )
        assert response.status_code == 200
        assert response.json()["operation_type"] == "QUALITY_CONTROL", (
            "Alias assist must never overwrite an already-typed operation"
        )

    def test_blank_operation_type_treated_as_absent_on_create(
        self, db, client, make_product
    ):
        """CodeRabbit #4630789865 finding 2: an empty-string operation_type
        must be treated as ABSENT (falls to alias assist), not as an
        explicit value that leaks through unchanged."""
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(
            client, routing["id"], operation_code="PRINT", operation_type="",
        )
        assert op["operation_type"] == "FDM_PRINT", (
            "A blank operation_type must fall through to alias assist "
            "exactly like an absent one, never persist as ''"
        )

    def test_whitespace_operation_type_treated_as_absent_on_create(
        self, db, client, make_product
    ):
        """Same as above, for a whitespace-only value — must not be
        treated as an explicit provided type either."""
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(
            client, routing["id"], operation_code="PRINT", operation_type="   ",
        )
        assert op["operation_type"] == "FDM_PRINT"

    def test_blank_operation_type_treated_as_absent_on_update(
        self, db, client, make_product
    ):
        """Same blank-is-absent rule on the update_operation path."""
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"], operation_code="OP10")
        assert op["operation_type"] is None

        response = client.put(
            f"{BASE_URL}/operations/{op['id']}",
            json={"operation_code": "PACK", "operation_type": ""},
        )
        assert response.status_code == 200
        assert response.json()["operation_type"] == "PACK_SHIP", (
            "A blank operation_type on update must fall through to alias "
            "assist rather than persisting as ''"
        )


class TestOperationTypeValidation:
    """Write-time validation (#876 PR-2 design §5): a non-null operation_type
    must be a known, case-normalized-upper code in the operation_types
    catalog, else 400."""

    def test_unknown_operation_type_returns_400(self, db, client, make_product):
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        response = client.post(f"{BASE_URL}/{routing['id']}/operations", json={
            "work_center_id": 1,
            "sequence": 10,
            "operation_code": "OP10",
            "operation_type": "NOT_A_REAL_TYPE",
            "run_time_minutes": "5.0",
        })
        assert response.status_code == 400

    def test_unknown_operation_type_on_update_returns_400(self, db, client, make_product):
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)
        op = _create_operation(client, routing["id"], operation_code="OP10")

        response = client.put(
            f"{BASE_URL}/operations/{op['id']}",
            json={"operation_type": "NOT_A_REAL_TYPE"},
        )
        assert response.status_code == 400

    def test_known_type_case_insensitive_passes(self, db, client, make_product):
        """A lowercase-but-otherwise-known type code is case-normalized and
        accepted, not rejected."""
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(
            client, routing["id"], operation_code="OP10", operation_type="pack_ship",
        )
        assert op["operation_type"] == "PACK_SHIP"

    def test_null_operation_type_always_allowed(self, db, client, make_product):
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        op = _create_operation(client, routing["id"], operation_code="OP99")
        assert op["operation_type"] is None

    def test_deactivated_operation_type_returns_400(self, db, client, make_product):
        """CodeRabbit #4630789865 finding 3: a deactivated type must be
        rejected on write exactly like an unknown one — deactivation blocks
        future assignability even though it still exists in the catalog."""
        _seed_operation_types(db)
        from app.models.manufacturing import OperationType

        deactivated_type = db.query(OperationType).filter(
            OperationType.code == "PAINTING"
        ).first()
        deactivated_type.is_active = False
        db.flush()

        product = make_product(item_type="finished_good", procurement_type="make")
        routing = _create_routing(client, product_id=product.id)

        response = client.post(f"{BASE_URL}/{routing['id']}/operations", json={
            "work_center_id": 1,
            "sequence": 10,
            "operation_code": "OP10",
            "operation_type": "PAINTING",
            "run_time_minutes": "5.0",
        })
        assert response.status_code == 400


class TestOperationTypeSnapshotPropagation:
    """Type propagation at copy sites (#876 PR-2 design §4): template seeds
    carry operation_type, and apply-template copies it onto the new
    per-product routing."""

    def test_apply_template_propagates_operation_type(self, db, client, make_product):
        _seed_operation_types(db)
        product = make_product(item_type="finished_good", procurement_type="make")

        template = _create_routing(
            client, is_template=True,
            code="TPL-TYPE-PROPAGATION", name="Type Propagation Template",
        )
        _create_operation(
            client, template["id"],
            operation_code="PRINT", operation_type="FDM_PRINT",
            operation_name="3D Print", run_time_minutes="60.0",
        )

        response = client.post(f"{BASE_URL}/apply-template", json={
            "template_id": template["id"],
            "product_id": product.id,
        })
        assert response.status_code == 200

        data = response.json()
        assert data["operations"][0]["operation_code"] == "PRINT"
        assert data["operations"][0]["operation_type"] == "FDM_PRINT"
