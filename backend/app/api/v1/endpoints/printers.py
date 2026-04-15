"""
Printers API Endpoints

Brand-agnostic printer management with support for:
- CRUD operations
- Network discovery (BambuLab, Klipper, etc.)
- Connection testing
- Bulk CSV import for print farms
"""
import csv
import io
import time
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.logging_config import get_logger
from app.models.printer import Printer
from app.api.v1.endpoints.auth import get_current_user
from app.models.user import User
from app.core.features import enforce_resource_limit, get_current_tier
from app.schemas.printer import (
    PrinterBrand,
    PrinterStatus,
    PrinterCreate,
    PrinterUpdate,
    PrinterResponse,
    PrinterListResponse,
    DiscoveredPrinterResponse,
    DiscoveryResultResponse,
    DiscoveryRequest,
    PrinterCSVImportRequest,
    PrinterCSVImportResult,
    PrinterStatusUpdate,
    PrinterConnectionTest,
    PrinterConnectionTestResult,
    PrinterBrandInfo,
    PrinterModelInfo,
)
from app.services.printer_discovery import get_orchestrator
from app.models.production_order import ProductionOrder, ProductionOrderOperation

router = APIRouter()
logger = get_logger(__name__)


# ============================================================================
# Brand registry (tiered)
# ============================================================================
#
# Core ships with only Bambu Lab + Generic brands visible to the UI. The
# discovery orchestrator may register additional adapter stubs (e.g. Klipper
# mDNS), but those are hidden from `/brands/info` unless a PRO plugin opts
# them in via `register_brand()`. This is the single surface PRO uses to
# advertise multi-brand support without Core having to know about PRO.
#
# PRO calls this at import time from `filaops_pro.register()`:
#
#     from app.api.v1.endpoints.printers import register_brand
#     register_brand(PrinterBrandInfo(code="klipper", ...))
#
# Duplicate registrations (same code) overwrite earlier entries, so PRO can
# supply its own richer model lists without colliding with Core defaults.

_CORE_BRAND_CODES: frozenset[str] = frozenset({"bambulab", "generic"})
_extra_brands: Dict[str, PrinterBrandInfo] = {}


def register_brand(brand_info: PrinterBrandInfo) -> None:
    """
    Register an additional brand for `/brands/info`.

    Intended for PRO plugins to advertise brands beyond Core's Bambu+Generic
    baseline (Klipper, OctoPrint, Prusa, Creality, etc.). Called at import
    time from `filaops_pro.register()`; no-op if the brand code already
    lives in `_CORE_BRAND_CODES`.

    Brand codes are canonicalized (trimmed + lower-cased) at the boundary so
    plugins passing `" Klipper "` or `"KLIPPER"` land in the same dict slot
    as `"klipper"` and can't sneak past the Core-brand check.
    """
    code = (brand_info.code or "").strip().lower()
    if not code:
        logger.debug("Ignoring register_brand(): empty or whitespace-only code")
        return
    if code in _CORE_BRAND_CODES:
        logger.debug(
            "Ignoring register_brand(%s): already a Core brand", code
        )
        return
    # Store the normalized code on the stored copy so downstream consumers
    # (the /brands/info response) see the canonical form.
    normalized = brand_info.model_copy(update={"code": code})
    _extra_brands[code] = normalized
    logger.info("Registered extra printer brand: %s", code)


def _generate_printer_code(db: Session, prefix: str = "PRT") -> str:
    """Generate next printer code (PRT-001, PRT-002, etc.)"""
    last = db.query(Printer).filter(
        Printer.code.like(f"{prefix}-%")
    ).order_by(desc(Printer.code)).first()

    if last and last.code.startswith(f"{prefix}-"):
        try:
            num = int(last.code.split("-")[1])
            return f"{prefix}-{num + 1:03d}"
        except (IndexError, ValueError):
            pass
    return f"{prefix}-001"


