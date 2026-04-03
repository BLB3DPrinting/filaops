"""Status Configuration and Transition Rules

This module defines valid status values and allowed transitions for
Production Orders and Sales Orders. Status transitions are validated
to prevent invalid state changes.

Sprint 3-4: Data Model Cleanup - Status Validation
"""
from enum import Enum
from typing import Dict, List, Set


# =============================================================================
# Production Order Status
# =============================================================================

class ProductionOrderStatus(str, Enum):
    """Valid status values for Production Orders"""
    DRAFT = "draft"
    RELEASED = "released"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    SHORT = "short"  # Produced less than ordered, awaiting accept-short decision
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    SPLIT = "split"  # Order was split into child orders


# Allowed transitions: current_status -> set of allowed next statuses
PRODUCTION_ORDER_TRANSITIONS: Dict[str, Set[str]] = {
    ProductionOrderStatus.DRAFT: {
        ProductionOrderStatus.RELEASED,
        ProductionOrderStatus.CANCELLED,
    },
    ProductionOrderStatus.RELEASED: {
        ProductionOrderStatus.IN_PROGRESS,
        ProductionOrderStatus.ON_HOLD,
        ProductionOrderStatus.CANCELLED,
        ProductionOrderStatus.SPLIT,
    },
    ProductionOrderStatus.IN_PROGRESS: {
        ProductionOrderStatus.ON_HOLD,
        ProductionOrderStatus.COMPLETE,
        ProductionOrderStatus.SHORT,
        ProductionOrderStatus.CANCELLED,
        ProductionOrderStatus.SPLIT,
    },
    ProductionOrderStatus.ON_HOLD: {
        ProductionOrderStatus.RELEASED,
        ProductionOrderStatus.IN_PROGRESS,
        ProductionOrderStatus.CANCELLED,
    },
    ProductionOrderStatus.SHORT: {
        ProductionOrderStatus.COMPLETE,  # Accept short → complete
        ProductionOrderStatus.CANCELLED,
    },
    ProductionOrderStatus.COMPLETE: set(),  # Terminal state - no transitions allowed
    ProductionOrderStatus.CANCELLED: set(),  # Terminal state
    ProductionOrderStatus.SPLIT: set(),  # Terminal state - children take over
}


def get_allowed_production_order_transitions(current_status: str) -> List[str]:
    """Get list of allowed next statuses for a production order"""
    return list(PRODUCTION_ORDER_TRANSITIONS.get(current_status, set()))


def is_valid_production_order_transition(current_status: str, new_status: str) -> bool:
    """Check if a production order status transition is valid"""
    if current_status == new_status:
        return True  # No change is always valid
    allowed = PRODUCTION_ORDER_TRANSITIONS.get(current_status, set())
    return new_status in allowed


# =============================================================================
# Production Order Operation Status
# =============================================================================

