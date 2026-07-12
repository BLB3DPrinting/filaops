"""
Printer Discovery Models

Data models for discovered printers and their capabilities.
"""

from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, model_validator


class PrinterBrand(str, Enum):
    """Supported printer brands"""
    BAMBULAB = "bambulab"
    KLIPPER = "klipper"
    OCTOPRINT = "octoprint"
    PRUSA = "prusa"
    CREALITY = "creality"
    GENERIC = "generic"


class PrinterStatus(str, Enum):
    """Printer operational status"""
    OFFLINE = "offline"
    IDLE = "idle"
    PRINTING = "printing"
    PAUSED = "paused"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class ConnectionType(str, Enum):
    """How we connect to the printer"""
    LOCAL = "local"      # Direct IP/network connection
    CLOUD = "cloud"      # Via manufacturer's cloud API
    BOTH = "both"        # Supports both local and cloud


# Exact-synonym field pairs mirrored by PrinterCapabilities._sync_legacy_aliases:
# (legacy_name, canonical_name, legacy_from_canonical, canonical_from_legacy).
# Only exact synonyms are mirrored. Deliberately NOT mirrored:
#   has_heated_chamber (loose "warm/enclosed chamber") vs
#   has_active_chamber_heat (strict: machine has a chamber HEATER) — an X1C is
#   enclosed-warm but has no chamber heater, so the pair is not a synonym.
#   filament_count ("typical loaded filaments", e.g. 4 with one AMS) vs
#   max_material_slots ("max with full expansion", e.g. 24 on H2S).
_CAPABILITY_FIELD_ALIASES: Tuple[Tuple[str, str, Callable, Callable], ...] = (
    ("bed_width", "bed_width_mm", float, lambda v: int(round(v))),
    ("bed_depth", "bed_depth_mm", float, lambda v: int(round(v))),
    ("bed_height", "bed_height_mm", float, lambda v: int(round(v))),
    ("has_ams", "has_ams_support", bool, bool),
    ("max_nozzle_temp", "nozzle_temp_max_c", int, int),
)


class PrinterCapabilities(BaseModel):
    """
    Printer hardware capabilities.

    Canonical fields carry units in their names (dims in mm, temps in °C).
    The unsuffixed legacy fields predate that rule and are kept so stored
    JSON blobs and the Klipper capability probe keep working; the
    `_sync_legacy_aliases` validator mirrors values both ways, so callers
    using either naming generation get a fully-populated model.
    """

    # --- Canonical capability fields (WS1 spec §1.1) ---
    bed_width_mm: Optional[int] = None
    bed_depth_mm: Optional[int] = None
    bed_height_mm: Optional[int] = None
    has_enclosure: bool = False
    has_active_chamber_heat: bool = False   # passive-warm ≠ actively heated
    chamber_temp_max_c: Optional[int] = None
    nozzle_count: int = 1
    nozzle_temp_max_c: Optional[int] = None
    has_ams_support: bool = False           # AMS / CFS / MMU compatible
    max_material_slots: Optional[int] = None  # 24 (H2S), 5 (MMU3), …
    dual_mode_bed_width_mm: Optional[int] = None  # dual-nozzle usable X width
    # No longer sold. UI metadata only: labeled "(discontinued)" and sorted
    # last in the creation dropdown — never gates connectivity or lookups.
    discontinued: bool = False

    # --- Legacy fields (pre-WS1 names) ---
    # Build volume (mm)
    bed_width: Optional[float] = None
    bed_depth: Optional[float] = None
    bed_height: Optional[float] = None

    # Features
    has_heated_bed: bool = True
    has_heated_chamber: bool = False

    # Multi-material
    has_ams: bool = False  # BambuLab AMS
    has_mmu: bool = False  # Prusa MMU
    filament_count: int = 1  # Number of filaments (1, 4, etc.)

    # Camera
    has_camera: bool = False
    has_lidar: bool = False

    # Max temperatures
    max_nozzle_temp: Optional[int] = None
    max_bed_temp: Optional[int] = None

    # Nozzle
    nozzle_diameter: float = 0.4

    @model_validator(mode="after")
    def _sync_legacy_aliases(self) -> "PrinterCapabilities":
        """
        Mirror exact-synonym fields between legacy and canonical names.

        Only fields the caller did NOT set are backfilled, so an explicit
        value always wins regardless of which naming generation the caller
        used. Both-set and neither-set pairs are left untouched.
        """
        provided = frozenset(self.model_fields_set)
        for legacy, canonical, from_canonical, from_legacy in _CAPABILITY_FIELD_ALIASES:
            if canonical in provided and legacy not in provided:
                value = getattr(self, canonical)
                if value is not None:
                    setattr(self, legacy, from_canonical(value))
            elif legacy in provided and canonical not in provided:
                value = getattr(self, legacy)
                if value is not None:
                    setattr(self, canonical, from_legacy(value))
        return self


