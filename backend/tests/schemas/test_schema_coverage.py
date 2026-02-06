"""
Schema coverage tests.

Instantiates every Pydantic model in the target schema modules to exercise
class definitions, field defaults, validators, computed fields, and Config
blocks.  The goal is LINE COVERAGE, not exhaustive validation testing.
"""
from datetime import datetime, date, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError


# ============================================================================
# production_order.py
# ============================================================================


class TestProductionOrderSchemas:
    """Cover app/schemas/production_order.py"""

    # -- Enums ---------------------------------------------------------------

    def test_production_order_status_enum(self):
        from app.schemas.production_order import ProductionOrderStatus

        assert ProductionOrderStatus.DRAFT == "draft"
        assert ProductionOrderStatus.RELEASED == "released"
        assert ProductionOrderStatus.SCHEDULED == "scheduled"
        assert ProductionOrderStatus.IN_PROGRESS == "in_progress"
        assert ProductionOrderStatus.COMPLETED == "completed"
        assert ProductionOrderStatus.QC_HOLD == "qc_hold"
        assert ProductionOrderStatus.SCRAPPED == "scrapped"
        assert ProductionOrderStatus.CLOSED == "closed"
        assert ProductionOrderStatus.CANCELLED == "cancelled"
        assert ProductionOrderStatus.ON_HOLD == "on_hold"

    def test_production_order_source_enum(self):
        from app.schemas.production_order import ProductionOrderSource

        assert ProductionOrderSource.MANUAL == "manual"
        assert ProductionOrderSource.SALES_ORDER == "sales_order"
        assert ProductionOrderSource.MRP_PLANNED == "mrp_planned"

    def test_production_order_type_enum(self):
        from app.schemas.production_order import ProductionOrderType

        assert ProductionOrderType.MAKE_TO_ORDER == "MAKE_TO_ORDER"
        assert ProductionOrderType.MAKE_TO_STOCK == "MAKE_TO_STOCK"

    def test_operation_status_enum(self):
        from app.schemas.production_order import OperationStatus

        assert OperationStatus.PENDING == "pending"
        assert OperationStatus.QUEUED == "queued"
        assert OperationStatus.RUNNING == "running"
        assert OperationStatus.COMPLETE == "complete"
        assert OperationStatus.SKIPPED == "skipped"

    def test_qc_status_enum(self):
        from app.schemas.production_order import QCStatus

        assert QCStatus.NOT_REQUIRED == "not_required"
        assert QCStatus.PENDING == "pending"
        assert QCStatus.IN_PROGRESS == "in_progress"
        assert QCStatus.PASSED == "passed"
        assert QCStatus.FAILED == "failed"
        assert QCStatus.WAIVED == "waived"

    # -- Operation schemas ---------------------------------------------------

    def test_production_order_operation_base(self):
        from app.schemas.production_order import ProductionOrderOperationBase

        op = ProductionOrderOperationBase(
            work_center_id=1,
            sequence=1,
            planned_run_minutes=Decimal("30"),
        )
        assert op.resource_id is None
        assert op.operation_code is None
        assert op.operation_name is None
        assert op.planned_setup_minutes == 0
        assert op.notes is None

    def test_production_order_operation_create(self):
        from app.schemas.production_order import ProductionOrderOperationCreate

        op = ProductionOrderOperationCreate(
            work_center_id=1, sequence=1, planned_run_minutes=Decimal("60"),
            routing_operation_id=5,
        )
        assert op.routing_operation_id == 5

    def test_production_order_operation_create_defaults(self):
        from app.schemas.production_order import ProductionOrderOperationCreate

        op = ProductionOrderOperationCreate(
            work_center_id=1, sequence=1, planned_run_minutes=Decimal("10"),
        )
        assert op.routing_operation_id is None

    def test_production_order_operation_update(self):
        from app.schemas.production_order import ProductionOrderOperationUpdate

        op = ProductionOrderOperationUpdate()
        assert op.resource_id is None
        assert op.status is None
        assert op.quantity_completed is None
        assert op.quantity_scrapped is None
        assert op.actual_setup_minutes is None
        assert op.actual_run_minutes is None
        assert op.scheduled_start is None
        assert op.scheduled_end is None
        assert op.actual_start is None
        assert op.actual_end is None
        assert op.bambu_task_id is None
        assert op.bambu_plate_index is None
        assert op.operator_name is None
        assert op.notes is None

    def test_production_order_operation_update_with_values(self):
        from app.schemas.production_order import (
            ProductionOrderOperationUpdate,
            OperationStatus,
        )

        now = datetime.now(timezone.utc)
        op = ProductionOrderOperationUpdate(
            resource_id=1,
            status=OperationStatus.RUNNING,
            quantity_completed=Decimal("5"),
            quantity_scrapped=Decimal("1"),
            actual_setup_minutes=Decimal("3"),
            actual_run_minutes=Decimal("20"),
            scheduled_start=now,
            scheduled_end=now,
            actual_start=now,
            actual_end=now,
            bambu_task_id="task-123",
            bambu_plate_index=0,
            operator_name="Brandan",
            notes="all good",
        )
        assert op.status == OperationStatus.RUNNING

    def test_production_order_operation_response(self):
        from app.schemas.production_order import ProductionOrderOperationResponse

        now = datetime.now(timezone.utc)
        op = ProductionOrderOperationResponse(
            id=1,
            production_order_id=1,
            work_center_id=1,
            sequence=1,
            status="running",
            planned_run_minutes=Decimal("30"),
            created_at=now,
            updated_at=now,
        )
        assert op.routing_operation_id is None
        assert op.work_center_code is None
        assert op.work_center_name is None
        assert op.resource_id is None
        assert op.resource_code is None
        assert op.resource_name is None
        assert op.operation_code is None
        assert op.operation_name is None
        assert op.quantity_completed == 0
        assert op.quantity_scrapped == 0
        assert op.planned_setup_minutes == 0
        assert op.actual_setup_minutes is None
        assert op.actual_run_minutes is None
        assert op.scheduled_start is None
        assert op.scheduled_end is None
        assert op.actual_start is None
        assert op.actual_end is None
        assert op.bambu_task_id is None
        assert op.bambu_plate_index is None
        assert op.operator_name is None
        assert op.notes is None
        assert op.is_complete is False
        assert op.is_running is False
        assert op.efficiency_percent is None
        assert op.materials == []

    def test_operation_material_response(self):
        from app.schemas.production_order import OperationMaterialResponse

        mat = OperationMaterialResponse(
            id=1,
            component_id=10,
            quantity_required=Decimal("100"),
            unit="G",
            status="pending",
        )
        assert mat.component_sku is None
        assert mat.component_name is None
        assert mat.quantity_allocated == Decimal("0")
        assert mat.quantity_consumed == Decimal("0")

    # -- Production Order CRUD schemas ---------------------------------------

    def test_production_order_base(self):
        from app.schemas.production_order import ProductionOrderBase

        po = ProductionOrderBase(
            product_id=1,
            quantity_ordered=Decimal("10"),
        )
        assert po.due_date is None
        assert po.priority == 3
        assert po.notes is None

    def test_production_order_base_invalid_priority(self):
        from app.schemas.production_order import ProductionOrderBase

        with pytest.raises(ValidationError):
            ProductionOrderBase(
                product_id=1, quantity_ordered=Decimal("10"), priority=6,
            )

    def test_production_order_base_invalid_quantity(self):
        from app.schemas.production_order import ProductionOrderBase

        with pytest.raises(ValidationError):
            ProductionOrderBase(product_id=1, quantity_ordered=Decimal("0"))

    def test_production_order_create(self):
        from app.schemas.production_order import (
            ProductionOrderCreate,
            ProductionOrderSource,
            ProductionOrderType,
        )

        po = ProductionOrderCreate(
            product_id=1,
            quantity_ordered=Decimal("50"),
        )
        assert po.bom_id is None
        assert po.routing_id is None
        assert po.sales_order_id is None
        assert po.sales_order_line_id is None
        assert po.source == ProductionOrderSource.MANUAL
        assert po.order_type == ProductionOrderType.MAKE_TO_ORDER
        assert po.assigned_to is None

    def test_production_order_create_all_fields(self):
        from app.schemas.production_order import (
            ProductionOrderCreate,
            ProductionOrderSource,
            ProductionOrderType,
        )

        po = ProductionOrderCreate(
            product_id=1,
            quantity_ordered=Decimal("50"),
            due_date=date(2026, 3, 1),
            priority=1,
            notes="rush",
            bom_id=10,
            routing_id=5,
            sales_order_id=100,
            sales_order_line_id=200,
            source=ProductionOrderSource.SALES_ORDER,
            order_type=ProductionOrderType.MAKE_TO_STOCK,
            assigned_to="Operator A",
        )
        assert po.source == ProductionOrderSource.SALES_ORDER

    def test_production_order_update(self):
        from app.schemas.production_order import ProductionOrderUpdate

        upd = ProductionOrderUpdate()
        assert upd.quantity_ordered is None
        assert upd.quantity_completed is None
        assert upd.quantity_scrapped is None
        assert upd.status is None
        assert upd.order_type is None
        assert upd.priority is None
        assert upd.due_date is None
        assert upd.scheduled_start is None
        assert upd.scheduled_end is None
        assert upd.assigned_to is None
        assert upd.notes is None

    def test_production_order_schedule_request(self):
        from app.schemas.production_order import ProductionOrderScheduleRequest

        now = datetime.now(timezone.utc)
        req = ProductionOrderScheduleRequest(
            scheduled_start=now, scheduled_end=now,
        )
        assert req.resource_id is None
        assert req.notes is None

    def test_production_order_status_update(self):
        from app.schemas.production_order import (
            ProductionOrderStatusUpdate,
            ProductionOrderStatus,
        )

        upd = ProductionOrderStatusUpdate(status=ProductionOrderStatus.RELEASED)
        assert upd.notes is None

    def test_production_order_list_response(self):
        from app.schemas.production_order import ProductionOrderListResponse

        now = datetime.now(timezone.utc)
        resp = ProductionOrderListResponse(
            id=1, code="MO-001", product_id=1, quantity_ordered=Decimal("10"),
            status="draft", priority=3, source="manual", created_at=now,
        )
        assert resp.product_sku is None
        assert resp.product_name is None
        assert resp.quantity_completed == 0
        assert resp.quantity_remaining == 0
        assert resp.completion_percent == 0
        assert resp.order_type == "MAKE_TO_ORDER"
        assert resp.qc_status == "not_required"
        assert resp.due_date is None
        assert resp.scheduled_start is None
        assert resp.scheduled_end is None
        assert resp.sales_order_id is None
        assert resp.sales_order_code is None
        assert resp.assigned_to is None
        assert resp.operation_count == 0
        assert resp.current_operation is None

    def test_production_order_response(self):
        from app.schemas.production_order import ProductionOrderResponse

        now = datetime.now(timezone.utc)
        resp = ProductionOrderResponse(
            id=1, code="MO-001", product_id=1, quantity_ordered=Decimal("10"),
            source="manual", status="draft", priority=3,
            created_at=now, updated_at=now,
        )
        assert resp.product_sku is None
        assert resp.product_name is None
        assert resp.bom_id is None
        assert resp.bom_code is None
        assert resp.routing_id is None
        assert resp.routing_code is None
        assert resp.sales_order_id is None
        assert resp.sales_order_code is None
        assert resp.sales_order_line_id is None
        assert resp.quantity_completed == 0
        assert resp.quantity_scrapped == 0
        assert resp.quantity_remaining == 0
        assert resp.completion_percent == 0
        assert resp.order_type == "MAKE_TO_ORDER"
        assert resp.qc_status == "not_required"
        assert resp.qc_notes is None
        assert resp.qc_inspected_by is None
        assert resp.qc_inspected_at is None
        assert resp.due_date is None
        assert resp.scheduled_start is None
        assert resp.scheduled_end is None
        assert resp.actual_start is None
        assert resp.actual_end is None
        assert resp.estimated_time_minutes is None
        assert resp.actual_time_minutes is None
        assert resp.estimated_material_cost is None
        assert resp.estimated_labor_cost is None
        assert resp.estimated_total_cost is None
        assert resp.actual_material_cost is None
        assert resp.actual_labor_cost is None
        assert resp.actual_total_cost is None
        assert resp.assigned_to is None
        assert resp.notes is None
        assert resp.remake_of_id is None
        assert resp.remake_of_code is None
        assert resp.remake_reason is None
        assert resp.operations == []
        assert resp.created_by is None
        assert resp.released_at is None
        assert resp.completed_at is None

    def test_production_order_scrap_response(self):
        from app.schemas.production_order import ProductionOrderScrapResponse

        now = datetime.now(timezone.utc)
        resp = ProductionOrderScrapResponse(
            id=1, code="MO-001", product_id=1, quantity_ordered=Decimal("10"),
            source="manual", status="scrapped", priority=3,
            created_at=now, updated_at=now,
        )
        assert resp.remake_order_id is None
        assert resp.remake_order_code is None

    def test_production_order_scrap_response_with_remake(self):
        from app.schemas.production_order import ProductionOrderScrapResponse

        now = datetime.now(timezone.utc)
        resp = ProductionOrderScrapResponse(
            id=1, code="MO-001", product_id=1, quantity_ordered=Decimal("10"),
            source="manual", status="scrapped", priority=3,
            created_at=now, updated_at=now,
            remake_order_id=2, remake_order_code="MO-002",
        )
        assert resp.remake_order_id == 2

    # -- Bulk operations -----------------------------------------------------

    def test_production_order_bulk_create(self):
        from app.schemas.production_order import (
            ProductionOrderBulkCreate,
            ProductionOrderCreate,
        )

        bulk = ProductionOrderBulkCreate(orders=[
            ProductionOrderCreate(product_id=1, quantity_ordered=Decimal("5")),
            ProductionOrderCreate(product_id=2, quantity_ordered=Decimal("10")),
        ])
        assert len(bulk.orders) == 2

    def test_production_order_bulk_status_update(self):
        from app.schemas.production_order import (
            ProductionOrderBulkStatusUpdate,
            ProductionOrderStatus,
        )

        bulk = ProductionOrderBulkStatusUpdate(
            order_ids=[1, 2, 3], status=ProductionOrderStatus.RELEASED,
        )
        assert len(bulk.order_ids) == 3

    # -- Queue / Schedule views ----------------------------------------------

    def test_production_queue_item(self):
        from app.schemas.production_order import ProductionQueueItem

        item = ProductionQueueItem(
            id=1, code="MO-001", product_sku="SKU-001", product_name="Widget",
            quantity_ordered=Decimal("10"), status="released", priority=2,
        )
        assert item.quantity_completed == 0
        assert item.due_date is None
        assert item.current_operation_name is None
        assert item.current_work_center_code is None
        assert item.is_late is False
        assert item.days_until_due is None

    def test_work_center_queue(self):
        from app.schemas.production_order import WorkCenterQueue

        q = WorkCenterQueue(
            work_center_id=1, work_center_code="WC-01",
            work_center_name="Printers",
        )
        assert q.queued_operations == []
        assert q.running_operations == []
        assert q.total_queued_minutes == 0

    def test_production_schedule_summary(self):
        from app.schemas.production_order import ProductionScheduleSummary

        s = ProductionScheduleSummary()
        assert s.total_orders == 0
        assert s.orders_by_status == {}
        assert s.orders_due_today == 0
        assert s.orders_overdue == 0
        assert s.orders_in_progress == 0
        assert s.total_quantity_to_produce == 0

    # -- Split Order ---------------------------------------------------------

    def test_split_quantity(self):
        from app.schemas.production_order import SplitQuantity

        sq = SplitQuantity(quantity=25)
        assert sq.quantity == 25

    def test_split_quantity_invalid(self):
        from app.schemas.production_order import SplitQuantity

        with pytest.raises(ValidationError):
            SplitQuantity(quantity=0)

    def test_production_order_split_request(self):
        from app.schemas.production_order import (
            ProductionOrderSplitRequest,
            SplitQuantity,
        )

        req = ProductionOrderSplitRequest(splits=[
            SplitQuantity(quantity=25),
            SplitQuantity(quantity=25),
        ])
        assert len(req.splits) == 2

    def test_production_order_split_request_too_few(self):
        from app.schemas.production_order import (
            ProductionOrderSplitRequest,
            SplitQuantity,
        )

        with pytest.raises(ValidationError):
            ProductionOrderSplitRequest(splits=[SplitQuantity(quantity=50)])

    def test_production_order_split_response(self):
        from app.schemas.production_order import ProductionOrderSplitResponse

        resp = ProductionOrderSplitResponse(
            parent_order_id=1, parent_order_code="MO-001",
            parent_status="closed", child_orders=[], message="Split done",
        )
        assert resp.child_orders == []

    # -- Scrap Reason --------------------------------------------------------

    def test_scrap_reason_create(self):
        from app.schemas.production_order import ScrapReasonCreate

        sr = ScrapReasonCreate(code="LAYER_SHIFT", name="Layer Shift")
        assert sr.description is None
        assert sr.sequence == 0

    def test_scrap_reason_create_invalid_empty_code(self):
        from app.schemas.production_order import ScrapReasonCreate

        with pytest.raises(ValidationError):
            ScrapReasonCreate(code="", name="Name")

    def test_scrap_reason_detail(self):
        from app.schemas.production_order import ScrapReasonDetail

        sd = ScrapReasonDetail(id=1, code="LS", name="Layer Shift", sequence=1)
        assert sd.description is None

    def test_scrap_reason_update(self):
        from app.schemas.production_order import ScrapReasonUpdate

        upd = ScrapReasonUpdate()
        assert upd.name is None
        assert upd.description is None
        assert upd.active is None
        assert upd.sequence is None

    def test_scrap_reasons_response(self):
        from app.schemas.production_order import ScrapReasonsResponse

        resp = ScrapReasonsResponse(
            reasons=["LS", "WRP"],
            details=[],
            descriptions={"LS": "Layer Shift", "WRP": "Warping"},
        )
        assert len(resp.reasons) == 2

    # -- QC Inspection -------------------------------------------------------

    def test_qc_inspection_request(self):
        from app.schemas.production_order import QCInspectionRequest, QCStatus

        req = QCInspectionRequest(result=QCStatus.PASSED)
        assert req.notes is None

    def test_qc_inspection_response(self):
        from app.schemas.production_order import QCInspectionResponse

        resp = QCInspectionResponse(
            production_order_id=1, production_order_code="MO-001",
            qc_status="passed", message="QC passed",
        )
        assert resp.qc_notes is None
        assert resp.qc_inspected_by is None
        assert resp.qc_inspected_at is None
        assert resp.sales_order_updated is False
        assert resp.sales_order_status is None

    # -- Spool Consumption ---------------------------------------------------

    def test_spool_usage(self):
        from app.schemas.production_order import SpoolUsage

        su = SpoolUsage(product_id=5, spool_id=12)
        assert su.weight_consumed_g is None

    def test_spool_usage_with_weight(self):
        from app.schemas.production_order import SpoolUsage

        su = SpoolUsage(
            product_id=5, spool_id=12, weight_consumed_g=Decimal("150.5"),
        )
        assert su.weight_consumed_g == Decimal("150.5")

    def test_production_order_complete_request(self):
        from app.schemas.production_order import ProductionOrderCompleteRequest

        req = ProductionOrderCompleteRequest()
        assert req.quantity_completed is None
        assert req.quantity_scrapped is None
        assert req.force_close_short is False
        assert req.notes is None
        assert req.spools_used is None

    def test_production_order_complete_request_with_spools(self):
        from app.schemas.production_order import (
            ProductionOrderCompleteRequest,
            SpoolUsage,
        )

        req = ProductionOrderCompleteRequest(
            quantity_completed=Decimal("10"),
            spools_used=[SpoolUsage(product_id=5, spool_id=12)],
        )
        assert len(req.spools_used) == 1

    # -- Operation-Level Scrap -----------------------------------------------

    def test_operation_scrap_request(self):
        from app.schemas.production_order import OperationScrapRequest

        req = OperationScrapRequest(
            quantity_scrapped=2, scrap_reason_code="layer_shift",
        )
        assert req.notes is None
        assert req.create_replacement is True

    def test_operation_scrap_request_invalid(self):
        from app.schemas.production_order import OperationScrapRequest

        with pytest.raises(ValidationError):
            OperationScrapRequest(
                quantity_scrapped=0, scrap_reason_code="x",
            )

    def test_scrap_cascade_material(self):
        from app.schemas.production_order import ScrapCascadeMaterial

        mat = ScrapCascadeMaterial(
            operation_id=1, operation_sequence=1, operation_name="Print",
            component_id=10, component_sku="PLA-BLU",
            component_name="PLA Blue", quantity=100.0, unit="G",
            unit_cost=0.02, cost=2.0,
        )
        assert mat.cost == 2.0

    def test_scrap_cascade_response(self):
        from app.schemas.production_order import ScrapCascadeResponse

        resp = ScrapCascadeResponse(
            production_order_id=1, production_order_code="MO-001",
            operation_id=5, operation_name="Assembly",
            quantity_scrapped=2, materials_consumed=[],
            total_cost=0.0, operations_affected=0,
        )
        assert resp.materials_consumed == []

    def test_replacement_order_info(self):
        from app.schemas.production_order import ReplacementOrderInfo

        info = ReplacementOrderInfo(id=2, code="MO-002")
        assert info.code == "MO-002"

    def test_operation_scrap_response(self):
        from app.schemas.production_order import OperationScrapResponse

        resp = OperationScrapResponse(
            success=True, scrap_records_created=5,
            operations_affected=3, total_scrap_cost=12.50,
        )
        assert resp.journal_entry_number is None
        assert resp.downstream_ops_skipped == 0
        assert resp.replacement_order is None

    def test_operation_scrap_response_with_replacement(self):
        from app.schemas.production_order import (
            OperationScrapResponse,
            ReplacementOrderInfo,
        )

        resp = OperationScrapResponse(
            success=True, scrap_records_created=5,
            operations_affected=3, total_scrap_cost=12.50,
            journal_entry_number="JE-001", downstream_ops_skipped=2,
            replacement_order=ReplacementOrderInfo(id=2, code="MO-002"),
        )
        assert resp.replacement_order.id == 2

    # -- Partial Operation Completion ----------------------------------------

    def test_operation_partial_complete_request(self):
        from app.schemas.production_order import OperationPartialCompleteRequest

        req = OperationPartialCompleteRequest(quantity_completed=8)
        assert req.quantity_scrapped == 0
        assert req.scrap_reason_code is None
        assert req.scrap_notes is None
        assert req.actual_run_minutes is None
        assert req.notes is None
        assert req.create_replacement is True

    def test_operation_partial_complete_request_with_scrap(self):
        from app.schemas.production_order import OperationPartialCompleteRequest

        req = OperationPartialCompleteRequest(
            quantity_completed=8, quantity_scrapped=2,
            scrap_reason_code="layer_shift", scrap_notes="bad layers",
            actual_run_minutes=45, notes="partial",
            create_replacement=False,
        )
        assert req.create_replacement is False


