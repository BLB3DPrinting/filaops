import { useRef, useState } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";
import { API_URL } from "../../config/api";
import {
  INTAKE_UNIFIED_FLOW,
  INTAKE_UNIFIED_FLOW_FEATURE,
} from "../../config/intakeFlags";
import SearchableSelect from "../../components/SearchableSelect";
import OperationMaterialModal from "../../components/OperationMaterialModal";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function secondsToHms(s) {
  if (!s) return "0m";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0 && m > 0) return `${h}h ${m}m`;
  if (h > 0) return `${h}h`;
  return `${m}m`;
}

function Spinner() {
  return (
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
  );
}

function StepHeader({ step, total, label }) {
  return (
    <div className="mb-6">
      <div className="flex items-center gap-3 mb-2">
        <span className="text-sm text-gray-400 font-medium">
          Step {step} of {total}
        </span>
        <span className="text-gray-600">·</span>
        <span className="text-sm font-semibold text-white">{label}</span>
      </div>
      <div className="flex gap-1">
        {Array.from({ length: total }).map((_, i) => (
          <div
            key={i}
            className={`h-1 flex-1 rounded-full transition-colors ${
              i < step ? "bg-blue-500" : "bg-gray-700"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

// Human labels for the pre-parse detected file kind.
const PREPARSE_KIND_LABELS = {
  bare: "Bare mesh (will be sliced)",
  raw3mf: "Bambu .3mf (will be sliced)",
  sliced: "Pre-sliced (.gcode.3mf)",
};

/**
 * Pre-parse summary panel (unified flow). Shows the detected file kind, slot
 * count, multi-material badge, and a color swatch per detected slot — rendered
 * on drop, before any slice. Purely informational; renders nothing without a
 * pre-parse payload.
 * @param {object} props
 * @param {object|null} props.preparse - the /preparse response (kind, slots,
 *   slot_count, is_multi_material, model_name), or null.
 * @returns {JSX.Element|null}
 */
function PreParsePanel({ preparse }) {
  if (!preparse) return null;
  const slots = Array.isArray(preparse.slots) ? preparse.slots : [];
  const kindLabel = PREPARSE_KIND_LABELS[preparse.kind] || preparse.kind || "Detected";
  return (
    <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 mb-5">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="px-3 py-1 rounded-full bg-blue-500/20 border border-blue-500/40 text-sm text-blue-300">
          {kindLabel}
        </span>
        {preparse.slot_count != null && (
          <span className="px-3 py-1 rounded-full bg-gray-800 border border-gray-700 text-sm text-gray-300">
            {preparse.slot_count} slot{preparse.slot_count === 1 ? "" : "s"}
          </span>
        )}
        {preparse.is_multi_material && (
          <span className="px-3 py-1 rounded-full bg-blue-500/20 border border-blue-500/40 text-sm text-blue-300">
            Multi-material
          </span>
        )}
        {preparse.model_name && (
          <span className="text-gray-400 text-sm ml-1 truncate">
            {preparse.model_name}
          </span>
        )}
      </div>
      {slots.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {slots.map((s, i) => (
            <div
              key={s.slot_index ?? i}
              className="flex items-center gap-2 bg-gray-800 border border-gray-700 rounded-lg px-2 py-1"
            >
              <span
                className="inline-block w-4 h-4 rounded border border-gray-600"
                style={{ backgroundColor: s.color_hex || "#888" }}
              />
              <span className="text-gray-300 text-xs">
                {s.material_type || "—"}
              </span>
              <span className="text-gray-500 font-mono text-[10px]">
                {s.color_hex || ""}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Multi-plate selection panel (unified flow). Rendered when a dropped file's
 * pre-parse reports more than one plate (preparse.plate_count > 1). Lists every
 * plate and lets the operator pick exactly one to intake; nothing is selected by
 * default, so the operator must choose before continuing. The chosen plate's
 * `plate_index` (read verbatim — value-matched server-side) is sent to /parse.
 *
 * Renders what each kind of file can offer:
 *   - SLICED (.gcode.3mf): the plate already carries slice data, so each row
 *     shows weight (total_weight_g), print time (print_time_seconds), a swatch
 *     row of the plate's slot colors, and a multi-material badge.
 *   - RAW (.3mf): not sliced yet, so each row shows only the plate name and its
 *     object_count. Picking one triggers the actual slice of just that plate.
 * @param {object} props
 * @param {Array<object>} props.plates - preparse.plates[] (sliced or raw shape).
 * @param {boolean} props.isRaw - true for a raw .3mf (no weight/time per plate).
 * @param {number|null} props.selectedPlateIndex - the chosen plate_index, or null.
 * @param {(plateIndex: number) => void} props.onSelect - called with a plate_index.
 * @returns {JSX.Element|null}
 */
function PlatePicker({ plates, isRaw, selectedPlateIndex, onSelect }) {
  if (!Array.isArray(plates) || plates.length === 0) return null;
  return (
    <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 mb-5">
      <h2 className="text-base font-semibold text-white mb-1">
        Choose a plate
      </h2>
      <p className="text-gray-500 text-sm mb-4">
        {isRaw
          ? `This file has ${plates.length} plates. Pick the one to intake — it will be sliced on the server.`
          : `This file has ${plates.length} plates. Pick the one to intake.`}
      </p>
      <div className="space-y-2">
        {plates.map((p) => {
          if (p.plate_index == null) return null;
          const idx = p.plate_index;
          const selected = selectedPlateIndex != null && idx === selectedPlateIndex;
          const slots = Array.isArray(p.slots) ? p.slots : [];
          return (
            <button
              key={idx}
              type="button"
              onClick={() => onSelect(idx)}
              aria-pressed={selected}
              className={`w-full text-left rounded-lg border px-4 py-3 transition-colors flex items-center gap-3 ${
                selected
                  ? "border-blue-500 bg-blue-500/10"
                  : "border-gray-700 bg-gray-800 hover:border-gray-600"
              }`}
            >
              <span
                className={`inline-block w-4 h-4 rounded-full border flex-shrink-0 ${
                  selected
                    ? "border-blue-400 bg-blue-500"
                    : "border-gray-500"
                }`}
              />
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-white font-medium">
                    Plate {idx}
                  </span>
                  {isRaw ? (
                    <>
                      {p.name && (
                        <span className="text-gray-300 text-sm truncate">
                          {p.name}
                        </span>
                      )}
                      {p.object_count != null && (
                        <span className="text-gray-500 text-sm">
                          ({p.object_count} object
                          {p.object_count === 1 ? "" : "s"})
                        </span>
                      )}
                    </>
                  ) : (
                    <>
                      {p.total_weight_g != null && (
                        <span className="text-gray-300 text-sm">
                          {Number(p.total_weight_g).toFixed(1)} g
                        </span>
                      )}
                      {p.print_time_seconds != null && (
                        <>
                          <span className="text-gray-600">·</span>
                          <span className="text-gray-300 text-sm">
                            {secondsToHms(p.print_time_seconds)}
                          </span>
                        </>
                      )}
                      {p.is_multi_material && (
                        <span className="px-2 py-0.5 rounded-full bg-blue-500/20 border border-blue-500/40 text-xs text-blue-300">
                          Multi-material
                        </span>
                      )}
                    </>
                  )}
                </div>
                {/* Sliced plates: a swatch row of the plate's slot colors. */}
                {!isRaw && slots.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 mt-2">
                    {slots.map((s, si) => (
                      <span
                        key={s.slot_id ?? si}
                        title={s.color_hex || s.filament_type || ""}
                        className="inline-block w-4 h-4 rounded border border-gray-600"
                        style={{ backgroundColor: s.color_hex || "#888" }}
                      />
                    ))}
                  </div>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Per-slot catalog material selector (unified flow). Renders a material-type
 * select then a color select, both sourced from /materials/for-bom. The chosen
 * (type, color) resolves to a single purchasable catalog item, surfaced via
 * `onPick`. Pre-filled from `chosen` (the existing matchChoices entry).
 * @param {object} props
 * @param {object} props.slot - the parsed slot (filament_type, color_hex, used_g).
 * @param {(string|number)} props.slotId - the slot identifier.
 * @param {Array<object>} props.items - the purchasable catalog (/materials/for-bom).
 * @param {object|undefined} props.chosen - the current matchChoices entry
 *   ({ product_id, sku, name }) for this slot.
 * @param {(item: object) => void} props.onPick - called with the picked catalog item.
 * @returns {JSX.Element}
 */
function MaterialSelectRow({ slot, slotId, items, chosen, onPick }) {
  // Distinct material types present in the catalog.
  const typeOptions = [];
  const seenTypes = new Set();
  for (const it of items) {
    if (it.material_code && !seenTypes.has(it.material_code)) {
      seenTypes.add(it.material_code);
      typeOptions.push({ id: it.material_code, name: it.material_code });
    }
  }

  // Derive the currently-selected material type from the chosen catalog item.
  // Compare ids as strings so a sticky default whose product_id arrives as a
  // string still resolves against the numeric catalog item ids (and vice versa).
  const chosenItem = chosen
    ? items.find((it) => String(it.id) === String(chosen.product_id))
    : null;
  const selectedType = chosenItem?.material_code || "";

  // Colors available for the selected type.
  const colorOptions = items
    .filter((it) => it.material_code === selectedType)
    .map((it) => ({
      id: it.id,
      name: `${it.color_code || it.name} — $${Number(it.standard_cost || 0).toFixed(2)}/kg`,
      sku: it.sku,
      color_hex: it.color_hex,
    }));

  const pickFirstColorForType = (typeCode) => {
    const first = items.find((it) => it.material_code === typeCode);
    if (first) onPick(first);
  };

  return (
    <div className="bg-gray-800/50 rounded-lg p-4">
      <div className="flex items-center gap-3 mb-3">
        <span
          className="inline-block w-5 h-5 rounded border border-gray-600 flex-shrink-0"
          style={{ backgroundColor: slot?.color_hex || "#888" }}
        />
        <span className="text-white font-medium">
          {slot?.filament_type || `Slot ${slotId}`}
        </span>
        <span className="text-gray-400 text-sm">
          {slot?.used_g != null ? `${slot.used_g.toFixed(1)} g` : ""}
        </span>
        {slot?.color_hex && (
          <span className="ml-auto text-gray-500 font-mono text-xs">
            {slot.color_hex}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-gray-400 mb-1">Material</label>
          <SearchableSelect
            options={typeOptions}
            value={selectedType}
            onChange={(val) => pickFirstColorForType(val)}
            placeholder="Select material…"
            displayKey="name"
            valueKey="id"
            formatOption={(opt) => opt.name}
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Color</label>
          <SearchableSelect
            options={colorOptions}
            value={chosen?.product_id != null ? String(chosen.product_id) : ""}
            onChange={(val) => {
              const it = items.find((x) => String(x.id) === val);
              if (it) onPick(it);
            }}
            placeholder={selectedType ? "Select color…" : "Pick a material first"}
            displayKey="name"
            valueKey="id"
            formatOption={(opt) => (
              <span className="flex items-center gap-2">
                <span
                  className="inline-block w-3 h-3 rounded border border-gray-600 flex-shrink-0"
                  style={{ backgroundColor: opt.color_hex || "#888" }}
                />
                {opt.name}
              </span>
            )}
          />
        </div>
      </div>
    </div>
  );
}

/**
 * Bare-mesh staging catalog material picker (unified flow). A material-type
 * select then a color select, both sourced from /materials/for-bom — the same
 * type→color approach as MaterialSelectRow, but standalone (no parsed slot
 * yet, since the mesh hasn't been sliced). The single chosen purchasable item
 * drives BOTH the derived slice profile and the downstream cost, so there's no
 * separate slice-profile pick.
 * @param {object} props
 * @param {Array<object>} props.items - the purchasable catalog (/materials/for-bom).
 * @param {object|null} props.chosen - the currently-chosen catalog item, or null.
 * @param {(item: object) => void} props.onPick - called with the picked catalog item.
 * @returns {JSX.Element}
 */
function BareMeshMaterialPicker({ items, chosen, onPick }) {
  // Distinct material types present in the catalog.
  const typeOptions = [];
  const seenTypes = new Set();
  for (const it of items) {
    if (it.material_code && !seenTypes.has(it.material_code)) {
      seenTypes.add(it.material_code);
      typeOptions.push({ id: it.material_code, name: it.material_code });
    }
  }

  const selectedType = chosen?.material_code || "";

  // Colors available for the selected type.
  const colorOptions = items
    .filter((it) => it.material_code === selectedType)
    .map((it) => ({
      id: it.id,
      name: `${it.color_code || it.name} — $${Number(it.standard_cost || 0).toFixed(2)}/kg`,
      sku: it.sku,
      color_hex: it.color_hex,
    }));

  const pickFirstColorForType = (typeCode) => {
    const first = items.find((it) => it.material_code === typeCode);
    if (first) onPick(first);
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-1">
          Material
        </label>
        <SearchableSelect
          options={typeOptions}
          value={selectedType}
          onChange={(val) => pickFirstColorForType(val)}
          placeholder="Select material…"
          displayKey="name"
          valueKey="id"
          formatOption={(opt) => opt.name}
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-1">
          Color
        </label>
        <SearchableSelect
          options={colorOptions}
          value={chosen?.id != null ? String(chosen.id) : ""}
          onChange={(val) => {
            const it = items.find((x) => String(x.id) === val);
            if (it) onPick(it);
          }}
          placeholder={selectedType ? "Select color…" : "Pick a material first"}
          displayKey="name"
          valueKey="id"
          formatOption={(opt) => (
            <span className="flex items-center gap-2">
              <span
                className="inline-block w-3 h-3 rounded border border-gray-600 flex-shrink-0"
                style={{ backgroundColor: opt.color_hex || "#888" }}
              />
              {opt.name}
            </span>
          )}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const INTAKE_ITEM_TYPES = [
  { value: "finished_good", label: "Finished Good" },
  { value: "component", label: "Component" },
  { value: "packaging", label: "Packaging" },
  { value: "supply", label: "Supply" },
  { value: "service", label: "Service" },
];

// Bare-mesh (.stl/.obj) slicing profile options. A mesh carries no embedded
// slice profile, so the server needs a material/printer/quality reference
// before it can slice. Values must match the worker's profile resolver.
const SLICE_MATERIALS = [
  { value: "PLA Basic", label: "PLA Basic (PLA)" },
  { value: "PLA Matte", label: "PLA Matte" },
  { value: "PETG Basic", label: "PETG Basic (PETG)" },
  { value: "ABS", label: "ABS" },
  { value: "ASA", label: "ASA" },
  { value: "PC", label: "PC (Polycarbonate)" },
  { value: "PA6-CF", label: "PA6-CF (Nylon-CF)" },
  { value: "PAHT-CF", label: "PAHT-CF" },
  { value: "PET-CF", label: "PET-CF" },
  { value: "PLA-CF", label: "PLA-CF" },
  { value: "TPU 95A", label: "TPU 95A" },
];

const SLICE_PRINTERS = [
  { value: "X1C", label: "X1C (X1 Carbon)" },
  { value: "A1", label: "A1" },
];

const SLICE_QUALITIES = [
  { value: "standard", label: "Standard" },
  { value: "fine", label: "Fine" },
  { value: "draft", label: "Draft" },
];

const isBareMesh = (name) =>
  name.endsWith(".stl") || name.endsWith(".obj");

// ---------------------------------------------------------------------------
// Unified-flow helpers (only used when the unified flow is enabled)
// ---------------------------------------------------------------------------

/**
 * Parse a #RRGGBB (or RRGGBB) hex string into an [r, g, b] tuple.
 * @param {string} hex - the color string.
 * @returns {[number, number, number]|null} the RGB tuple, or null if unparseable.
 */
const hexToRgb = (hex) => {
  if (!hex) return null;
  const m = String(hex).trim().replace(/^#/, "");
  if (!/^[0-9a-fA-F]{6}$/.test(m)) return null;
  return [
    parseInt(m.slice(0, 2), 16),
    parseInt(m.slice(2, 4), 16),
    parseInt(m.slice(4, 6), 16),
  ];
};

/**
 * Squared Euclidean RGB distance between two hex colors.
 * @param {string} a - first #RRGGBB color.
 * @param {string} b - second #RRGGBB color.
 * @returns {number} the squared distance, or Infinity if either is unparseable.
 */
const colorDistance = (a, b) => {
  const ra = hexToRgb(a);
  const rb = hexToRgb(b);
  if (!ra || !rb) return Infinity;
  return (
    (ra[0] - rb[0]) ** 2 + (ra[1] - rb[1]) ** 2 + (ra[2] - rb[2]) ** 2
  );
};

/**
 * Normalize a material code/type for comparison: uppercase, then drop every
 * non-alphanumeric char (so spaces, underscores and hyphens collapse). Lets
 * "PLA Basic", "PLA_BASIC" and "pla-basic" all reduce to "PLABASIC".
 * @param {string} s - the raw code or type string.
 * @returns {string} the normalized code ("" for nullish input).
 */
const normalizeCode = (s) => (s || "").toUpperCase().replace(/[^A-Z0-9]/g, "");

/**
 * Loose, symmetric containment test between a catalog material_code and a
 * normalized slot type. Matches in BOTH directions so a slicer profile like
 * "PLA Basic" (→ "PLABASIC") matches a catalog code "PLA", and a catalog code
 * "PLA Basic" matches a "PLA" slot.
 * @param {string} materialCode - the catalog item's material_code.
 * @param {string} typeNorm - the already-normalized slot filament type.
 * @returns {boolean} true when either normalized string contains the other.
 */
const looselyMatchesCode = (materialCode, typeNorm) => {
  const codeNorm = normalizeCode(materialCode);
  return (
    !!codeNorm &&
    !!typeNorm &&
    (codeNorm.includes(typeNorm) || typeNorm.includes(codeNorm))
  );
};

/**
 * Best purchasable catalog item (from /materials/for-bom) for a slot's
 * material_type + color_hex. Prefers items whose material_code EXACTLY matches
 * (normalized) the slot's filament type, then items that loosely match either
 * direction, then picks the nearest color; falls back to nearest color across
 * the whole catalog. The exact-first ordering avoids cross-family mis-prefill
 * (e.g. a plain "PLA" slot seeding a "PLA-CF" purchasable).
 * @param {Array<object>} items - the purchasable catalog (each has id,
 *   material_code, color_hex, sku, name).
 * @param {string} filamentType - the slot's slicer material/type string.
 * @param {string} colorHex - the slot's #RRGGBB color.
 * @returns {object|null} the chosen catalog item, or null when none.
 */
const nearestCatalogMatch = (items, filamentType, colorHex) => {
  if (!Array.isArray(items) || items.length === 0) return null;
  const typeNorm = normalizeCode(filamentType);
  let typed = [];
  if (typeNorm) {
    // Exact normalized-code match first.
    typed = items.filter((it) => normalizeCode(it.material_code) === typeNorm);
    // Fall back to symmetric substring/contains only when there is no
    // exact-code match (so "PLA Basic" still matches catalog "PLA").
    if (typed.length === 0) {
      typed = items.filter((it) =>
        looselyMatchesCode(it.material_code, typeNorm)
      );
    }
  }
  const pool = typed.length > 0 ? typed : items;
  let best = null;
  let bestDist = Infinity;
  for (const it of pool) {
    const d = colorDistance(colorHex, it.color_hex);
    if (d < bestDist) {
      bestDist = d;
      best = it;
    }
  }
  // If no color was parseable in the preferred pool, just take the first item.
  return best || pool[0] || null;
};

// Safe fallback slice profile — a generic PLA profile the worker always
// supports. Used when a chosen catalog material can't be mapped to any
// SLICE_MATERIALS entry, so the slice POST never carries an invalid material.
const DEFAULT_SLICE_PROFILE = "PLA Basic";

/**
 * Derive a coarse base-material family ("PLA"/"PETG"/"ABS"/"ASA"/"PC"/"TPU"/
 * "NYLON") from a catalog material_code by matching a known family prefix
 * (mirrors the backend's base-material extraction). Returns "" when nothing
 * recognizable is found. Normalized (uppercase, non-alphanumeric stripped) so
 * "PLA_BASIC", "pla-cf" and "PLA Basic" all reduce the same way.
 * @param {string} materialCode - the catalog item's material_code.
 * @returns {string} the base family ("" when unrecognized).
 */
const baseFamilyFromCode = (materialCode) => {
  const norm = normalizeCode(materialCode);
  if (!norm) return "";
  // PCTG (a copolyester / PETG variant) would otherwise match the "PC" prefix
  // below and resolve to the polycarbonate profile, which prints far hotter.
  // Steer it to the PETG family before the generic prefix scan.
  if (norm.startsWith("PCTG")) return "PETG";
  // PETG before PET so "PETG_BASIC" isn't truncated to the PET-CF family, and
  // longer-prefix families first so the most specific known base wins.
  // No "NYLON" entry: SLICE_MATERIALS has no NYLON-family profile (the nylon
  // worker profiles are PA6-CF/PAHT-CF, families "PA6"/"PAHT"), so listing
  // "NYLON" only mis-signals a match before falling through to the PLA default.
  // A bare "NYLON"/"NYLON_CF" code therefore resolves via the safe default with
  // the non-exact notice shown, rather than a phantom family hit.
  for (const fam of ["PETG", "PET", "PAHT", "PA6", "PLA", "ABS", "ASA", "PC", "TPU"]) {
    if (norm.startsWith(fam)) return fam;
  }
  return "";
};

/**
 * Map a chosen purchasable catalog item to a valid SLICE_MATERIALS profile
 * string (the worker's A.4c profile resolver only accepts these exact strings).
 * Resolution order, never producing an invalid string and never blocking:
 *   1. Exact normalized match of material_code against a SLICE_MATERIALS value
 *      (e.g. "PLA_BASIC" → "PLA Basic", "PLA_CF" → "PLA-CF").
 *   2. Base-family match — the first SLICE_MATERIALS entry sharing the catalog
 *      item's base family, preferring a generic/"Basic" profile over a
 *      specialty (CF/Matte) one (e.g. "PLA_SILK" → "PLA Basic").
 *   3. The safe DEFAULT_SLICE_PROFILE.
 * Returns { profile, exact } so the caller can surface a non-blocking notice
 * when the mapping wasn't an exact hit.
 * @param {object|null} item - the chosen catalog item ({ material_code, ... }).
 * @returns {{ profile: string, exact: boolean }} the resolved profile + whether
 *   it was an exact material_code match.
 */
const catalogMaterialToSliceProfile = (item) => {
  const code = item?.material_code;
  const codeNorm = normalizeCode(code);
  // 1. Exact normalized material_code → SLICE_MATERIALS value.
  if (codeNorm) {
    const exact = SLICE_MATERIALS.find(
      (m) => normalizeCode(m.value) === codeNorm
    );
    if (exact) return { profile: exact.value, exact: true };
  }
  // 2. Base-family match, preferring a generic "Basic"/plain profile.
  const fam = baseFamilyFromCode(code);
  if (fam) {
    const sameFamily = SLICE_MATERIALS.filter(
      (m) => baseFamilyFromCode(m.value) === fam
    );
    if (sameFamily.length > 0) {
      const generic =
        sameFamily.find((m) => /BASIC/.test(normalizeCode(m.value))) ||
        sameFamily.find(
          (m) => !/(CF|MATTE|SILK)/.test(normalizeCode(m.value))
        ) ||
        sameFamily[0];
      return { profile: generic.value, exact: false };
    }
  }
  // 3. Safe default — always a valid worker profile.
  return { profile: DEFAULT_SLICE_PROFILE, exact: false };
};

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function AdminIntakeStudio() {
  const toast = useToast();
  const api = useApi();
  const { isPro, hasFeature, loading: flagsLoading } = useFeatureFlags();

  // Unified-flow gate (RUNTIME, OFF by default). Enabled when EITHER the backend
  // advertises the feature (per-tenant, no rebuild) OR the build sets
  // VITE_INTAKE_UNIFIED_FLOW=true. Both default OFF, so the gate is never
  // statically false and the OFF path is byte-identical to the legacy flow.
  // See frontend/src/config/intakeFlags.js for the two flip mechanisms.
  const unifiedFlow =
    INTAKE_UNIFIED_FLOW || hasFeature(INTAKE_UNIFIED_FLOW_FEATURE);

  // Wizard state
  const [step, setStep] = useState(1);

  // Step 1 — Upload
  const [dragActive, setDragActive] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [busyMode, setBusyMode] = useState("parsing");
  // Bare-mesh staging: a .stl/.obj is held here while the operator picks a
  // slicing profile, since a slice needs a material BEFORE the upload POST.
  const [pendingMesh, setPendingMesh] = useState(null);
  const [sliceMaterial, setSliceMaterial] = useState("PLA Basic");
  const [slicePrinter, setSlicePrinter] = useState("X1C");
  const [sliceQuality, setSliceQuality] = useState("standard");
  // Unified flow only: the purchasable catalog material chosen at staging for a
  // bare mesh. This single pick is the one source of truth — it drives the
  // derived slice profile AND seeds the Step-3 slot so cost/BOM reuse it. Inert
  // when the gate is off (the legacy SLICE_MATERIALS picker is used instead).
  const [stagedMaterial, setStagedMaterial] = useState(null);
  // Optional advanced override: when set, forces the slice profile instead of
  // the one derived from stagedMaterial (for the rare wrong-mapping case).
  const [sliceProfileOverride, setSliceProfileOverride] = useState("");

  // Step 2 — Review
  const [parseResult, setParseResult] = useState(null);
  const [productName, setProductName] = useState("");

  // Step 3 — Match
  const [matchResults, setMatchResults] = useState(null);
  const [matchBusy, setMatchBusy] = useState(false);
  // map slot_id -> { product_id, sku, name }
  const [matchChoices, setMatchChoices] = useState({});

  // Unified flow (gated by `unifiedFlow`) — pre-parse + catalog material
  // selection. All inert when the gate is off (never set, rendered, or read).
  const [preparseResult, setPreparseResult] = useState(null);
  // Multi-plate (unified flow) — the operator's chosen plate. Holds the chosen
  // plate's `plate_index` (read verbatim from preparseResult.plates[]), or null
  // when no plate is selected yet / the file is single-plate. Sent to /parse as
  // the `plate_index` form field. Inert when the gate is off or plate_count<=1.
  const [selectedPlateIndex, setSelectedPlateIndex] = useState(null);
  const [bomMaterials, setBomMaterials] = useState([]); // /materials/for-bom items
  // Drop-time catalog fetch state for the bare-mesh staging picker. Distinguishes
  // in-flight ("loading") from a resolved-but-unusable catalog ("empty"/"failed")
  // so the staging step shows the right recoverable message instead of a single
  // permanent "Loading…" banner that traps every bare mesh. Mirrors how
  // runMaterialSelect (Step 3) already separates these states via materialsError.
  const [bomMaterialsLoading, setBomMaterialsLoading] = useState(false);
  const [bomMaterialsError, setBomMaterialsError] = useState(null); // "empty" | "failed" | null
  const [reconcileNotice, setReconcileNotice] = useState(null);
  // Distinguishes a failed catalog fetch ("failed") from a genuinely empty
  // catalog ("empty") vs. a healthy one (null) so Step 3 can surface an
  // explicit, recoverable message instead of trapping the operator behind
  // empty material selectors. Set by runMaterialSelect.
  const [materialsError, setMaterialsError] = useState(null);

  // Step 4 — Configure
  const [context, setContext] = useState(null);
  const [contextBusy, setContextBusy] = useState(false);
  const [printWorkCenterId, setPrintWorkCenterId] = useState("");
  const [finishingOps, setFinishingOps] = useState([]);
  const [matModalOpIdx, setMatModalOpIdx] = useState(null);
  const [actualPrice, setActualPrice] = useState("");
  const [itemType, setItemType] = useState("finished_good");
  const [categoryId, setCategoryId] = useState(null);
  const [categories, setCategories] = useState([]);

  // Step 4 — new UX state
  const [partsOnPlate, setPartsOnPlate] = useState(1);
  const [skuCode, setSkuCode] = useState("");
  const [skuEdited, setSkuEdited] = useState(false);
  const [estimatedCost, setEstimatedCost] = useState(null);
  const [previewBusy, setPreviewBusy] = useState(false);

  // Guards against stale /preview responses overwriting newer state. priceEditedRef
  // lets the async runPreview closure read the live value without a stale capture.
  // (No useEffect — Core eslint forbids it.)
  const previewRequestIdRef = useRef(0);
  const priceEditedRef = useRef(false);
  // Retains the dropped/selected File so it can be uploaded after /sku succeeds.
  const sourceFileRef = useRef(null);
  // Monotonic token for the active upload → /parse (slice/parse) request. A new
  // file or a reset bumps it; an upload whose token no longer matches is stale
  // (a slower slice that finished after Reset or a new file drop) and must not
  // re-apply its parseResult/matchChoices/staged-material seed or advance to
  // Step 2. Mirrors previewRequestIdRef. (CodeRabbit #802 — flagged race.)
  const uploadRequestIdRef = useRef(0);
  // Monotonic token for the legacy /match call (runMatch, gate-off path). The
  // Step-2 "Start over" button (handleReset) is clickable while /match is in
  // flight, so without this a slow response could re-apply stale matchResults
  // and jump to Step 3 after the reset. Bumped in both reset paths.
  const matchRequestIdRef = useRef(0);
  // Mirror of preparseResult readable by the async uploadIntakeFile closure.
  // On the raw-.3mf path the pre-parse POST resolves AFTER uploadIntakeFile's
  // closure was created, so reading the preparseResult state there would see a
  // stale (null) value and the slice-vs-preparse reconcile notice would never
  // fire. The ref always holds the freshest pre-parse payload.
  const preparseResultRef = useRef(null);
  // Monotonic token for the active pre-parse request. A new file or a reset
  // bumps it; a pre-parse response whose token no longer matches is stale (it
  // belongs to a prior file) and is dropped, so a slow response can't overwrite
  // the current file's pre-parse panel or slot count. Mirrors previewRequestIdRef.
  const preparseRequestIdRef = useRef(0);
  // Monotonic token for the active /materials/for-bom request. A new file, a
  // reset, or a manual retry bumps it; a response whose token no longer matches
  // is stale and is dropped so a slow fetch can't clobber a newer result.
  const bomMaterialsRequestIdRef = useRef(0);
  // Monotonic token for the active runMaterialSelect call. A new file or a
  // reset bumps it; any in-flight runMaterialSelect whose token no longer
  // matches is stale and must not advance the wizard (setMatchResults/setStep).
  const materialSelectRequestIdRef = useRef(0);
  // Multi-plate (unified flow): retains the dropped .3mf/.gcode.3mf File while
  // its pre-parse is in flight. On a single-plate result the pre-parse handler
  // auto-continues to /parse with this file; on a multi-plate result it's held
  // so the PlatePicker can drive the /parse once the operator chooses a plate.
  // Cleared by reset and once the parse is dispatched.
  const pendingPlateFileRef = useRef(null);

  // Step 5 — Result
  const [skuResult, setSkuResult] = useState(null);
  const [skuBusy, setSkuBusy] = useState(false);
  const [sliceFileSaved, setSliceFileSaved] = useState(false);

  // ---------------------------------------------------------------------------
  // PRO gate
  // ---------------------------------------------------------------------------

  if (flagsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner />
      </div>
    );
  }

  if (!isPro) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Intake Studio</h1>
          <p className="text-gray-400 mt-1">
            Drop a sliced file and create a sellable SKU in minutes
          </p>
        </div>
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-6 text-center">
          <svg
            className="w-12 h-12 text-blue-400 mx-auto mb-3"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
          <h3 className="text-lg font-semibold text-white mb-2">PRO Feature</h3>
          <p className="text-gray-400 mb-4">
            Intake Studio lets you drop a 3D model (.3mf, sliced on the server)
            or a pre-sliced .gcode.3mf, automatically match filament spools from
            your inventory, configure print work centers and finishing operations,
            and instantly create a sellable SKU with a fully costed routing — all
            in one guided workflow.
          </p>
          <a
            href="/pricing"
            className="inline-block bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg transition-colors"
          >
            Upgrade to PRO
          </a>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Step 1 handlers — Upload
  // ---------------------------------------------------------------------------

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0]);
    }
  };

  // Clears every wizard-derived value so a newly selected file starts clean.
  // Does NOT touch `step` — handleFile/staging manages navigation.
  const resetDerivedStateForNewFile = () => {
    // bare-mesh picker
    setPendingMesh(null);
    setSliceMaterial("PLA Basic");
    setSlicePrinter("X1C");
    setSliceQuality("standard");
    setStagedMaterial(null);
    setSliceProfileOverride("");
    // Step 2 — Review
    setParseResult(null);
    setProductName("");
    // Step 3 — Match
    setMatchResults(null);
    setMatchBusy(false);
    setMatchChoices({});
    // Unified flow
    setPreparseResult(null);
    preparseResultRef.current = null;
    // Multi-plate: clear the chosen plate and drop any file held for the picker
    // so a stale pre-parse/plate-pick can't dispatch a parse for the old file.
    setSelectedPlateIndex(null);
    pendingPlateFileRef.current = null;
    // Invalidate any pre-parse still in flight so its response is ignored.
    preparseRequestIdRef.current += 1;
    // Invalidate any catalog fetch still in flight so a stale /for-bom response
    // from a prior file cannot overwrite the fresh load for this file.
    bomMaterialsRequestIdRef.current += 1;
    // Invalidate any runMaterialSelect still in flight so a stale call cannot
    // call setMatchResults/setStep(3) with the old parseResult.
    materialSelectRequestIdRef.current += 1;
    setMaterialsError(null);
    setBomMaterialsLoading(false);
    setBomMaterialsError(null);
    setReconcileNotice(null);
    // Step 4 — Configure
    setContext(null);
    setContextBusy(false);
    setPrintWorkCenterId("");
    setFinishingOps([]);
    setMatModalOpIdx(null);
    setActualPrice("");
    setItemType("finished_good");
    setCategoryId(null);
    setCategories([]);
    setPartsOnPlate(1);
    setSkuCode("");
    setSkuEdited(false);
    setEstimatedCost(null);
    setPreviewBusy(false);
    // Step 5 — Result
    setSkuResult(null);
    setSkuBusy(false);
    setSliceFileSaved(false);
    // refs
    priceEditedRef.current = false;
    sourceFileRef.current = null;
    // Invalidate any preview still in flight so its response is ignored.
    previewRequestIdRef.current += 1;
    // Invalidate any upload (slice/parse) still in flight so a slow response
    // can't re-apply this prior file's parseResult/matchChoices or jump to Step 2.
    uploadRequestIdRef.current += 1;
    // Invalidate any legacy /match still in flight (gate-off path).
    matchRequestIdRef.current += 1;
  };

  const handleFile = (f) => {
    const name = f.name.toLowerCase();
    if (
      !name.endsWith(".3mf") &&
      !name.endsWith(".gcode.3mf") &&
      !isBareMesh(name)
    ) {
      toast.error("Please select a .stl, .obj, .3mf or .gcode.3mf file");
      return;
    }
    // A new file invalidates everything downstream — start from a clean slate.
    resetDerivedStateForNewFile();
    const bare = isBareMesh(name);
    // Unified flow: pre-parse every dropped file to show the detected kind +
    // per-slot color swatches BEFORE any slice. Non-blocking — the panel is
    // additive and never gates the existing parse/stage path.
    if (unifiedFlow) {
      // For a non-bare file (.3mf/.gcode.3mf), defer the immediate /parse: the
      // pre-parse response decides whether to auto-continue (single plate) or
      // surface the PlatePicker (multi-plate). Hold the file so that decision
      // (or the operator's plate pick) can drive the parse. Bare meshes stage
      // for a slice profile instead and are always single-plate.
      if (!bare) pendingPlateFileRef.current = f;
      // Tag this pre-parse with the post-reset token so a slower response from a
      // prior file (whose token was bumped by resetDerivedStateForNewFile) is
      // ignored rather than clobbering this file's pre-parse state.
      preparseIntakeFile(f, preparseRequestIdRef.current);
      loadBomMaterials();
    }
    if (bare) {
      // Stage the mesh and reveal the slicing-profile picker; don't POST yet —
      // the slice needs a material/printer/quality first.
      setPendingMesh(f);
      return;
    }
    // Gate off: .3mf / .gcode.3mf keep the immediate behavior. Under the unified
    // flow the parse is dispatched by the pre-parse handler / PlatePicker once
    // the plate count (and chosen plate) is known.
    if (!unifiedFlow) {
      uploadIntakeFile(f);
    }
  };

  // ---------------------------------------------------------------------------
  // Unified flow — pre-parse + catalog loading (gated; no-op when off)
  // ---------------------------------------------------------------------------

  /**
   * POST /preparse — detect file kind + slots before slicing, for the pre-parse
   * panel. Best-effort: a failure just leaves the panel hidden and the normal
   * flow continues. Stale-guarded by `requestId`: if a newer file (or a reset)
   * has bumped `preparseRequestIdRef` since this request started, the response
   * is dropped so it can't overwrite the current file's pre-parse state.
   * @param {File} f - the dropped/selected file to pre-parse.
   * @param {number} requestId - the pre-parse token captured at request time.
   * @returns {Promise<void>}
   */
  const preparseIntakeFile = async (f, requestId) => {
    let ok = false;
    try {
      const formData = new FormData();
      formData.append("file", f);
      const res = await fetch(`${API_URL}/api/v1/pro/intake/preparse`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      if (!res.ok) return;
      const data = await res.json();
      // Drop a stale response: a newer file or a reset has superseded this one.
      if (requestId !== preparseRequestIdRef.current) return;
      // Write the ref first so any in-flight uploadIntakeFile closure (raw .3mf
      // path) reads the fresh value for the reconcile check; then update state
      // for the PreParsePanel render.
      preparseResultRef.current = data;
      setPreparseResult(data);
      ok = true;
      // Multi-plate gating (non-bare files only — bare meshes stage separately
      // and are single-plate). A held file whose pre-parse reports >1 plate
      // waits for the PlatePicker to choose a plate before /parse; a single-plate
      // (or plate-count-absent) file auto-continues to the unchanged parse path.
      const pending = pendingPlateFileRef.current;
      if (pending && (data.plate_count ?? 1) <= 1) {
        pendingPlateFileRef.current = null;
        uploadIntakeFile(pending);
      }
      // A multi-plate file is intentionally left in pendingPlateFileRef so the
      // PlatePicker (rendered from preparseResult.plate_count > 1) can drive the
      // parse with the chosen plate_index.
    } catch {
      // Non-fatal — the pre-parse panel is purely informational.
    } finally {
      // If the pre-parse failed (or was superseded by a newer/stale token) but a
      // non-bare file is still held, fall back to the unchanged immediate parse
      // so the operator is never stranded with no parse and no picker. The stale
      // guard above already returned without setting `ok`, so this only fires for
      // a genuine failure of the CURRENT file's pre-parse.
      if (!ok && requestId === preparseRequestIdRef.current) {
        const pending = pendingPlateFileRef.current;
        if (pending) {
          pendingPlateFileRef.current = null;
          uploadIntakeFile(pending);
        }
      }
    }
  };

  /**
   * GET /materials/for-bom — load the purchasable catalog backing the material
   * selector (each item.id is the spool_product_id the slot payload needs).
   * Cached for the session: returns early if already loaded, refetches only when
   * empty, and on failure leaves the list empty (runMaterialSelect surfaces the
   * recoverable error state).
   * @returns {Promise<void>}
   */
  const loadBomMaterials = async () => {
    if (bomMaterials.length > 0) return;
    const requestId = ++bomMaterialsRequestIdRef.current;
    setBomMaterialsLoading(true);
    setBomMaterialsError(null);
    try {
      const data = await api.get("/api/v1/materials/for-bom");
      const items = Array.isArray(data?.items) ? data.items : [];
      // Drop the response if a newer request has superseded this one (e.g. the
      // user dropped a new file or hit Reset while this fetch was in flight).
      if (requestId !== bomMaterialsRequestIdRef.current) return;
      setBomMaterials(items);
      // Resolved but unusable: an empty catalog is a recoverable state, not a
      // dead-end. The staging picker reads this to show "add materials, then
      // retry" instead of a perpetual loading banner.
      setBomMaterialsError(items.length === 0 ? "empty" : null);
    } catch {
      if (requestId !== bomMaterialsRequestIdRef.current) return;
      setBomMaterials([]);
      setBomMaterialsError("failed");
    } finally {
      if (requestId === bomMaterialsRequestIdRef.current) {
        setBomMaterialsLoading(false);
      }
    }
  };

  // Shared upload → /parse. When a mesh profile is supplied, append the
  // material/printer/quality form fields the server uses to slice the bare mesh.
  // `seedCatalogItem` (unified flow, bare mesh): the purchasable catalog material
  // chosen at staging; when present, every resulting slot is pre-seeded with it
  // so the one staging pick === the slice profile source === the slot's
  // matchChoices, and Step 3 shows it pre-confirmed with cost.
  // `plateIndex` (unified flow, multi-plate): the chosen plate's `plate_index`
  // (read verbatim from the /preparse plates[] — value-matched server-side, so it
  // round-trips with no off-by-one). When set it's sent as the `plate_index` form
  // field; the backend returns that plate's data as the top-level parse contract
  // (sliced: that plate; raw: slices ONLY that plate). null = unchanged behavior.
  const uploadIntakeFile = async (
    f,
    profile = null,
    seedCatalogItem = null,
    plateIndex = null
  ) => {
    // Token this upload; a new file or a reset bumps uploadRequestIdRef, marking
    // any in-flight slice/parse stale so a slow response can't re-apply an old
    // parseResult/matchChoices/staged-material seed or advance to Step 2.
    const requestId = ++uploadRequestIdRef.current;
    const isStaleUpload = () => requestId !== uploadRequestIdRef.current;
    const name = f.name.toLowerCase();
    sourceFileRef.current = f;
    // Bare meshes and raw .3mf are sliced on the server; .gcode.3mf is parsed.
    const willSlice = profile != null || (name.endsWith(".3mf") && !name.endsWith(".gcode.3mf"));
    setBusyMode(willSlice ? "slicing" : "parsing");
    setUploadBusy(true);
    try {
      const formData = new FormData();
      formData.append("file", f);
      if (profile) {
        formData.append("material", profile.material);
        formData.append("printer", profile.printer);
        formData.append("quality", profile.quality);
      }
      // Multi-plate: select a single plate. Sent verbatim (the backend matches
      // plates by value, p.plate_index == plate_index, so this round-trips with
      // no off-by-one). Sliced → returns that plate's data as the top-level
      // contract; raw → slices ONLY that plate (--slice n). Omitted when null so
      // single-plate / gate-off behavior is byte-identical.
      if (plateIndex != null) {
        formData.append("plate_index", String(plateIndex));
      }
      const res = await fetch(`${API_URL}/api/v1/pro/intake/parse`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      let data;
      try {
        data = await res.json();
      } catch {
        data = {};
      }
      // A new file or a reset superseded this upload while it was in flight —
      // drop the response so it can't re-apply stale parse/seed state or toast.
      if (isStaleUpload()) return;
      if (!res.ok) {
        toast.error(data.detail || `Parse failed (${res.status})`);
        return;
      }
      setPendingMesh(null);
      setParseResult(data);
      setProductName(data.model_name || "");
      // Unified flow, bare mesh: pre-seed every sliced slot with the catalog
      // material chosen at staging so Step 3 opens pre-confirmed and /preview
      // + /sku cost it from that purchasable product (one pick, no re-pick).
      if (unifiedFlow && seedCatalogItem && Array.isArray(data.slots)) {
        const seeded = {};
        data.slots.forEach((s) => {
          seeded[s.slot_id] = {
            product_id: seedCatalogItem.id,
            sku: seedCatalogItem.sku,
            name: seedCatalogItem.name,
          };
        });
        setMatchChoices(seeded);
        // A bare mesh normally slices to one slot, but if it produced several,
        // the single staging pick was fanned out to all of them. Surface a
        // non-blocking notice so the operator reviews each slot in Step 3 rather
        // than shipping a multi-material item costed as one material.
        if (data.slots.length > 1) {
          // Append rather than replace: the slot-count-mismatch notice set below
          // may fire for the same slice run — both warnings must survive so the
          // operator sees the full picture.
          setReconcileNotice((prev) =>
            [
              prev,
              `Slicing produced ${data.slots.length} material slots; all were ` +
                `pre-filled with ${seedCatalogItem.name || "the selected material"} ` +
                `— confirm the material for each slot below.`,
            ]
              .filter(Boolean)
              .join(" ")
          );
        }
      }
      // Unified flow: when a slice ran, the slice result is canonical. If its
      // slot count diverges from the pre-parse estimate, surface a notice so
      // the operator knows the material rows below were re-keyed to the slice.
      // Any selections made earlier are carried by slot position downstream.
      // Read the pre-parse slot count from the ref (not the state) so the raw
      // .3mf path — where preparseIntakeFile resolves after this closure was
      // created — compares against the just-computed value, not a stale null.
      // For a multi-plate pick, compare against the CHOSEN plate's slot count
      // (the pre-parse top-level slot_count describes the default plate, not the
      // one selected), falling back to the top-level count when unavailable.
      let preparseSlotCount = preparseResultRef.current?.slot_count;
      if (plateIndex != null) {
        const chosenPlate = (preparseResultRef.current?.plates || []).find(
          (p) => p.plate_index === plateIndex
        );
        const chosenSlotCount = Array.isArray(chosenPlate?.slots)
          ? chosenPlate.slots.length
          : null;
        if (chosenSlotCount != null) preparseSlotCount = chosenSlotCount;
      }
      if (unifiedFlow && willSlice && preparseSlotCount != null) {
        const slicedCount = Array.isArray(data.slots)
          ? data.slots.length
          : data.slot_count;
        if (slicedCount != null && slicedCount !== preparseSlotCount) {
          // Append to preserve any fan-out pre-fill notice set just above.
          setReconcileNotice((prev) =>
            [
              prev,
              `Slicing detected ${slicedCount} material slot${slicedCount === 1 ? "" : "s"}, ` +
                `but the pre-parse estimated ${preparseSlotCount}. ` +
                `Using the slice result — please confirm the material for each slot below.`,
            ]
              .filter(Boolean)
              .join(" ")
          );
        }
      }
      // Multi-plate: the parse succeeded — now it's safe to clear the held file
      // and picker state. Clearing before uploadIntakeFile (as it was) left an
      // enabled but no-op Continue after a parse failure or Step-2 Back.
      if (plateIndex != null) {
        pendingPlateFileRef.current = null;
        setPreparseResult(null);
        preparseResultRef.current = null;
        setSelectedPlateIndex(null);
      }
      setStep(2);
    } catch (err) {
      // Suppress a stale upload's error toast (its file was already superseded).
      if (isStaleUpload()) return;
      toast.error(err.message || "Upload failed");
    } finally {
      // Only the live upload owns the busy spinner; a stale one clearing it
      // would prematurely hide the spinner for the upload that replaced it.
      if (!isStaleUpload()) {
        setUploadBusy(false);
      }
    }
  };

  // Multi-plate (unified flow): the operator picked a plate in the PlatePicker
  // and clicked continue. Dispatch /parse for the held file with the chosen
  // plate_index — sliced returns that plate's data as the top-level contract,
  // raw slices ONLY that plate (busyMode "slicing"). The chosen plate's data
  // then flows into parseResult exactly like the single-plate path. No-op if
  // there's no held file or no selection (the button is disabled in that case).
  const continueWithSelectedPlate = () => {
    const pending = pendingPlateFileRef.current;
    if (!pending || selectedPlateIndex == null) return;
    // Do NOT clear pendingPlateFileRef here — keep the held file available for
    // retry (parse failure) or Step-2 Back. It is cleared in uploadIntakeFile's
    // success path once the parse returns ok (plateIndex != null branch above).
    uploadIntakeFile(pending, null, null, selectedPlateIndex);
  };

  const sliceAndContinue = () => {
    if (!pendingMesh) return;
    if (unifiedFlow) {
      // Unified flow: the single catalog pick drives BOTH the slice profile and
      // the cost. Derive a valid SLICE_MATERIALS profile from the chosen catalog
      // material (an explicit advanced override wins), then seed the resulting
      // slot(s) with that catalog product so Step 3 is pre-confirmed and cost
      // uses it — one source of truth.
      const derived = catalogMaterialToSliceProfile(stagedMaterial);
      const profile = sliceProfileOverride || derived.profile;
      uploadIntakeFile(
        pendingMesh,
        { material: profile, printer: slicePrinter, quality: sliceQuality },
        stagedMaterial
      );
      return;
    }
    uploadIntakeFile(pendingMesh, {
      material: sliceMaterial,
      printer: slicePrinter,
      quality: sliceQuality,
    });
  };

  // ---------------------------------------------------------------------------
  // Step 2 → 3: run /match
  // ---------------------------------------------------------------------------

  const runMatch = async () => {
    if (unifiedFlow) {
      return runMaterialSelect();
    }
    // Token this /match; a reset (Step-2 "Start over") or a new-file drop bumps
    // matchRequestIdRef, marking an in-flight call stale so a slow response can't
    // re-apply old matchResults/matchChoices or jump to Step 3 after the reset.
    const requestId = ++matchRequestIdRef.current;
    const isStale = () => requestId !== matchRequestIdRef.current;
    setMatchBusy(true);
    try {
      const body = {
        slots: parseResult.slots.map((s) => ({
          slot_id: s.slot_id,
          filament_type: s.filament_type,
          color_hex: s.color_hex,
          used_g: s.used_g,
        })),
        top_n: 5,
      };
      const data = await api.post("/api/v1/pro/intake/match", body);
      // A reset/new file superseded this match — drop the stale response.
      if (isStale()) return;
      setMatchResults(data.results || []);
      // Seed default choices
      const defaults = {};
      (data.results || []).forEach((r) => {
        if (r.suggestions && r.suggestions.length > 0) {
          const s = r.suggestions[0];
          defaults[r.slot_id] = {
            product_id: s.product_id,
            sku: s.sku,
            name: s.name,
          };
        }
      });
      setMatchChoices(defaults);
      setStep(3);
    } catch (err) {
      if (isStale()) return;
      toast.error(err.message || "Spool match failed");
    } finally {
      if (!isStale()) {
        setMatchBusy(false);
      }
    }
  };

  // ---------------------------------------------------------------------------
  // Unified flow — Step 2 → 3: catalog material selection (replaces /match)
  // ---------------------------------------------------------------------------

  /**
   * Unified-flow replacement for /match: build one selector row per parsed slot,
   * pre-filled from the nearest purchasable catalog item for that slot's
   * material_type + color_hex. The operator can override via the full catalog
   * dropdown, so there is no zero-suggestions dead end. The chosen product is
   * written into the SAME matchChoices[slot_id] = { product_id, sku, name } shape
   * so buildSlotsPayload and the allSlotsMatched gate are unchanged. /match is
   * still consulted (best effort) to honor sticky operator memory, but never
   * blocks, and sticky ids are validated against the catalog before use. When the
   * catalog is empty or fails to load, advances Step 3 into an explicit,
   * recoverable error state (materialsError) rather than an empty-selector trap.
   * @returns {Promise<void>}
   */
  const runMaterialSelect = async () => {
    // Capture a monotonic token so any state updates from a stale invocation
    // (one that started before a Reset or new-file drop) are suppressed.
    const requestId = ++materialSelectRequestIdRef.current;
    const isStale = () => requestId !== materialSelectRequestIdRef.current;
    setMatchBusy(true);
    setMaterialsError(null);
    try {
      // Ensure the catalog is loaded (drop-time fetch may still be in flight).
      // Track a hard fetch failure separately from an empty result so the
      // operator gets "couldn't load" vs "catalog is empty".
      let items = bomMaterials;
      let fetchFailed = false;
      if (items.length === 0) {
        // Bump the catalog-fetch token so any in-flight loadBomMaterials request
        // (from the drop-time call) is treated as stale and won't overwrite the
        // result we're about to set here.
        const catalogRequestId = ++bomMaterialsRequestIdRef.current;
        try {
          const data = await api.get("/api/v1/materials/for-bom");
          if (isStale()) return;
          items = Array.isArray(data?.items) ? data.items : [];
          // Only write if still the current request (avoids a race with a
          // concurrent retry from the Step 1 UI).
          if (catalogRequestId === bomMaterialsRequestIdRef.current) {
            setBomMaterials(items);
          }
        } catch {
          if (isStale()) return;
          items = [];
          fetchFailed = true;
        }
      }
      // No purchasable materials → the per-slot selectors would render empty
      // with no dropdown options, and allSlotsMatched could never become true.
      // Surface an explicit, recoverable state instead of advancing into that
      // dead-end. (This is the failure mode the unified flow was meant to kill.)
      if (items.length === 0) {
        if (isStale()) return;
        const mode = fetchFailed ? "failed" : "empty";
        setMaterialsError(mode);
        if (fetchFailed) {
          toast.error(
            "Couldn't load the purchasable materials catalog. Check your connection and try again."
          );
        } else {
          toast.error(
            "No purchasable materials found. Add materials to your catalog, then retry."
          );
        }
        // Render Step 3 in its error/empty state rather than a trap.
        setMatchResults(parseResult.slots.map((s) => ({ slot_id: s.slot_id })));
        setMatchChoices({});
        setStep(3);
        return;
      }
      // Optional sticky seed from /match (non-blocking, never a hard gate).
      let stickyBySlot = {};
      try {
        const body = {
          slots: parseResult.slots.map((s) => ({
            slot_id: s.slot_id,
            filament_type: s.filament_type,
            color_hex: s.color_hex,
            used_g: s.used_g,
          })),
          top_n: 5,
        };
        const data = await api.post("/api/v1/pro/intake/match", body);
        if (isStale()) return;
        (data.results || []).forEach((r) => {
          if (r.sticky && r.suggestions && r.suggestions.length > 0) {
            stickyBySlot[r.slot_id] = r.suggestions[0];
          }
        });
      } catch {
        if (isStale()) return;
        // ignore — pre-fill falls back to nearest catalog match
      }
      // One synthetic "result" per slot so the render + allSlotsMatched gate
      // iterate slots uniformly.
      const results = parseResult.slots.map((s) => ({ slot_id: s.slot_id }));
      const defaults = {};
      parseResult.slots.forEach((s) => {
        // Honor an already-chosen material for this slot if it's still in the
        // catalog — e.g. a bare mesh whose staging catalog pick was pre-seeded
        // into matchChoices. That explicit operator choice is the source of
        // truth and must not be clobbered by an auto nearest-match.
        const preChosen = matchChoices[s.slot_id];
        if (
          preChosen?.product_id != null &&
          items.some((it) => String(it.id) === String(preChosen.product_id))
        ) {
          defaults[s.slot_id] = preChosen;
          return;
        }
        // A sticky /match suggestion only seeds the slot if the remembered
        // product is still in the purchasable catalog — otherwise the selector
        // can't display it and allSlotsMatched would pass on an item /preview
        // and /sku can't validate. Resolve it against `items` first; if it's
        // gone, fall through to the nearest catalog match.
        const sticky = stickyBySlot[s.slot_id];
        const stickyItem = sticky
          ? items.find(
              (it) => String(it.id) === String(sticky.product_id)
            )
          : null;
        if (stickyItem) {
          defaults[s.slot_id] = {
            product_id: stickyItem.id,
            sku: stickyItem.sku,
            name: stickyItem.name,
          };
          return;
        }
        const match = nearestCatalogMatch(items, s.filament_type, s.color_hex);
        if (match) {
          defaults[s.slot_id] = {
            product_id: match.id,
            sku: match.sku,
            name: match.name,
          };
        }
      });
      if (isStale()) return;
      setMatchResults(results);
      setMatchChoices(defaults);
      setStep(3);
    } catch (err) {
      if (isStale()) return;
      toast.error(err.message || "Failed to load materials");
    } finally {
      if (!isStale()) {
        setMatchBusy(false);
      }
    }
  };

  // ---------------------------------------------------------------------------
  // Step 3 → 4: GET /context
  // ---------------------------------------------------------------------------

  const buildSuggestedSku = (name) =>
    `INTAKE-${(name || "").toUpperCase().replace(/[^A-Z0-9]+/g, "-").replace(/^-+|-+$/g, "")}`;

  const runContext = async () => {
    setContextBusy(true);
    try {
      const data = await api.get("/api/v1/pro/intake/context");
      setContext(data);
      // Default print work center from printer map
      const mapped =
        data.printer_work_center_map?.[parseResult.printer_model];
      const mappedWcId = mapped?.work_center_id
        ? String(mapped.work_center_id)
        : null;
      if (mappedWcId) {
        setPrintWorkCenterId(mappedWcId);
      }
      // Seed SKU code from product name unless the operator has edited it
      if (!skuEdited && productName) {
        setSkuCode(buildSuggestedSku(productName));
      }
      // Fetch item categories (non-fatal — wizard works without them)
      try {
        const cats = await api.get("/api/v1/items/categories");
        setCategories(Array.isArray(cats) ? cats : []);
      } catch {
        // Clear stale options so a later failure can't submit an outdated category_id
        setCategories([]);
      }
      setStep(4);
      // Kick off preview now that we have the work center (if available)
      if (mappedWcId) {
        runPreview({ printWorkCenterId: mappedWcId });
      }
    } catch (err) {
      toast.error(err.message || "Failed to load context");
    } finally {
      setContextBusy(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Step 4 → 5: POST /sku
  // ---------------------------------------------------------------------------

  const runCreateSku = async () => {
    setSkuBusy(true);
    try {
      const body = {
        name: productName,
        actual_price: Number(actualPrice),
        print_work_center_id: Number(printWorkCenterId),
        print_time_seconds: parseResult.print_time_seconds,
        parts_on_plate: partsOnPlate,
        sku: skuCode || undefined,
        item_type: itemType,
        category_id: categoryId ? Number(categoryId) : undefined,
        slots: buildSlotsPayload(),
        finishing_ops: finishingOps
          .filter((o) => o.work_center_id)
          .map((o) => ({
            work_center_id: Number(o.work_center_id),
            operation_name: o.operation_name,
            run_time_minutes: Number(o.run_time_minutes) || 0,
            setup_time_minutes: Number(o.setup_time_minutes) || 0,
            materials: (o.materials || []).map((m) => ({
              component_product_id: m.component_id,
              quantity: Number(m.quantity) || 0,
              unit: m.unit || "EA",
              quantity_per: m.quantity_per || "unit",
              scrap_factor: Number(m.scrap_factor) || 0,
            })),
          })),
        packaging: [],
        persist_color_map: true,
      };
      const data = await api.post("/api/v1/pro/intake/sku", body);
      // Persist the printable slice file non-fatally — the SKU is already created.
      const createdId = data.product?.id;
      // SERVER-SLICED inputs (a raw .3mf, or a bare .stl/.obj) carry the worker
      // artifact ids in the parse contract: gcode_3mf_artifact_id is the
      // exported printable .gcode.3mf, gcode_artifact_id is the raw per-plate
      // G-code (its presence flags "this was sliced server-side"). For those,
      // the source upload is NOT the slice file, so we fetch + persist the
      // worker's .gcode.3mf by id instead. A pre-sliced .gcode.3mf upload has
      // neither id (it's parsed, not sliced) and IS the slice file itself.
      const sliceArtifactId = parseResult?.gcode_3mf_artifact_id;
      const isServerSliced = Boolean(parseResult?.gcode_artifact_id);
      const src = sourceFileRef.current;
      if (createdId && sliceArtifactId) {
        try {
          const res = await fetch(
            `${API_URL}/api/v1/pro/intake/products/${createdId}/slice-file-from-artifact`,
            {
              method: "POST",
              credentials: "include",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                gcode_artifact_id: sliceArtifactId,
                filename: `${productName || data.product?.sku || "model"}.gcode.3mf`,
              }),
            }
          );
          setSliceFileSaved(res.ok);
        } catch {
          setSliceFileSaved(false);
        }
      } else if (
        createdId &&
        !isServerSliced &&
        src &&
        src.name.toLowerCase().endsWith(".gcode.3mf")
      ) {
        // Pre-sliced .gcode.3mf upload: the uploaded file IS the printable
        // slice file — persist it directly (unchanged path). Requiring the
        // .gcode.3mf extension here (not just "not a bare mesh") guarantees we
        // never persist a raw .3mf source even under FE/backend version skew
        // where the parse contract lacks the artifact ids. Server-sliced inputs
        // whose worker produced no .gcode.3mf are intentionally skipped.
        try {
          const fd = new FormData();
          fd.append("file", src);
          const res = await fetch(
            `${API_URL}/api/v1/pro/intake/products/${createdId}/slice-file`,
            { method: "POST", credentials: "include", body: fd }
          );
          setSliceFileSaved(res.ok);
        } catch {
          setSliceFileSaved(false);
        }
      }
      setSkuResult(data);
      setStep(5);
      toast.success(`SKU ${data.product?.sku} created`);
    } catch (err) {
      toast.error(err.message || "SKU creation failed");
    } finally {
      setSkuBusy(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Shared slot-payload builder (used by /preview and /sku)
  // ---------------------------------------------------------------------------

  const buildSlotsPayload = () =>
    (parseResult?.slots || []).map((s) => ({
      slot_id: s.slot_id,
      filament_type: s.filament_type,
      color_hex: s.color_hex,
      used_g: s.used_g,
      spool_product_id: matchChoices[s.slot_id]?.product_id,
    }));

  // ---------------------------------------------------------------------------
  // Step 4 — /preview (cost estimate before committing)
  // ---------------------------------------------------------------------------

  const runPreview = async (overrides = {}) => {
    const wcId = overrides.printWorkCenterId ?? printWorkCenterId;
    const parts = overrides.partsOnPlate ?? partsOnPlate;
    const ops = overrides.finishingOps ?? finishingOps;
    if (!wcId || !parseResult) return;
    // Token this request; a newer call invalidates anything in flight.
    const requestId = ++previewRequestIdRef.current;
    setPreviewBusy(true);
    try {
      const body = {
        print_work_center_id: Number(wcId),
        print_time_seconds: parseResult.print_time_seconds,
        parts_on_plate: parts,
        slots: buildSlotsPayload(),
        finishing_ops: ops
          .filter((o) => o.work_center_id)
          .map((o) => ({
            work_center_id: Number(o.work_center_id),
            operation_name: o.operation_name,
            run_time_minutes: Number(o.run_time_minutes) || 0,
            setup_time_minutes: Number(o.setup_time_minutes) || 0,
            materials: (o.materials || []).map((m) => ({
              component_product_id: m.component_id,
              quantity: Number(m.quantity) || 0,
              unit: m.unit || "EA",
              quantity_per: m.quantity_per || "unit",
              scrap_factor: Number(m.scrap_factor) || 0,
            })),
          })),
        packaging: [],
      };
      const data = await api.post("/api/v1/pro/intake/preview", body);
      // A newer preview started while we awaited — drop this stale response.
      if (requestId !== previewRequestIdRef.current) return;
      setEstimatedCost(data);
      if (!priceEditedRef.current && data.suggested_price != null) {
        setActualPrice(String(data.suggested_price));
      }
    } catch {
      if (requestId === previewRequestIdRef.current) {
        setEstimatedCost(null);
      }
    } finally {
      if (requestId === previewRequestIdRef.current) {
        setPreviewBusy(false);
      }
    }
  };

  // ---------------------------------------------------------------------------
  // Reset
  // ---------------------------------------------------------------------------

  const handleReset = () => {
    setStep(1);
    setDragActive(false);
    setUploadBusy(false);
    setBusyMode("parsing");
    // bare-mesh staging + picker
    setPendingMesh(null);
    setSliceMaterial("PLA Basic");
    setSlicePrinter("X1C");
    setSliceQuality("standard");
    setStagedMaterial(null);
    setSliceProfileOverride("");
    setParseResult(null);
    setProductName("");
    setMatchResults(null);
    setMatchBusy(false);
    setMatchChoices({});
    // Invalidate any in-flight /preparse before clearing its result state —
    // a slow response from the old file can't repopulate preparseResult and
    // reopen the stale picker. Mirror the drop-zone new-file reset path.
    preparseRequestIdRef.current += 1;
    setPreparseResult(null);
    preparseResultRef.current = null;
    // Multi-plate: clear the chosen plate and any file held for the picker.
    setSelectedPlateIndex(null);
    pendingPlateFileRef.current = null;
    setMaterialsError(null);
    setBomMaterialsLoading(false);
    setBomMaterialsError(null);
    setReconcileNotice(null);
    setContext(null);
    setContextBusy(false);
    setPrintWorkCenterId("");
    setFinishingOps([]);
    setMatModalOpIdx(null);
    setActualPrice("");
    setSkuResult(null);
    setSkuBusy(false);
    // new UX state
    setPartsOnPlate(1);
    setSkuCode("");
    setSkuEdited(false);
    setEstimatedCost(null);
    setPreviewBusy(false);
    priceEditedRef.current = false;
    // Invalidate any preview still in flight so its response is ignored.
    previewRequestIdRef.current += 1;
    // Invalidate any catalog fetch still in flight (same pattern as
    // resetDerivedStateForNewFile).
    bomMaterialsRequestIdRef.current += 1;
    // Invalidate any runMaterialSelect still in flight so a stale call cannot
    // call setMatchResults/setStep(3) after the reset clears parseResult.
    materialSelectRequestIdRef.current += 1;
    // Invalidate any upload (slice/parse) still in flight so a slow response
    // can't re-apply stale parseResult/matchChoices or jump to Step 2 post-reset.
    uploadRequestIdRef.current += 1;
    // Invalidate any legacy /match still in flight (gate-off path) so it can't
    // re-apply stale matchResults / jump to Step 3 after this reset.
    matchRequestIdRef.current += 1;
    // item type / category
    setItemType("finished_good");
    setCategoryId(null);
    setCategories([]);
    // slice file
    sourceFileRef.current = null;
    setSliceFileSaved(false);
  };

  // ---------------------------------------------------------------------------
  // Validate match step: every slot must have a chosen product_id
  // ---------------------------------------------------------------------------

  const allSlotsMatched =
    matchResults != null &&
    matchResults.every(
      (r) => matchChoices[r.slot_id]?.product_id != null
    );

  // Multi-plate (unified flow): a dropped .3mf/.gcode.3mf whose pre-parse found
  // more than one plate is held (pendingPlateFileRef) and the PlatePicker is
  // shown instead of auto-parsing. `isRawPreparse` distinguishes a raw .3mf
  // (plates carry name/object_count, picking slices that plate) from a sliced
  // .gcode.3mf (plates carry weight/time/slots). Inert when the gate is off.
  const isMultiPlatePending =
    unifiedFlow && (preparseResult?.plate_count ?? 1) > 1;
  const isRawPreparse = preparseResult?.kind === "raw3mf";

  // ---------------------------------------------------------------------------
  // Finishing ops helpers
  // ---------------------------------------------------------------------------

  const addFinishingOp = () => {
    const next = [
      ...finishingOps,
      {
        work_center_id: "",
        operation_name: "",
        run_time_minutes: "",
        setup_time_minutes: "",
        materials: [],
      },
    ];
    setFinishingOps(next);
    runPreview({ finishingOps: next });
  };

  const updateFinishingOp = (idx, field, value) => {
    const next = finishingOps.map((op, i) =>
      i === idx ? { ...op, [field]: value } : op
    );
    setFinishingOps(next);
    runPreview({ finishingOps: next });
  };

  const removeFinishingOp = (idx) => {
    const next = finishingOps.filter((_, i) => i !== idx);
    setFinishingOps(next);
    runPreview({ finishingOps: next });
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6 p-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Intake Studio</h1>
        <p className="text-gray-400 mt-1">
          Drop a sliced file and create a sellable SKU in minutes
        </p>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* STEP 1 — Upload                                                     */}
      {/* ------------------------------------------------------------------ */}
      {step === 1 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <StepHeader step={1} total={5} label="Upload file" />

          {uploadBusy ? (
            <div className="flex flex-col items-center justify-center py-16 gap-4">
              <Spinner />
              {busyMode === "slicing" ? (
                <>
                  <p className="text-gray-400">Slicing your model…</p>
                  <p className="text-gray-600 text-sm">
                    This can take a minute or two — Bambu Studio is slicing on the server.
                  </p>
                </>
              ) : (
                <p className="text-gray-400">Parsing file…</p>
              )}
            </div>
          ) : pendingMesh ? (
            /* Slicing-profile picker for a staged bare mesh (.stl/.obj) */
            <div className="space-y-5">
              {unifiedFlow && <PreParsePanel preparse={preparseResult} />}
              <div className="flex items-center gap-3 text-sm text-gray-300">
                <svg
                  className="w-5 h-5 text-blue-400 flex-shrink-0"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
                  />
                </svg>
                <span className="font-medium text-white">{pendingMesh.name}</span>
              </div>
              <h2 className="text-base font-semibold text-white">
                Slicing options
              </h2>
              {unifiedFlow ? (
                <p className="text-gray-500 text-sm">
                  A bare model has no embedded profile. Pick the purchasable
                  material you&apos;ll print it in — that one choice drives both
                  how it&apos;s sliced and its cost. Choose a printer and quality
                  to slice against.
                </p>
              ) : (
                <p className="text-gray-500 text-sm">
                  A bare model has no embedded profile, so it&apos;s sliced on the
                  server using a reference profile. Pick the material, printer and
                  quality to slice against.
                </p>
              )}

              {unifiedFlow && bomMaterials.length === 0 ? (
                // Three distinct states — never a silent permanent banner.
                // Loading: fetch in flight. Empty: catalog resolved with no
                // purchasable materials. Failed: fetch errored. Both empty and
                // failed are recoverable via Retry, mirroring runMaterialSelect.
                bomMaterialsLoading ? (
                  <div className="text-gray-400 text-sm bg-gray-800/50 border border-gray-700 rounded-lg p-3 flex items-center gap-3">
                    <span className="inline-block w-3 h-3 rounded-full border-2 border-gray-500 border-t-transparent animate-spin" />
                    <span>Loading your purchasable materials…</span>
                  </div>
                ) : (
                  <div className="text-yellow-400/90 text-sm bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3 flex items-center gap-3">
                    <span>
                      {bomMaterialsError === "failed"
                        ? "Couldn't load your purchasable materials catalog. Check your connection and retry."
                        : "No purchasable materials in your catalog. Add materials, then retry."}
                    </span>
                    <button
                      onClick={() => {
                        // Bump the token so the outgoing stale request (if any)
                        // is ignored once the retry's response arrives.
                        bomMaterialsRequestIdRef.current += 1;
                        setBomMaterials([]);
                        loadBomMaterials();
                      }}
                      className="ml-auto border border-yellow-500/40 text-yellow-300 hover:bg-yellow-500/10 px-3 py-1 rounded-lg text-xs transition-colors"
                    >
                      Retry
                    </button>
                  </div>
                )
              ) : (
                unifiedFlow && (
                  <BareMeshMaterialPicker
                    items={bomMaterials}
                    chosen={stagedMaterial}
                    onPick={(item) => {
                      // The staged pick is the single source of truth. If the
                      // operator changes to a different material TYPE, drop any
                      // advanced slice-profile override so it can't silently keep
                      // driving the slice for the now-discarded material. A
                      // same-type color change preserves a deliberate override.
                      if (
                        sliceProfileOverride &&
                        item?.material_code !== stagedMaterial?.material_code
                      ) {
                        setSliceProfileOverride("");
                      }
                      setStagedMaterial(item);
                    }}
                  />
                )
              )}
              {unifiedFlow && stagedMaterial && (
                (() => {
                  const derived = catalogMaterialToSliceProfile(stagedMaterial);
                  const effective = sliceProfileOverride || derived.profile;
                  return (
                    <div className="space-y-2">
                      <p className="text-gray-400 text-xs">
                        Slice profile:{" "}
                        <span className="text-gray-200 font-medium">
                          {effective}
                        </span>
                        {sliceProfileOverride ? (
                          <>
                            <span className="text-yellow-500/90">
                              {" "}
                              (overridden)
                            </span>
                            <button
                              type="button"
                              onClick={() => setSliceProfileOverride("")}
                              className="ml-2 text-blue-400 hover:text-blue-300 underline"
                            >
                              Reset to auto
                            </button>
                          </>
                        ) : derived.exact ? (
                          <span className="text-gray-600"> (matched)</span>
                        ) : (
                          <span className="text-gray-600"> (auto)</span>
                        )}
                      </p>
                      {!sliceProfileOverride && !derived.exact && (
                        <p className="text-yellow-400/90 text-xs bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-2">
                          No exact slice profile for{" "}
                          {stagedMaterial.material_code || "this material"}; using{" "}
                          {derived.profile} — adjust in advanced if needed.
                        </p>
                      )}
                      <details className="text-xs">
                        <summary className="cursor-pointer text-gray-500 hover:text-gray-400">
                          Advanced: override slice profile
                        </summary>
                        <div className="mt-2">
                          <select
                            value={sliceProfileOverride}
                            onChange={(e) =>
                              setSliceProfileOverride(e.target.value)
                            }
                            className="w-full md:w-72 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                          >
                            <option value="">
                              Auto (from material) — {derived.profile}
                            </option>
                            {SLICE_MATERIALS.map((m) => (
                              <option key={m.value} value={m.value}>
                                {m.label}
                              </option>
                            ))}
                          </select>
                        </div>
                      </details>
                    </div>
                  );
                })()
              )}

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Material — most important (legacy SLICE_MATERIALS picker) */}
                {!unifiedFlow && (
                <div className="md:col-span-3">
                  <label
                    htmlFor="slice-material"
                    className="block text-sm font-medium text-gray-300 mb-1"
                  >
                    Material
                  </label>
                  <select
                    id="slice-material"
                    value={sliceMaterial}
                    onChange={(e) => setSliceMaterial(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                  >
                    {SLICE_MATERIALS.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </div>
                )}
                <div>
                  <label
                    htmlFor="slice-printer"
                    className="block text-sm text-gray-400 mb-1"
                  >
                    Printer
                  </label>
                  <select
                    id="slice-printer"
                    value={slicePrinter}
                    onChange={(e) => setSlicePrinter(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                  >
                    {SLICE_PRINTERS.map((p) => (
                      <option key={p.value} value={p.value}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label
                    htmlFor="slice-quality"
                    className="block text-sm text-gray-400 mb-1"
                  >
                    Quality
                  </label>
                  <select
                    id="slice-quality"
                    value={sliceQuality}
                    onChange={(e) => setSliceQuality(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                  >
                    {SLICE_QUALITIES.map((q) => (
                      <option key={q.value} value={q.value}>
                        {q.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="flex items-center gap-3 pt-2">
                <button
                  onClick={sliceAndContinue}
                  disabled={unifiedFlow && !stagedMaterial}
                  className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-6 py-2 rounded-lg font-medium transition-colors"
                >
                  Slice &amp; continue
                </button>
                {unifiedFlow && !stagedMaterial && (
                  <span className="text-gray-500 text-sm">
                    Pick a material to continue
                  </span>
                )}
                <button
                  onClick={() => setPendingMesh(null)}
                  className="border border-gray-700 text-gray-400 hover:bg-gray-800 hover:text-gray-300 px-4 py-2 rounded-lg transition-colors"
                >
                  Choose a different file
                </button>
              </div>
            </div>
          ) : isMultiPlatePending ? (
            /* Multi-plate file: pick a single plate before parsing/slicing. */
            <div className="space-y-5">
              <PreParsePanel preparse={preparseResult} />
              <PlatePicker
                plates={preparseResult?.plates || []}
                isRaw={isRawPreparse}
                selectedPlateIndex={selectedPlateIndex}
                onSelect={setSelectedPlateIndex}
              />
              <div className="flex items-center gap-3 pt-1">
                <button
                  onClick={continueWithSelectedPlate}
                  disabled={selectedPlateIndex == null}
                  className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-6 py-2 rounded-lg font-medium transition-colors"
                >
                  {isRawPreparse ? "Slice & continue" : "Continue"}
                </button>
                {selectedPlateIndex == null && (
                  <span className="text-gray-500 text-sm">
                    Pick a plate to continue
                  </span>
                )}
                <button
                  onClick={handleReset}
                  className="border border-gray-700 text-gray-400 hover:bg-gray-800 hover:text-gray-300 px-4 py-2 rounded-lg transition-colors"
                >
                  Choose a different file
                </button>
              </div>
            </div>
          ) : (
            <div
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-lg p-16 text-center transition-colors ${
                dragActive
                  ? "border-blue-500 bg-blue-500/10"
                  : "border-gray-700 hover:border-gray-600"
              }`}
            >
              <svg
                className="w-16 h-16 mx-auto text-gray-500 mb-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                />
              </svg>
              <p className="text-lg font-medium text-white mb-2">
                Drop a 3D model (.stl/.obj) or a Bambu .3mf here
              </p>
              <p className="text-gray-400 text-sm mb-4">or</p>
              <label className="inline-block bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-medium cursor-pointer transition-colors">
                Browse Files
                <input
                  type="file"
                  accept=".3mf,.gcode.3mf,.stl,.obj"
                  onChange={handleFileInput}
                  className="hidden"
                />
              </label>
              <p className="text-gray-600 text-xs mt-4">
                Bare .stl/.obj meshes are sliced on a reference profile (you pick
                material/printer/quality next); raw .3mf is sliced on upload; pre-sliced
                .gcode.3mf is instant.
              </p>
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* STEP 2 — Review                                                     */}
      {/* ------------------------------------------------------------------ */}
      {step === 2 && parseResult && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <StepHeader step={2} total={5} label="Review" />

          <div className="flex flex-col lg:flex-row gap-6 mb-6">
            {/* Thumbnail */}
            {parseResult.thumbnail_base64 && (
              <div className="flex-shrink-0">
                <img
                  alt="plate"
                  src={`data:${parseResult.thumbnail_mime || "image/png"};base64,${parseResult.thumbnail_base64}`}
                  className="w-48 h-48 object-contain rounded-lg border border-gray-700 bg-gray-800"
                />
              </div>
            )}

            {/* Summary */}
            <div className="flex-1 space-y-4">
              {/* Product name */}
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Product name
                </label>
                <input
                  type="text"
                  value={productName}
                  onChange={(e) => setProductName(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                />
              </div>

              {/* Chips */}
              <div className="flex flex-wrap gap-2">
                {parseResult.printer_model && (
                  <span className="px-3 py-1 rounded-full bg-gray-800 border border-gray-700 text-sm text-gray-300">
                    {parseResult.printer_model}
                  </span>
                )}
                {parseResult.nozzle_diameter_mm != null && (
                  <span className="px-3 py-1 rounded-full bg-gray-800 border border-gray-700 text-sm text-gray-300">
                    {parseResult.nozzle_diameter_mm} mm nozzle
                  </span>
                )}
                {parseResult.print_time_seconds != null && (
                  <span className="px-3 py-1 rounded-full bg-gray-800 border border-gray-700 text-sm text-gray-300">
                    {secondsToHms(parseResult.print_time_seconds)}
                  </span>
                )}
                {parseResult.total_weight_g != null && (
                  <span className="px-3 py-1 rounded-full bg-gray-800 border border-gray-700 text-sm text-gray-300">
                    {parseResult.total_weight_g} g
                  </span>
                )}
                {parseResult.plate_index != null && (
                  <span className="px-3 py-1 rounded-full bg-gray-800 border border-gray-700 text-sm text-gray-300">
                    Plate {parseResult.plate_index}
                  </span>
                )}
                {parseResult.is_multi_material && (
                  <span className="px-3 py-1 rounded-full bg-blue-500/20 border border-blue-500/40 text-sm text-blue-300">
                    Multi-material
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Slots table */}
          <div className="overflow-x-auto mb-4">
            <table className="w-full text-sm">
              <thead className="bg-gray-800/50">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase">
                    AMS
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase">
                    Color
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase">
                    Type
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase">
                    Material
                  </th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-400 uppercase">
                    Grams
                  </th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-400 uppercase">
                    Meters
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {parseResult.slots.map((slot) => (
                  <tr key={slot.slot_id} className="hover:bg-gray-800/30">
                    <td className="px-3 py-2 text-gray-300">
                      {slot.ams_slot ?? slot.tray ?? "—"}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <span
                          className="inline-block w-4 h-4 rounded border border-gray-600"
                          style={{
                            backgroundColor: slot.color_hex || "#888",
                          }}
                        />
                        <span className="text-gray-300 font-mono text-xs">
                          {slot.color_hex || "—"}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-gray-300">
                      {slot.filament_type || "—"}
                    </td>
                    <td className="px-3 py-2 text-gray-400 text-xs">
                      {[slot.filament_profile, slot.filament_vendor]
                        .filter(Boolean)
                        .join(" · ") || "—"}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-300">
                      {slot.used_g != null ? slot.used_g.toFixed(1) : "—"}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-300">
                      {slot.used_m != null ? slot.used_m.toFixed(2) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Warnings */}
          {parseResult.warnings && parseResult.warnings.length > 0 && (
            <div className="mb-4 text-yellow-400 text-sm bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
              {parseResult.warnings.map((w, i) => (
                <p key={i}>{w}</p>
              ))}
            </div>
          )}

          {/* Buttons */}
          <div className="flex justify-between pt-2">
            <div className="flex gap-2">
              <button
                onClick={() => setStep(1)}
                className="border border-gray-700 text-gray-300 hover:bg-gray-800 px-4 py-2 rounded-lg transition-colors"
              >
                Back
              </button>
              <button
                onClick={handleReset}
                className="border border-gray-700 text-gray-500 hover:bg-gray-800 hover:text-gray-300 px-4 py-2 rounded-lg transition-colors"
              >
                Start over
              </button>
            </div>
            <button
              onClick={runMatch}
              disabled={matchBusy || !productName.trim()}
              className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
            >
              {matchBusy && <Spinner />}
              {unifiedFlow ? "Next: select material" : "Next: match spools"}
            </button>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* STEP 3 — Match                                                      */}
      {/* ------------------------------------------------------------------ */}
      {step === 3 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <StepHeader
            step={3}
            total={5}
            label={unifiedFlow ? "Select material" : "Match spools"}
          />

          {matchBusy || matchResults == null ? (
            <div className="flex items-center justify-center py-12">
              <Spinner />
            </div>
          ) : (
            <>
              {unifiedFlow && reconcileNotice && (
                <div className="mb-4 text-yellow-400 text-sm bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
                  {reconcileNotice}
                </div>
              )}
              {unifiedFlow && materialsError ? (
                <div className="mb-6 bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-5 text-center">
                  <p className="text-yellow-300 font-medium mb-1">
                    {materialsError === "failed"
                      ? "Couldn't load the materials catalog"
                      : "No purchasable materials found"}
                  </p>
                  <p className="text-gray-400 text-sm mb-4">
                    {materialsError === "failed"
                      ? "The purchasable materials catalog failed to load. Check your connection, then retry."
                      : "Add purchasable materials to your catalog, then retry to continue selecting a material for each slot."}
                  </p>
                  <button
                    onClick={() => {
                      setBomMaterials([]);
                      setMaterialsError(null);
                      runMaterialSelect();
                    }}
                    disabled={matchBusy}
                    className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg transition-colors"
                  >
                    Retry
                  </button>
                </div>
              ) : (
              <div className="space-y-4 mb-6">
                {matchResults.map((result) => {
                  const slot = parseResult.slots.find(
                    (s) => s.slot_id === result.slot_id
                  );
                  const chosen = matchChoices[result.slot_id];

                  // Unified flow: catalog-driven type → color selectors. Always
                  // has the full purchasable catalog, so no dead-end.
                  if (unifiedFlow) {
                    return (
                      <MaterialSelectRow
                        key={result.slot_id}
                        slot={slot}
                        slotId={result.slot_id}
                        items={bomMaterials}
                        chosen={chosen}
                        onPick={(item) =>
                          setMatchChoices((prev) => ({
                            ...prev,
                            [result.slot_id]: {
                              product_id: item.id,
                              sku: item.sku,
                              name: item.name,
                            },
                          }))
                        }
                      />
                    );
                  }

                  const options = result.suggestions.map((s) => ({
                    id: s.product_id,
                    name: `${s.name} (${s.sku}) — ${s.color_name} · Δ${Math.round(s.color_distance)}`,
                    sku: s.sku,
                  }));

                  return (
                    <div
                      key={result.slot_id}
                      className="bg-gray-800/50 rounded-lg p-4"
                    >
                      <div className="flex items-center gap-3 mb-3">
                        <span
                          className="inline-block w-5 h-5 rounded border border-gray-600 flex-shrink-0"
                          style={{
                            backgroundColor: slot?.color_hex || "#888",
                          }}
                        />
                        <span className="text-white font-medium">
                          {slot?.filament_type || `Slot ${result.slot_id}`}
                        </span>
                        <span className="text-gray-400 text-sm">
                          {result.used_g != null
                            ? `${result.used_g.toFixed(1)} g`
                            : ""}
                        </span>
                        {result.sticky && (
                          <span className="ml-auto text-xs text-green-400 bg-green-500/10 border border-green-500/30 px-2 py-0.5 rounded-full">
                            ✓ remembered
                          </span>
                        )}
                      </div>

                      {result.suggestions.length === 0 ? (
                        <p className="text-yellow-400 text-sm">
                          No match — pick manually
                        </p>
                      ) : (
                        <SearchableSelect
                          options={options}
                          value={chosen?.product_id != null ? String(chosen.product_id) : ""}
                          onChange={(val) => {
                            const s = result.suggestions.find(
                              (x) => String(x.product_id) === val
                            );
                            if (s) {
                              setMatchChoices((prev) => ({
                                ...prev,
                                [result.slot_id]: {
                                  product_id: s.product_id,
                                  sku: s.sku,
                                  name: s.name,
                                },
                              }));
                            }
                          }}
                          placeholder="Select spool…"
                          displayKey="name"
                          valueKey="id"
                          formatOption={(opt) => opt.name}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
              )}

              <div className="flex justify-between">
                <button
                  onClick={() => setStep(2)}
                  className="border border-gray-700 text-gray-300 hover:bg-gray-800 px-4 py-2 rounded-lg transition-colors"
                >
                  Back
                </button>
                <button
                  onClick={() => {
                    if (!allSlotsMatched) {
                      toast.error(
                        unifiedFlow
                          ? "Every slot must have a material selected before continuing"
                          : "Every slot must have a spool selected before continuing"
                      );
                      return;
                    }
                    runContext();
                  }}
                  disabled={contextBusy}
                  className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
                >
                  {contextBusy && <Spinner />}
                  Next: finishing &amp; price
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* STEP 4 — Configure                                                  */}
      {/* ------------------------------------------------------------------ */}
      {step === 4 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <StepHeader step={4} total={5} label="Configure & price" />

          {contextBusy || context == null ? (
            <div className="flex items-center justify-center py-12">
              <Spinner />
            </div>
          ) : (
            <>
              {/* Print work center */}
              <div className="mb-6">
                <h2 className="text-base font-semibold text-white mb-3">
                  Print work center
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">
                      Work center
                    </label>
                    <SearchableSelect
                      options={(context.work_centers || [])
                        .filter((wc) => wc.is_active)
                        .map((wc) => ({
                          id: wc.id,
                          name: `${wc.name} (${wc.code}) — $${wc.total_rate_per_hour}/hr`,
                          sku: wc.code,
                        }))}
                      value={printWorkCenterId}
                      onChange={(v) => {
                        setPrintWorkCenterId(v);
                        runPreview({ printWorkCenterId: v });
                      }}
                      placeholder="Select work center…"
                      displayKey="name"
                      valueKey="id"
                      formatOption={(opt) => opt.name}
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">
                      Print time
                    </label>
                    <div className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white">
                      {secondsToHms(parseResult.print_time_seconds)}
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">
                      Parts on this plate
                    </label>
                    <input
                      type="number"
                      min="1"
                      value={partsOnPlate}
                      onChange={(e) => {
                        const v = Math.max(1, parseInt(e.target.value, 10) || 1);
                        setPartsOnPlate(v);
                        runPreview({ partsOnPlate: v });
                      }}
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                    />
                    <p className="text-gray-600 text-xs mt-1">
                      Per-unit cost = plate &divide; parts.
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">
                      SKU code
                    </label>
                    <input
                      type="text"
                      value={skuCode}
                      onChange={(e) => {
                        setSkuCode(e.target.value);
                        setSkuEdited(true);
                      }}
                      placeholder="INTAKE-MY-PRODUCT"
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                    />
                    <p className="text-gray-600 text-xs mt-1">
                      Letters, numbers, hyphens — auto-uppercased on save.
                    </p>
                  </div>
                </div>
              </div>

              {/* Product details */}
              <div className="mb-6">
                <h2 className="text-base font-semibold text-white mb-3">
                  Product details
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">
                      Item type
                    </label>
                    <select
                      value={itemType}
                      onChange={(e) => setItemType(e.target.value)}
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                    >
                      {INTAKE_ITEM_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">
                      Category
                      <span className="text-gray-600 font-normal ml-1">
                        (optional)
                      </span>
                      {categoryId && (
                        <button
                          type="button"
                          onClick={() => setCategoryId(null)}
                          className="ml-2 text-xs text-blue-400 hover:text-blue-300"
                        >
                          Clear
                        </button>
                      )}
                    </label>
                    <SearchableSelect
                      options={categories.map((cat) => ({
                        id: cat.id,
                        name: cat.full_path || cat.name,
                      }))}
                      value={categoryId != null ? String(categoryId) : ""}
                      onChange={(val) => setCategoryId(val || null)}
                      placeholder="No category…"
                      displayKey="name"
                      valueKey="id"
                      formatOption={(opt) => opt.name}
                    />
                  </div>
                </div>
              </div>

              {/* Finishing ops */}
              <div className="mb-6">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-base font-semibold text-white">
                    Finishing operations
                    <span className="text-gray-500 font-normal text-sm ml-2">
                      (optional)
                    </span>
                  </h2>
                  <button
                    onClick={addFinishingOp}
                    className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1 transition-colors"
                  >
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 4v16m8-8H4"
                      />
                    </svg>
                    Add operation
                  </button>
                </div>

                {finishingOps.length === 0 ? (
                  <p className="text-gray-600 text-sm">
                    No finishing operations — click "Add operation" to include
                    post-print steps like support removal or painting.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {finishingOps.map((op, idx) => (
                      <div
                        key={idx}
                        className="bg-gray-800/50 rounded-lg p-4 space-y-3"
                      >
                        {/* Op fields row */}
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
                          <div>
                            <label className="block text-xs text-gray-400 mb-1">
                              Work center
                            </label>
                            <SearchableSelect
                              options={(context.work_centers || [])
                                .filter((wc) => wc.is_active)
                                .map((wc) => ({
                                  id: wc.id,
                                  name: `${wc.name} (${wc.code})`,
                                  sku: wc.code,
                                }))}
                              value={op.work_center_id ? String(op.work_center_id) : ""}
                              onChange={(val) =>
                                updateFinishingOp(idx, "work_center_id", val)
                              }
                              placeholder="Work center…"
                              displayKey="name"
                              valueKey="id"
                              formatOption={(opt) => opt.name}
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-gray-400 mb-1">
                              Operation name
                            </label>
                            <input
                              type="text"
                              value={op.operation_name}
                              onChange={(e) =>
                                updateFinishingOp(
                                  idx,
                                  "operation_name",
                                  e.target.value
                                )
                              }
                              placeholder="e.g. Support removal"
                              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-gray-400 mb-1">
                              Run time (min)
                            </label>
                            <input
                              type="number"
                              min="0"
                              value={op.run_time_minutes}
                              onChange={(e) =>
                                updateFinishingOp(
                                  idx,
                                  "run_time_minutes",
                                  e.target.value
                                )
                              }
                              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                            />
                          </div>
                          <div className="flex gap-2 items-end">
                            <div className="flex-1">
                              <label className="block text-xs text-gray-400 mb-1">
                                Setup (min)
                              </label>
                              <input
                                type="number"
                                min="0"
                                value={op.setup_time_minutes}
                                onChange={(e) =>
                                  updateFinishingOp(
                                    idx,
                                    "setup_time_minutes",
                                    e.target.value
                                  )
                                }
                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                              />
                            </div>
                            <button
                              onClick={() => removeFinishingOp(idx)}
                              className="text-gray-500 hover:text-red-400 p-2 transition-colors flex-shrink-0"
                              title="Remove"
                            >
                              <svg
                                className="w-4 h-4"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M6 18L18 6M6 6l12 12"
                                />
                              </svg>
                            </button>
                          </div>
                        </div>

                        {/* Materials sub-section */}
                        <div className="border-t border-gray-700 pt-2">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs text-gray-500">
                              Materials
                            </span>
                            <button
                              onClick={() => setMatModalOpIdx(idx)}
                              className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 transition-colors"
                            >
                              <svg
                                className="w-3 h-3"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M12 4v16m8-8H4"
                                />
                              </svg>
                              + Add material
                            </button>
                          </div>
                          {(op.materials || []).length > 0 && (
                            <div className="space-y-1">
                              {(op.materials || []).map((m, mIdx) => (
                                <div
                                  key={mIdx}
                                  className="flex items-center justify-between text-xs text-gray-300 bg-gray-800 rounded px-2 py-1"
                                >
                                  <span>
                                    {m.component_sku} — {m.component_name} · {m.quantity} {m.unit}
                                  </span>
                                  <button
                                    onClick={() => {
                                      const next = finishingOps.map((o, i) =>
                                        i === idx
                                          ? { ...o, materials: o.materials.filter((_, mi) => mi !== mIdx) }
                                          : o
                                      );
                                      setFinishingOps(next);
                                      runPreview({ finishingOps: next });
                                    }}
                                    className="text-gray-500 hover:text-red-400 ml-2 transition-colors"
                                    title="Remove material"
                                  >
                                    ×
                                  </button>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Pricing */}
              <div className="mb-6">
                <h2 className="text-base font-semibold text-white mb-3">
                  Pricing
                </h2>

                {/* Estimated cost panel — shown BEFORE the price input */}
                <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 mb-4">
                  {previewBusy && (
                    <p className="text-gray-400 text-sm">Calculating…</p>
                  )}
                  {!previewBusy && estimatedCost == null && (
                    <p className="text-gray-500 text-sm">
                      Pick a work center to estimate cost.
                    </p>
                  )}
                  {!previewBusy && estimatedCost != null && (
                    <>
                      <div className="flex items-baseline gap-3 mb-3">
                        <span className="text-2xl font-bold text-white">
                          ${Number(estimatedCost.per_unit_cost || 0).toFixed(2)}
                        </span>
                        <span className="text-gray-400 text-sm">
                          estimated cost per unit
                        </span>
                      </div>
                    </>
                  )}
                </div>

                <div className="flex justify-end mb-2">
                  <button
                    type="button"
                    onClick={() => runPreview()}
                    disabled={previewBusy || !printWorkCenterId}
                    className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    Recalculate cost
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-3">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">
                      Selling price ($)
                    </label>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={actualPrice}
                      onChange={(e) => {
                        setActualPrice(e.target.value);
                        priceEditedRef.current = true;
                      }}
                      placeholder="0.00"
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                    />
                  </div>
                </div>
                {/* Retail / Wholesale price box */}
                {(() => {
                  const cost = Number(estimatedCost?.per_unit_cost) || 0;
                  const tiers = context.margin_tiers || [];
                  const defaultMargin = context.default_margin_percent;
                  const priceLevels = context.price_levels || [];
                  const currentPrice = Number(actualPrice) || 0;

                  // Retail price for a given margin %
                  const retailFor = (m) =>
                    cost > 0 && m < 100 ? cost / (1 - m / 100) : null;

                  // Baseline for wholesale: use actualPrice if set, else fall back
                  // to the default-tier retail, else 0
                  const defaultRetail =
                    defaultMargin != null ? (retailFor(defaultMargin) ?? 0) : 0;
                  const wholesaleBase = currentPrice > 0 ? currentPrice : defaultRetail;

                  const hasCost = cost > 0;
                  const hasTiers = tiers.length > 0;
                  const hasLevels = priceLevels.length > 0;

                  if (!hasTiers && !hasLevels) {
                    // Nothing to show — render the minimal tax/fee note only
                    return (
                      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-3 text-sm text-blue-300">
                        <p className="text-gray-400 text-xs">
                          Tax (
                          {context.tax?.enabled
                            ? `${((context.tax.rate || 0) * 100).toFixed(1)}% ${context.tax.name || ""}`
                            : "disabled"}
                          ) and CC fee (
                          {context.cc_fee_percent != null
                            ? `${context.cc_fee_percent}%`
                            : "—"}
                          ) are configured in Company Settings.
                        </p>
                      </div>
                    );
                  }

                  return (
                    <div className="border border-gray-700 rounded-lg overflow-hidden text-sm">
                      {/* Cost row */}
                      <div className="flex justify-between items-center px-4 py-3 bg-gray-800/60">
                        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                          Cost
                        </span>
                        {hasCost ? (
                          <span className="font-semibold text-white">
                            ${cost.toFixed(2)}
                            <span className="text-gray-500 font-normal ml-1">/ unit</span>
                          </span>
                        ) : (
                          <span className="text-gray-600 italic text-xs">
                            enter work center to calculate
                          </span>
                        )}
                      </div>

                      {/* Retail tiers */}
                      {hasTiers && (
                        <>
                          <div className="px-4 py-2 bg-gray-800/30 border-t border-gray-700">
                            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                              Retail
                              <span className="font-normal normal-case ml-1 text-gray-600">
                                (suggested by margin)
                              </span>
                            </span>
                          </div>
                          {tiers.map((m) => {
                            const price = retailFor(m);
                            const isDefault = m === defaultMargin;
                            return (
                              <div
                                key={m}
                                className={`flex items-center justify-between px-4 py-2 border-t border-gray-700/60 ${
                                  isDefault
                                    ? "bg-blue-500/10"
                                    : "hover:bg-gray-800/30"
                                } transition-colors`}
                              >
                                <div className="flex items-center gap-2">
                                  <span
                                    className={
                                      isDefault ? "text-blue-300" : "text-gray-400"
                                    }
                                  >
                                    {m}% margin
                                  </span>
                                  {isDefault && (
                                    <span className="text-yellow-400 text-xs" title="default">
                                      ★
                                    </span>
                                  )}
                                </div>
                                <div className="flex items-center gap-3">
                                  {price != null ? (
                                    <span
                                      className={`font-semibold ${
                                        isDefault ? "text-green-400" : "text-white"
                                      }`}
                                    >
                                      ${price.toFixed(2)}
                                    </span>
                                  ) : (
                                    <span className="text-gray-600 italic text-xs">—</span>
                                  )}
                                  {price != null && (
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setActualPrice(price.toFixed(2));
                                        priceEditedRef.current = true;
                                      }}
                                      className="text-xs text-blue-400 hover:text-blue-300 border border-blue-500/40 hover:border-blue-400 px-2 py-0.5 rounded transition-colors"
                                    >
                                      Use
                                    </button>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </>
                      )}

                      {/* Wholesale price levels */}
                      {hasLevels && (
                        <>
                          <div className="px-4 py-2 bg-gray-800/30 border-t border-gray-700">
                            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
                              Wholesale
                              <span className="font-normal normal-case ml-1 text-gray-600">
                                (price levels — live off selling price)
                              </span>
                            </span>
                          </div>
                          {priceLevels.map((level) => {
                            const disc = Number(level.discount_percent) || 0;
                            const wp =
                              wholesaleBase > 0
                                ? wholesaleBase * (1 - disc / 100)
                                : null;
                            return (
                              <div
                                key={level.id}
                                className="flex items-center justify-between px-4 py-2 border-t border-gray-700/60 hover:bg-gray-800/30 transition-colors"
                              >
                                <div className="flex items-center gap-2">
                                  <span className="text-gray-400">
                                    {level.name || level.code}
                                  </span>
                                  {disc > 0 && (
                                    <span className="text-gray-600 text-xs">
                                      {disc}% off
                                    </span>
                                  )}
                                </div>
                                {wp != null ? (
                                  <span className="font-semibold text-white">
                                    ${wp.toFixed(2)}
                                  </span>
                                ) : (
                                  <span className="text-gray-600 italic text-xs">
                                    set a price above
                                  </span>
                                )}
                              </div>
                            );
                          })}
                        </>
                      )}

                      {/* Tax / fee footnote */}
                      <div className="px-4 py-2 border-t border-gray-700 bg-gray-800/20">
                        <p className="text-gray-600 text-xs">
                          Tax (
                          {context.tax?.enabled
                            ? `${((context.tax.rate || 0) * 100).toFixed(1)}% ${context.tax.name || ""}`
                            : "disabled"}
                          ) and CC fee (
                          {context.cc_fee_percent != null
                            ? `${context.cc_fee_percent}%`
                            : "—"}
                          ) are configured in Company Settings.
                        </p>
                      </div>
                    </div>
                  );
                })()}
              </div>

              <div className="flex justify-between">
                <button
                  onClick={() => setStep(3)}
                  className="border border-gray-700 text-gray-300 hover:bg-gray-800 px-4 py-2 rounded-lg transition-colors"
                >
                  Back
                </button>
                <button
                  onClick={runCreateSku}
                  disabled={
                    skuBusy ||
                    !printWorkCenterId ||
                    !actualPrice ||
                    Number(actualPrice) <= 0
                  }
                  className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
                >
                  {skuBusy && <Spinner />}
                  Create SKU
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Operation Material Modal (wizard / collect-into-state mode)        */}
      {/* ------------------------------------------------------------------ */}
      <OperationMaterialModal
        isOpen={matModalOpIdx !== null}
        operationId={null}
        material={null}
        defaultTypeFilter="all"
        onClose={() => setMatModalOpIdx(null)}
        onSave={(mat) => {
          const next = finishingOps.map((op, i) =>
            i === matModalOpIdx ? { ...op, materials: [...(op.materials || []), mat] } : op
          );
          setFinishingOps(next);
          setMatModalOpIdx(null);
          runPreview({ finishingOps: next });
        }}
      />

      {/* ------------------------------------------------------------------ */}
      {/* STEP 5 — Result                                                     */}
      {/* ------------------------------------------------------------------ */}
      {step === 5 && skuResult && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <StepHeader step={5} total={5} label="Done" />

          <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4 mb-6 flex items-center gap-3">
            <svg
              className="w-6 h-6 text-green-400 flex-shrink-0"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <div>
              <p className="text-green-400 font-semibold">SKU created</p>
              <p className="text-gray-300 text-sm">
                {skuResult.product?.name}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            {/* Product */}
            <div className="bg-gray-800/50 rounded-lg p-4 space-y-2">
              <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
                Product
              </h3>
              <p className="text-white font-mono text-lg">
                {skuResult.product?.sku}
              </p>
              <p className="text-gray-300">{skuResult.product?.name}</p>
              <p className="text-green-400 font-semibold text-lg">
                ${Number(skuResult.selling_price || 0).toFixed(2)}
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                <span className="px-2 py-0.5 rounded-full bg-gray-700 border border-gray-600 text-xs text-gray-300">
                  {INTAKE_ITEM_TYPES.find((t) => t.value === itemType)?.label ?? itemType}
                </span>
                {categoryId && categories.length > 0 && (
                  <span className="px-2 py-0.5 rounded-full bg-gray-700 border border-gray-600 text-xs text-gray-300">
                    {categories.find((c) => String(c.id) === String(categoryId))?.full_path ||
                      categories.find((c) => String(c.id) === String(categoryId))?.name ||
                      `Category #${categoryId}`}
                  </span>
                )}
              </div>
            </div>

            {/* Cost breakdown */}
            <div className="bg-gray-800/50 rounded-lg p-4 space-y-2">
              <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
                Cost breakdown
              </h3>
              {skuResult.cost && (
                <>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">Routing cost (materials + labor)</span>
                    <span className="text-white">
                      ${Number(skuResult.cost.routing_cost || 0).toFixed(2)}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm border-t border-gray-700 pt-2">
                    <span className="text-gray-400">Total cost</span>
                    <span className="text-white font-semibold">
                      ${Number(skuResult.cost.total_cost || 0).toFixed(2)}
                    </span>
                  </div>
                  {skuResult.cost.cost_source && (
                    <p className="text-gray-600 text-xs">
                      Source: {skuResult.cost.cost_source}
                    </p>
                  )}
                </>
              )}
              <div className="flex justify-between text-sm pt-1">
                <span className="text-gray-400">Margin vs cost</span>
                <span className="text-blue-300">
                  {skuResult.margin_vs_cost_percent != null
                    ? `${Number(skuResult.margin_vs_cost_percent).toFixed(1)}%`
                    : "—"}
                </span>
              </div>
            </div>

            {/* Routing (materials live on the operations) */}
            <div className="bg-gray-800/50 rounded-lg p-4 space-y-1">
              <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
                Routing
              </h3>
              <p className="text-white font-mono">
                {skuResult.routing?.code}
              </p>
              <p className="text-gray-400 text-sm">
                {skuResult.routing?.operation_count} operation
                {skuResult.routing?.operation_count !== 1 ? "s" : ""}
                {" · "}
                {skuResult.routing?.material_count} material
                {skuResult.routing?.material_count !== 1 ? "s" : ""}
              </p>
            </div>
          </div>

          {skuResult.sticky_mappings_saved != null && (
            <p className="text-gray-500 text-sm mb-6">
              Saved {skuResult.sticky_mappings_saved} color mapping
              {skuResult.sticky_mappings_saved !== 1 ? "s" : ""} for future
              use.
            </p>
          )}

          <div className="flex items-center gap-4">
            <button
              onClick={handleReset}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
            >
              Create another
            </button>
            {skuResult.product?.id && (
              <a
                href="/admin/items"
                className="border border-gray-700 text-gray-300 hover:bg-gray-800 px-4 py-2 rounded-lg transition-colors"
              >
                View / edit product
              </a>
            )}
            {sliceFileSaved && skuResult.product?.id && (
              <a
                href={`${API_URL}/api/v1/pro/intake/products/${skuResult.product.id}/slice-file`}
                className="border border-gray-700 text-gray-300 hover:bg-gray-800 px-4 py-2 rounded-lg transition-colors"
                download
              >
                Download slice file
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
