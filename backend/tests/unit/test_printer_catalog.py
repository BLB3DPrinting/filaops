"""
Tests for the printer-model catalog (services/printer_discovery/models.py).

WS1 acceptance (SPEC-printer-catalog-and-live-bridge Rev B §1.7):
- Capability lookup correct for every catalog key.
- Unknown model → default PrinterCapabilities() (existing fallback preserved).
- Discontinued labeled in creation dropdowns (never hidden or gated),
  included in lookups.
- Catalog module coverage 100%.
"""
import pytest

from app.services.printer_discovery.models import (
    KNOWN_PRINTER_MODELS,
    PrinterBrand,
    PrinterCapabilities,
    get_brand_model_options,
    get_model_capabilities,
)


# =============================================================================
# PrinterCapabilities defaults + legacy/canonical alias mirroring
# =============================================================================

class TestPrinterCapabilitiesDefaults:
    """Zero-arg construction must stay valid — it is the unknown-model fallback."""

    def test_zero_arg_constructor_defaults(self):
        caps = PrinterCapabilities()
        # canonical fields
        assert caps.bed_width_mm is None
        assert caps.bed_depth_mm is None
        assert caps.bed_height_mm is None
        assert caps.has_enclosure is False
        assert caps.has_active_chamber_heat is False
        assert caps.chamber_temp_max_c is None
        assert caps.nozzle_count == 1
        assert caps.nozzle_temp_max_c is None
        assert caps.has_ams_support is False
        assert caps.max_material_slots is None
        assert caps.dual_mode_bed_width_mm is None
        assert caps.discontinued is False
        # legacy fields
        assert caps.bed_width is None
        assert caps.has_heated_bed is True
        assert caps.has_heated_chamber is False
        assert caps.has_ams is False
        assert caps.has_mmu is False
        assert caps.filament_count == 1
        assert caps.has_camera is False
        assert caps.has_lidar is False
        assert caps.max_nozzle_temp is None
        assert caps.max_bed_temp is None
        assert caps.nozzle_diameter == 0.4


class TestCapabilityAliasMirroring:
    """_sync_legacy_aliases mirrors exact-synonym pairs both ways."""

    def test_canonical_dims_backfill_legacy(self):
        caps = PrinterCapabilities(bed_width_mm=256, bed_depth_mm=250, bed_height_mm=260)
        assert caps.bed_width == 256.0
        assert caps.bed_depth == 250.0
        assert caps.bed_height == 260.0
        assert isinstance(caps.bed_width, float)

    def test_legacy_dims_backfill_canonical(self):
        # Klipper probe constructs with legacy float names
        caps = PrinterCapabilities(bed_width=235.0, bed_depth=235.4, bed_height=249.6)
        assert caps.bed_width_mm == 235
        assert caps.bed_depth_mm == 235
        assert caps.bed_height_mm == 250  # rounded, not truncated

    def test_canonical_temp_backfills_legacy(self):
        caps = PrinterCapabilities(nozzle_temp_max_c=350)
        assert caps.max_nozzle_temp == 350

    def test_legacy_temp_backfills_canonical(self):
        caps = PrinterCapabilities(max_nozzle_temp=300)
        assert caps.nozzle_temp_max_c == 300

    def test_ams_flag_mirrors_both_ways(self):
        assert PrinterCapabilities(has_ams_support=True).has_ams is True
        assert PrinterCapabilities(has_ams=True).has_ams_support is True

    def test_explicit_values_never_clobbered(self):
        # Both generations set → caller wins on both, no mirroring
        caps = PrinterCapabilities(bed_width_mm=256, bed_width=999.0)
        assert caps.bed_width_mm == 256
        assert caps.bed_width == 999.0

    def test_none_values_do_not_mirror(self):
        caps = PrinterCapabilities(bed_width_mm=None)
        assert caps.bed_width is None
        caps = PrinterCapabilities(bed_width=None)
        assert caps.bed_width_mm is None

    def test_chamber_semantics_not_mirrored(self):
        # has_heated_chamber (loose) and has_active_chamber_heat (strict)
        # are deliberately independent: enclosed-warm ≠ chamber heater.
        caps = PrinterCapabilities(has_heated_chamber=True)
        assert caps.has_active_chamber_heat is False
        caps = PrinterCapabilities(has_active_chamber_heat=True)
        assert caps.has_heated_chamber is False

    def test_slot_semantics_not_mirrored(self):
        # filament_count (typical loadout) ≠ max_material_slots (max expansion)
        caps = PrinterCapabilities(filament_count=4)
        assert caps.max_material_slots is None
        caps = PrinterCapabilities(max_material_slots=24)
        assert caps.filament_count == 1


# =============================================================================
# Catalog lookups
# =============================================================================

class TestModelCapabilityLookup:
    """get_model_capabilities: correct for every key, None for unknown."""

    @pytest.mark.parametrize("key", sorted(KNOWN_PRINTER_MODELS.keys()))
    def test_every_catalog_key_resolves(self, key):
        brand, _, model = key.partition(":")
        caps = get_model_capabilities(brand, model)
        assert caps is KNOWN_PRINTER_MODELS[key]["capabilities"]

    def test_unknown_model_returns_none(self):
        assert get_model_capabilities("bambulab", "NotARealPrinter") is None

    def test_unknown_brand_returns_none(self):
        assert get_model_capabilities("madeupbrand", "X1C") is None

    def test_unknown_model_fallback_is_default_capabilities(self):
        # The adapters fall back to PrinterCapabilities() when lookup misses —
        # that zero-arg construction must remain valid (see defaults test) and
        # the miss itself must be a clean None, not an exception.
        caps = get_model_capabilities("bambulab", "") or PrinterCapabilities()
        assert caps.discontinued is False
        assert caps.nozzle_count == 1