# ============================================================================
# manufacturing.py
# ============================================================================


class TestManufacturingSchemas:
    """Cover app/schemas/manufacturing.py"""

    # -- Helper function -----------------------------------------------------

    def test_validate_uom_code_valid(self):
        from app.schemas.manufacturing import validate_uom_code

        assert validate_uom_code("kg") == "KG"
        assert validate_uom_code("ea") == "EA"
        assert validate_uom_code(" G ") == "G"

    def test_validate_uom_code_none_and_empty(self):
        from app.schemas.manufacturing import validate_uom_code

        assert validate_uom_code(None) is None
        assert validate_uom_code("") is None
        assert validate_uom_code("  ") is None

    def test_validate_uom_code_invalid(self):
        from app.schemas.manufacturing import validate_uom_code

        with pytest.raises(ValueError, match="Invalid unit"):
            validate_uom_code("FOOBAR")

    def test_valid_uom_codes_list(self):
        from app.schemas.manufacturing import VALID_UOM_CODES

        assert "EA" in VALID_UOM_CODES
        assert "KG" in VALID_UOM_CODES
        assert "HR" in VALID_UOM_CODES

    # -- Enums ---------------------------------------------------------------

    def test_work_center_type_enum(self):
        from app.schemas.manufacturing import WorkCenterType

        assert WorkCenterType.MACHINE == "machine"
        assert WorkCenterType.STATION == "station"
        assert WorkCenterType.LABOR == "labor"

    def test_resource_status_enum(self):
        from app.schemas.manufacturing import ResourceStatus

        assert ResourceStatus.AVAILABLE == "available"
        assert ResourceStatus.BUSY == "busy"
        assert ResourceStatus.MAINTENANCE == "maintenance"
        assert ResourceStatus.OFFLINE == "offline"

    def test_runtime_source_enum(self):
        from app.schemas.manufacturing import RuntimeSource

        assert RuntimeSource.MANUAL == "manual"
        assert RuntimeSource.SLICER == "slicer"
        assert RuntimeSource.CALCULATED == "calculated"

    def test_quantity_per_enum(self):
        from app.schemas.manufacturing import QuantityPer

        assert QuantityPer.UNIT == "unit"
        assert QuantityPer.BATCH == "batch"
        assert QuantityPer.ORDER == "order"

    def test_po_operation_material_status_enum(self):
        from app.schemas.manufacturing import POOperationMaterialStatus

        assert POOperationMaterialStatus.PENDING == "pending"
        assert POOperationMaterialStatus.ALLOCATED == "allocated"
        assert POOperationMaterialStatus.CONSUMED == "consumed"
        assert POOperationMaterialStatus.RETURNED == "returned"

    # -- Work Center schemas -------------------------------------------------

    def test_work_center_base(self):
        from app.schemas.manufacturing import WorkCenterBase, WorkCenterType

        wc = WorkCenterBase(code="WC-01", name="Print Farm")
        assert wc.description is None
        assert wc.center_type == WorkCenterType.STATION
        assert wc.capacity_hours_per_day is None
        assert wc.capacity_units_per_hour is None
        assert wc.machine_rate_per_hour is None
        assert wc.labor_rate_per_hour is None
        assert wc.overhead_rate_per_hour is None
        assert wc.is_bottleneck is False
        assert wc.scheduling_priority == 50
        assert wc.is_active is True

    def test_work_center_create(self):
        from app.schemas.manufacturing import WorkCenterCreate

        wc = WorkCenterCreate(code="WC-01", name="Print Farm")
        assert wc.code == "WC-01"

    def test_work_center_update(self):
        from app.schemas.manufacturing import WorkCenterUpdate

        upd = WorkCenterUpdate()
        assert upd.code is None
        assert upd.name is None
        assert upd.description is None
        assert upd.center_type is None
        assert upd.is_active is None

    def test_work_center_response(self):
        from app.schemas.manufacturing import WorkCenterResponse

        now = datetime.now(timezone.utc)
        resp = WorkCenterResponse(
            id=1, code="WC-01", name="Print Farm",
            created_at=now, updated_at=now,
        )
        assert resp.resource_count == 0
        assert resp.total_rate_per_hour == Decimal("0")

    def test_work_center_list_response(self):
        from app.schemas.manufacturing import WorkCenterListResponse

        resp = WorkCenterListResponse(
            id=1, code="WC-01", name="Print Farm",
            center_type="station", is_active=True,
        )
        assert resp.capacity_hours_per_day is None
        assert resp.total_rate_per_hour == Decimal("0")
        assert resp.resource_count == 0
        assert resp.is_bottleneck is False

    # -- Resource schemas ----------------------------------------------------

    def test_resource_base(self):
        from app.schemas.manufacturing import ResourceBase

        r = ResourceBase(code="P1S-01", name="Bambu P1S #1")
        assert r.machine_type is None
        assert r.serial_number is None
        assert r.bambu_device_id is None
        assert r.bambu_ip_address is None
        assert r.capacity_hours_per_day is None
        assert r.status.value == "available"
        assert r.is_active is True

    def test_resource_create(self):
        from app.schemas.manufacturing import ResourceCreate

        r = ResourceCreate(code="P1S-01", name="Bambu P1S #1")
        assert r.work_center_id is None

    def test_resource_update(self):
        from app.schemas.manufacturing import ResourceUpdate

        upd = ResourceUpdate()
        assert upd.work_center_id is None
        assert upd.code is None
        assert upd.name is None
        assert upd.status is None
        assert upd.is_active is None

    def test_resource_response(self):
        from app.schemas.manufacturing import ResourceResponse

        now = datetime.now(timezone.utc)
        resp = ResourceResponse(
            id=1, code="P1S-01", name="Bambu P1S #1",
            work_center_id=1, created_at=now, updated_at=now,
        )
        assert resp.work_center_code is None
        assert resp.work_center_name is None

    # -- Routing Operation schemas -------------------------------------------

    def test_routing_operation_base(self):
        from app.schemas.manufacturing import RoutingOperationBase

        op = RoutingOperationBase(
            work_center_id=1, sequence=1, run_time_minutes=Decimal("30"),
        )
        assert op.operation_code is None
        assert op.operation_name is None
        assert op.description is None
        assert op.setup_time_minutes == Decimal("0")
        assert op.wait_time_minutes == Decimal("0")
        assert op.move_time_minutes == Decimal("0")
        assert op.runtime_source.value == "manual"
        assert op.slicer_file_path is None
        assert op.units_per_cycle == 1
        assert op.scrap_rate_percent == Decimal("0")
        assert op.labor_rate_override is None
        assert op.machine_rate_override is None
        assert op.predecessor_operation_id is None
        assert op.can_overlap is False
        assert op.is_active is True

    def test_routing_operation_create(self):
        from app.schemas.manufacturing import RoutingOperationCreate

        op = RoutingOperationCreate(
            work_center_id=1, sequence=1, run_time_minutes=Decimal("30"),
        )
        assert op.work_center_id == 1

    def test_routing_operation_update(self):
        from app.schemas.manufacturing import RoutingOperationUpdate

        upd = RoutingOperationUpdate()
        assert upd.work_center_id is None
        assert upd.sequence is None
        assert upd.run_time_minutes is None
        assert upd.can_overlap is None
        assert upd.is_active is None

    def test_routing_operation_response(self):
        from app.schemas.manufacturing import RoutingOperationResponse

        now = datetime.now(timezone.utc)
        resp = RoutingOperationResponse(
            id=1, routing_id=1, work_center_id=1, sequence=1,
            run_time_minutes=Decimal("30"),
            created_at=now, updated_at=now,
        )
        assert resp.work_center_code is None
        assert resp.work_center_name is None
        assert resp.total_time_minutes == Decimal("0")
        assert resp.calculated_cost == Decimal("0")

    # -- Routing schemas -----------------------------------------------------

    def test_routing_base(self):
        from app.schemas.manufacturing import RoutingBase

        r = RoutingBase()
        assert r.product_id is None
        assert r.code is None
        assert r.name is None
        assert r.is_template is False
        assert r.version == 1
        assert r.revision == "1.0"
        assert r.effective_date is None
        assert r.notes is None
        assert r.is_active is True

    def test_routing_create(self):
        from app.schemas.manufacturing import RoutingCreate

        r = RoutingCreate()
        assert r.operations == []

    def test_routing_update(self):
        from app.schemas.manufacturing import RoutingUpdate

        upd = RoutingUpdate()
        assert upd.code is None
        assert upd.name is None
        assert upd.is_template is None
        assert upd.revision is None
        assert upd.is_active is None

    def test_routing_response(self):
        from app.schemas.manufacturing import RoutingResponse

        now = datetime.now(timezone.utc)
        resp = RoutingResponse(
            id=1, created_at=now, updated_at=now,
        )
        assert resp.product_sku is None
        assert resp.product_name is None
        assert resp.total_setup_time_minutes is None
        assert resp.total_run_time_minutes is None
        assert resp.total_cost is None
        assert resp.operations == []

    def test_routing_list_response(self):
        from app.schemas.manufacturing import RoutingListResponse

        now = datetime.now(timezone.utc)
        resp = RoutingListResponse(
            id=1, code="RT-01", version=1, revision="1.0",
            is_active=True, created_at=now,
        )
        assert resp.product_id is None
        assert resp.product_sku is None
        assert resp.product_name is None
        assert resp.name is None
        assert resp.is_template is False
        assert resp.total_run_time_minutes is None
        assert resp.total_cost is None
        assert resp.operation_count == 0

    # -- Capacity schemas ----------------------------------------------------

    def test_capacity_summary(self):
        from app.schemas.manufacturing import CapacitySummary

        cs = CapacitySummary(
            work_center_id=1, work_center_code="WC-01",
            work_center_name="Printers",
            capacity_hours_per_day=Decimal("24"),
        )
        assert cs.scheduled_hours == Decimal("0")
        assert cs.available_hours == Decimal("0")
        assert cs.utilization_percent == Decimal("0")
        assert cs.is_bottleneck is False

    def test_capacity_check_request(self):
        from app.schemas.manufacturing import CapacityCheckRequest

        req = CapacityCheckRequest(
            product_id=1, quantity=10, required_date=date(2026, 3, 1),
        )
        assert req.quantity == 10

    def test_capacity_check_response(self):
        from app.schemas.manufacturing import CapacityCheckResponse

        resp = CapacityCheckResponse(
            can_fulfill=True, earliest_completion_date=date(2026, 3, 1),
        )
        assert resp.bottleneck_work_center is None
        assert resp.details == []

    # -- Apply Template schemas ----------------------------------------------

    def test_operation_time_override(self):
        from app.schemas.manufacturing import OperationTimeOverride

        oto = OperationTimeOverride(operation_code="PRINT")
        assert oto.run_time_minutes is None
        assert oto.setup_time_minutes is None

    def test_apply_template_request(self):
        from app.schemas.manufacturing import ApplyTemplateRequest

        req = ApplyTemplateRequest(product_id=1, template_id=5)
        assert req.overrides == []

    def test_apply_template_response(self):
        from app.schemas.manufacturing import ApplyTemplateResponse

        resp = ApplyTemplateResponse(
            routing_id=1, routing_code="RT-01",
            product_sku="SKU-01", product_name="Widget",
            operations=[], total_run_time_minutes=Decimal("0"),
            total_cost=Decimal("0"), message="Applied",
        )
        assert resp.operations == []

    # -- Routing Operation Material schemas ----------------------------------

    def test_routing_operation_material_base(self):
        from app.schemas.manufacturing import RoutingOperationMaterialBase

        m = RoutingOperationMaterialBase(
            component_id=1, quantity=Decimal("100"),
        )
        assert m.quantity_per.value == "unit"
        assert m.unit == "EA"
        assert m.scrap_factor == Decimal("0")
        assert m.is_cost_only is False
        assert m.is_optional is False
        assert m.notes is None

    def test_routing_operation_material_base_unit_validator(self):
        from app.schemas.manufacturing import RoutingOperationMaterialBase

        m = RoutingOperationMaterialBase(
            component_id=1, quantity=Decimal("100"), unit="kg",
        )
        assert m.unit == "KG"

    def test_routing_operation_material_base_invalid_unit(self):
        from app.schemas.manufacturing import RoutingOperationMaterialBase

        with pytest.raises(ValidationError, match="Invalid unit"):
            RoutingOperationMaterialBase(
                component_id=1, quantity=Decimal("100"), unit="INVALID",
            )

    def test_routing_operation_material_create(self):
        from app.schemas.manufacturing import RoutingOperationMaterialCreate

        m = RoutingOperationMaterialCreate(
            component_id=1, quantity=Decimal("50"), unit="G",
        )
        assert m.component_id == 1

    def test_routing_operation_material_update(self):
        from app.schemas.manufacturing import RoutingOperationMaterialUpdate

        upd = RoutingOperationMaterialUpdate()
        assert upd.component_id is None
        assert upd.quantity is None
        assert upd.unit is None

    def test_routing_operation_material_update_with_unit(self):
        from app.schemas.manufacturing import RoutingOperationMaterialUpdate

        upd = RoutingOperationMaterialUpdate(unit="kg")
        assert upd.unit == "KG"

    def test_routing_operation_material_update_invalid_unit(self):
        from app.schemas.manufacturing import RoutingOperationMaterialUpdate

        with pytest.raises(ValidationError, match="Invalid unit"):
            RoutingOperationMaterialUpdate(unit="NOPE")

    def test_routing_operation_material_response(self):
        from app.schemas.manufacturing import RoutingOperationMaterialResponse

        now = datetime.now(timezone.utc)
        resp = RoutingOperationMaterialResponse(
            id=1, routing_operation_id=1, component_id=1,
            quantity=Decimal("100"),
            created_at=now, updated_at=now,
        )
        assert resp.component_sku is None
        assert resp.component_name is None
        assert resp.unit_cost == Decimal("0")
        assert resp.extended_cost == Decimal("0")

    # -- PO Operation Material schemas ---------------------------------------

    def test_po_operation_material_response(self):
        from app.schemas.manufacturing import POOperationMaterialResponse

        now = datetime.now(timezone.utc)
        resp = POOperationMaterialResponse(
            id=1, production_order_operation_id=1,
            component_id=10, quantity_required=Decimal("100"),
            unit="G", status="pending",
            created_at=now, updated_at=now,
        )
        assert resp.component_sku is None
        assert resp.component_name is None
        assert resp.routing_operation_material_id is None
        assert resp.quantity_allocated == Decimal("0")
        assert resp.quantity_consumed == Decimal("0")
        assert resp.quantity_remaining == Decimal("0")
        assert resp.lot_number is None
        assert resp.shortage_quantity == Decimal("0")
        assert resp.consumed_at is None

    def test_po_operation_material_consume(self):
        from app.schemas.manufacturing import POOperationMaterialConsume

        c = POOperationMaterialConsume(quantity=Decimal("50"))
        assert c.lot_number is None

    def test_po_operation_material_allocate(self):
        from app.schemas.manufacturing import POOperationMaterialAllocate

        a = POOperationMaterialAllocate(quantity=Decimal("50"))
        assert a.lot_number is None

    # -- Extended Routing Operation with Materials ---------------------------

    def test_routing_operation_with_materials_response(self):
        from app.schemas.manufacturing import RoutingOperationWithMaterialsResponse

        now = datetime.now(timezone.utc)
        resp = RoutingOperationWithMaterialsResponse(
            id=1, routing_id=1, work_center_id=1, sequence=1,
            run_time_minutes=Decimal("30"),
            created_at=now, updated_at=now,
        )
        assert resp.materials == []
        assert resp.material_cost == Decimal("0")
        assert resp.total_cost_with_materials == Decimal("0")

    # -- Manufacturing BOM Response ------------------------------------------

    def test_manufacturing_bom_response(self):
        from app.schemas.manufacturing import ManufacturingBOMResponse

        now = datetime.now(timezone.utc)
        resp = ManufacturingBOMResponse(
            routing_id=1, routing_code="RT-01",
            product_id=1, product_sku="SKU-01", product_name="Widget",
            version=1, revision="1.0", is_active=True,
            created_at=now, updated_at=now,
        )
        assert resp.routing_name is None
        assert resp.operations == []
        assert resp.total_labor_cost == Decimal("0")
        assert resp.total_material_cost == Decimal("0")
        assert resp.total_cost == Decimal("0")