def _printer_to_response(printer: Printer) -> PrinterResponse:
    """Convert Printer model to response schema"""
    return PrinterResponse(
        id=printer.id,
        code=printer.code,
        name=printer.name,
        model=printer.model,
        brand=PrinterBrand(printer.brand) if printer.brand else PrinterBrand.GENERIC,
        serial_number=printer.serial_number,
        ip_address=printer.ip_address,
        mqtt_topic=printer.mqtt_topic,
        location=printer.location,
        work_center_id=printer.work_center_id,
        notes=printer.notes,
        active=printer.active,
        status=PrinterStatus(printer.status) if printer.status else PrinterStatus.OFFLINE,
        connection_config=printer.connection_config or {},
        capabilities=printer.capabilities or {},
        last_seen=printer.last_seen,
        created_at=printer.created_at,
        updated_at=printer.updated_at,
        is_online=printer.is_online,
        has_ams=printer.has_ams,
        has_camera=printer.has_camera,
    )


# ============================================================================
# Static routes (must be before /{printer_id} route to avoid conflicts)
# ============================================================================

@router.get("/generate-code")
async def generate_printer_code(
    prefix: str = Query("PRT", max_length=5),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a new unique printer code"""
    return {"code": _generate_printer_code(db, prefix.upper())}


@router.get("/brands/info", response_model=List[PrinterBrandInfo])
async def get_supported_brands(
    current_user: User = Depends(get_current_user),
):
    """
    Get information about supported printer brands.

    Core returns only Bambu Lab + Generic. PRO plugins opt additional brands
    in via `register_brand()` (see module docstring). Returns details about
    each brand including supported models, discovery support, and required
    connection fields.
    """
    orchestrator = get_orchestrator()
    brands: List[PrinterBrandInfo] = []

    # Core brands sourced from the discovery orchestrator
    for brand_code, adapter in orchestrator.adapters.items():
        if brand_code not in _CORE_BRAND_CODES:
            continue

        models = [
            PrinterModelInfo(
                value=m["value"],
                label=m["label"],
                capabilities=m.get("capabilities"),
            )
            for m in adapter.get_supported_models()
        ]

        brands.append(PrinterBrandInfo(
            code=brand_code,
            name=adapter.brand_name,
            supports_discovery=hasattr(adapter, "discover_local"),
            models=models,
            connection_fields=adapter.get_connection_fields(),
        ))

    # PRO-contributed brands (Klipper, OctoPrint, Prusa, Creality, ...)
    brands.extend(_extra_brands.values())

    return brands


# ============================================================================
# Active Work Tracking (must be before /{printer_id} to avoid route conflicts)
# ============================================================================

@router.get("/active-work")
async def get_printers_active_work(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get active/scheduled work for all printers.

    Returns a mapping of printer_id -> current work info based on
    production order operations scheduled to their work centers.

    Community feature: Shows scheduled work from production order operations.
    Pro feature (future): Live MQTT status with actual print progress.
    """
    from sqlalchemy.orm import joinedload

    # Get all active printers with work centers
    printers = db.query(Printer).filter(
        Printer.active.is_(True),
        Printer.work_center_id.isnot(None)
    ).all()

    if not printers:
        return {"printers": {}}

    # Get work center IDs
    work_center_ids = [p.work_center_id for p in printers]

    # Find running or queued operations for these work centers
    active_ops = db.query(ProductionOrderOperation).options(
        joinedload(ProductionOrderOperation.production_order).joinedload(ProductionOrder.product)
    ).filter(
        ProductionOrderOperation.work_center_id.in_(work_center_ids),
        ProductionOrderOperation.status.in_(['running', 'queued'])
    ).order_by(
        ProductionOrderOperation.status.desc(),  # running first
        ProductionOrderOperation.scheduled_start
    ).all()

    # Build work center -> operations mapping
    wc_ops = {}
    for op in active_ops:
        if op.work_center_id not in wc_ops:
            wc_ops[op.work_center_id] = []
        wc_ops[op.work_center_id].append(op)

    # Build printer -> work info mapping
    result = {}
    for printer in printers:
        ops = wc_ops.get(printer.work_center_id, [])

        # Get the first running operation, or first queued if none running
        current_op = None
        for op in ops:
            if op.status == 'running':
                current_op = op
                break
        if not current_op and ops:
            current_op = ops[0]  # First queued

        if current_op:
            po = current_op.production_order
            product = po.product if po else None
            result[printer.id] = {
                "production_order_code": po.code if po else None,
                "production_order_id": po.id if po else None,
                "operation_status": current_op.status,
                "operation_name": current_op.operation_name,
                "product_sku": product.sku if product else None,
                "product_name": product.name if product else None,
                "quantity_ordered": float(po.quantity_ordered) if po else None,
                "quantity_completed": float(po.quantity_completed) if po else 0,
                "scheduled_start": current_op.scheduled_start.isoformat() if current_op.scheduled_start else None,
                "scheduled_end": current_op.scheduled_end.isoformat() if current_op.scheduled_end else None,
                "queue_depth": len([o for o in ops if o.status == 'queued']),
            }
        else:
            result[printer.id] = None

    return {"printers": result}


# ============================================================================
# Printer CRUD
# ============================================================================

@router.get("/", response_model=PrinterListResponse)
async def list_printers(
    search: Optional[str] = None,
    brand: Optional[PrinterBrand] = None,
    status: Optional[PrinterStatus] = None,
    active_only: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all printers with filtering and pagination

    - **search**: Search by name, code, model, or location
    - **brand**: Filter by brand (bambulab, klipper, etc.)
    - **status**: Filter by status (offline, idle, printing, etc.)
    - **active_only**: Only show active printers
    """
    query = db.query(Printer)

    if active_only:
        query = query.filter(Printer.active.is_(True))

    if brand:
        query = query.filter(Printer.brand == brand.value)

    if status:
        query = query.filter(Printer.status == status.value)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (Printer.name.ilike(search_filter)) |
            (Printer.code.ilike(search_filter)) |
            (Printer.model.ilike(search_filter)) |
            (Printer.location.ilike(search_filter))
        )

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    printers = query.order_by(Printer.name).offset(offset).limit(page_size).all()

    return PrinterListResponse(
        items=[_printer_to_response(p) for p in printers],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/{printer_id}", response_model=PrinterResponse)
async def get_printer(
    printer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single printer by ID"""
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")
    return _printer_to_response(printer)


@router.post("/", response_model=PrinterResponse)
async def create_printer(
    data: PrinterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new printer

    The printer code can be auto-generated if not provided.

    Note: Subject to tier limits. Community tier allows up to 4 printers.
    """
    # Check tier limits before creating
    current_printer_count = db.query(Printer).filter(
        Printer.active.is_(True)
    ).count()

    user_tier = get_current_tier(db, current_user)
    enforce_resource_limit(db, "printers", current_printer_count, user_tier.value)

    # Check for duplicate code
    if db.query(Printer).filter(Printer.code == data.code).first():
        raise HTTPException(
            status_code=400,
            detail=f"Printer with code '{data.code}' already exists"
        )

    printer = Printer(
        code=data.code,
        name=data.name,
        model=data.model,
        brand=data.brand.value if data.brand else "generic",
        serial_number=data.serial_number,
        ip_address=data.ip_address,
        mqtt_topic=data.mqtt_topic,
        location=data.location,
        work_center_id=data.work_center_id,
        notes=data.notes,
        active=data.active if data.active is not None else True,
        connection_config=data.connection_config or {},
        capabilities=data.capabilities or {},
        status="offline",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db.add(printer)
    db.commit()
    db.refresh(printer)

    logger.info(f"Created printer {printer.code}: {printer.name}")
    return _printer_to_response(printer)


@router.put("/{printer_id}", response_model=PrinterResponse)
async def update_printer(
    printer_id: int,
    data: PrinterUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an existing printer"""
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")

    # Check for duplicate code if changing
    if data.code and data.code != printer.code:
        if db.query(Printer).filter(Printer.code == data.code).first():
            raise HTTPException(
                status_code=400,
                detail=f"Printer with code '{data.code}' already exists"
            )

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "brand" and value:
            value = value.value if hasattr(value, "value") else value
        setattr(printer, field, value)

    printer.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(printer)

    logger.info(f"Updated printer {printer.code}")
    return _printer_to_response(printer)


@router.delete("/{printer_id}")
async def delete_printer(
    printer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a printer

    Note: This performs a hard delete. Consider using update with active=False
    for soft delete instead.
    """
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")

    code = printer.code
    db.delete(printer)
    db.commit()

    logger.info(f"Deleted printer {code}")
    return {"message": f"Printer {code} deleted successfully"}


# ============================================================================
# Status Updates
# ============================================================================

@router.patch("/{printer_id}/status", response_model=PrinterResponse)
async def update_printer_status(
    printer_id: int,
    data: PrinterStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update printer status"""
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")

    printer.status = data.status.value
    printer.last_seen = datetime.now(timezone.utc)
    printer.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(printer)

    return _printer_to_response(printer)


# ============================================================================
# Network Discovery
# ============================================================================

@router.post("/discover", response_model=DiscoveryResultResponse)
async def discover_printers(
    request: DiscoveryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Discover printers on the local network

    Scans for:
    - BambuLab printers (SSDP on port 1990)
    - Klipper/Moonraker instances (mDNS)
    - OctoPrint instances (if supported)

    Returns a list of discovered printers with their capabilities.
    """
    start_time = time.time()
    errors = []

    orchestrator = get_orchestrator()

    # Filter brands if specified
    brands_to_scan = None
    if request.brands:
        brands_to_scan = [b.value for b in request.brands]

    try:
        discovered = await orchestrator.discover_all(
            timeout_seconds=request.timeout_seconds,
            brand_filter=brands_to_scan,
        )
    except Exception as e:
        logger.error(f"Discovery error: {e}")
        errors.append(str(e))
        discovered = []

    # Get existing printer serials/IPs for duplicate detection
    existing_serials = set(
        p.serial_number for p in db.query(Printer.serial_number).filter(
            Printer.serial_number.isnot(None)
        ).all()
    )
    existing_ips = set(
        p.ip_address for p in db.query(Printer.ip_address).filter(
            Printer.ip_address.isnot(None)
        ).all()
    )

    result_printers = []
    for printer in discovered:
        already_registered = (
            (printer.serial_number and printer.serial_number in existing_serials) or
            (printer.ip_address and printer.ip_address in existing_ips)
        )

        result_printers.append(DiscoveredPrinterResponse(
            brand=PrinterBrand(printer.brand.value),
            model=printer.model,
            name=printer.name,
            ip_address=printer.ip_address,
            serial_number=printer.serial_number,
            capabilities=printer.capabilities.model_dump() if printer.capabilities else {},
            suggested_code=_generate_printer_code(db, printer.brand.value.upper()[:3]),
            already_registered=already_registered,
        ))

    scan_duration = time.time() - start_time
    logger.info(f"Discovery completed: {len(result_printers)} printers found in {scan_duration:.2f}s")

    return DiscoveryResultResponse(
        printers=result_printers,
        scan_duration_seconds=scan_duration,
        errors=errors,
    )


@router.post("/probe-ip")
async def probe_printer_ip(
    ip_address: str = Query(..., description="IP address to probe"),
    brand: Optional[PrinterBrand] = Query(None, description="Expected brand (optional)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Probe an IP address to detect printer info.

    Since SSDP discovery doesn't work from Docker containers,
    this provides an alternative: enter an IP and we'll try to
    detect what printer is there.

    For BambuLab: Tries MQTT port 8883 and HTTP endpoints
    """
    import socket

    result = {
        "ip_address": ip_address,
        "reachable": False,
        "brand": None,
        "model": None,
        "suggested_name": None,
        "ports_open": [],
    }

    # Check common printer ports
    ports_to_check = [
        (8883, "mqtt", "bambulab"),      # BambuLab MQTT
        (80, "http", None),               # HTTP
        (443, "https", None),             # HTTPS
        (7125, "moonraker", "klipper"),   # Klipper/Moonraker
        (5000, "octoprint", "octoprint"), # OctoPrint
    ]

    def check_port(ip: str, port: int) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            res = sock.connect_ex((ip, port))
            sock.close()
            return res == 0
        except Exception:
            return False

    # Run port checks
    for port, service, detected_brand in ports_to_check:
        if check_port(ip_address, port):
            result["reachable"] = True
            result["ports_open"].append({"port": port, "service": service})
            if detected_brand and not result["brand"]:
                result["brand"] = detected_brand

    # If BambuLab detected, try to get more info
    if result["brand"] == "bambulab" or (brand and brand.value == "bambulab"):
        result["brand"] = "bambulab"
        # Default to generic model - user will need to specify
        result["model"] = "Unknown"
        result["suggested_name"] = f"BambuLab Printer ({ip_address.split('.')[-1]})"

    elif result["brand"] == "klipper":
        result["suggested_name"] = f"Klipper Printer ({ip_address.split('.')[-1]})"

    elif result["brand"] == "octoprint":
        result["suggested_name"] = f"OctoPrint ({ip_address.split('.')[-1]})"

    elif result["reachable"]:
        result["brand"] = brand.value if brand else "generic"
        result["suggested_name"] = f"Printer ({ip_address.split('.')[-1]})"

    # Check if already registered
    existing = db.query(Printer).filter(Printer.ip_address == ip_address).first()
    result["already_registered"] = existing is not None
    if existing:
        result["existing_printer"] = {
            "id": existing.id,
            "code": existing.code,
            "name": existing.name,
        }

    # Generate suggested code
    if not result["already_registered"] and result["brand"]:
        prefix = result["brand"].upper()[:3]
        result["suggested_code"] = _generate_printer_code(db, prefix)

    return result


@router.post("/test-connection", response_model=PrinterConnectionTestResult)
async def test_printer_connection(
    data: PrinterConnectionTest,
    current_user: User = Depends(get_current_user),
):
    """
    Test connection to a printer

    Tests if the printer is reachable and responding to API calls.
    """
    orchestrator = get_orchestrator()
    adapter = orchestrator.get_adapter(data.brand.value)

    if not adapter:
        raise HTTPException(
            status_code=400,
            detail=f"No adapter available for brand '{data.brand}'"
        )

    start_time = time.time()

    from app.services.printer_discovery.models import PrinterConnectionConfig
    config = PrinterConnectionConfig(
        ip_address=data.ip_address,
        **data.connection_config
    )

    try:
        success, error_msg = await adapter.test_connection(config)
        response_time = (time.time() - start_time) * 1000  # ms

        return PrinterConnectionTestResult(
            success=success,
            message=error_msg if not success else "Connection successful",
            response_time_ms=response_time if success else None,
        )
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return PrinterConnectionTestResult(
            success=False,
            message=str(e),
            response_time_ms=None,
        )


# ============================================================================
# Bulk Import
# ============================================================================

@router.post("/import-csv", response_model=PrinterCSVImportResult)
async def import_printers_csv(
    data: PrinterCSVImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Import printers from CSV data

    CSV format:
    code,name,model,brand,serial_number,ip_address,location,notes

    Example:
    PRT-001,X1C-01,X1 Carbon,bambulab,ABC123,192.168.1.100,Farm A,Bay 1
    """
    errors = []
    imported = 0
    skipped = 0

    try:
        reader = csv.DictReader(io.StringIO(data.csv_data))
        rows = list(reader)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid CSV format: {str(e)}"
        )

    total_rows = len(rows)

    for row_num, row in enumerate(rows, start=2):  # Start at 2 (header is row 1)
        try:
            code = row.get("code", "").strip()
            name = row.get("name", "").strip()
            model = row.get("model", "").strip()

            if not code or not name or not model:
                errors.append({
                    "row": str(row_num),
                    "error": "Missing required field (code, name, or model)"
                })
                continue

            # Check for duplicate
            if db.query(Printer).filter(Printer.code == code).first():
                if data.skip_duplicates:
                    skipped += 1
                    continue
                else:
                    errors.append({
                        "row": str(row_num),
                        "error": f"Printer code '{code}' already exists"
                    })
                    continue

            # Validate brand
            brand = row.get("brand", "generic").strip().lower()
            valid_brands = [b.value for b in PrinterBrand]
            if brand not in valid_brands:
                brand = "generic"

            printer = Printer(
                code=code,
                name=name,
                model=model,
                brand=brand,
                serial_number=row.get("serial_number", "").strip() or None,
                ip_address=row.get("ip_address", "").strip() or None,
                location=row.get("location", "").strip() or None,
                notes=row.get("notes", "").strip() or None,
                active=True,
                status="offline",
                connection_config={},
                capabilities={},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            db.add(printer)
            imported += 1

        except Exception as e:
            errors.append({
                "row": str(row_num),
                "error": str(e)
            })

    if imported > 0:
        db.commit()
        logger.info(f"Imported {imported} printers from CSV")

    return PrinterCSVImportResult(
        total_rows=total_rows,
        imported=imported,
        skipped=skipped,
        errors=errors,
    )