class PrinterConnectionConfig(BaseModel):
    """Connection configuration for a printer"""
    # Network
    ip_address: Optional[str] = None
    port: Optional[int] = None

    # Authentication
    access_code: Optional[str] = None  # BambuLab access code
    api_key: Optional[str] = None      # OctoPrint/Klipper API key

    # Cloud credentials (stored separately, referenced by ID)
    cloud_account_id: Optional[int] = None

    # MQTT (for BambuLab)
    mqtt_topic: Optional[str] = None

    # Serial connection (for some printers)
    serial_port: Optional[str] = None
    baud_rate: Optional[int] = None


class DiscoveredPrinter(BaseModel):
    """
    A printer discovered on the network or via cloud API.

    This is the unified representation before being saved to the database.
    """
    # Identification
    brand: PrinterBrand
    model: str
    name: str
    serial_number: Optional[str] = None

    # Connection info
    connection_type: ConnectionType = ConnectionType.LOCAL
    ip_address: Optional[str] = None

    # Capabilities (auto-detected or from known models)
    capabilities: PrinterCapabilities = Field(default_factory=PrinterCapabilities)

    # Connection config
    connection_config: PrinterConnectionConfig = Field(default_factory=PrinterConnectionConfig)

    # Discovery metadata
    discovered_via: str = "manual"  # "ssdp", "mdns", "cloud", "manual"
    firmware_version: Optional[str] = None

    # Brand-specific raw data (for debugging/advanced features)
    raw_data: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