# ============================================================================
# purchasing.py
# ============================================================================


class TestPurchasingSchemas:
    """Cover app/schemas/purchasing.py"""

    # -- Enums ---------------------------------------------------------------

    def test_po_status_enum(self):
        from app.schemas.purchasing import POStatus

        assert POStatus.DRAFT == "draft"
        assert POStatus.ORDERED == "ordered"
        assert POStatus.SHIPPED == "shipped"
        assert POStatus.RECEIVED == "received"
        assert POStatus.CLOSED == "closed"
        assert POStatus.CANCELLED == "cancelled"

    def test_document_type_enum(self):
        from app.schemas.purchasing import DocumentType

        assert DocumentType.INVOICE == "invoice"
        assert DocumentType.PACKING_SLIP == "packing_slip"
        assert DocumentType.RECEIPT == "receipt"
        assert DocumentType.QUOTE == "quote"
        assert DocumentType.SHIPPING_LABEL == "shipping_label"
        assert DocumentType.OTHER == "other"

    # -- Vendor schemas ------------------------------------------------------

    def test_vendor_base(self):
        from app.schemas.purchasing import VendorBase

        v = VendorBase(name="Acme Filament")
        assert v.contact_name is None
        assert v.email is None
        assert v.phone is None
        assert v.website is None
        assert v.address_line1 is None
        assert v.address_line2 is None
        assert v.city is None
        assert v.state is None
        assert v.postal_code is None
        assert v.country == "USA"
        assert v.payment_terms is None
        assert v.account_number is None
        assert v.tax_id is None
        assert v.lead_time_days is None
        assert v.rating is None
        assert v.notes is None
        assert v.is_active is True

    def test_vendor_create(self):
        from app.schemas.purchasing import VendorCreate

        v = VendorCreate(name="Acme Filament")
        assert v.code is None

    def test_vendor_update(self):
        from app.schemas.purchasing import VendorUpdate

        upd = VendorUpdate()
        assert upd.code is None
        assert upd.name is None
        assert upd.is_active is None

    def test_vendor_list_response(self):
        from app.schemas.purchasing import VendorListResponse

        resp = VendorListResponse(
            id=1, code="V-001", name="Acme", is_active=True,
        )
        assert resp.contact_name is None
        assert resp.email is None
        assert resp.phone is None
        assert resp.city is None
        assert resp.state is None
        assert resp.payment_terms is None
        assert resp.po_count == 0

    def test_vendor_response(self):
        from app.schemas.purchasing import VendorResponse

        now = datetime.now(timezone.utc)
        resp = VendorResponse(
            id=1, code="V-001", name="Acme",
            created_at=now, updated_at=now,
        )
        assert resp.code == "V-001"

    # -- PO Line schemas -----------------------------------------------------

    def test_po_line_base(self):
        from app.schemas.purchasing import POLineBase

        line = POLineBase(
            product_id=1,
            quantity_ordered=Decimal("10"),
            unit_cost=Decimal("5.00"),
        )
        assert line.purchase_unit is None
        assert line.notes is None

    def test_po_line_create(self):
        from app.schemas.purchasing import POLineCreate

        line = POLineCreate(
            product_id=1,
            quantity_ordered=Decimal("10"),
            unit_cost=Decimal("5.00"),
        )
        assert line.product_id == 1

    def test_po_line_update(self):
        from app.schemas.purchasing import POLineUpdate

        upd = POLineUpdate()
        assert upd.quantity_ordered is None
        assert upd.unit_cost is None
        assert upd.notes is None

    def test_po_line_response(self):
        from app.schemas.purchasing import POLineResponse

        now = datetime.now(timezone.utc)
        resp = POLineResponse(
            id=1, line_number=1, product_id=1,
            quantity_ordered=Decimal("10"),
            unit_cost=Decimal("5.00"),
            quantity_received=Decimal("0"),
            line_total=Decimal("50.00"),
            created_at=now, updated_at=now,
        )
        assert resp.product_sku is None
        assert resp.product_name is None
        assert resp.product_unit is None

    # -- Purchase Order schemas ----------------------------------------------

    def test_purchase_order_base(self):
        from app.schemas.purchasing import PurchaseOrderBase

        po = PurchaseOrderBase(vendor_id=1)
        assert po.order_date is None
        assert po.expected_date is None
        assert po.notes is None
        assert po.tracking_number is None
        assert po.carrier is None
        assert po.tax_amount == Decimal("0")
        assert po.shipping_cost == Decimal("0")
        assert po.payment_method is None
        assert po.payment_reference is None
        assert po.document_url is None

    def test_purchase_order_create(self):
        from app.schemas.purchasing import PurchaseOrderCreate

        po = PurchaseOrderCreate(vendor_id=1)
        assert po.lines == []

    def test_purchase_order_update(self):
        from app.schemas.purchasing import PurchaseOrderUpdate

        upd = PurchaseOrderUpdate()
        assert upd.vendor_id is None
        assert upd.order_date is None
        assert upd.expected_date is None
        assert upd.shipped_date is None
        assert upd.received_date is None
        assert upd.notes is None
        assert upd.tracking_number is None
        assert upd.carrier is None
        assert upd.tax_amount is None
        assert upd.shipping_cost is None
        assert upd.payment_method is None
        assert upd.payment_reference is None
        assert upd.document_url is None

    def test_purchase_order_list_response(self):
        from app.schemas.purchasing import PurchaseOrderListResponse

        now = datetime.now(timezone.utc)
        resp = PurchaseOrderListResponse(
            id=1, po_number="PO-001", vendor_id=1, vendor_name="Acme",
            status="draft", total_amount=Decimal("100.00"),
            created_at=now,
        )
        assert resp.order_date is None
        assert resp.expected_date is None
        assert resp.received_date is None
        assert resp.line_count == 0

    def test_purchase_order_response(self):
        from app.schemas.purchasing import PurchaseOrderResponse

        now = datetime.now(timezone.utc)
        resp = PurchaseOrderResponse(
            id=1, po_number="PO-001", vendor_id=1, status="draft",
            subtotal=Decimal("100.00"), total_amount=Decimal("100.00"),
            created_at=now, updated_at=now,
        )
        assert resp.shipped_date is None
        assert resp.received_date is None
        assert resp.vendor_name is None
        assert resp.created_by is None
        assert resp.lines == []

    # -- Status Update -------------------------------------------------------

    def test_po_status_update(self):
        from app.schemas.purchasing import POStatusUpdate, POStatus

        upd = POStatusUpdate(status=POStatus.ORDERED)
        assert upd.tracking_number is None
        assert upd.carrier is None

    # -- Receiving schemas ---------------------------------------------------

    def test_spool_create_data(self):
        from app.schemas.purchasing import SpoolCreateData

        s = SpoolCreateData(weight_g=Decimal("1000"))
        assert s.spool_number is None
        assert s.supplier_lot_number is None
        assert s.expiry_date is None
        assert s.notes is None

    def test_receive_line_item(self):
        from app.schemas.purchasing import ReceiveLineItem

        li = ReceiveLineItem(
            line_id=1, quantity_received=Decimal("10"),
        )
        assert li.lot_number is None
        assert li.vendor_lot_number is None
        assert li.notes is None
        assert li.create_spools is False
        assert li.spools is None

    def test_receive_po_request(self):
        from app.schemas.purchasing import ReceivePORequest, ReceiveLineItem

        req = ReceivePORequest(lines=[
            ReceiveLineItem(line_id=1, quantity_received=Decimal("10")),
        ])
        assert req.location_id is None
        assert req.notes is None
        assert req.received_date is None

    def test_receive_po_response(self):
        from app.schemas.purchasing import ReceivePOResponse

        resp = ReceivePOResponse(
            po_number="PO-001", lines_received=1,
            total_quantity=Decimal("10"), inventory_updated=True,
        )
        assert resp.transactions_created == []
        assert resp.spools_created == []
        assert resp.material_lots_created == []

    # -- Document schemas ----------------------------------------------------

    def test_po_document_base(self):
        from app.schemas.purchasing import PODocumentBase, DocumentType

        doc = PODocumentBase(document_type=DocumentType.INVOICE)
        assert doc.notes is None

    def test_po_document_create(self):
        from app.schemas.purchasing import PODocumentCreate, DocumentType

        doc = PODocumentCreate(document_type=DocumentType.PACKING_SLIP)
        assert doc.document_type == DocumentType.PACKING_SLIP

    def test_po_document_update(self):
        from app.schemas.purchasing import PODocumentUpdate

        upd = PODocumentUpdate()
        assert upd.document_type is None
        assert upd.notes is None

    def test_po_document_response(self):
        from app.schemas.purchasing import PODocumentResponse

        now = datetime.now(timezone.utc)
        resp = PODocumentResponse(
            id=1, purchase_order_id=1, document_type="invoice",
            file_name="invoice.pdf", storage_type="local",
            uploaded_at=now,
        )
        assert resp.original_file_name is None
        assert resp.file_url is None
        assert resp.file_path is None
        assert resp.file_size is None
        assert resp.mime_type is None
        assert resp.notes is None
        assert resp.uploaded_by is None
        assert resp.download_url is None
        assert resp.preview_url is None

    # -- Vendor Item schemas -------------------------------------------------

    def test_vendor_item_base(self):
        from app.schemas.purchasing import VendorItemBase

        vi = VendorItemBase(vendor_sku="PLA-BLK-1KG")
        assert vi.vendor_description is None
        assert vi.product_id is None
        assert vi.default_unit_cost is None
        assert vi.default_purchase_unit is None
        assert vi.notes is None

    def test_vendor_item_create(self):
        from app.schemas.purchasing import VendorItemCreate

        vi = VendorItemCreate(vendor_sku="PLA-BLK-1KG")
        assert vi.vendor_sku == "PLA-BLK-1KG"

    def test_vendor_item_update(self):
        from app.schemas.purchasing import VendorItemUpdate

        upd = VendorItemUpdate()
        assert upd.vendor_description is None
        assert upd.product_id is None
        assert upd.default_unit_cost is None
        assert upd.default_purchase_unit is None
        assert upd.notes is None

    def test_vendor_item_response(self):
        from app.schemas.purchasing import VendorItemResponse

        now = datetime.now(timezone.utc)
        resp = VendorItemResponse(
            id=1, vendor_id=1, vendor_sku="PLA-BLK-1KG",
            created_at=now, updated_at=now,
        )
        assert resp.last_seen_at is None
        assert resp.times_ordered == 0
        assert resp.product_sku is None
        assert resp.product_name is None

    # -- QB Export schemas ---------------------------------------------------

    def test_qb_export_preview_line(self):
        from app.schemas.purchasing import QBExportPreviewLine

        line = QBExportPreviewLine(
            date=date(2026, 1, 1), vendor="Acme",
            po_number="PO-001", account="5000",
            amount=Decimal("100"), memo="PO line 1",
        )
        assert line.class_name is None

    def test_qb_export_preview_response(self):
        from app.schemas.purchasing import QBExportPreviewResponse

        resp = QBExportPreviewResponse(
            total_pos=1, total_amount=Decimal("100"),
            date_range="Jan 2026", lines=[],
        )
        assert resp.lines == []

    # -- Low Stock schemas ---------------------------------------------------

    def test_low_stock_item(self):
        from app.schemas.purchasing import LowStockItem

        item = LowStockItem(
            product_id=1, sku="PLA-BLK", name="PLA Black",
            current_qty=Decimal("500"), reorder_point=Decimal("1000"),
            reorder_qty=Decimal("5000"), shortage=Decimal("500"),
            unit="G",
        )
        assert item.purchase_uom is None
        assert item.last_cost is None
        assert item.preferred_vendor_id is None
        assert item.preferred_vendor_name is None

    def test_low_stock_by_vendor(self):
        from app.schemas.purchasing import LowStockByVendor

        v = LowStockByVendor(
            vendor_name="Unassigned", items=[],
            total_estimated_cost=Decimal("0"),
        )
        assert v.vendor_id is None
        assert v.vendor_code is None

    def test_low_stock_response(self):
        from app.schemas.purchasing import LowStockResponse

        resp = LowStockResponse(total_items=0, vendors=[])
        assert resp.total_items == 0

    def test_create_po_from_low_stock_item(self):
        from app.schemas.purchasing import CreatePOFromLowStockItem

        item = CreatePOFromLowStockItem(
            product_id=1, quantity=Decimal("5000"),
        )
        assert item.unit_cost is None
        assert item.purchase_unit is None

    def test_create_po_from_low_stock_request(self):
        from app.schemas.purchasing import (
            CreatePOFromLowStockRequest,
            CreatePOFromLowStockItem,
        )

        req = CreatePOFromLowStockRequest(
            vendor_id=1,
            items=[CreatePOFromLowStockItem(
                product_id=1, quantity=Decimal("5000"),
            )],
        )
        assert req.notes is None