class OperationStatus(str, Enum):
    """Valid status values for Production Order Operations"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    SKIPPED = "skipped"


OPERATION_STATUS_TRANSITIONS: Dict[str, Set[str]] = {
    OperationStatus.PENDING: {
        OperationStatus.QUEUED,
        OperationStatus.SKIPPED,
    },
    OperationStatus.QUEUED: {
        OperationStatus.RUNNING,
        OperationStatus.SKIPPED,
    },
    OperationStatus.RUNNING: {
        OperationStatus.COMPLETE,
        OperationStatus.QUEUED,  # Can pause/restart
    },
    OperationStatus.COMPLETE: set(),  # Terminal
    OperationStatus.SKIPPED: set(),  # Terminal
}


# =============================================================================
# Sales Order Status
# =============================================================================

class SalesOrderStatus(str, Enum):
    """Valid status values for Sales Orders"""
    PENDING_CONFIRMATION = "pending_confirmation"  # Awaiting admin review (external orders)
    DRAFT = "draft"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    IN_PRODUCTION = "in_production"
    READY_TO_SHIP = "ready_to_ship"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"


SALES_ORDER_TRANSITIONS: Dict[str, Set[str]] = {
    SalesOrderStatus.PENDING_CONFIRMATION: {
        SalesOrderStatus.CONFIRMED,
        SalesOrderStatus.CANCELLED,
    },
    SalesOrderStatus.DRAFT: {
        SalesOrderStatus.PENDING,
        SalesOrderStatus.CANCELLED,
    },
    SalesOrderStatus.PENDING: {
        SalesOrderStatus.CONFIRMED,
        SalesOrderStatus.ON_HOLD,
        SalesOrderStatus.CANCELLED,
    },
    SalesOrderStatus.CONFIRMED: {
        SalesOrderStatus.IN_PRODUCTION,
        SalesOrderStatus.READY_TO_SHIP,  # If no production needed
        SalesOrderStatus.ON_HOLD,
        SalesOrderStatus.CANCELLED,
        SalesOrderStatus.COMPLETED,  # Close short
    },
    SalesOrderStatus.IN_PRODUCTION: {
        SalesOrderStatus.READY_TO_SHIP,
        SalesOrderStatus.ON_HOLD,
        SalesOrderStatus.CANCELLED,
        SalesOrderStatus.COMPLETED,  # Close short
    },
    SalesOrderStatus.READY_TO_SHIP: {
        SalesOrderStatus.SHIPPED,
        SalesOrderStatus.ON_HOLD,
        SalesOrderStatus.CANCELLED,
        SalesOrderStatus.COMPLETED,  # Close short
    },
    SalesOrderStatus.SHIPPED: {
        SalesOrderStatus.DELIVERED,
        SalesOrderStatus.COMPLETED,
    },
    SalesOrderStatus.DELIVERED: {
        SalesOrderStatus.COMPLETED,
    },
    SalesOrderStatus.COMPLETED: set(),  # Terminal
    SalesOrderStatus.CANCELLED: set(),  # Terminal
    SalesOrderStatus.ON_HOLD: {
        SalesOrderStatus.PENDING,
        SalesOrderStatus.CONFIRMED,
        SalesOrderStatus.IN_PRODUCTION,
        SalesOrderStatus.READY_TO_SHIP,
        SalesOrderStatus.CANCELLED,
        SalesOrderStatus.COMPLETED,  # Close short
    },
}


def get_allowed_sales_order_transitions(current_status: str) -> List[str]:
    """Get list of allowed next statuses for a sales order"""
    return list(SALES_ORDER_TRANSITIONS.get(current_status, set()))


def is_valid_sales_order_transition(current_status: str, new_status: str) -> bool:
    """Check if a sales order status transition is valid"""
    if current_status == new_status:
        return True
    allowed = SALES_ORDER_TRANSITIONS.get(current_status, set())
    return new_status in allowed


# =============================================================================
# Payment Status
# =============================================================================

class PaymentStatus(str, Enum):
    """Valid payment status values for Sales Orders"""
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"
    REFUNDED = "refunded"
    OVERDUE = "overdue"


# =============================================================================
# QC Status
# =============================================================================

class QCStatus(str, Enum):
    """Valid QC status values for Production Orders"""
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    WAIVED = "waived"


QC_STATUS_TRANSITIONS: Dict[str, Set[str]] = {
    QCStatus.NOT_REQUIRED: set(),  # Can't change from not_required
    QCStatus.PENDING: {
        QCStatus.PASSED,
        QCStatus.FAILED,
        QCStatus.WAIVED,
    },
    QCStatus.PASSED: set(),  # Terminal
    QCStatus.FAILED: {
        QCStatus.PENDING,  # Re-inspect
    },
    QCStatus.WAIVED: set(),  # Terminal
}


# =============================================================================
# Validation Helpers
# =============================================================================

class StatusTransitionError(Exception):
    """Raised when an invalid status transition is attempted"""
    def __init__(self, entity: str, current: str, requested: str, allowed: List[str]):
        self.entity = entity
        self.current = current
        self.requested = requested
        self.allowed = allowed
        super().__init__(
            f"Invalid {entity} status transition: '{current}' -> '{requested}'. "
            f"Allowed: {allowed if allowed else 'none (terminal state)'}"
        )


def validate_production_order_transition(current: str, new: str) -> None:
    """Validate and raise error if transition is invalid"""
    if not is_valid_production_order_transition(current, new):
        raise StatusTransitionError(
            "production order",
            current,
            new,
            get_allowed_production_order_transitions(current)
        )


def validate_sales_order_transition(current: str, new: str) -> None:
    """Validate and raise error if transition is invalid"""
    if not is_valid_sales_order_transition(current, new):
        raise StatusTransitionError(
            "sales order",
            current,
            new,
            get_allowed_sales_order_transitions(current)
        )
