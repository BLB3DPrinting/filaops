"""
Tests for production operation service modules:
- operation_status: Status transitions, validation, PO status derivation
- production_execution: BOM explosion, material reservation, finished goods
- operation_blocking: Material availability checks, blocking detection
- operation_generation: Routing-to-PO operation generation, release workflow

Covers both happy-path and error/edge-case scenarios.
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import patch

from app.models.product import Product
from app.models.production_order import (
    ProductionOrder,
    ProductionOrderOperation,
    ProductionOrderOperationMaterial,
)
from app.models.manufacturing import (
    Resource,
    Routing,
    RoutingOperation,
    RoutingOperationMaterial,
)
from app.models.work_center import WorkCenter
from app.models.bom import BOM, BOMLine
from app.models.inventory import Inventory, InventoryLocation, InventoryTransaction
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.vendor import Vendor
from app.services import (
    operation_status,
    production_execution,
    operation_blocking,
    operation_generation,
    routing_service,
)
from app.services.operation_status import OperationError
from app.services.operation_blocking import OperationBlockingError


# =============================================================================
# Helpers
# =============================================================================

def _uid():
    return uuid.uuid4().hex[:8]


def _make_product(db, *, sku=None, name=None, item_type="finished_good", unit="EA",
                  cost_method="standard", standard_cost=None, average_cost=None,
                  procurement_type="make", **kwargs):
    uid = _uid()
    product = Product(
        sku=sku or f"TST-{uid}",
        name=name or f"Test Product {uid}",
        item_type=item_type,
        unit=unit,
        cost_method=cost_method,
        standard_cost=standard_cost,
        average_cost=average_cost,
        procurement_type=procurement_type,
        **kwargs,
    )
    db.add(product)
    db.flush()
    return product


def _make_po(db, product, *, quantity=10, status="draft", bom_id=None, routing_id=None,
             sales_order_id=None, quantity_completed=0, quantity_scrapped=0):
    uid = _uid()
    po = ProductionOrder(
        code=f"PO-TEST-{uid}",
        product_id=product.id,
        bom_id=bom_id,
        routing_id=routing_id,
        sales_order_id=sales_order_id,
        quantity_ordered=quantity,
        quantity_completed=quantity_completed,
        quantity_scrapped=quantity_scrapped,
        source="manual",
        status=status,
        priority=3,
    )
    db.add(po)
    db.flush()
    return po


def _make_operation(db, po, *, sequence=10, status="pending", operation_code="PRINT",
                    operation_name="Print", work_center_id=1, planned_run_minutes=60,
                    quantity_completed=0, quantity_scrapped=0, actual_start=None,
                    operator_name=None, routing_operation_id=None):
    op = ProductionOrderOperation(
        production_order_id=po.id,
        sequence=sequence,
        operation_code=operation_code,
        operation_name=operation_name,
        work_center_id=work_center_id,
        planned_setup_minutes=5,
        planned_run_minutes=planned_run_minutes,
        status=status,
        quantity_completed=quantity_completed,
        quantity_scrapped=quantity_scrapped,
        actual_start=actual_start,
        operator_name=operator_name,
        routing_operation_id=routing_operation_id,
    )
    db.add(op)
    db.flush()
    return op


def _make_routing(db, product, *, operations_data=None):
    """Create a routing with operations for a product."""
    uid = _uid()
    routing = Routing(
        product_id=product.id,
        code=f"RT-{uid}",
        name=f"Routing for {product.name}",
        is_active=True,
    )
    db.add(routing)
    db.flush()

    created_ops = []
    if operations_data is None:
        operations_data = [
            {"sequence": 10, "operation_code": "PRINT", "operation_name": "Print",
             "setup_time_minutes": 5, "run_time_minutes": 10},
        ]

    for op_data in operations_data:
        rop = RoutingOperation(
            routing_id=routing.id,
            work_center_id=1,
            **op_data,
        )
        db.add(rop)
        db.flush()
        created_ops.append(rop)

    return routing, created_ops


def _make_inventory(db, product, *, on_hand=Decimal("100"), allocated=Decimal("0"),
                    location_id=1):
    inv = Inventory(
        product_id=product.id,
        location_id=location_id,
        on_hand_quantity=on_hand,
        allocated_quantity=allocated,
    )
    db.add(inv)
    db.flush()
    return inv


def _make_resource(db, *, work_center_id=1, code=None, name=None, status="available",
                   is_active=True):
    uid = _uid()
    resource = Resource(
        work_center_id=work_center_id,
        code=code or f"RES-{uid}",
        name=name or f"Test Resource {uid}",
        status=status,
        is_active=is_active,
    )
    db.add(resource)
    db.flush()
    return resource


# =============================================================================
# operation_status — get_operation_with_validation
# =============================================================================

class TestGetOperationWithValidation:
    def test_returns_po_and_op(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op = _make_operation(db, po)

        result_po, result_op = operation_status.get_operation_with_validation(db, po.id, op.id)
        assert result_po.id == po.id
        assert result_op.id == op.id

    def test_po_not_found_raises(self, db):
        with pytest.raises(OperationError) as exc_info:
            operation_status.get_operation_with_validation(db, 999999, 1)
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.message

    def test_op_not_found_raises(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="released")

        with pytest.raises(OperationError) as exc_info:
            operation_status.get_operation_with_validation(db, po.id, 999999)
        assert exc_info.value.status_code == 404

    def test_op_belongs_to_different_po_raises(self, db):
        product = _make_product(db)
        po1 = _make_po(db, product, status="released")
        po2 = _make_po(db, product, status="released")
        op = _make_operation(db, po2)

        with pytest.raises(OperationError) as exc_info:
            operation_status.get_operation_with_validation(db, po1.id, op.id)
        assert exc_info.value.status_code == 404
        assert "does not belong" in exc_info.value.message


# =============================================================================
# operation_status — get_previous_operation / get_next_operation
# =============================================================================

class TestGetPreviousNextOperation:
    def test_get_previous_for_first_op_returns_none(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op1 = _make_operation(db, po, sequence=10)

        result = operation_status.get_previous_operation(db, po, op1)
        assert result is None

    def test_get_previous_returns_correct_op(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op1 = _make_operation(db, po, sequence=10)
        op2 = _make_operation(db, po, sequence=20)

        result = operation_status.get_previous_operation(db, po, op2)
        assert result.id == op1.id

    def test_get_next_for_last_op_returns_none(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op1 = _make_operation(db, po, sequence=10)

        result = operation_status.get_next_operation(db, po, op1)
        assert result is None

    def test_get_next_returns_correct_op(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op1 = _make_operation(db, po, sequence=10)
        op2 = _make_operation(db, po, sequence=20)

        result = operation_status.get_next_operation(db, po, op1)
        assert result.id == op2.id


# =============================================================================
# operation_status — get_operation_max_quantity
# =============================================================================

class TestGetOperationMaxQuantity:
    def test_first_op_returns_order_quantity(self, db):
        product = _make_product(db)
        po = _make_po(db, product, quantity=25, status="released")
        op = _make_operation(db, po, sequence=10)

        result = operation_status.get_operation_max_quantity(po, op)
        assert result == Decimal("25")

    def test_second_op_returns_previous_completed_qty(self, db):
        product = _make_product(db)
        po = _make_po(db, product, quantity=25, status="in_progress")
        op1 = _make_operation(db, po, sequence=10, status="complete",
                              quantity_completed=20)
        op2 = _make_operation(db, po, sequence=20)

        result = operation_status.get_operation_max_quantity(po, op2)
        assert result == Decimal("20")

    def test_skipped_prev_walks_back(self, db):
        product = _make_product(db)
        po = _make_po(db, product, quantity=25, status="in_progress")
        op1 = _make_operation(db, po, sequence=10, status="complete",
                              quantity_completed=18)
        op2 = _make_operation(db, po, sequence=20, status="skipped")
        op3 = _make_operation(db, po, sequence=30)

        result = operation_status.get_operation_max_quantity(po, op3)
        assert result == Decimal("18")

    def test_all_previous_skipped_returns_order_qty(self, db):
        product = _make_product(db)
        po = _make_po(db, product, quantity=25, status="in_progress")
        op1 = _make_operation(db, po, sequence=10, status="skipped")
        op2 = _make_operation(db, po, sequence=20, status="skipped")
        op3 = _make_operation(db, po, sequence=30)

        result = operation_status.get_operation_max_quantity(po, op3)
        assert result == Decimal("25")

    def test_previous_not_done_returns_zero(self, db):
        product = _make_product(db)
        po = _make_po(db, product, quantity=25, status="in_progress")
        op1 = _make_operation(db, po, sequence=10, status="running")
        op2 = _make_operation(db, po, sequence=20)

        result = operation_status.get_operation_max_quantity(po, op2)
        assert result == Decimal("0")


# =============================================================================
# operation_status — derive_po_status
# =============================================================================

class TestDerivePOStatus:
    def test_no_operations_keeps_current(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="released")
        # No operations attached
        assert operation_status.derive_po_status(po) == "released"

    def test_all_pending_returns_released(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="released")
        _make_operation(db, po, sequence=10, status="pending")
        _make_operation(db, po, sequence=20, status="pending")

        assert operation_status.derive_po_status(po) == "released"

    def test_mixed_statuses_returns_in_progress(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="in_progress")
        _make_operation(db, po, sequence=10, status="complete", quantity_completed=10)
        _make_operation(db, po, sequence=20, status="running")

        assert operation_status.derive_po_status(po) == "in_progress"

    def test_all_complete_with_enough_qty_returns_complete(self, db):
        product = _make_product(db)
        po = _make_po(db, product, quantity=10, status="in_progress",
                      quantity_completed=10)
        _make_operation(db, po, sequence=10, status="complete", quantity_completed=10)

        assert operation_status.derive_po_status(po) == "complete"

    def test_all_complete_with_short_qty_returns_short(self, db):
        product = _make_product(db)
        po = _make_po(db, product, quantity=10, status="in_progress",
                      quantity_completed=5)
        _make_operation(db, po, sequence=10, status="complete", quantity_completed=5)

        assert operation_status.derive_po_status(po) == "short"

    def test_complete_and_skipped_returns_complete(self, db):
        product = _make_product(db)
        po = _make_po(db, product, quantity=10, status="in_progress",
                      quantity_completed=10)
        _make_operation(db, po, sequence=10, status="complete", quantity_completed=10)
        _make_operation(db, po, sequence=20, status="skipped")

        assert operation_status.derive_po_status(po) == "complete"


# =============================================================================
# operation_status — start_operation
# =============================================================================

class TestStartOperation:
    @patch("app.services.operation_status.check_operation_blocking")
    def test_start_pending_first_op(self, mock_blocking, db):
        """Starting the first pending operation succeeds."""
        mock_blocking.return_value = {"can_start": True, "blocking_issues": []}

        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op = _make_operation(db, po, sequence=10, status="pending")

        result = operation_status.start_operation(
            db, po.id, op.id, operator_name="Tester"
        )
        assert result.status == "running"
        assert result.operator_name == "Tester"
        assert result.actual_start is not None

    @patch("app.services.operation_status.check_operation_blocking")
    def test_start_already_running_raises(self, mock_blocking, db):
        mock_blocking.return_value = {"can_start": True, "blocking_issues": []}

        product = _make_product(db)
        po = _make_po(db, product, status="in_progress")
        op = _make_operation(db, po, sequence=10, status="running",
                             actual_start=datetime.now(timezone.utc))

        with pytest.raises(OperationError) as exc_info:
            operation_status.start_operation(db, po.id, op.id)
        assert exc_info.value.status_code == 400
        assert "already running" in exc_info.value.message

    @patch("app.services.operation_status.check_operation_blocking")
    def test_start_already_complete_raises(self, mock_blocking, db):
        mock_blocking.return_value = {"can_start": True, "blocking_issues": []}

        product = _make_product(db)
        po = _make_po(db, product, status="in_progress")
        op = _make_operation(db, po, sequence=10, status="complete",
                             quantity_completed=10)

        with pytest.raises(OperationError) as exc_info:
            operation_status.start_operation(db, po.id, op.id)
        assert exc_info.value.status_code == 400
        assert "already complete" in exc_info.value.message

    @patch("app.services.operation_status.check_operation_blocking")
    def test_start_second_op_before_first_complete_raises(self, mock_blocking, db):
        mock_blocking.return_value = {"can_start": True, "blocking_issues": []}

        product = _make_product(db)
        po = _make_po(db, product, status="in_progress")
        op1 = _make_operation(db, po, sequence=10, status="running")
        op2 = _make_operation(db, po, sequence=20, status="pending")

        with pytest.raises(OperationError) as exc_info:
            operation_status.start_operation(db, po.id, op2.id)
        assert "must be complete" in exc_info.value.message

    @patch("app.services.operation_status.check_operation_blocking")
    def test_start_blocked_by_material_raises(self, mock_blocking, db):
        mock_blocking.return_value = {
            "can_start": False,
            "blocking_issues": [{"product_sku": "RAW-001"}],
        }

        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op = _make_operation(db, po, sequence=10, status="pending")

        with pytest.raises(OperationError) as exc_info:
            operation_status.start_operation(db, po.id, op.id)
        assert "material shortages" in exc_info.value.message
        assert "RAW-001" in exc_info.value.message

    @patch("app.services.operation_status.check_operation_blocking")
    @patch("app.services.operation_status.check_resource_available_now")
    def test_start_with_resource(self, mock_resource_check, mock_blocking, db):
        mock_blocking.return_value = {"can_start": True, "blocking_issues": []}
        mock_resource_check.return_value = (True, None)

        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op = _make_operation(db, po, sequence=10, status="pending")
        resource = _make_resource(db)

        result = operation_status.start_operation(
            db, po.id, op.id, resource_id=resource.id
        )
        assert result.resource_id == resource.id
        assert result.status == "running"

    @patch("app.services.operation_status.check_operation_blocking")
    @patch("app.services.operation_status.check_resource_available_now")
    def test_start_with_busy_resource_raises(self, mock_resource_check, mock_blocking, db):
        mock_blocking.return_value = {"can_start": True, "blocking_issues": []}

        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op = _make_operation(db, po, sequence=10, status="pending")
        resource = _make_resource(db)

        # Simulate busy resource
        blocking_op = _make_operation(db, po, sequence=99, status="running")
        mock_resource_check.return_value = (False, blocking_op)

        with pytest.raises(OperationError) as exc_info:
            operation_status.start_operation(db, po.id, op.id, resource_id=resource.id)
        assert exc_info.value.status_code == 409
        assert "busy" in exc_info.value.message

    @patch("app.services.operation_status.check_operation_blocking")
    def test_start_with_nonexistent_resource_raises(self, mock_blocking, db):
        mock_blocking.return_value = {"can_start": True, "blocking_issues": []}

        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op = _make_operation(db, po, sequence=10, status="pending")

        with pytest.raises(OperationError) as exc_info:
            operation_status.start_operation(db, po.id, op.id, resource_id=999999)
        assert exc_info.value.status_code == 404
        assert "Resource" in exc_info.value.message


# =============================================================================
# operation_status — complete_operation
# =============================================================================

class TestCompleteOperation:
    @patch("app.services.operation_status.consume_operation_materials")
    @patch("app.services.operation_status.process_production_completion")
    @patch("app.services.operation_status.sync_on_production_complete")
    def test_complete_running_op_happy_path(self, mock_sync, mock_prod_complete,
                                           mock_consume, db):
        mock_consume.return_value = []

        product = _make_product(db)
        po = _make_po(db, product, quantity=10, status="in_progress")
        op = _make_operation(db, po, sequence=10, status="running",
                             actual_start=datetime.now(timezone.utc) - timedelta(hours=1))

        result_op, scrap_result = operation_status.complete_operation(
            db, po.id, op.id,
            quantity_completed=Decimal("10"),
            quantity_scrapped=Decimal("0"),
        )
        assert result_op.status == "complete"
        assert result_op.quantity_completed == Decimal("10")
        assert result_op.actual_end is not None
        assert scrap_result is None

    @patch("app.services.operation_status.consume_operation_materials")
    @patch("app.services.operation_status.process_production_completion")
    @patch("app.services.operation_status.sync_on_production_complete")
    def test_complete_not_running_raises(self, mock_sync, mock_prod_complete,
                                        mock_consume, db):
        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op = _make_operation(db, po, sequence=10, status="pending")

        with pytest.raises(OperationError) as exc_info:
            operation_status.complete_operation(
                db, po.id, op.id,
                quantity_completed=Decimal("10"),
            )
        assert exc_info.value.status_code == 400
        assert "not running" in exc_info.value.message

    @patch("app.services.operation_status.consume_operation_materials")
    @patch("app.services.operation_status.process_production_completion")
    @patch("app.services.operation_status.sync_on_production_complete")
    def test_complete_exceeds_max_qty_raises(self, mock_sync, mock_prod_complete,
                                            mock_consume, db):
        product = _make_product(db)
        po = _make_po(db, product, quantity=10, status="in_progress")
        op = _make_operation(db, po, sequence=10, status="running",
                             actual_start=datetime.now(timezone.utc))

        with pytest.raises(OperationError) as exc_info:
            operation_status.complete_operation(
                db, po.id, op.id,
                quantity_completed=Decimal("8"),
                quantity_scrapped=Decimal("5"),  # total 13 > 10
            )
        assert "exceeds maximum" in exc_info.value.message

    @patch("app.services.operation_status.consume_operation_materials")
    @patch("app.services.operation_status.process_production_completion")
    @patch("app.services.operation_status.sync_on_production_complete")
    def test_complete_scrap_without_reason_raises(self, mock_sync, mock_prod_complete,
                                                 mock_consume, db):
        product = _make_product(db)
        po = _make_po(db, product, quantity=10, status="in_progress")
        op = _make_operation(db, po, sequence=10, status="running",
                             actual_start=datetime.now(timezone.utc))

        with pytest.raises(OperationError) as exc_info:
            operation_status.complete_operation(
                db, po.id, op.id,
                quantity_completed=Decimal("8"),
                quantity_scrapped=Decimal("2"),
                scrap_reason=None,
            )
        assert "Scrap reason is required" in exc_info.value.message

    @patch("app.services.operation_status.consume_operation_materials")
    @patch("app.services.operation_status.process_production_completion")
    @patch("app.services.operation_status.sync_on_production_complete")
    def test_complete_with_actual_run_minutes_override(self, mock_sync, mock_prod_complete,
                                                      mock_consume, db):
        mock_consume.return_value = []

        product = _make_product(db)
        po = _make_po(db, product, quantity=10, status="in_progress")
        op = _make_operation(db, po, sequence=10, status="running",
                             actual_start=datetime.now(timezone.utc))

        result_op, _ = operation_status.complete_operation(
            db, po.id, op.id,
            quantity_completed=Decimal("10"),
            actual_run_minutes=42,
        )
        assert result_op.actual_run_minutes == 42

    @patch("app.services.operation_status.consume_operation_materials")
    @patch("app.services.operation_status.process_production_completion")
    @patch("app.services.operation_status.sync_on_production_complete")
    def test_complete_calculates_run_minutes_from_actual_start(
        self, mock_sync, mock_prod_complete, mock_consume, db
    ):
        mock_consume.return_value = []

        product = _make_product(db)
        po = _make_po(db, product, quantity=10, status="in_progress")
        start_time = datetime.now(timezone.utc) - timedelta(minutes=90)
        op = _make_operation(db, po, sequence=10, status="running",
                             actual_start=start_time)

        result_op, _ = operation_status.complete_operation(
            db, po.id, op.id,
            quantity_completed=Decimal("10"),
        )
        # Should be approximately 90 minutes (allowing some tolerance)
        assert result_op.actual_run_minutes >= 89
        assert result_op.actual_run_minutes <= 91


# =============================================================================
# operation_status — auto_skip_downstream_operations
# =============================================================================

class TestAutoSkipDownstream:
    def test_skips_pending_downstream_ops(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="in_progress")
        op1 = _make_operation(db, po, sequence=10, status="complete",
                              quantity_completed=0)
        op2 = _make_operation(db, po, sequence=20, status="pending")
        op3 = _make_operation(db, po, sequence=30, status="pending")

        # Expire the PO to force a fresh load of the operations relationship
        db.expire(po, ["operations"])

        count = operation_status.auto_skip_downstream_operations(db, po, op1)
        assert count == 2

        # The function modifies objects in-memory without flushing, so check
        # the in-memory state directly instead of refreshing from DB.
        assert op2.status == "skipped"
        assert op3.status == "skipped"
        assert "SKIPPED" in op2.notes
        assert "SKIPPED" in op3.notes

    def test_does_not_skip_already_complete_ops(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="in_progress")
        op1 = _make_operation(db, po, sequence=10, status="complete",
                              quantity_completed=0)
        op2 = _make_operation(db, po, sequence=20, status="complete",
                              quantity_completed=5)
        op3 = _make_operation(db, po, sequence=30, status="pending")

        count = operation_status.auto_skip_downstream_operations(db, po, op1)
        # Only op3 is pending and downstream
        assert count == 1
        db.refresh(op2)
        assert op2.status == "complete"

    def test_no_downstream_ops_returns_zero(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="in_progress")
        op1 = _make_operation(db, po, sequence=10, status="complete",
                              quantity_completed=0)

        count = operation_status.auto_skip_downstream_operations(db, po, op1)
        assert count == 0


# =============================================================================
# operation_status — skip_operation
# =============================================================================

class TestSkipOperation:
    def test_skip_pending_op(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op = _make_operation(db, po, sequence=10, status="pending")

        result = operation_status.skip_operation(
            db, po.id, op.id, reason="Not needed"
        )
        assert result.status == "skipped"
        assert "SKIPPED: Not needed" in result.notes

    def test_skip_running_op_raises(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="in_progress")
        op = _make_operation(db, po, sequence=10, status="running")

        with pytest.raises(OperationError) as exc_info:
            operation_status.skip_operation(db, po.id, op.id, reason="Skip")
        assert exc_info.value.status_code == 400

    def test_skip_second_op_with_pending_first_raises(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op1 = _make_operation(db, po, sequence=10, status="pending")
        op2 = _make_operation(db, po, sequence=20, status="pending")

        with pytest.raises(OperationError) as exc_info:
            operation_status.skip_operation(db, po.id, op2.id, reason="Skip")
        assert "must be complete" in exc_info.value.message


# =============================================================================
# operation_status — list_operations
# =============================================================================

class TestListOperations:
    def test_returns_sorted_by_sequence(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op2 = _make_operation(db, po, sequence=20, operation_name="QC")
        op1 = _make_operation(db, po, sequence=10, operation_name="Print")

        ops = operation_status.list_operations(db, po.id)
        assert len(ops) == 2
        assert ops[0].sequence == 10
        assert ops[1].sequence == 20

    def test_po_not_found_raises(self, db):
        with pytest.raises(OperationError) as exc_info:
            operation_status.list_operations(db, 999999)
        assert exc_info.value.status_code == 404


# =============================================================================
# operation_status — OperationError
# =============================================================================

class TestOperationError:
    def test_str_returns_message(self):
        err = OperationError("Something went wrong", 422)
        assert str(err) == "Something went wrong"
        assert err.status_code == 422

    def test_default_status_code(self):
        err = OperationError("Bad thing")
        assert err.status_code == 400


# =============================================================================
# operation_blocking — get_operation_with_validation (blocking module version)
# =============================================================================

class TestBlockingGetOperationWithValidation:
    def test_po_not_found_raises_blocking_error(self, db):
        with pytest.raises(OperationBlockingError) as exc_info:
            operation_blocking.get_operation_with_validation(db, 999999, 1)
        assert exc_info.value.status_code == 404

    def test_op_not_found_raises_blocking_error(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="released")

        with pytest.raises(OperationBlockingError) as exc_info:
            operation_blocking.get_operation_with_validation(db, po.id, 999999)
        assert exc_info.value.status_code == 404

    def test_op_wrong_po_raises_blocking_error(self, db):
        product = _make_product(db)
        po1 = _make_po(db, product, status="released")
        po2 = _make_po(db, product, status="released")
        op = _make_operation(db, po2)

        with pytest.raises(OperationBlockingError) as exc_info:
            operation_blocking.get_operation_with_validation(db, po1.id, op.id)
        assert "does not belong" in exc_info.value.message


# =============================================================================
# operation_blocking — get_material_available
# =============================================================================

class TestGetMaterialAvailable:
    def test_returns_available_quantity(self, db):
        product = _make_product(db, item_type="supply", unit="G")
        _make_inventory(db, product, on_hand=Decimal("500"), allocated=Decimal("100"))

        result = operation_blocking.get_material_available(db, product.id)
        assert result == Decimal("400")

    def test_no_inventory_returns_zero(self, db):
        product = _make_product(db, item_type="supply", unit="G")

        result = operation_blocking.get_material_available(db, product.id)
        assert result == Decimal("0")


# =============================================================================
# operation_blocking — check_operation_blocking (routing materials path)
# =============================================================================

class TestCheckOperationBlocking:
    def test_no_materials_can_start(self, db):
        """Operation with no materials should always be startable."""
        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op = _make_operation(db, po, sequence=10)

        result = operation_blocking.check_operation_blocking(db, po.id, op.id)
        assert result["can_start"] is True
        assert result["blocking_issues"] == []

    def test_sufficient_routing_materials_can_start(self, db):
        """Operation with enough routing materials can start."""
        product = _make_product(db)
        component = _make_product(db, item_type="supply", unit="G", sku=f"RAW-{_uid()}")
        _make_inventory(db, component, on_hand=Decimal("1000"))

        po = _make_po(db, product, status="released")
        op = _make_operation(db, po, sequence=10)

        # Create operation material that requires 500g
        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("500"),
            quantity_allocated=Decimal("0"),
            unit="G",
            status="pending",
        )
        db.add(mat)
        db.flush()

        result = operation_blocking.check_operation_blocking(db, po.id, op.id)
        assert result["can_start"] is True
        assert result["material_source"] == "routing"

    def test_insufficient_routing_materials_blocks(self, db):
        """Operation with shortage blocks start."""
        product = _make_product(db)
        component = _make_product(db, item_type="supply", unit="G", sku=f"RAW-{_uid()}")
        _make_inventory(db, component, on_hand=Decimal("100"))

        po = _make_po(db, product, status="released")
        op = _make_operation(db, po, sequence=10)

        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("500"),
            quantity_allocated=Decimal("0"),
            unit="G",
            status="pending",
        )
        db.add(mat)
        db.flush()

        result = operation_blocking.check_operation_blocking(db, po.id, op.id)
        assert result["can_start"] is False
        assert len(result["blocking_issues"]) == 1
        assert result["blocking_issues"][0]["product_sku"] == component.sku

    def test_consumed_materials_are_excluded(self, db):
        """Already consumed materials should not block the operation."""
        product = _make_product(db)
        component = _make_product(db, item_type="supply", unit="G", sku=f"RAW-{_uid()}")
        # No inventory - but material is already consumed

        po = _make_po(db, product, status="released")
        op = _make_operation(db, po, sequence=10)

        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("500"),
            quantity_allocated=Decimal("500"),
            quantity_consumed=Decimal("500"),
            unit="G",
            status="consumed",
        )
        db.add(mat)
        db.flush()

        result = operation_blocking.check_operation_blocking(db, po.id, op.id)
        assert result["can_start"] is True

    def test_bom_fallback_path_with_sufficient_material(self, db):
        """When no routing materials exist, falls back to BOM lines."""
        product = _make_product(db)
        component = _make_product(db, item_type="supply", unit="G", sku=f"RAW-{_uid()}")
        _make_inventory(db, component, on_hand=Decimal("5000"))

        bom = BOM(product_id=product.id, name="Test BOM", active=True)
        db.add(bom)
        db.flush()

        bom_line = BOMLine(
            bom_id=bom.id,
            component_id=component.id,
            quantity=Decimal("50"),
            unit="G",
            consume_stage="production",
            is_cost_only=False,
        )
        db.add(bom_line)
        db.flush()

        po = _make_po(db, product, quantity=10, status="released", bom_id=bom.id)
        op = _make_operation(db, po, sequence=10, operation_code="PRINT")

        result = operation_blocking.check_operation_blocking(db, po.id, op.id)
        assert result["can_start"] is True
        assert result["material_source"] == "bom"

    def test_bom_fallback_path_with_shortage_blocks(self, db):
        """BOM fallback with insufficient inventory blocks."""
        product = _make_product(db)
        component = _make_product(db, item_type="supply", unit="G", sku=f"RAW-{_uid()}")
        _make_inventory(db, component, on_hand=Decimal("10"))  # Only 10g

        bom = BOM(product_id=product.id, name="Test BOM", active=True)
        db.add(bom)
        db.flush()

        bom_line = BOMLine(
            bom_id=bom.id,
            component_id=component.id,
            quantity=Decimal("50"),  # 50g per unit * 10 units = 500g needed
            unit="G",
            consume_stage="production",
            is_cost_only=False,
        )
        db.add(bom_line)
        db.flush()

        po = _make_po(db, product, quantity=10, status="released", bom_id=bom.id)
        op = _make_operation(db, po, sequence=10, operation_code="PRINT")

        result = operation_blocking.check_operation_blocking(db, po.id, op.id)
        assert result["can_start"] is False
        assert result["material_source"] == "bom"
        assert len(result["blocking_issues"]) == 1

    def test_no_bom_id_returns_can_start(self, db):
        """PO without bom_id and no routing materials should return can_start."""
        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op = _make_operation(db, po, sequence=10)

        result = operation_blocking.check_operation_blocking(db, po.id, op.id)
        assert result["can_start"] is True
        assert result["material_source"] is None


# =============================================================================
# operation_blocking — can_operation_start
# =============================================================================

class TestCanOperationStart:
    def test_returns_simplified_response(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="released")
        op = _make_operation(db, po, sequence=10)

        result = operation_blocking.can_operation_start(db, po.id, op.id)
        assert "can_start" in result
        assert "blocking_issues" in result
        # Should not include full material_issues in simplified result
        assert "material_issues" not in result


# =============================================================================
# operation_blocking — get_pending_purchase_orders
# =============================================================================

class TestGetPendingPurchaseOrders:
    def test_returns_pending_po_with_remaining_quantity(self, db):
        component = _make_product(db, item_type="supply", unit="G")
        vendor = Vendor(code=f"V-{_uid()}", name="Test Vendor", is_active=True)
        db.add(vendor)
        db.flush()

        purchase_order = PurchaseOrder(
            po_number=f"PO-{_uid()}",
            vendor_id=vendor.id,
            status="ordered",
            created_by="test",
        )
        db.add(purchase_order)
        db.flush()

        pol = PurchaseOrderLine(
            purchase_order_id=purchase_order.id,
            product_id=component.id,
            line_number=1,
            quantity_ordered=Decimal("1000"),
            quantity_received=Decimal("200"),
            unit_cost=Decimal("0.02"),
            line_total=Decimal("20"),
        )
        db.add(pol)
        db.flush()

        results = operation_blocking.get_pending_purchase_orders(db, component.id)
        assert len(results) >= 1
        po_result, remaining = results[0]
        assert remaining == Decimal("800")

    def test_fully_received_po_excluded(self, db):
        component = _make_product(db, item_type="supply", unit="G")
        vendor = Vendor(code=f"V-{_uid()}", name="Test Vendor", is_active=True)
        db.add(vendor)
        db.flush()

        purchase_order = PurchaseOrder(
            po_number=f"PO-{_uid()}",
            vendor_id=vendor.id,
            status="ordered",
            created_by="test",
        )
        db.add(purchase_order)
        db.flush()

        pol = PurchaseOrderLine(
            purchase_order_id=purchase_order.id,
            product_id=component.id,
            line_number=1,
            quantity_ordered=Decimal("1000"),
            quantity_received=Decimal("1000"),  # fully received
            unit_cost=Decimal("0.02"),
            line_total=Decimal("20"),
        )
        db.add(pol)
        db.flush()

        results = operation_blocking.get_pending_purchase_orders(db, component.id)
        # Filter to just this product's results (DB may have others from prior tests)
        relevant = [r for r in results if r[0].id == purchase_order.id]
        assert len(relevant) == 0


# =============================================================================
# operation_generation — get_active_routing
# =============================================================================

class TestGetActiveRouting:
    def test_returns_active_routing(self, db):
        product = _make_product(db)
        routing, _ = _make_routing(db, product)

        result = operation_generation.get_active_routing(db, product.id)
        assert result is not None
        assert result.id == routing.id

    def test_inactive_routing_not_returned(self, db):
        product = _make_product(db)
        routing, _ = _make_routing(db, product)
        routing.is_active = False
        db.flush()

        result = operation_generation.get_active_routing(db, product.id)
        assert result is None

    def test_no_routing_returns_none(self, db):
        product = _make_product(db)

        result = operation_generation.get_active_routing(db, product.id)
        assert result is None


# =============================================================================
# operation_generation — get_routing_operations
# =============================================================================

class TestGetRoutingOperations:
    def test_returns_ops_sorted_by_sequence(self, db):
        product = _make_product(db)
        routing, _ = _make_routing(db, product, operations_data=[
            {"sequence": 20, "operation_code": "QC", "operation_name": "Quality Check",
             "setup_time_minutes": 0, "run_time_minutes": 5},
            {"sequence": 10, "operation_code": "PRINT", "operation_name": "Print",
             "setup_time_minutes": 5, "run_time_minutes": 10},
        ])

        ops = operation_generation.get_routing_operations(db, routing.id)
        assert len(ops) == 2
        assert ops[0].sequence == 10
        assert ops[1].sequence == 20


# =============================================================================
# operation_generation — generate_operations_from_routing
# =============================================================================

class TestGenerateOperationsFromRouting:
    def test_creates_po_operations_from_routing(self, db):
        product = _make_product(db)
        routing, routing_ops = _make_routing(db, product, operations_data=[
            {"sequence": 10, "operation_code": "PRINT", "operation_name": "Print",
             "setup_time_minutes": 5, "run_time_minutes": Decimal("2.5")},
            {"sequence": 20, "operation_code": "QC", "operation_name": "QC",
             "setup_time_minutes": 0, "run_time_minutes": Decimal("1.0")},
        ])
        po = _make_po(db, product, quantity=10, status="draft")

        ops = operation_generation.generate_operations_from_routing(db, po, routing)

        assert len(ops) == 2
        assert ops[0].sequence == 10
        assert ops[0].operation_code == "PRINT"
        assert ops[0].planned_setup_minutes == 5
        # run_time_minutes * quantity = 2.5 * 10 = 25
        assert float(ops[0].planned_run_minutes) == 25.0
        assert ops[0].status == "pending"
        assert ops[0].routing_operation_id == routing_ops[0].id
        assert ops[1].sequence == 20

    def test_creates_materials_for_operations(self, db):
        product = _make_product(db)
        component = _make_product(db, item_type="supply", unit="G")
        routing, routing_ops = _make_routing(db, product)
        rop = routing_ops[0]

        # Add a routing operation material
        rom = RoutingOperationMaterial(
            routing_operation_id=rop.id,
            component_id=component.id,
            quantity=Decimal("37"),
            quantity_per="unit",
            unit="G",
            scrap_factor=Decimal("5"),
        )
        db.add(rom)
        db.flush()

        po = _make_po(db, product, quantity=10, status="draft")
        ops = operation_generation.generate_operations_from_routing(db, po, routing)

        # Check that materials were generated
        po_op = ops[0]
        mats = db.query(ProductionOrderOperationMaterial).filter(
            ProductionOrderOperationMaterial.production_order_operation_id == po_op.id
        ).all()

        assert len(mats) == 1
        mat = mats[0]
        assert mat.component_id == component.id
        assert mat.unit == "G"
        # 37 * 10 * (1 + 0.05) = 388.5
        assert float(mat.quantity_required) == pytest.approx(388.5, rel=1e-2)
        assert mat.status == "pending"


# =============================================================================
# operation_generation — release_production_order
# =============================================================================

class TestReleaseProductionOrder:
    def test_release_draft_po_generates_operations(self, db):
        product = _make_product(db)
        routing, _ = _make_routing(db, product)
        po = _make_po(db, product, status="draft")

        released_po, created_ops = operation_generation.release_production_order(db, po)
        assert released_po.status == "released"
        assert len(created_ops) == 1

    def test_release_non_draft_raises(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="released")

        with pytest.raises(ValueError, match="Cannot release PO"):
            operation_generation.release_production_order(db, po)

    def test_release_without_routing_still_releases(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="draft")

        released_po, created_ops = operation_generation.release_production_order(db, po)
        assert released_po.status == "released"
        assert len(created_ops) == 0

    def test_release_with_existing_ops_does_not_regenerate(self, db):
        product = _make_product(db)
        routing, _ = _make_routing(db, product)
        po = _make_po(db, product, status="draft")

        # Pre-create an operation
        _make_operation(db, po, sequence=10)

        released_po, created_ops = operation_generation.release_production_order(db, po)
        assert released_po.status == "released"
        assert len(created_ops) == 0  # Did not regenerate


# =============================================================================
# operation_generation — generate_operations_manual
# =============================================================================

class TestGenerateOperationsManual:
    def test_generates_when_no_existing_ops(self, db):
        product = _make_product(db)
        routing, _ = _make_routing(db, product)
        po = _make_po(db, product, status="released")

        ops = operation_generation.generate_operations_manual(db, po)
        assert len(ops) == 1

    def test_raises_when_ops_exist_without_force(self, db):
        product = _make_product(db)
        routing, _ = _make_routing(db, product)
        po = _make_po(db, product, status="released")
        _make_operation(db, po, sequence=10)

        with pytest.raises(ValueError, match="Operations already exist"):
            operation_generation.generate_operations_manual(db, po)

    def test_force_regenerates_operations(self, db):
        product = _make_product(db)
        routing, _ = _make_routing(db, product, operations_data=[
            {"sequence": 10, "operation_code": "PRINT", "operation_name": "Print",
             "setup_time_minutes": 5, "run_time_minutes": 10},
            {"sequence": 20, "operation_code": "QC", "operation_name": "QC",
             "setup_time_minutes": 0, "run_time_minutes": 5},
        ])
        po = _make_po(db, product, status="released")
        _make_operation(db, po, sequence=10)

        ops = operation_generation.generate_operations_manual(db, po, force=True)
        assert len(ops) == 2

    def test_no_routing_returns_empty(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="released")

        ops = operation_generation.generate_operations_manual(db, po)
        assert ops == []


# =============================================================================
# operation_generation — get_product_routing_details
# =============================================================================

class TestGetProductRoutingDetails:
    def test_returns_routing_info(self, db):
        product = _make_product(db)
        routing, _ = _make_routing(db, product)

        result = operation_generation.get_product_routing_details(db, product.id)
        assert result is not None
        assert result["routing_id"] == routing.id
        assert result["routing_code"] == routing.code
        assert result["is_active"] is True
        assert len(result["operations"]) == 1

    def test_no_routing_returns_none(self, db):
        product = _make_product(db)

        result = operation_generation.get_product_routing_details(db, product.id)
        assert result is None


# =============================================================================
# production_execution — get_default_location
# =============================================================================

class TestGetDefaultLocation:
    def test_returns_existing_main_location(self, db):
        """Should find the DEFAULT location seeded by conftest."""
        location = production_execution.ProductionExecutionService.get_default_location(db)
        assert location is not None
        assert location.id is not None

    def test_returns_any_active_location_when_no_main(self, db):
        """When MAIN does not exist but another active location does, returns it."""
        # The DEFAULT location from conftest will be found as a fallback
        location = production_execution.ProductionExecutionService.get_default_location(db)
        assert location is not None
        assert location.active is True


# =============================================================================
# production_execution — get_bom_for_production_order
# =============================================================================

class TestGetBomForProductionOrder:
    def test_returns_bom_by_bom_id(self, db):
        product = _make_product(db)
        bom = BOM(product_id=product.id, name="Test BOM", active=True)
        db.add(bom)
        db.flush()

        po = _make_po(db, product, bom_id=bom.id)
        result = production_execution.ProductionExecutionService.get_bom_for_production_order(po, db)
        assert result is not None
        assert result.id == bom.id

    def test_falls_back_to_product_active_bom(self, db):
        product = _make_product(db)
        bom = BOM(product_id=product.id, name="Active BOM", active=True)
        db.add(bom)
        db.flush()

        po = _make_po(db, product)  # no bom_id set
        result = production_execution.ProductionExecutionService.get_bom_for_production_order(po, db)
        assert result is not None
        assert result.id == bom.id

    def test_returns_none_when_no_bom(self, db):
        product = _make_product(db)
        po = _make_po(db, product)

        result = production_execution.ProductionExecutionService.get_bom_for_production_order(po, db)
        assert result is None


# =============================================================================
# production_execution — ensure_inventory_records_exist
# =============================================================================

class TestEnsureInventoryRecordsExist:
    def test_creates_inventory_for_new_components(self, db):
        product = _make_product(db)
        component = _make_product(db, item_type="supply", unit="G")
        bom = BOM(product_id=product.id, name="Test BOM", active=True)
        db.add(bom)
        db.flush()

        bom_line = BOMLine(
            bom_id=bom.id, component_id=component.id,
            quantity=Decimal("100"), unit="G",
        )
        db.add(bom_line)
        db.flush()

        synced = production_execution.ProductionExecutionService.ensure_inventory_records_exist(bom, db)
        assert len(synced) == 1
        assert synced[0]["sku"] == component.sku
        assert synced[0]["action"] == "created"

        # Verify inventory record was created
        inv = db.query(Inventory).filter(Inventory.product_id == component.id).first()
        assert inv is not None
        assert inv.on_hand_quantity == Decimal("0")

    def test_skips_existing_inventory_records(self, db):
        product = _make_product(db)
        component = _make_product(db, item_type="supply", unit="G")
        _make_inventory(db, component, on_hand=Decimal("500"))

        bom = BOM(product_id=product.id, name="Test BOM", active=True)
        db.add(bom)
        db.flush()

        bom_line = BOMLine(
            bom_id=bom.id, component_id=component.id,
            quantity=Decimal("100"), unit="G",
        )
        db.add(bom_line)
        db.flush()

        synced = production_execution.ProductionExecutionService.ensure_inventory_records_exist(bom, db)
        assert len(synced) == 0  # Nothing created


# =============================================================================
# production_execution — produce_finished_goods
# =============================================================================

class TestProduceFinishedGoods:
    def test_adds_goods_to_existing_inventory(self, db):
        product = _make_product(db, standard_cost=Decimal("5.00"))
        _make_inventory(db, product, on_hand=Decimal("10"))
        po = _make_po(db, product, quantity=5, status="in_progress")

        result = production_execution.ProductionExecutionService.produce_finished_goods(
            po, good_quantity=5.0, db=db, created_by="test"
        )
        assert result["quantity_produced"] == 5.0
        assert result["product_id"] == product.id

        inv = db.query(Inventory).filter(Inventory.product_id == product.id).first()
        assert float(inv.on_hand_quantity) == 15.0

    def test_creates_inventory_record_if_needed(self, db):
        product = _make_product(db, standard_cost=Decimal("5.00"))
        po = _make_po(db, product, quantity=3, status="in_progress")

        result = production_execution.ProductionExecutionService.produce_finished_goods(
            po, good_quantity=3.0, db=db, created_by="test"
        )
        assert result["quantity_produced"] == 3.0

        inv = db.query(Inventory).filter(
            Inventory.product_id == product.id
        ).first()
        assert inv is not None
        assert float(inv.on_hand_quantity) == 3.0

    def test_creates_production_transaction(self, db):
        product = _make_product(db, standard_cost=Decimal("5.00"))
        po = _make_po(db, product, quantity=2, status="in_progress")

        production_execution.ProductionExecutionService.produce_finished_goods(
            po, good_quantity=2.0, db=db, created_by="tester"
        )

        txn = db.query(InventoryTransaction).filter(
            InventoryTransaction.reference_type == "production_order",
            InventoryTransaction.reference_id == po.id,
            InventoryTransaction.transaction_type == "production",
        ).first()
        assert txn is not None
        assert float(txn.quantity) == 2.0
        assert txn.created_by == "tester"

    def test_no_product_id_raises(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="in_progress")
        po.product_id = None

        with pytest.raises(ValueError, match="no product_id"):
            production_execution.ProductionExecutionService.produce_finished_goods(
                po, good_quantity=1.0, db=db
            )

    def test_product_not_found_raises(self, db):
        product = _make_product(db)
        po = _make_po(db, product, status="in_progress")

        # Use no_autoflush to prevent FK constraint from firing before the
        # service function can check for the missing product
        with db.no_autoflush:
            po.product_id = 999999
            with pytest.raises(ValueError, match="not found"):
                production_execution.ProductionExecutionService.produce_finished_goods(
                    po, good_quantity=1.0, db=db
                )


# =============================================================================
# production_execution — explode_bom_and_reserve_materials
# =============================================================================

class TestExplodeBomAndReserveMaterials:
    def test_no_bom_returns_empty(self, db):
        product = _make_product(db)
        po = _make_po(db, product, quantity=5, status="draft")

        reserved, insufficient, lot_reqs = (
            production_execution.ProductionExecutionService
            .explode_bom_and_reserve_materials(po, db)
        )
        assert reserved == []
        assert insufficient == []
        assert lot_reqs == []

    def test_reserves_sufficient_materials(self, db):
        product = _make_product(db)
        component = _make_product(db, item_type="supply", unit="G",
                                  standard_cost=Decimal("0.02"))
        _make_inventory(db, component, on_hand=Decimal("1000"))

        bom = BOM(product_id=product.id, name="BOM", active=True)
        db.add(bom)
        db.flush()
        bom_line = BOMLine(
            bom_id=bom.id, component_id=component.id,
            quantity=Decimal("50"), unit="G",
        )
        db.add(bom_line)
        db.flush()

        po = _make_po(db, product, quantity=10, status="draft", bom_id=bom.id)

        reserved, insufficient, lot_reqs = (
            production_execution.ProductionExecutionService
            .explode_bom_and_reserve_materials(po, db)
        )
        assert len(reserved) == 1
        assert reserved[0]["component_id"] == component.id
        assert reserved[0]["quantity_reserved"] == 500.0  # 50 * 10
        assert len(insufficient) == 0

    def test_reports_insufficient_materials(self, db):
        product = _make_product(db)
        component = _make_product(db, item_type="supply", unit="G",
                                  standard_cost=Decimal("0.02"))
        _make_inventory(db, component, on_hand=Decimal("100"))  # Only 100g

        bom = BOM(product_id=product.id, name="BOM", active=True)
        db.add(bom)
        db.flush()
        bom_line = BOMLine(
            bom_id=bom.id, component_id=component.id,
            quantity=Decimal("50"), unit="G",
        )
        db.add(bom_line)
        db.flush()

        po = _make_po(db, product, quantity=10, status="draft", bom_id=bom.id)

        reserved, insufficient, lot_reqs = (
            production_execution.ProductionExecutionService
            .explode_bom_and_reserve_materials(po, db)
        )
        assert len(reserved) == 0
        assert len(insufficient) == 1
        assert insufficient[0]["component_id"] == component.id
        assert insufficient[0]["shortage"] > 0

    def test_skips_svc_and_mfg_skus(self, db):
        """Service and manufacturing overhead items should be skipped."""
        product = _make_product(db)
        svc_item = _make_product(db, item_type="service", sku=f"SVC-{_uid()}")
        mfg_item = _make_product(db, item_type="service", sku=f"MFG-{_uid()}")

        bom = BOM(product_id=product.id, name="BOM", active=True)
        db.add(bom)
        db.flush()
        for comp in [svc_item, mfg_item]:
            db.add(BOMLine(
                bom_id=bom.id, component_id=comp.id,
                quantity=Decimal("1"), unit="HR",
            ))
        db.flush()

        po = _make_po(db, product, quantity=5, status="draft", bom_id=bom.id)

        reserved, insufficient, lot_reqs = (
            production_execution.ProductionExecutionService
            .explode_bom_and_reserve_materials(po, db)
        )
        # Both should be skipped
        assert len(reserved) == 0
        assert len(insufficient) == 0


# =============================================================================
# routing_service.py — add_operation_material (duplicate guard)
# =============================================================================

class TestAddOperationMaterialDuplicateGuard:
    def test_raises_409_for_duplicate_component(self, db):
        from fastapi import HTTPException

        product = _make_product(db, item_type="finished_good")
        comp = _make_product(db, item_type="raw_material", standard_cost=Decimal("1.00"))
        db.commit()

        _routing, ops = _make_routing(db, product)
        routing_op = ops[0]
        db.commit()

        data = {
            "component_id": comp.id,
            "quantity": Decimal("10"),
            "unit": "EA",
            "quantity_per": "unit",
        }
        routing_service.add_operation_material(db, routing_op.id, data=data)

        with pytest.raises(HTTPException) as exc_info:
            routing_service.add_operation_material(db, routing_op.id, data=data)
        assert exc_info.value.status_code == 409
        assert "already on this operation" in exc_info.value.detail