# ============================================================================
# quote.py
# ============================================================================


class TestQuoteSchemas:
    """Cover app/schemas/quote.py"""

    def test_quote_file_upload(self):
        from app.schemas.quote import QuoteFileUpload

        f = QuoteFileUpload(
            original_filename="part.3mf",
            stored_filename="abc123.3mf",
            file_path="/uploads/abc123.3mf",
            file_size_bytes=1024000,
            file_format="3mf",
            file_hash="sha256abc",
            mime_type="application/octet-stream",
        )
        assert f.file_size_bytes == 1024000

    def test_quote_file_response(self):
        from app.schemas.quote import QuoteFileResponse

        now = datetime.now(timezone.utc)
        resp = QuoteFileResponse(
            id=1, quote_id=1, original_filename="part.3mf",
            file_size_bytes=1024000, file_format="3mf",
            is_valid=True, processed=False, uploaded_at=now,
        )
        assert resp.validation_errors is None
        assert resp.processing_error is None
        # property
        assert resp.file_size_mb == pytest.approx(1024000 / (1024 * 1024))

    def test_quote_create_valid(self):
        from app.schemas.quote import QuoteCreate

        q = QuoteCreate(material_type="pla", quantity=5)
        assert q.material_type == "PLA"
        assert q.finish == "standard"
        assert q.rush_level == "standard"
        assert q.product_name is None
        assert q.requested_delivery_date is None
        assert q.customer_notes is None

    def test_quote_create_all_materials(self):
        from app.schemas.quote import QuoteCreate

        for mat in ["PLA", "PETG", "ABS", "ASA", "TPU"]:
            q = QuoteCreate(material_type=mat)
            assert q.material_type == mat

    def test_quote_create_invalid_material(self):
        from app.schemas.quote import QuoteCreate

        with pytest.raises(ValidationError, match="Invalid material"):
            QuoteCreate(material_type="NYLON")

    def test_quote_create_all_finishes(self):
        from app.schemas.quote import QuoteCreate

        for finish in ["standard", "smooth", "painted"]:
            q = QuoteCreate(material_type="PLA", finish=finish)
            assert q.finish == finish

    def test_quote_create_invalid_finish(self):
        from app.schemas.quote import QuoteCreate

        with pytest.raises(ValidationError, match="Invalid finish"):
            QuoteCreate(material_type="PLA", finish="matte")

    def test_quote_create_all_rush_levels(self):
        from app.schemas.quote import QuoteCreate

        for rush in ["standard", "rush", "super_rush", "urgent"]:
            q = QuoteCreate(material_type="PLA", rush_level=rush)
            assert q.rush_level == rush

    def test_quote_create_invalid_rush(self):
        from app.schemas.quote import QuoteCreate

        with pytest.raises(ValidationError, match="Invalid rush"):
            QuoteCreate(material_type="PLA", rush_level="yesterday")

    def test_quote_response(self):
        from app.schemas.quote import QuoteResponse

        now = datetime.now(timezone.utc)
        resp = QuoteResponse(
            id=1, user_id=1, quote_number="Q-001",
            quantity=1, material_type="PLA", finish="standard",
            total_price=Decimal("25.00"),
            file_format="3mf", file_size_bytes=1000,
            status="pending", auto_approved=False,
            auto_approve_eligible=True, rush_level="standard",
            created_at=now, updated_at=now,
            expires_at=now,
        )
        assert resp.product_name is None
        assert resp.material_grams is None
        assert resp.print_time_hours is None
        assert resp.unit_price is None
        assert resp.margin_percent is None
        assert resp.dimensions_x is None
        assert resp.dimensions_y is None
        assert resp.dimensions_z is None
        assert resp.approval_method is None
        assert resp.approved_by is None
        assert resp.approved_at is None
        assert resp.rejection_reason is None
        assert resp.requires_review_reason is None
        assert resp.requested_delivery_date is None
        assert resp.customer_notes is None
        assert resp.admin_notes is None
        assert resp.sales_order_id is None
        assert resp.converted_at is None
        assert resp.product_id is None
        assert resp.files == []

    def test_quote_response_is_expired_property(self):
        from app.schemas.quote import QuoteResponse
        from datetime import timedelta

        past = datetime.now(timezone.utc) - timedelta(days=1)
        resp = QuoteResponse(
            id=1, user_id=1, quote_number="Q-001",
            quantity=1, material_type="PLA", finish="standard",
            total_price=Decimal("25.00"),
            file_format="3mf", file_size_bytes=1000,
            status="pending", auto_approved=False,
            auto_approve_eligible=True, rush_level="standard",
            created_at=past, updated_at=past, expires_at=past,
        )
        assert resp.is_expired is True

    def test_quote_response_file_size_mb_property(self):
        from app.schemas.quote import QuoteResponse

        now = datetime.now(timezone.utc)
        resp = QuoteResponse(
            id=1, user_id=1, quote_number="Q-001",
            quantity=1, material_type="PLA", finish="standard",
            total_price=Decimal("25.00"),
            file_format="3mf", file_size_bytes=2 * 1024 * 1024,
            status="pending", auto_approved=False,
            auto_approve_eligible=True, rush_level="standard",
            created_at=now, updated_at=now, expires_at=now,
        )
        assert resp.file_size_mb == pytest.approx(2.0)

    def test_quote_list_response(self):
        from app.schemas.quote import QuoteListResponse

        now = datetime.now(timezone.utc)
        resp = QuoteListResponse(
            id=1, quote_number="Q-001", quantity=1,
            material_type="PLA", total_price=Decimal("25"),
            status="pending", auto_approved=False,
            rush_level="standard", created_at=now, expires_at=now,
        )
        assert resp.product_name is None
        assert resp.color is None
        assert resp.product_id is None
        assert resp.sales_order_id is None

    def test_quote_list_response_is_expired_property(self):
        from app.schemas.quote import QuoteListResponse
        from datetime import timedelta

        past = datetime.now(timezone.utc) - timedelta(days=1)
        resp = QuoteListResponse(
            id=1, quote_number="Q-001", quantity=1,
            material_type="PLA", total_price=Decimal("25"),
            status="expired", auto_approved=False,
            rush_level="standard", created_at=past, expires_at=past,
        )
        assert resp.is_expired is True

    def test_quote_update_status(self):
        from app.schemas.quote import QuoteUpdateStatus

        upd = QuoteUpdateStatus(status="approved")
        assert upd.rejection_reason is None
        assert upd.admin_notes is None

    def test_quote_update_status_all_values(self):
        from app.schemas.quote import QuoteUpdateStatus

        for status in ["approved", "rejected", "cancelled"]:
            upd = QuoteUpdateStatus(status=status)
            assert upd.status == status

    def test_quote_update_status_invalid(self):
        from app.schemas.quote import QuoteUpdateStatus

        with pytest.raises(ValidationError, match="Invalid status"):
            QuoteUpdateStatus(status="active")

    def test_quote_accept(self):
        from app.schemas.quote import QuoteAccept

        qa = QuoteAccept()
        assert qa.accepted is True
        assert qa.customer_notes is None

    def test_quote_pricing_response(self):
        from app.schemas.quote import QuotePricingResponse

        resp = QuotePricingResponse(
            material_grams=Decimal("50"),
            print_time_hours=Decimal("3"),
            unit_price=Decimal("15"),
            total_price=Decimal("15"),
            margin_percent=Decimal("40"),
            dimensions_x=Decimal("50"),
            dimensions_y=Decimal("50"),
            dimensions_z=Decimal("50"),
            auto_approve_eligible=True,
        )
        assert resp.requires_review_reason is None

    def test_quote_stats_response(self):
        from app.schemas.quote import QuoteStatsResponse

        stats = QuoteStatsResponse(
            total_quotes=100, pending_quotes=10,
            approved_quotes=50, rejected_quotes=5,
            expired_quotes=20, converted_quotes=45,
            auto_approved_count=30, manual_approved_count=20,
            total_value=Decimal("5000"), average_quote_value=Decimal("50"),
        )
        assert stats.total_quotes == 100

    def test_bambu_quote_request(self):
        from app.schemas.quote import BambuQuoteRequest

        req = BambuQuoteRequest(
            file_path="/files/part.3mf", material_type="PLA", quantity=1,
        )
        assert req.finish == "standard"
        assert req.rush_level == "standard"

    def test_bambu_quote_response(self):
        from app.schemas.quote import BambuQuoteResponse

        resp = BambuQuoteResponse(success=True)
        assert resp.material_grams is None
        assert resp.print_time_hours is None
        assert resp.material_cost is None
        assert resp.labor_cost is None
        assert resp.unit_price is None
        assert resp.total_price is None
        assert resp.dimensions_x is None
        assert resp.dimensions_y is None
        assert resp.dimensions_z is None
        assert resp.error is None
        assert resp.error_code is None

    # -- Portal Quote schemas ------------------------------------------------

    def test_quote_material_create(self):
        from app.schemas.quote import QuoteMaterialCreate

        m = QuoteMaterialCreate(
            slot_number=1, material_type="PLA_BASIC",
            material_grams=Decimal("50"),
        )
        assert m.color_code is None
        assert m.color_name is None
        assert m.color_hex is None
        assert m.is_primary is False

    def test_multi_material_data(self):
        from app.schemas.quote import MultiMaterialData

        md = MultiMaterialData()
        assert md.is_multi_material is False
        assert md.material_count == 1
        assert md.filament_types is None
        assert md.filament_weights_grams is None
        assert md.filament_colors is None
        assert md.filament_color_names is None
        assert md.filament_color_hexes is None
        assert md.tool_change_count is None

    def test_portal_quote_create_base_material(self):
        from app.schemas.quote import PortalQuoteCreate

        q = PortalQuoteCreate(
            filename="part.3mf", file_format=".3mf",
            material="PLA", quantity=1,
            unit_price=Decimal("15"), total_price=Decimal("15"),
            material_grams=Decimal("50"),
            print_time_minutes=Decimal("180"),
        )
        assert q.material == "PLA"
        assert q.quality == "standard"
        assert q.infill == "standard"
        assert q.color is None
        assert q.color_name is None
        assert q.dimensions_x is None
        assert q.material_in_stock is True
        assert q.customer_id is None
        assert q.customer_email is None
        assert q.customer_notes is None
        assert q.multi_material is None

    def test_portal_quote_create_variant_material(self):
        from app.schemas.quote import PortalQuoteCreate

        q = PortalQuoteCreate(
            filename="part.3mf", file_format=".3mf",
            material="PLA_SILK", quantity=1,
            unit_price=Decimal("20"), total_price=Decimal("20"),
            material_grams=Decimal("50"),
            print_time_minutes=Decimal("180"),
        )
        assert q.material == "PLA_SILK"

    def test_portal_quote_create_invalid_material(self):
        from app.schemas.quote import PortalQuoteCreate

        with pytest.raises(ValidationError, match="Invalid material"):
            PortalQuoteCreate(
                filename="part.3mf", file_format=".3mf",
                material="NYLON", quantity=1,
                unit_price=Decimal("15"), total_price=Decimal("15"),
                material_grams=Decimal("50"),
                print_time_minutes=Decimal("180"),
            )

    def test_portal_quote_response(self):
        from app.schemas.quote import PortalQuoteResponse

        now = datetime.now(timezone.utc)
        resp = PortalQuoteResponse(
            id=1, quote_number="PQ-001", filename="part.3mf",
            material="PLA", quality="standard", quantity=1,
            unit_price=Decimal("15"), total_price=Decimal("15"),
            material_grams=Decimal("50"),
            print_time_minutes=Decimal("180"),
            status="pending", created_at=now, expires_at=now,
        )
        assert resp.infill is None
        assert resp.color is None
        assert resp.color_name is None
        assert resp.material_in_stock is True

    def test_multi_color_slot(self):
        from app.schemas.quote import MultiColorSlot

        s = MultiColorSlot(slot=1, color_code="BLK")
        assert s.color_name is None
        assert s.color_hex is None
        assert s.is_primary is False

    def test_multi_color_info(self):
        from app.schemas.quote import MultiColorInfo, MultiColorSlot

        info = MultiColorInfo(
            slot_colors=[MultiColorSlot(slot=1, color_code="BLK")],
        )
        assert info.primary_slot is None

    def test_portal_accept_quote(self):
        from app.schemas.quote import PortalAcceptQuote

        accept = PortalAcceptQuote(
            shipping_address_line1="123 Main St",
            shipping_city="Denver",
            shipping_state="CO",
            shipping_zip="80202",
        )
        assert accept.shipping_name is None
        assert accept.shipping_address_line2 is None
        assert accept.shipping_country == "USA"
        assert accept.shipping_phone is None
        assert accept.shipping_rate_id is None
        assert accept.shipping_carrier is None
        assert accept.shipping_service is None
        assert accept.shipping_cost is None
        assert accept.print_mode is None
        assert accept.adjusted_unit_price is None
        assert accept.multi_color_info is None

    def test_portal_submit_for_review(self):
        from app.schemas.quote import PortalSubmitForReview

        req = PortalSubmitForReview(
            customer_email="test@example.com",
            shipping_address_line1="123 Main St",
            shipping_city="Denver",
            shipping_state="CO",
            shipping_zip="80202",
        )
        assert req.customer_name is None
        assert req.shipping_name is None
        assert req.shipping_address_line2 is None
        assert req.shipping_country == "USA"
        assert req.shipping_phone is None
        assert req.shipping_rate_id is None
        assert req.shipping_carrier is None
        assert req.shipping_service is None
        assert req.shipping_cost is None