class TestCatalogIntegrity:
    """Structural invariants over every catalog entry."""

    @pytest.mark.parametrize("key,entry", sorted(KNOWN_PRINTER_MODELS.items()))
    def test_entry_shape(self, key, entry):
        brand, sep, model = key.partition(":")
        assert sep == ":", f"{key} must be 'brand:model'"
        assert model, f"{key} has empty model part"
        assert entry["brand"] == PrinterBrand(brand)
        assert entry["model"], f"{key} missing display label"
        assert isinstance(entry["capabilities"], PrinterCapabilities)

    @pytest.mark.parametrize("key,entry", sorted(KNOWN_PRINTER_MODELS.items()))
    def test_verified_dimensions_present_and_sane(self, key, entry):
        caps = entry["capabilities"]
        assert caps.bed_width_mm is not None, f"{key} missing bed_width_mm"
        assert caps.bed_depth_mm is not None, f"{key} missing bed_depth_mm"
        assert caps.bed_height_mm is not None, f"{key} missing bed_height_mm"
        for dim in (caps.bed_width_mm, caps.bed_depth_mm, caps.bed_height_mm):
            assert 100 <= dim <= 600, f"{key} implausible dim {dim}mm"
        # legacy mirrors populated by the alias validator
        assert caps.bed_width == float(caps.bed_width_mm)
        assert caps.bed_depth == float(caps.bed_depth_mm)
        assert caps.bed_height == float(caps.bed_height_mm)

    @pytest.mark.parametrize("key,entry", sorted(KNOWN_PRINTER_MODELS.items()))
    def test_chamber_heat_implies_enclosure_and_temp(self, key, entry):
        caps = entry["capabilities"]
        if caps.has_active_chamber_heat:
            assert caps.has_enclosure, f"{key}: active chamber heat without enclosure"
            assert caps.chamber_temp_max_c, f"{key}: active chamber heat without max temp"
        if caps.chamber_temp_max_c is not None:
            assert caps.has_active_chamber_heat, (
                f"{key}: chamber temp listed but not flagged actively heated"
            )

    @pytest.mark.parametrize("key,entry", sorted(KNOWN_PRINTER_MODELS.items()))
    def test_dual_mode_width_only_on_multi_nozzle(self, key, entry):
        caps = entry["capabilities"]
        if caps.dual_mode_bed_width_mm is not None:
            assert caps.nozzle_count >= 2, f"{key}: dual-mode width on single-nozzle model"
            assert caps.dual_mode_bed_width_mm <= caps.bed_width_mm

    @pytest.mark.parametrize("key,entry", sorted(KNOWN_PRINTER_MODELS.items()))
    def test_slots_require_multi_material_support(self, key, entry):
        # Slot capacity comes from AMS/CFS/MMU units OR multiple toolheads
        # (Prusa XL: 5 slots via 5 toolheads, no AMS-style unit).
        caps = entry["capabilities"]
        if caps.max_material_slots is not None:
            assert caps.has_ams_support or caps.nozzle_count > 1, (
                f"{key}: slots listed without AMS/CFS/MMU support or multi-toolhead"
            )
            assert caps.max_material_slots >= 1


class TestDiscontinuedFlags:
    """Exactly the models locked in spec §1.2/§1.3 task 5 are discontinued."""

    DISCONTINUED_KEYS = {
        "bambulab:X1C",
        "bambulab:X1",
        "bambulab:X1E",
        "prusa:MK3S+",
    }

    def test_discontinued_set(self):
        flagged = {
            key for key, entry in KNOWN_PRINTER_MODELS.items()
            if entry["capabilities"].discontinued
        }
        assert flagged == self.DISCONTINUED_KEYS

    def test_discontinued_models_still_resolvable(self):
        # Discontinued is UI metadata only (label + sort) — lookups and
        # connectivity for existing fleet rows must keep working.
        caps = get_model_capabilities("bambulab", "X1C")
        assert caps is not None
        assert caps.discontinued is True
        assert caps.bed_width_mm == 256


# =============================================================================
# Dropdown options helper
# =============================================================================

class TestBrandModelOptions:
    """get_brand_model_options feeds /brands/info model lists."""

    def test_bambulab_options_match_catalog(self):
        options = get_brand_model_options("bambulab")
        catalog_keys = {
            k.split(":", 1)[1] for k in KNOWN_PRINTER_MODELS if k.startswith("bambulab:")
        }
        assert {o["value"] for o in options} == catalog_keys

    def test_options_include_discontinued_flag(self):
        options = {o["value"]: o for o in get_brand_model_options("bambulab")}
        assert options["X1C"]["discontinued"] is True
        assert options["P1S"]["discontinued"] is False

    def test_options_carry_capability_dict(self):
        options = get_brand_model_options("bambulab")
        for o in options:
            assert o["label"]
            assert isinstance(o["capabilities"], dict)
            assert o["capabilities"]["bed_width_mm"] is not None

    def test_unknown_brand_returns_empty(self):
        assert get_brand_model_options("madeupbrand") == []

    def test_values_unique_per_brand(self):
        for brand in ("bambulab", "prusa", "creality"):
            options = get_brand_model_options(brand)
            values = [o["value"] for o in options]
            assert len(values) == len(set(values)), f"duplicate model values for {brand}"
