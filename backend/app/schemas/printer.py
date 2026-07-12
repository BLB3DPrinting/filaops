"""
Printer Pydantic Schemas

Supports brand-agnostic printer management for:
- BambuLab (X1C, P1S, A1, etc.)
- Klipper/Moonraker
- OctoPrint
- Prusa Connect
- Generic/Manual entry
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ============================================================================
# Enums
# ============================================================================

class PrinterBrand(str, Enum):
    """Supported printer brands"""
    BAMBULAB = "bambulab"
    KLIPPER = "klipper"
    OCTOPRINT = "octoprint"
    PRUSA = "prusa"
    CREALITY = "creality"
    GENERIC = "generic"


class PrinterStatus(str, Enum):
    """Printer status states"""
    OFFLINE = "offline"
    IDLE = "idle"
    PRINTING = "printing"
    PAUSED = "paused"
    ERROR = "error"
    MAINTENANCE = "maintenance"


# ============================================================================
# Printer Capabilities Schema
# ============================================================================

class PrinterCapabilities(BaseModel):
    """Printer capabilities/features"""
    bed_size_x: Optional[float] = Field(None, description="Bed width in mm")
    bed_size_y: Optional[float] = Field(None, description="Bed depth in mm")
    bed_size_z: Optional[float] = Field(None, description="Max height in mm")
    heated_bed: Optional[bool] = Field(True, description="Has heated bed")
    enclosure: Optional[bool] = Field(False, description="Has enclosure")
    ams_slots: Optional[int] = Field(0, description="Number of AMS/multi-material slots")
    camera: Optional[bool] = Field(False, description="Has camera")
    max_temp_hotend: Optional[int] = Field(None, description="Max hotend temperature")
    max_temp_bed: Optional[int] = Field(None, description="Max bed temperature")

    # Canonical capability fields (WS1) — unit-suffixed names, mirrored from
    # the printer-model catalog (services/printer_discovery/models.py).
    bed_width_mm: Optional[int] = Field(None, description="Bed width in mm")
    bed_depth_mm: Optional[int] = Field(None, description="Bed depth in mm")
    bed_height_mm: Optional[int] = Field(None, description="Max height in mm")
    has_enclosure: Optional[bool] = Field(None, description="Has enclosure")
    has_active_chamber_heat: Optional[bool] = Field(
        None, description="Has an active chamber heater (passive-warm enclosure = False)"
    )
    chamber_temp_max_c: Optional[int] = Field(None, description="Max chamber temperature in °C")
    nozzle_count: Optional[int] = Field(None, description="Number of nozzles/toolheads")
    nozzle_temp_max_c: Optional[int] = Field(None, description="Max nozzle temperature in °C")
    has_ams_support: Optional[bool] = Field(None, description="AMS / CFS / MMU compatible")
    max_material_slots: Optional[int] = Field(
        None, description="Max material slots with full multi-material expansion"
    )
    dual_mode_bed_width_mm: Optional[int] = Field(
        None, description="Usable bed width in dual-nozzle mode, in mm"
    )
    discontinued: Optional[bool] = Field(
        None, description="Model no longer sold — UI label/sort hint only, never gates usage"
    )


# ============================================================================
# Connection Configuration Schema
# ============================================================================

class PrinterConnectionConfig(BaseModel):
    """Brand-specific connection configuration"""
    # Common fields
    port: Optional[int] = Field(None, description="Port number for API")
    api_key: Optional[str] = Field(None, description="API key if required")

    # BambuLab specific
    access_code: Optional[str] = Field(None, description="BambuLab access code")

    # Generic
    protocol: Optional[str] = Field(None, description="Connection protocol (http, mqtt, etc.)")


# ============================================================================
# Printer CRUD Schemas
# ============================================================================

class PrinterBase(BaseModel):
    """Base printer fields"""
    code: str = Field(..., min_length=1, max_length=50, description="Unique printer code")
    name: str = Field(..., min_length=1, max_length=255, description="Printer name")
    model: str = Field(..., min_length=1, max_length=100, description="Printer model")
    brand: PrinterBrand = Field(PrinterBrand.GENERIC, description="Printer brand")
    serial_number: Optional[str] = Field(None, max_length=100)
    ip_address: Optional[str] = Field(None, max_length=50)
    mqtt_topic: Optional[str] = Field(None, max_length=255)
    location: Optional[str] = Field(None, max_length=255)
    work_center_id: Optional[int] = Field(None, description="Associated work center")
    notes: Optional[str] = Field(None, description="Operator notes")
    active: Optional[bool] = Field(True)


class PrinterCreate(PrinterBase):
    """Create a new printer"""
    connection_config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    capabilities: Optional[Dict[str, Any]] = Field(default_factory=dict)


class PrinterUpdate(BaseModel):
    """Update an existing printer"""
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    model: Optional[str] = Field(None, min_length=1, max_length=100)
    brand: Optional[PrinterBrand] = None
    serial_number: Optional[str] = Field(None, max_length=100)
    ip_address: Optional[str] = Field(None, max_length=50)
    mqtt_topic: Optional[str] = Field(None, max_length=255)
    location: Optional[str] = Field(None, max_length=255)
    work_center_id: Optional[int] = None
    notes: Optional[str] = None
    active: Optional[bool] = None
    connection_config: Optional[Dict[str, Any]] = None
    capabilities: Optional[Dict[str, Any]] = None


class PrinterResponse(PrinterBase):
    """Printer response with computed fields"""
    id: int
    status: PrinterStatus = PrinterStatus.OFFLINE
    connection_config: Dict[str, Any] = {}
    capabilities: Dict[str, Any] = {}
    last_seen: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Computed properties
    is_online: bool = False
    has_ams: bool = False
    has_camera: bool = False

    class Config:
        from_attributes = True


class PrinterListResponse(BaseModel):
    """Paginated list of printers"""
    items: List[PrinterResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================================
# Discovery Schemas
# ============================================================================

class DiscoveredPrinterResponse(BaseModel):
    """A printer found during network discovery"""
    brand: PrinterBrand
    model: str
    name: str
    ip_address: str
    serial_number: Optional[str] = None
    capabilities: Dict[str, Any] = {}
    suggested_code: str
    already_registered: bool = False


class DiscoveryResultResponse(BaseModel):
    """Result of a discovery scan"""
    printers: List[DiscoveredPrinterResponse]
    scan_duration_seconds: float
    errors: List[str] = []


class DiscoveryRequest(BaseModel):
    """Request to start printer discovery"""
    brands: Optional[List[PrinterBrand]] = Field(
        None,
        description="Brands to scan for (None = all)"
    )
    timeout_seconds: float = Field(5.0, ge=1.0, le=30.0)


# ============================================================================
# Bulk Import Schemas
# ============================================================================

class PrinterCSVRow(BaseModel):
    """Single row from CSV import"""
    code: str
    name: str
    model: str
    brand: Optional[str] = "generic"
    serial_number: Optional[str] = None
    ip_address: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None


class PrinterCSVImportRequest(BaseModel):
    """Request to import printers from CSV"""
    csv_data: str = Field(..., description="CSV content as string")
    skip_duplicates: bool = Field(True, description="Skip rows with existing codes")


class PrinterCSVImportResult(BaseModel):
    """Result of CSV import"""
    total_rows: int
    imported: int
    skipped: int
    errors: List[Dict[str, str]] = []


# ============================================================================
# Status Update Schemas
# ============================================================================

class PrinterStatusUpdate(BaseModel):
    """Update printer status"""
    status: PrinterStatus


class PrinterConnectionTest(BaseModel):
    """Test connection to a printer"""
    ip_address: str
    brand: PrinterBrand
    connection_config: Optional[Dict[str, Any]] = {}


class PrinterConnectionTestResult(BaseModel):
    """Result of connection test"""
    success: bool
    message: Optional[str] = None
    response_time_ms: Optional[float] = None


# ============================================================================
# Brand Info Schemas
# ============================================================================

class PrinterModelInfo(BaseModel):
    """Information about a printer model"""
    value: str
    label: str
    capabilities: Optional[Dict[str, Any]] = None
    # No longer sold. UI metadata only — the client labels these
    # "(discontinued)" and sorts them last; they stay fully selectable
    # because owned fleet hardware outlives retail availability.
    discontinued: bool = False


class PrinterBrandInfo(BaseModel):
    """Information about a supported brand"""
    code: str
    name: str
    supports_discovery: bool
    models: List[PrinterModelInfo]
    connection_fields: List[Dict[str, Any]]