# Known printer models with their capabilities.
#
# VERIFY protocol (SPEC-printer-catalog-and-live-bridge Rev B §1.5): every row below was
# checked against the official manufacturer spec page on 2026-07-11. Source
# per model (secondary URL where the primary page omits a value):
#
#   bambulab:H2D        https://bambulab.com/en-us/h2d/tech-specs
#                       (24 slots: https://us.store.bambulab.com/products/h2d)
#   bambulab:H2D Pro    https://bambulab.com/en-us/h2d-pro/tech-specs
#                       (24 slots: https://us.store.bambulab.com/products/h2d-pro)
#   bambulab:H2S        https://bambulab.com/en-us/h2s/tech-specs
#   bambulab:X2D        https://bambulab.com/en/x2d/specs
#                       (slots: https://wiki.bambulab.com/en/x2d/manual/x2d-faq —
#                       "4 AMS 2 Pro and 8 AMS HT units (12 units total, 24 slots)";
#                       dual-hotend mode enables 25-color printing)
#   bambulab:P2S        https://bambulab.com/en-us/p2s/specs
#                       (chamber + slots: https://wiki.bambulab.com/en/p2s/manual/p2s-faq —
#                       "does not have an active chamber temperature function";
#                       "8 units with 20 slots")
#   bambulab:A2L        https://bambulab.com/en/a2l/specs (AMS lite serial → 19 slots)
#   bambulab:P1S        https://us.store.bambulab.com/products/p1s
#   bambulab:P1P        https://bambulab.com/en-us/p1 (P1 series; P1P no longer sold —
#                       store page redirects to P1S)
#   bambulab:A1         https://bambulab.com/en/a1/tech-specs
#   bambulab:A1 Mini    https://bambulab.com/en-us/a1-mini/tech-specs
#   bambulab:X1C        https://public-cdn.bambulab.com/store/bambulab-X1-carbon-tech-specs.pdf
#                       + https://bambulab.com/en-us/x1 ("16 Multi Color", "Parallel 4*4";
#                       chamber has a regulator FAN only — no heater, so no
#                       chamber_temp_max_c despite the page's passive "60℃" figure)
#   bambulab:X1         https://bambulab.com/en/x1 (X1 column of the X1-series table)
#   bambulab:X1E        https://bambulab.com/en-us/x1e (chamber 60 °C active, 320 °C hotend)
#                       + https://wiki.bambulab.com/en/x1/manual/x1e-faq (build volume)
#   prusa:MK4S          https://www.prusa3d.com/product/original-prusa-mk4s-3d-printer/
#   prusa:MK4           https://blog.prusa3d.com/announcing-original-prusa-mk4_76585/
#                       (spec table: 300 °C hotend; product URL now serves MK4S)
#   prusa:MK3S+         https://www.prusa3d.com/product/original-prusa-i3-mk3s-10th-anniversary-edition-3d-printer/
#                       (identical MK3S+ hardware; original product page now serves MK4S)
#   prusa:CORE One      https://www.prusa3d.com/product/prusa-core-one/ +
#                       https://www.prusa3d.com/downloads/manual/prusa3d_manual_coreone_101_en.pdf
#                       (chamber heated to 55 °C via managed heatbed convection —
#                       counted as active: settable, closed-loop; see field note)
#   prusa:CORE One L    https://www.prusa3d.com/product/prusa-core-one-l-2/
#                       (300×300×330, 60 °C active-convection chamber, INDX → 8 slots)
#   prusa:Mini+         https://cdn.prusa3d.com/en/product/original-prusa-mini/
#   prusa:XL            https://www.prusa3d.com/product/original-prusa-xl-2/
#                       (semi-open frame — official page lists no enclosure;
#                       5 toolheads = 5 material slots without an AMS-style unit)
#   creality:K2 Plus    https://www.creality.com/products/creality-k2-plus-cfs-combo
#                       (350×350×350 confirmed on official page — resolves the
#                       350³-vs-350×300×300 conflict in secondary sources)
#   creality:K2 Pro     https://store.creality.com/products/k2-pro-combo-3d-printer
#   creality:K2 SE      https://www.creality.com/products/k2-se
#   creality:K1C        https://www.creality.com/support/k1c-carbon-3d-printer
#   creality:K1         https://www.creality.com/support/creality-k1-3d-printer
#   creality:K1 Max     https://www.creality.com/support/creality-k1-max-3d-printer
#   (K1/K1C/K1 Max CFS: https://www.creality.com/products/cfs-c-smart-filament-system —
#   "Compatible Models: K1 Max 2025 / K1C 2025 / K1 Max / K1C / K1 / K1 SE",
#   "Number of Filament Slots: 4", "Multiple CFS-C Units: Not supported")
#   creality:Ender 3 V3     https://www.creality.com/support/creality-ender-3-v3
#   creality:Ender 3 V3 KE  https://www.creality.com/support/creality-ender-3-v3-ke
#
# Deliberately omitted (could not verify against official pages — do not add
# without a source): bambulab:H2C (official page readings conflict on nozzle
# count and single-nozzle build volume).
#
# `has_active_chamber_heat` = closed-loop, SETTABLE chamber temperature
# (dedicated heater or managed heatbed convection). Passively-warmed
# enclosures (X1C/X1, P1S, P2S, K1 family) are False even where marketing
# quotes a chamber figure.
KNOWN_PRINTER_MODELS: Dict[str, Dict[str, Any]] = {
    # ---- Bambu Lab — current lineup ----
    "bambulab:H2D": {
        "brand": PrinterBrand.BAMBULAB,
        "model": "H2D",
        "capabilities": PrinterCapabilities(
            bed_width_mm=325, bed_depth_mm=320, bed_height_mm=325,
            dual_mode_bed_width_mm=300,
            has_enclosure=True, has_active_chamber_heat=True, chamber_temp_max_c=65,
            nozzle_count=2, nozzle_temp_max_c=350,
            has_ams_support=True, max_material_slots=24,
            has_heated_chamber=True, filament_count=4,
        ),
    },
    "bambulab:H2D Pro": {
        "brand": PrinterBrand.BAMBULAB,
        "model": "H2D Pro",
        "capabilities": PrinterCapabilities(
            bed_width_mm=325, bed_depth_mm=320, bed_height_mm=325,
            dual_mode_bed_width_mm=300,
            has_enclosure=True, has_active_chamber_heat=True, chamber_temp_max_c=65,
            nozzle_count=2, nozzle_temp_max_c=350,
            has_ams_support=True, max_material_slots=24,
            has_heated_chamber=True, filament_count=4,
        ),
    },
    "bambulab:H2S": {
        "brand": PrinterBrand.BAMBULAB,
        "model": "H2S",
        "capabilities": PrinterCapabilities(
            bed_width_mm=340, bed_depth_mm=320, bed_height_mm=340,
            has_enclosure=True, has_active_chamber_heat=True, chamber_temp_max_c=65,
            nozzle_count=1, nozzle_temp_max_c=350,
            has_ams_support=True, max_material_slots=24,
            has_heated_chamber=True, filament_count=4,
        ),
    },
    "bambulab:X2D": {
        "brand": PrinterBrand.BAMBULAB,
        "model": "X2D",
        "capabilities": PrinterCapabilities(
            bed_width_mm=256, bed_depth_mm=256, bed_height_mm=260,
            # Official dual-nozzle usable width is 235.5 mm — floored, never
            # over-promise usable envelope.
            dual_mode_bed_width_mm=235,
            has_enclosure=True, has_active_chamber_heat=True, chamber_temp_max_c=65,
            nozzle_count=2, nozzle_temp_max_c=300,
            has_ams_support=True, max_material_slots=24,
            has_heated_chamber=True, filament_count=4,
        ),
    },
    "bambulab:P2S": {
        "brand": PrinterBrand.BAMBULAB,
        "model": "P2S",
        "capabilities": PrinterCapabilities(
            bed_width_mm=256, bed_depth_mm=256, bed_height_mm=256,
            has_enclosure=True, has_active_chamber_heat=False,
            nozzle_count=1, nozzle_temp_max_c=300,
            has_ams_support=True, max_material_slots=20,
            filament_count=4,
        ),
    },
    "bambulab:A2L": {
        "brand": PrinterBrand.BAMBULAB,
        "model": "A2L",
        "capabilities": PrinterCapabilities(
            bed_width_mm=330, bed_depth_mm=320, bed_height_mm=325,
            has_enclosure=False,
            nozzle_count=1, nozzle_temp_max_c=300,
            has_ams_support=True, max_material_slots=19,
            filament_count=4,
        ),
    },
    "bambulab:P1S": {
        "brand": PrinterBrand.BAMBULAB,
        "model": "P1S",
        "capabilities": PrinterCapabilities(
            bed_width_mm=256, bed_depth_mm=256, bed_height_mm=256,
            has_enclosure=True, has_active_chamber_heat=False,
            nozzle_count=1, nozzle_temp_max_c=300,
            has_ams_support=True, max_material_slots=16,
            filament_count=4, has_camera=True, max_bed_temp=110,
        ),
    },
    "bambulab:P1P": {
        "brand": PrinterBrand.BAMBULAB,
        "model": "P1P",
        "capabilities": PrinterCapabilities(
            bed_width_mm=256, bed_depth_mm=256, bed_height_mm=256,
            has_enclosure=False, has_active_chamber_heat=False,
            nozzle_count=1, nozzle_temp_max_c=300,
            # AMS support carried over from the pre-refresh catalog; a P1P-
            # specific max-slot figure was not verifiable (model delisted,
            # store page redirects to P1S) so no slot count is claimed.
            has_ams_support=True,
            filament_count=4, has_camera=True, max_bed_temp=110,
        ),
    },
    "bambulab:A1": {
        "brand": PrinterBrand.BAMBULAB,
        "model": "A1",
        "capabilities": PrinterCapabilities(
            bed_width_mm=256, bed_depth_mm=256, bed_height_mm=256,
            has_enclosure=False, has_active_chamber_heat=False,
            nozzle_count=1, nozzle_temp_max_c=300,
            has_ams_support=True, max_material_slots=4,  # AMS lite, no chaining
            filament_count=4, has_camera=True, max_bed_temp=100,
        ),
    },
    "bambulab:A1 Mini": {
        "brand": PrinterBrand.BAMBULAB,
        "model": "A1 Mini",
        "capabilities": PrinterCapabilities(
            bed_width_mm=180, bed_depth_mm=180, bed_height_mm=180,
            has_enclosure=False, has_active_chamber_heat=False,
            nozzle_count=1, nozzle_temp_max_c=300,
            has_ams_support=True, max_material_slots=4,  # AMS lite, no chaining
            filament_count=4, has_camera=True, max_bed_temp=80,
        ),
    },
    # ---- Bambu Lab — discontinued (X1 series delisted Apr 2026) ----
    "bambulab:X1C": {
        "brand": PrinterBrand.BAMBULAB,
        "model": "X1 Carbon",
        "capabilities": PrinterCapabilities(
            bed_width_mm=256, bed_depth_mm=256, bed_height_mm=256,
            has_enclosure=True, has_active_chamber_heat=False,
            nozzle_count=1, nozzle_temp_max_c=300,
            has_ams_support=True, max_material_slots=16,
            discontinued=True,
            has_heated_chamber=True,  # legacy loose flag: warm enclosed chamber
            filament_count=4, has_camera=True, has_lidar=True, max_bed_temp=110,
        ),
    },
    "bambulab:X1": {
        "brand": PrinterBrand.BAMBULAB,
        "model": "X1",
        "capabilities": PrinterCapabilities(
            bed_width_mm=256, bed_depth_mm=256, bed_height_mm=256,
            has_enclosure=True, has_active_chamber_heat=False,
            nozzle_count=1, nozzle_temp_max_c=300,
            has_ams_support=True, max_material_slots=16,
            discontinued=True,
            has_heated_chamber=True,  # legacy loose flag: warm enclosed chamber
            filament_count=4, has_camera=True, has_lidar=True, max_bed_temp=110,
        ),
    },
    "bambulab:X1E": {
        "brand": PrinterBrand.BAMBULAB,
        "model": "X1E",
        "capabilities": PrinterCapabilities(
            bed_width_mm=256, bed_depth_mm=256, bed_height_mm=256,
            has_enclosure=True, has_active_chamber_heat=True, chamber_temp_max_c=60,
            nozzle_count=1, nozzle_temp_max_c=320,
            has_ams_support=True, max_material_slots=16,
            discontinued=True,
            has_heated_chamber=True,
            filament_count=4, has_camera=True,
        ),
    },
    # ---- Prusa ----
    "prusa:MK4S": {
        "brand": PrinterBrand.PRUSA,
        "model": "MK4S",
        "capabilities": PrinterCapabilities(
            bed_width_mm=250, bed_depth_mm=210, bed_height_mm=220,
            has_enclosure=False,
            nozzle_count=1, nozzle_temp_max_c=290,
            has_ams_support=True, max_material_slots=5,  # MMU3
            has_mmu=True, filament_count=5, max_bed_temp=120,
        ),
    },
    "prusa:MK4": {
        "brand": PrinterBrand.PRUSA,
        "model": "MK4",
        "capabilities": PrinterCapabilities(
            bed_width_mm=250, bed_depth_mm=210, bed_height_mm=220,
            has_enclosure=False,
            nozzle_count=1, nozzle_temp_max_c=300,
            has_ams_support=True, max_material_slots=5,  # MMU3
            has_mmu=True, filament_count=5, max_bed_temp=120,
        ),
    },
    "prusa:CORE One": {
        "brand": PrinterBrand.PRUSA,
        "model": "CORE One",
        "capabilities": PrinterCapabilities(
            bed_width_mm=250, bed_depth_mm=220, bed_height_mm=270,
            has_enclosure=True, has_active_chamber_heat=True, chamber_temp_max_c=55,
            nozzle_count=1, nozzle_temp_max_c=290,
            has_ams_support=True, max_material_slots=5,  # MMU3
            has_heated_chamber=True,
            has_mmu=True, filament_count=5, max_bed_temp=120,
        ),
    },
    "prusa:CORE One L": {
        "brand": PrinterBrand.PRUSA,
        "model": "CORE One L",
        "capabilities": PrinterCapabilities(
            bed_width_mm=300, bed_depth_mm=300, bed_height_mm=330,
            has_enclosure=True, has_active_chamber_heat=True, chamber_temp_max_c=60,
            nozzle_count=1, nozzle_temp_max_c=290,
            has_ams_support=True, max_material_slots=8,  # optional INDX toolchanger
            has_heated_chamber=True,
            filament_count=8, max_bed_temp=120,
        ),
    },
    "prusa:Mini+": {
        "brand": PrinterBrand.PRUSA,
        "model": "MINI+",
        "capabilities": PrinterCapabilities(
            bed_width_mm=180, bed_depth_mm=180, bed_height_mm=180,
            has_enclosure=False,
            nozzle_count=1, nozzle_temp_max_c=280,
        ),
    },
    "prusa:XL": {
        "brand": PrinterBrand.PRUSA,
        "model": "XL",
        "capabilities": PrinterCapabilities(
            bed_width_mm=360, bed_depth_mm=360, bed_height_mm=360,
            has_enclosure=False,  # semi-open frame per official page
            nozzle_count=5,  # up to 5 toolheads
            nozzle_temp_max_c=290,
            max_material_slots=5,  # via toolheads, not an AMS-style unit
            filament_count=5, max_bed_temp=120,
        ),
    },
    "prusa:MK3S+": {
        "brand": PrinterBrand.PRUSA,
        "model": "MK3S+",
        "capabilities": PrinterCapabilities(
            bed_width_mm=250, bed_depth_mm=210, bed_height_mm=210,
            has_enclosure=False,
            nozzle_count=1, nozzle_temp_max_c=300,
            has_ams_support=True, max_material_slots=5,  # MMU3
            discontinued=True,
            has_mmu=True, filament_count=5, max_bed_temp=120,
        ),
    },
    # ---- Creality ----
    "creality:K2 Plus": {
        "brand": PrinterBrand.CREALITY,
        "model": "K2 Plus",
        "capabilities": PrinterCapabilities(
            bed_width_mm=350, bed_depth_mm=350, bed_height_mm=350,
            has_enclosure=True, has_active_chamber_heat=True, chamber_temp_max_c=60,
            nozzle_count=1, nozzle_temp_max_c=350,
            has_ams_support=True, max_material_slots=16,  # 4× CFS chained
            has_heated_chamber=True, filament_count=4,
        ),
    },
    "creality:K2 Pro": {
        "brand": PrinterBrand.CREALITY,
        "model": "K2 Pro",
        "capabilities": PrinterCapabilities(
            bed_width_mm=300, bed_depth_mm=300, bed_height_mm=300,
            has_enclosure=True, has_active_chamber_heat=True, chamber_temp_max_c=60,
            nozzle_count=1, nozzle_temp_max_c=300,
            has_ams_support=True, max_material_slots=16,  # 4× CFS chained
            has_heated_chamber=True, filament_count=4,
        ),
    },
    "creality:K2 SE": {
        "brand": PrinterBrand.CREALITY,
        "model": "K2 SE",
        "capabilities": PrinterCapabilities(
            bed_width_mm=220, bed_depth_mm=215, bed_height_mm=245,
            has_enclosure=False,
            nozzle_count=1, nozzle_temp_max_c=300,
            has_ams_support=True, max_material_slots=16,  # 4× CFS chained
            filament_count=4,
        ),
    },
    "creality:K1C": {
        "brand": PrinterBrand.CREALITY,
        "model": "K1C",
        "capabilities": PrinterCapabilities(
            bed_width_mm=220, bed_depth_mm=220, bed_height_mm=250,
            has_enclosure=True, has_active_chamber_heat=False,
            nozzle_count=1, nozzle_temp_max_c=300,
            has_ams_support=True, max_material_slots=4,  # CFS-C, no chaining
            filament_count=4,
        ),
    },
    "creality:K1": {
        "brand": PrinterBrand.CREALITY,
        "model": "K1",
        "capabilities": PrinterCapabilities(
            bed_width_mm=220, bed_depth_mm=220, bed_height_mm=250,
            has_enclosure=True, has_active_chamber_heat=False,
            nozzle_count=1, nozzle_temp_max_c=300,
            has_ams_support=True, max_material_slots=4,  # CFS-C, no chaining
            filament_count=4, has_camera=True, max_bed_temp=100,
        ),
    },
    "creality:K1 Max": {
        "brand": PrinterBrand.CREALITY,
        "model": "K1 Max",
        "capabilities": PrinterCapabilities(
            bed_width_mm=300, bed_depth_mm=300, bed_height_mm=300,
            has_enclosure=True, has_active_chamber_heat=False,
            nozzle_count=1, nozzle_temp_max_c=300,
            has_ams_support=True, max_material_slots=4,  # CFS-C, no chaining
            filament_count=4, has_camera=True, has_lidar=True, max_bed_temp=120,
        ),
    },
    "creality:Ender 3 V3": {
        "brand": PrinterBrand.CREALITY,
        "model": "Ender 3 V3",
        "capabilities": PrinterCapabilities(
            bed_width_mm=220, bed_depth_mm=220, bed_height_mm=250,
            has_enclosure=False,
            nozzle_count=1, nozzle_temp_max_c=300,
            max_bed_temp=100,
        ),
    },
    "creality:Ender 3 V3 KE": {
        "brand": PrinterBrand.CREALITY,
        "model": "Ender 3 V3 KE",
        "capabilities": PrinterCapabilities(
            bed_width_mm=220, bed_depth_mm=220, bed_height_mm=240,
            has_enclosure=False,
            nozzle_count=1, nozzle_temp_max_c=300,
            max_bed_temp=100,
        ),
    },
}


def get_model_capabilities(brand: str, model: str) -> Optional[PrinterCapabilities]:
    """Look up known capabilities for a printer model"""
    key = f"{brand}:{model}"
    if key in KNOWN_PRINTER_MODELS:
        return KNOWN_PRINTER_MODELS[key]["capabilities"]
    return None


def get_brand_model_options(brand: str) -> List[Dict[str, Any]]:
    """
    Dropdown options for a brand, derived from KNOWN_PRINTER_MODELS.

    Returns entries shaped for `/brands/info` model lists:
    {"value", "label", "capabilities", "discontinued"}. Discontinued models
    are INCLUDED with the flag set — the client labels them "(discontinued)"
    and sorts them after the current lineup; they stay selectable because
    owned fleet hardware outlives retail availability.
    """
    prefix = f"{brand}:"
    options: List[Dict[str, Any]] = []
    for key, entry in KNOWN_PRINTER_MODELS.items():
        if not key.startswith(prefix):
            continue
        capabilities: PrinterCapabilities = entry["capabilities"]
        options.append({
            "value": key[len(prefix):],
            "label": entry["model"],
            "capabilities": capabilities.model_dump(),
            "discontinued": capabilities.discontinued,
        })
    return options