# ============================================================================
# item.py
# ============================================================================


class TestItemSchemas:
    """Cover app/schemas/item.py"""

    # -- Enums ---------------------------------------------------------------

    def test_item_type_enum(self):
        from app.schemas.item import ItemType

        assert ItemType.FINISHED_GOOD == "finished_good"
        assert ItemType.COMPONENT == "component"
        assert ItemType.SUPPLY == "supply"
        assert ItemType.SERVICE == "service"
        assert ItemType.MATERIAL == "material"

    def test_cost_method_enum(self):
        from app.schemas.item import CostMethod

        assert CostMethod.FIFO == "fifo"
        assert CostMethod.AVERAGE == "average"
        assert CostMethod.STANDARD == "standard"

    def test_procurement_type_enum(self):
        from app.schemas.item import ProcurementType

        assert ProcurementType.MAKE == "make"
        assert ProcurementType.BUY == "buy"
        assert ProcurementType.MAKE_OR_BUY == "make_or_buy"

    def test_stocking_policy_enum(self):
        from app.schemas.item import StockingPolicy

        assert StockingPolicy.STOCKED == "stocked"
        assert StockingPolicy.ON_DEMAND == "on_demand"

    # -- Category schemas ----------------------------------------------------

    def test_item_category_base(self):
        from app.schemas.item import ItemCategoryBase

        cat = ItemCategoryBase(code="RAW", name="Raw Materials")
        assert cat.parent_id is None
        assert cat.description is None
        assert cat.sort_order == 0
        assert cat.is_active is True

    def test_item_category_create(self):
        from app.schemas.item import ItemCategoryCreate

        cat = ItemCategoryCreate(code="FG", name="Finished Goods")
        assert cat.code == "FG"

    def test_item_category_update(self):
        from app.schemas.item import ItemCategoryUpdate

        upd = ItemCategoryUpdate()
        assert upd.code is None
        assert upd.name is None
        assert upd.parent_id is None
        assert upd.description is None
        assert upd.sort_order is None
        assert upd.is_active is None

    def test_item_category_response(self):
        from app.schemas.item import ItemCategoryResponse

        now = datetime.now(timezone.utc)
        resp = ItemCategoryResponse(
            id=1, code="RAW", name="Raw Materials",
            created_at=now, updated_at=now,
        )
        assert resp.parent_name is None
        assert resp.full_path is None

    def test_item_category_tree_node(self):
        from app.schemas.item import ItemCategoryTreeNode

        node = ItemCategoryTreeNode(
            id=1, code="ROOT", name="All", is_active=True,
        )
        assert node.description is None
        assert node.children == []

    def test_item_category_tree_node_with_children(self):
        from app.schemas.item import ItemCategoryTreeNode

        child = ItemCategoryTreeNode(
            id=2, code="FG", name="Finished Goods", is_active=True,
        )
        parent = ItemCategoryTreeNode(
            id=1, code="ROOT", name="All", is_active=True,
            children=[child],
        )
        assert len(parent.children) == 1

    # -- Item schemas --------------------------------------------------------

    def test_item_base(self):
        from app.schemas.item import ItemBase, ItemType, CostMethod, ProcurementType, StockingPolicy

        item = ItemBase(name="Widget")
        assert item.sku is None
        assert item.description is None
        assert item.unit == "EA"
        assert item.purchase_uom == "EA"
        assert item.item_type == ItemType.FINISHED_GOOD
        assert item.procurement_type == ProcurementType.BUY
        assert item.category_id is None
        assert item.cost_method == CostMethod.AVERAGE
        assert item.standard_cost is None
        assert item.selling_price is None
        assert item.weight_oz is None
        assert item.length_in is None
        assert item.width_in is None
        assert item.height_in is None
        assert item.lead_time_days is None
        assert item.min_order_qty is None
        assert item.reorder_point is None
        assert item.stocking_policy == StockingPolicy.ON_DEMAND
        assert item.upc is None
        assert item.legacy_sku is None
        assert item.is_active is True
        assert item.is_raw_material is False
        assert item.track_lots is False
        assert item.track_serials is False
        assert item.material_type_id is None
        assert item.color_id is None

    def test_item_create(self):
        from app.schemas.item import ItemCreate

        item = ItemCreate(name="Widget")
        assert item.name == "Widget"

    def test_material_item_create(self):
        from app.schemas.item import MaterialItemCreate

        m = MaterialItemCreate(
            material_type_code="PLA_BASIC", color_code="BLK",
        )
        assert m.cost_per_kg is None
        assert m.selling_price is None
        assert m.initial_qty_kg == 0
        assert m.category_id is None

    def test_item_update(self):
        from app.schemas.item import ItemUpdate

        upd = ItemUpdate()
        assert upd.sku is None
        assert upd.name is None
        assert upd.description is None
        assert upd.unit is None
        assert upd.purchase_uom is None
        assert upd.item_type is None
        assert upd.procurement_type is None
        assert upd.category_id is None
        assert upd.cost_method is None
        assert upd.standard_cost is None
        assert upd.selling_price is None
        assert upd.weight_oz is None
        assert upd.length_in is None
        assert upd.width_in is None
        assert upd.height_in is None
        assert upd.lead_time_days is None
        assert upd.min_order_qty is None
        assert upd.reorder_point is None
        assert upd.stocking_policy is None
        assert upd.upc is None
        assert upd.legacy_sku is None
        assert upd.is_active is None
        assert upd.is_raw_material is None
        assert upd.track_lots is None
        assert upd.track_serials is None
        assert upd.image_url is None
        assert upd.material_type_id is None
        assert upd.color_id is None

    def test_item_list_response(self):
        from app.schemas.item import ItemListResponse

        resp = ItemListResponse(
            id=1, sku="WDG-001", name="Widget",
            item_type="finished_good", active=True,
        )
        assert resp.procurement_type == "buy"
        assert resp.category_id is None
        assert resp.category_name is None
        assert resp.unit is None
        assert resp.purchase_uom is None
        assert resp.standard_cost is None
        assert resp.average_cost is None
        assert resp.selling_price is None
        assert resp.suggested_price is None
        assert resp.on_hand_qty is None
        assert resp.available_qty is None
        assert resp.reorder_point is None
        assert resp.stocking_policy == "on_demand"
        assert resp.needs_reorder is False
        assert resp.material_type_id is None
        assert resp.color_id is None
        assert resp.material_type_code is None
        assert resp.color_code is None

    def test_item_response(self):
        from app.schemas.item import ItemResponse

        now = datetime.now(timezone.utc)
        resp = ItemResponse(
            id=1, name="Widget", active=True,
            created_at=now, updated_at=now,
        )
        assert resp.average_cost is None
        assert resp.last_cost is None
        assert resp.cost_per_storage_unit is None
        assert resp.category_name is None
        assert resp.category_path is None
        assert resp.on_hand_qty is None
        assert resp.available_qty is None
        assert resp.allocated_qty is None
        assert resp.has_bom is False
        assert resp.bom_count == 0
        assert resp.material_type_code is None
        assert resp.material_type_name is None
        assert resp.color_code is None
        assert resp.color_name is None
        assert resp.color_hex is None

    # -- Bulk Operations -----------------------------------------------------

    def test_item_csv_import_request(self):
        from app.schemas.item import ItemCSVImportRequest, ItemType

        req = ItemCSVImportRequest()
        assert req.update_existing is False
        assert req.default_item_type == ItemType.FINISHED_GOOD
        assert req.default_category_id is None

    def test_item_csv_import_result(self):
        from app.schemas.item import ItemCSVImportResult

        res = ItemCSVImportResult(
            total_rows=100, created=90, updated=5, skipped=5,
        )
        assert res.errors == []
        assert res.warnings == []

    def test_item_bulk_update_request(self):
        from app.schemas.item import ItemBulkUpdateRequest

        req = ItemBulkUpdateRequest(item_ids=[1, 2, 3])
        assert req.category_id is None
        assert req.item_type is None
        assert req.procurement_type is None
        assert req.is_active is None


