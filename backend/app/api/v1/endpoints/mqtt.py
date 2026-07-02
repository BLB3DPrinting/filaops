"""
MQTT Telemetry API Endpoints

Provides REST access to live printer telemetry for:
- AI workers (Otto, Sam, Ada)
- Admin UI for monitoring
- Frontend command center

All endpoints authenticate via the standard JWT dependency (get_current_user).
"""

from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel

from app.api.v1.deps import get_current_user
from app.models import User


router = APIRouter(prefix="/mqtt", tags=["MQTT Telemetry"])


# ==========================================================================
# Response Models
# ==========================================================================

class ServiceStatusResponse(BaseModel):
    running: bool
    total_printers: int
    connected_printers: int
    event_queue_size: int


class BulkPrinterStatusResponse(BaseModel):
    """Response for bulk printer status (Otto's main endpoint)."""
    timestamp: str
    printer_count: int
    printers: dict  # printer_id -> status


class TelemetryEventResponse(BaseModel):
    id: int
    event_type: str
    printer_id: int
    timestamp: str
    data: dict
    production_order_id: Optional[int] = None


# ==========================================================================
# Service Status Endpoints
# ==========================================================================

@router.get("/status", response_model=ServiceStatusResponse)
async def get_mqtt_status(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Get MQTT monitoring service status.

    Requires authentication.
    """
    monitor = getattr(request.app.state, "mqtt_monitor", None)
    if not monitor:
        return ServiceStatusResponse(
            running=False,
            total_printers=0,
            connected_printers=0,
            event_queue_size=0
        )
    return monitor.get_service_status()


@router.post("/start")
async def start_mqtt_monitoring(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Start MQTT monitoring service.

    Requires admin authentication.
    """
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")

    monitor = getattr(request.app.state, "mqtt_monitor", None)
    if not monitor:
        raise HTTPException(500, "MQTT monitor not configured")

    await monitor.start()
    return {"status": "started", **monitor.get_service_status()}


@router.post("/stop")
async def stop_mqtt_monitoring(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Stop MQTT monitoring service.

    Requires admin authentication.
    """
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")

    monitor = getattr(request.app.state, "mqtt_monitor", None)
    if not monitor:
        raise HTTPException(500, "MQTT monitor not configured")

    await monitor.stop()
    return {"status": "stopped"}


# ==========================================================================
# Live Status Endpoints (for AI workers)
# ==========================================================================

@router.get("/printers/live", response_model=BulkPrinterStatusResponse)
async def get_all_printers_live_status(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Get live status for ALL printers in one call.

    This is Otto's primary endpoint - bulk fetch for efficiency.
    Returns cached in-memory data (instant, no DB hit).

    Supports both JWT and API Key authentication.
    """
    monitor = getattr(request.app.state, "mqtt_monitor", None)
    if not monitor:
        raise HTTPException(503, "MQTT monitoring not available")

    all_status = monitor.get_all_printer_status()

    return BulkPrinterStatusResponse(
        timestamp=datetime.now(timezone.utc).isoformat(),
        printer_count=len(all_status),
        printers=all_status
    )


@router.get("/printer/{printer_id}/live")
async def get_printer_live_status(
    printer_id: int,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Get live status for a single printer.

    Returns cached in-memory data (instant, no DB hit).

    Supports both JWT and API Key authentication.
    """
    monitor = getattr(request.app.state, "mqtt_monitor", None)
    if not monitor:
        raise HTTPException(503, "MQTT monitoring not available")

    status = monitor.get_printer_status(printer_id)
    if not status:
        raise HTTPException(404, f"Printer {printer_id} not found in monitor")

    return status


# ==========================================================================
# Event Endpoints (for AI workers to detect issues)
# ==========================================================================

@router.get("/events/recent", response_model=List[TelemetryEventResponse])
async def get_recent_events(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user)
):
    """
    Get recent events across all printers.

    Events include: connections, disconnections, print completions,
    failures, errors, filament runouts.

    Otto polls this to detect issues proactively.
    """
    monitor = getattr(request.app.state, "mqtt_monitor", None)
    if not monitor:
        return []

    return monitor.get_recent_events(limit)


@router.get("/events/since/{since_id}", response_model=List[TelemetryEventResponse])
async def get_events_since(
    since_id: int,
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user)
):
    """
    Get events since a specific event ID.

    For efficient polling: Otto remembers the last event ID he saw,
    then asks for events since then. Only gets new events.
    """
    monitor = getattr(request.app.state, "mqtt_monitor", None)
    if not monitor:
        return []

    return monitor.get_events_since(since_id, limit)


@router.get("/events/failures", response_model=List[TelemetryEventResponse])
async def get_failure_events(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user)
):
    """
    Get recent failure events only.

    Convenience endpoint for Otto to check "what went wrong?"
    """
    monitor = getattr(request.app.state, "mqtt_monitor", None)
    if not monitor:
        return []

    from app.services.mqtt.events import EventType
    failures = []
    failures.extend(monitor.get_events_by_type(EventType.PRINT_FAILED, limit))
    failures.extend(monitor.get_events_by_type(EventType.PRINTER_ERROR, limit))
    failures.extend(monitor.get_events_by_type(EventType.FILAMENT_RUNOUT, limit))
    failures.extend(monitor.get_events_by_type(EventType.DISCONNECTED, limit))

    # Sort by timestamp descending
    failures.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return failures[:limit]


# ==========================================================================
# Production Order Linking (for fulfillment integration)
# ==========================================================================

@router.post("/printer/{printer_id}/link-po/{production_order_id}")
async def link_production_order(
    printer_id: int,
    production_order_id: int,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Link a production order to a printer.

    Call this when starting a print job for a PO.
    Events will then include the PO ID for correlation.
    """
    monitor = getattr(request.app.state, "mqtt_monitor", None)
    if not monitor:
        raise HTTPException(503, "MQTT monitoring not available")

    monitor.link_production_order(printer_id, production_order_id)
    return {"status": "linked", "printer_id": printer_id, "production_order_id": production_order_id}


@router.post("/printer/{printer_id}/unlink-po")
async def unlink_production_order(
    printer_id: int,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Unlink production order from printer.

    Call this when print completes or is cancelled.
    """
    monitor = getattr(request.app.state, "mqtt_monitor", None)
    if not monitor:
        raise HTTPException(503, "MQTT monitoring not available")

    monitor.unlink_production_order(printer_id)
    return {"status": "unlinked", "printer_id": printer_id}


# ==========================================================================
# Manual Controls
# ==========================================================================

@router.post("/printer/{printer_id}/reconnect")
async def reconnect_printer(
    printer_id: int,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Manually reconnect a printer.

    Use after updating MQTT credentials or if connection dropped.
    """
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")

    monitor = getattr(request.app.state, "mqtt_monitor", None)
    if not monitor:
        raise HTTPException(503, "MQTT monitoring not available")

    success = await monitor.reconnect_printer(printer_id)
    return {"status": "reconnected" if success else "failed", "printer_id": printer_id}


@router.post("/printer/{printer_id}/add")
async def add_printer_to_monitor(
    printer_id: int,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Add a printer to the monitor (after creating in admin).

    Use when a new Bambu printer is added with MQTT credentials.
    """
    if not current_user.is_admin:
        raise HTTPException(403, "Admin access required")

    monitor = getattr(request.app.state, "mqtt_monitor", None)
    if not monitor:
        raise HTTPException(503, "MQTT monitoring not available")

    success = await monitor.add_printer(printer_id)
    return {"status": "added" if success else "failed", "printer_id": printer_id}