# ============================================================================
# operation_blocking.py
# ============================================================================


class TestOperationBlockingSchemas:
    """Cover app/schemas/operation_blocking.py"""

    def test_incoming_supply_info(self):
        from app.schemas.operation_blocking import IncomingSupplyInfo

        info = IncomingSupplyInfo(
            purchase_order_id=1,
            purchase_order_code="PO-001",
            quantity=100.0,
        )
        assert info.expected_date is None

    def test_material_issue_info(self):
        from app.schemas.operation_blocking import MaterialIssueInfo

        info = MaterialIssueInfo(
            product_id=1, product_sku="PLA-BLK",
            quantity_required=100.0, quantity_available=50.0,
            quantity_short=50.0,
        )
        assert info.product_name is None
        assert info.unit == "EA"
        assert info.consume_stage == "production"
        assert info.incoming_supply is None

    def test_material_issue_info_with_supply(self):
        from app.schemas.operation_blocking import (
            MaterialIssueInfo,
            IncomingSupplyInfo,
        )

        info = MaterialIssueInfo(
            product_id=1, product_sku="PLA-BLK",
            quantity_required=100.0, quantity_available=50.0,
            quantity_short=50.0,
            incoming_supply=IncomingSupplyInfo(
                purchase_order_id=1, purchase_order_code="PO-001",
                quantity=100.0, expected_date="2026-03-01",
            ),
        )
        assert info.incoming_supply.quantity == 100.0

    def test_can_start_response(self):
        from app.schemas.operation_blocking import CanStartResponse

        resp = CanStartResponse(can_start=True)
        assert resp.blocking_issues == []

    def test_operation_blocking_response(self):
        from app.schemas.operation_blocking import OperationBlockingResponse

        resp = OperationBlockingResponse(
            operation_id=1, can_start=True,
        )
        assert resp.operation_code is None
        assert resp.operation_name is None
        assert resp.blocking_issues == []
        assert resp.material_issues == []


# ============================================================================
# routing_operations.py
# ============================================================================


class TestRoutingOperationsSchemas:
    """Cover app/schemas/routing_operations.py"""

    def test_routing_operation_info(self):
        from app.schemas.routing_operations import RoutingOperationInfo

        info = RoutingOperationInfo(id=1, sequence=1)
        assert info.operation_code is None
        assert info.operation_name is None
        assert info.work_center_id is None
        assert info.work_center_code is None
        assert info.setup_time_minutes is None
        assert info.run_time_minutes is None

    def test_product_routing_response(self):
        from app.schemas.routing_operations import ProductRoutingResponse

        resp = ProductRoutingResponse(product_id=1)
        assert resp.routing_id is None
        assert resp.routing_code is None
        assert resp.routing_name is None
        assert resp.is_active is False
        assert resp.operations == []

    def test_release_response(self):
        from app.schemas.routing_operations import ReleaseResponse

        resp = ReleaseResponse(
            success=True, production_order_id=1,
            status="released", operations_created=3,
            message="Released OK",
        )
        assert resp.operations_created == 3

    def test_generate_operations_request(self):
        from app.schemas.routing_operations import GenerateOperationsRequest

        req = GenerateOperationsRequest()
        assert req.force is False

    def test_generate_operations_request_force(self):
        from app.schemas.routing_operations import GenerateOperationsRequest

        req = GenerateOperationsRequest(force=True)
        assert req.force is True

    def test_generate_operations_response(self):
        from app.schemas.routing_operations import GenerateOperationsResponse

        resp = GenerateOperationsResponse(
            success=True, operations_created=5, message="Done",
        )
        assert resp.operations_created == 5


# ============================================================================
# scheduling.py
# ============================================================================


class TestSchedulingSchemas:
    """Cover app/schemas/scheduling.py"""

    def test_capacity_check_request(self):
        from app.schemas.scheduling import CapacityCheckRequest

        now = datetime.now(timezone.utc)
        req = CapacityCheckRequest(
            resource_id=1, start_time=now, end_time=now,
        )
        assert req.resource_id == 1

    def test_conflict_info(self):
        from app.schemas.scheduling import ConflictInfo

        info = ConflictInfo(
            order_id=1, order_code="MO-001",
            start_time="2026-03-01T08:00:00",
            end_time="2026-03-01T10:00:00",
            product_name="Widget",
        )
        assert info.order_code == "MO-001"

    def test_capacity_check_response(self):
        from app.schemas.scheduling import CapacityCheckResponse

        resp = CapacityCheckResponse(
            resource_id=1, resource_code="P1S-01",
            resource_name="Bambu P1S #1",
            start_time="2026-03-01T08:00:00",
            end_time="2026-03-01T10:00:00",
            has_capacity=True,
        )
        assert resp.conflicts == []

    def test_available_slot_response(self):
        from app.schemas.scheduling import AvailableSlotResponse

        resp = AvailableSlotResponse(
            start_time="2026-03-01T08:00:00",
            end_time="2026-03-01T16:00:00",
            duration_hours=8.0,
        )
        assert resp.duration_hours == 8.0

    def test_machine_availability_response(self):
        from app.schemas.scheduling import MachineAvailabilityResponse

        resp = MachineAvailabilityResponse(
            resource_id=1, resource_code="P1S-01",
            resource_name="Bambu P1S #1", work_center_id=1,
            status="available", total_hours=24.0,
            scheduled_hours=8.0, available_hours=16.0,
            utilization_percent=33.33,
            scheduled_order_count=3,
        )
        assert resp.work_center_code is None


# ============================================================================
# printer.py
# ============================================================================


class TestPrinterSchemas:
    """Cover app/schemas/printer.py"""

    # -- Enums ---------------------------------------------------------------

    def test_printer_brand_enum(self):
        from app.schemas.printer import PrinterBrand

        assert PrinterBrand.BAMBULAB == "bambulab"
        assert PrinterBrand.KLIPPER == "klipper"
        assert PrinterBrand.OCTOPRINT == "octoprint"
        assert PrinterBrand.PRUSA == "prusa"
        assert PrinterBrand.CREALITY == "creality"
        assert PrinterBrand.GENERIC == "generic"

    def test_printer_status_enum(self):
        from app.schemas.printer import PrinterStatus

        assert PrinterStatus.OFFLINE == "offline"
        assert PrinterStatus.IDLE == "idle"
        assert PrinterStatus.PRINTING == "printing"
        assert PrinterStatus.PAUSED == "paused"
        assert PrinterStatus.ERROR == "error"
        assert PrinterStatus.MAINTENANCE == "maintenance"

    # -- Capabilities and Connection Config ----------------------------------

    def test_printer_capabilities(self):
        from app.schemas.printer import PrinterCapabilities

        cap = PrinterCapabilities()
        assert cap.bed_size_x is None
        assert cap.bed_size_y is None
        assert cap.bed_size_z is None
        assert cap.heated_bed is True
        assert cap.enclosure is False
        assert cap.ams_slots == 0
        assert cap.camera is False
        assert cap.max_temp_hotend is None
        assert cap.max_temp_bed is None

    def test_printer_connection_config(self):
        from app.schemas.printer import PrinterConnectionConfig

        cfg = PrinterConnectionConfig()
        assert cfg.port is None
        assert cfg.api_key is None
        assert cfg.access_code is None
        assert cfg.protocol is None

    # -- CRUD schemas --------------------------------------------------------

    def test_printer_base(self):
        from app.schemas.printer import PrinterBase, PrinterBrand

        p = PrinterBase(code="P1S-01", name="Bambu P1S", model="P1S")
        assert p.brand == PrinterBrand.GENERIC
        assert p.serial_number is None
        assert p.ip_address is None
        assert p.mqtt_topic is None
        assert p.location is None
        assert p.work_center_id is None
        assert p.notes is None
        assert p.active is True

    def test_printer_create(self):
        from app.schemas.printer import PrinterCreate

        p = PrinterCreate(code="P1S-01", name="Bambu P1S", model="P1S")
        assert p.connection_config == {}
        assert p.capabilities == {}

    def test_printer_update(self):
        from app.schemas.printer import PrinterUpdate

        upd = PrinterUpdate()
        assert upd.code is None
        assert upd.name is None
        assert upd.model is None
        assert upd.brand is None
        assert upd.serial_number is None
        assert upd.ip_address is None
        assert upd.mqtt_topic is None
        assert upd.location is None
        assert upd.work_center_id is None
        assert upd.notes is None
        assert upd.active is None
        assert upd.connection_config is None
        assert upd.capabilities is None

    def test_printer_response(self):
        from app.schemas.printer import PrinterResponse, PrinterStatus

        now = datetime.now(timezone.utc)
        resp = PrinterResponse(
            id=1, code="P1S-01", name="Bambu P1S", model="P1S",
            created_at=now, updated_at=now,
        )
        assert resp.status == PrinterStatus.OFFLINE
        assert resp.connection_config == {}
        assert resp.capabilities == {}
        assert resp.last_seen is None
        assert resp.is_online is False
        assert resp.has_ams is False
        assert resp.has_camera is False

    def test_printer_list_response(self):
        from app.schemas.printer import PrinterListResponse, PrinterResponse

        now = datetime.now(timezone.utc)
        printer = PrinterResponse(
            id=1, code="P1S-01", name="Bambu P1S", model="P1S",
            created_at=now, updated_at=now,
        )
        resp = PrinterListResponse(
            items=[printer], total=1, page=1,
            page_size=25, total_pages=1,
        )
        assert len(resp.items) == 1

    # -- Discovery schemas ---------------------------------------------------

    def test_discovered_printer_response(self):
        from app.schemas.printer import DiscoveredPrinterResponse, PrinterBrand

        resp = DiscoveredPrinterResponse(
            brand=PrinterBrand.BAMBULAB, model="X1C",
            name="Bambu X1C", ip_address="192.168.1.100",
            suggested_code="X1C-01",
        )
        assert resp.serial_number is None
        assert resp.capabilities == {}
        assert resp.already_registered is False

    def test_discovery_result_response(self):
        from app.schemas.printer import DiscoveryResultResponse

        resp = DiscoveryResultResponse(
            printers=[], scan_duration_seconds=3.5,
        )
        assert resp.errors == []

    def test_discovery_request(self):
        from app.schemas.printer import DiscoveryRequest

        req = DiscoveryRequest()
        assert req.brands is None
        assert req.timeout_seconds == 5.0

    # -- Bulk Import schemas -------------------------------------------------

    def test_printer_csv_row(self):
        from app.schemas.printer import PrinterCSVRow

        row = PrinterCSVRow(code="P1", name="Printer 1", model="X1C")
        assert row.brand == "generic"
        assert row.serial_number is None
        assert row.ip_address is None
        assert row.location is None
        assert row.notes is None

    def test_printer_csv_import_request(self):
        from app.schemas.printer import PrinterCSVImportRequest

        req = PrinterCSVImportRequest(csv_data="code,name,model\nP1,Printer,X1C")
        assert req.skip_duplicates is True

    def test_printer_csv_import_result(self):
        from app.schemas.printer import PrinterCSVImportResult

        res = PrinterCSVImportResult(
            total_rows=10, imported=8, skipped=2,
        )
        assert res.errors == []

    # -- Status Update schemas -----------------------------------------------

    def test_printer_status_update(self):
        from app.schemas.printer import PrinterStatusUpdate, PrinterStatus

        upd = PrinterStatusUpdate(status=PrinterStatus.PRINTING)
        assert upd.status == PrinterStatus.PRINTING

    def test_printer_connection_test(self):
        from app.schemas.printer import PrinterConnectionTest, PrinterBrand

        t = PrinterConnectionTest(
            ip_address="192.168.1.100", brand=PrinterBrand.BAMBULAB,
        )
        assert t.connection_config == {}

    def test_printer_connection_test_result(self):
        from app.schemas.printer import PrinterConnectionTestResult

        res = PrinterConnectionTestResult(success=True)
        assert res.message is None
        assert res.response_time_ms is None

    # -- Brand Info schemas --------------------------------------------------

    def test_printer_model_info(self):
        from app.schemas.printer import PrinterModelInfo

        info = PrinterModelInfo(value="x1c", label="X1 Carbon")
        assert info.capabilities is None

    def test_printer_brand_info(self):
        from app.schemas.printer import PrinterBrandInfo

        info = PrinterBrandInfo(
            code="bambulab", name="BambuLab",
            supports_discovery=True,
            models=[], connection_fields=[],
        )
        assert len(info.models) == 0


# ============================================================================
# traceability.py
# ============================================================================


class TestTraceabilitySchemas:
    """Cover app/schemas/traceability.py"""

    # -- Customer Traceability Profile ---------------------------------------

    def test_customer_traceability_profile_base(self):
        from app.schemas.traceability import CustomerTraceabilityProfileBase

        p = CustomerTraceabilityProfileBase()
        assert p.traceability_level == "none"
        assert p.requires_coc is False
        assert p.requires_coa is False
        assert p.requires_first_article is False
        assert p.record_retention_days == 2555
        assert p.custom_serial_prefix is None
        assert p.compliance_standards is None
        assert p.notes is None

    def test_customer_traceability_profile_create(self):
        from app.schemas.traceability import CustomerTraceabilityProfileCreate

        p = CustomerTraceabilityProfileCreate(user_id=1)
        assert p.user_id == 1
        assert p.traceability_level == "none"

    def test_customer_traceability_profile_update(self):
        from app.schemas.traceability import CustomerTraceabilityProfileUpdate

        upd = CustomerTraceabilityProfileUpdate()
        assert upd.traceability_level is None
        assert upd.requires_coc is None
        assert upd.requires_coa is None
        assert upd.requires_first_article is None
        assert upd.record_retention_days is None
        assert upd.custom_serial_prefix is None
        assert upd.compliance_standards is None
        assert upd.notes is None

    def test_customer_traceability_profile_response(self):
        from app.schemas.traceability import CustomerTraceabilityProfileResponse

        now = datetime.now(timezone.utc)
        resp = CustomerTraceabilityProfileResponse(
            id=1, user_id=1, created_at=now, updated_at=now,
        )
        assert resp.traceability_level == "none"

    # -- Material Lot --------------------------------------------------------

    def test_material_lot_base(self):
        from app.schemas.traceability import MaterialLotBase

        lot = MaterialLotBase(
            lot_number="LOT-001", product_id=1,
            quantity_received=Decimal("1000"),
        )
        assert lot.vendor_id is None
        assert lot.purchase_order_id is None
        assert lot.vendor_lot_number is None
        assert lot.status == "active"
        assert lot.certificate_of_analysis is None
        assert lot.coa_file_path is None
        assert lot.inspection_status == "pending"
        assert lot.manufactured_date is None
        assert lot.expiration_date is None
        assert lot.received_date is None
        assert lot.unit_cost is None
        assert lot.location is None
        assert lot.notes is None

    def test_material_lot_create(self):
        from app.schemas.traceability import MaterialLotCreate

        lot = MaterialLotCreate(
            lot_number="LOT-001", product_id=1,
            quantity_received=Decimal("1000"),
        )
        assert lot.lot_number == "LOT-001"

    def test_material_lot_update(self):
        from app.schemas.traceability import MaterialLotUpdate

        upd = MaterialLotUpdate()
        assert upd.vendor_lot_number is None
        assert upd.status is None
        assert upd.certificate_of_analysis is None
        assert upd.coa_file_path is None
        assert upd.inspection_status is None
        assert upd.expiration_date is None
        assert upd.unit_cost is None
        assert upd.location is None
        assert upd.notes is None
        assert upd.quantity_scrapped is None
        assert upd.quantity_adjusted is None

    def test_material_lot_response(self):
        from app.schemas.traceability import MaterialLotResponse

        now = datetime.now(timezone.utc)
        resp = MaterialLotResponse(
            id=1, lot_number="LOT-001", product_id=1,
            quantity_received=Decimal("1000"),
            quantity_consumed=Decimal("100"),
            quantity_scrapped=Decimal("0"),
            quantity_adjusted=Decimal("0"),
            quantity_remaining=Decimal("900"),
            created_at=now, updated_at=now,
        )
        assert resp.quantity_remaining == Decimal("900")

    def test_material_lot_list_response(self):
        from app.schemas.traceability import MaterialLotListResponse

        resp = MaterialLotListResponse(
            items=[], total=0, page=1, page_size=25,
        )
        assert resp.items == []

    # -- Serial Number -------------------------------------------------------

    def test_serial_number_base(self):
        from app.schemas.traceability import SerialNumberBase

        sn = SerialNumberBase(
            serial_number="SN-001", product_id=1, production_order_id=1,
        )
        assert sn.status == "manufactured"
        assert sn.qc_passed is True
        assert sn.qc_date is None
        assert sn.qc_notes is None

    def test_serial_number_create(self):
        from app.schemas.traceability import SerialNumberCreate

        sn = SerialNumberCreate(product_id=1, production_order_id=1)
        assert sn.quantity == 1
        assert sn.qc_passed is True
        assert sn.qc_notes is None

    def test_serial_number_update(self):
        from app.schemas.traceability import SerialNumberUpdate

        upd = SerialNumberUpdate()
        assert upd.status is None
        assert upd.qc_passed is None
        assert upd.qc_date is None
        assert upd.qc_notes is None
        assert upd.sales_order_id is None
        assert upd.sales_order_line_id is None
        assert upd.tracking_number is None
        assert upd.return_reason is None

    def test_serial_number_response(self):
        from app.schemas.traceability import SerialNumberResponse

        now = datetime.now(timezone.utc)
        resp = SerialNumberResponse(
            id=1, serial_number="SN-001", product_id=1,
            production_order_id=1, status="manufactured",
            qc_passed=True, manufactured_at=now, created_at=now,
        )
        assert resp.qc_date is None
        assert resp.qc_notes is None
        assert resp.sales_order_id is None
        assert resp.sales_order_line_id is None
        assert resp.sold_at is None
        assert resp.shipped_at is None
        assert resp.tracking_number is None
        assert resp.returned_at is None
        assert resp.return_reason is None

    def test_serial_number_list_response(self):
        from app.schemas.traceability import SerialNumberListResponse

        resp = SerialNumberListResponse(
            items=[], total=0, page=1, page_size=25,
        )
        assert resp.items == []

    # -- Production Lot Consumption ------------------------------------------

    def test_production_lot_consumption_base(self):
        from app.schemas.traceability import ProductionLotConsumptionBase

        c = ProductionLotConsumptionBase(
            production_order_id=1, material_lot_id=1,
            quantity_consumed=Decimal("100"),
        )
        assert c.serial_number_id is None
        assert c.bom_line_id is None

    def test_production_lot_consumption_create(self):
        from app.schemas.traceability import ProductionLotConsumptionCreate

        c = ProductionLotConsumptionCreate(
            production_order_id=1, material_lot_id=1,
            quantity_consumed=Decimal("100"),
        )
        assert c.production_order_id == 1

    def test_production_lot_consumption_response(self):
        from app.schemas.traceability import ProductionLotConsumptionResponse

        now = datetime.now(timezone.utc)
        resp = ProductionLotConsumptionResponse(
            id=1, production_order_id=1, material_lot_id=1,
            quantity_consumed=Decimal("100"), consumed_at=now,
        )
        assert resp.consumed_at == now

    # -- Recall Queries ------------------------------------------------------

    def test_recall_forward_query_request(self):
        from app.schemas.traceability import RecallForwardQueryRequest

        req = RecallForwardQueryRequest(lot_number="LOT-001")
        assert req.lot_number == "LOT-001"

    def test_recall_backward_query_request(self):
        from app.schemas.traceability import RecallBackwardQueryRequest

        req = RecallBackwardQueryRequest(serial_number="SN-001")
        assert req.serial_number == "SN-001"

    def test_recall_affected_product(self):
        from app.schemas.traceability import RecallAffectedProduct

        now = datetime.now(timezone.utc)
        rap = RecallAffectedProduct(
            serial_number="SN-001", product_name="Widget",
            production_order_code="MO-001",
            manufactured_at=now, status="sold",
        )
        assert rap.customer_email is None
        assert rap.sales_order_number is None
        assert rap.shipped_at is None

    def test_recall_forward_query_response(self):
        from app.schemas.traceability import RecallForwardQueryResponse

        resp = RecallForwardQueryResponse(
            lot_number="LOT-001", material_name="PLA Black",
            quantity_received=Decimal("1000"),
            quantity_consumed=Decimal("500"),
            affected_products=[], total_affected=0,
        )
        assert resp.affected_products == []

    def test_material_lot_used(self):
        from app.schemas.traceability import MaterialLotUsed

        mlu = MaterialLotUsed(
            lot_number="LOT-001", material_name="PLA Black",
            quantity_consumed=Decimal("100"),
        )
        assert mlu.vendor_name is None
        assert mlu.vendor_lot_number is None

    def test_recall_backward_query_response(self):
        from app.schemas.traceability import RecallBackwardQueryResponse

        now = datetime.now(timezone.utc)
        resp = RecallBackwardQueryResponse(
            serial_number="SN-001", product_name="Widget",
            manufactured_at=now, material_lots_used=[],
        )
        assert resp.material_lots_used == []


# ============================================================================
# mrp.py
# ============================================================================


class TestMRPSchemas:
    """Cover app/schemas/mrp.py"""

    # -- Enums ---------------------------------------------------------------

    def test_planned_order_type_enum(self):
        from app.schemas.mrp import PlannedOrderType

        assert PlannedOrderType.PURCHASE == "purchase"
        assert PlannedOrderType.PRODUCTION == "production"

    def test_planned_order_status_enum(self):
        from app.schemas.mrp import PlannedOrderStatus

        assert PlannedOrderStatus.PLANNED == "planned"
        assert PlannedOrderStatus.FIRMED == "firmed"
        assert PlannedOrderStatus.RELEASED == "released"
        assert PlannedOrderStatus.CANCELLED == "cancelled"

    def test_mrp_run_status_enum(self):
        from app.schemas.mrp import MRPRunStatus

        assert MRPRunStatus.RUNNING == "running"
        assert MRPRunStatus.COMPLETED == "completed"
        assert MRPRunStatus.FAILED == "failed"
        assert MRPRunStatus.CANCELLED == "cancelled"

    def test_demand_source_enum(self):
        from app.schemas.mrp import DemandSource

        assert DemandSource.PRODUCTION_ORDER == "production_order"
        assert DemandSource.SALES_ORDER == "sales_order"
        assert DemandSource.FORECAST == "forecast"
        assert DemandSource.SAFETY_STOCK == "safety_stock"

    # -- MRP Run schemas -----------------------------------------------------

    def test_mrp_run_request(self):
        from app.schemas.mrp import MRPRunRequest

        req = MRPRunRequest()
        assert req.planning_horizon_days == 30
        assert req.include_draft_orders is True
        assert req.regenerate_planned is True

    def test_mrp_run_request_custom(self):
        from app.schemas.mrp import MRPRunRequest

        req = MRPRunRequest(
            planning_horizon_days=60,
            include_draft_orders=False,
            regenerate_planned=False,
        )
        assert req.planning_horizon_days == 60

    def test_mrp_run_response(self):
        from app.schemas.mrp import MRPRunResponse

        now = datetime.now(timezone.utc)
        resp = MRPRunResponse(
            id=1, run_date=now, planning_horizon_days=30,
            status="completed",
        )
        assert resp.orders_processed == 0
        assert resp.components_analyzed == 0
        assert resp.shortages_found == 0
        assert resp.planned_orders_created == 0
        assert resp.error_message is None
        assert resp.completed_at is None

    def test_mrp_run_summary(self):
        from app.schemas.mrp import MRPRunSummary

        s = MRPRunSummary(runs=[])
        assert s.last_successful_run is None

    # -- Planned Order schemas -----------------------------------------------

    def test_planned_order_base(self):
        from app.schemas.mrp import PlannedOrderBase, PlannedOrderType

        po = PlannedOrderBase(
            order_type=PlannedOrderType.PURCHASE,
            product_id=1, quantity=Decimal("100"),
            due_date=date(2026, 3, 1),
        )
        assert po.notes is None

    def test_planned_order_create(self):
        from app.schemas.mrp import PlannedOrderCreate, PlannedOrderType

        po = PlannedOrderCreate(
            order_type=PlannedOrderType.PRODUCTION,
            product_id=1, quantity=Decimal("50"),
            due_date=date(2026, 3, 1),
        )
        assert po.start_date is None

    def test_planned_order_update(self):
        from app.schemas.mrp import PlannedOrderUpdate

        upd = PlannedOrderUpdate()
        assert upd.quantity is None
        assert upd.due_date is None
        assert upd.start_date is None
        assert upd.notes is None

    def test_planned_order_response(self):
        from app.schemas.mrp import PlannedOrderResponse

        now = datetime.now(timezone.utc)
        resp = PlannedOrderResponse(
            id=1, order_type="purchase", product_id=1,
            quantity=Decimal("100"),
            due_date=date(2026, 3, 1), start_date=date(2026, 2, 15),
            status="planned", created_at=now,
        )
        assert resp.product_sku is None
        assert resp.product_name is None
        assert resp.source_demand_type is None
        assert resp.source_demand_id is None
        assert resp.mrp_run_id is None
        assert resp.converted_to_po_id is None
        assert resp.converted_to_mo_id is None
        assert resp.notes is None
        assert resp.firmed_at is None
        assert resp.released_at is None

    def test_planned_order_list_response(self):
        from app.schemas.mrp import PlannedOrderListResponse

        resp = PlannedOrderListResponse(items=[], total=0)
        assert resp.page == 1
        assert resp.page_size == 50

    # -- Requirements schemas ------------------------------------------------

    def test_component_requirement(self):
        from app.schemas.mrp import ComponentRequirement

        req = ComponentRequirement(
            product_id=1, product_sku="PLA-BLK",
            product_name="PLA Black", bom_level=0,
            gross_quantity=Decimal("1000"),
        )
        assert req.scrap_factor == 0
        assert req.parent_product_id is None

    def test_net_requirement(self):
        from app.schemas.mrp import NetRequirement

        req = NetRequirement(
            product_id=1, product_sku="PLA-BLK",
            product_name="PLA Black",
            gross_quantity=Decimal("1000"),
            on_hand_quantity=Decimal("500"),
            allocated_quantity=Decimal("100"),
            available_quantity=Decimal("400"),
            incoming_quantity=Decimal("0"),
            safety_stock=Decimal("200"),
            net_shortage=Decimal("800"),
            lead_time_days=7,
        )
        assert req.reorder_point is None
        assert req.min_order_qty is None
        assert req.has_bom is False
        assert req.unit_cost == Decimal("0")

    def test_requirements_summary(self):
        from app.schemas.mrp import RequirementsSummary

        s = RequirementsSummary(
            total_components_analyzed=10,
            shortages_found=3,
            components_in_stock=7,
            requirements=[],
        )
        assert s.requirements == []

    # -- Supply/Demand Timeline ----------------------------------------------

    def test_supply_demand_entry(self):
        from app.schemas.mrp import SupplyDemandEntry

        e = SupplyDemandEntry(
            date=date(2026, 3, 1), entry_type="demand",
            source_type="production_order",
            quantity=Decimal("100"),
        )
        assert e.source_id is None
        assert e.source_code is None
        assert e.running_balance is None

    def test_supply_demand_timeline(self):
        from app.schemas.mrp import SupplyDemandTimeline

        t = SupplyDemandTimeline(
            product_id=1, product_sku="PLA-BLK",
            product_name="PLA Black",
            current_on_hand=Decimal("500"),
            current_available=Decimal("400"),
            safety_stock=Decimal("200"),
            entries=[],
        )
        assert t.projected_shortage_date is None
        assert t.days_of_supply is None

    # -- Action schemas ------------------------------------------------------

    def test_firm_planned_order_request(self):
        from app.schemas.mrp import FirmPlannedOrderRequest

        req = FirmPlannedOrderRequest()
        assert req.notes is None

    def test_release_planned_order_request(self):
        from app.schemas.mrp import ReleasePlannedOrderRequest

        req = ReleasePlannedOrderRequest()
        assert req.vendor_id is None
        assert req.notes is None

    def test_release_planned_order_response(self):
        from app.schemas.mrp import ReleasePlannedOrderResponse

        resp = ReleasePlannedOrderResponse(
            planned_order_id=1, order_type="purchase",
        )
        assert resp.created_purchase_order_id is None
        assert resp.created_purchase_order_code is None
        assert resp.created_production_order_id is None
        assert resp.created_production_order_code is None

    # -- Pegging schemas -----------------------------------------------------

    def test_pegging_entry(self):
        from app.schemas.mrp import PeggingEntry

        pe = PeggingEntry(
            supply_type="purchase_order", supply_id=1,
            supply_code="PO-001", quantity=Decimal("100"),
            demand_type="production_order", demand_id=1,
        )
        assert pe.demand_code is None

    def test_product_pegging(self):
        from app.schemas.mrp import ProductPegging

        pp = ProductPegging(
            product_id=1, product_sku="PLA-BLK",
            supplies=[], demands=[],
        )
        assert pp.supplies == []
        assert pp.demands == []
