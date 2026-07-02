import { useState } from "react";
import { useApi } from "../../../hooks/useApi";
import { useToast } from "../../../components/Toast";
import SearchableSelect from "../../../components/SearchableSelect";
import OperationMaterialModal from "../../../components/OperationMaterialModal";

// ---------------------------------------------------------------------------
// Assembly Intake panel (unified flow, raw multi-plate .3mf only).
//
// Rendered by AdminIntakeStudio AFTER a slice-ALL-plates async job completes
// (POST /parse-async with NO plate_index → worker --slice 0 → every plate
// sliced in one job). The parse contract's plates[] — one entry per sliced
// plate with plate_index (1-based), total_weight_g, print_time_seconds and a
// full per-plate slots[] breakdown — drives the component table below.
//
// One submit → POST /api/v1/pro/intake/assembly creates N component products
// (one per plate, each with its own material BOM + print routing op) plus the
// parent finished-good assembly BOM (components + optional glue/packaging
// lines + optional assembly routing op) in a single transaction. The endpoint
// ships in the PR1 wheel; a 404 here means the backend wheel predates it, so
// we surface a deploy hint instead of a generic failure.
// ---------------------------------------------------------------------------

/** Mirror of AdminIntakeStudio's secondsToHms (not exported there — a page
 * module; importing it here would create a page↔panel import cycle). */
function secondsToHms(s) {
  if (!s) return "0m";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0 && m > 0) return `${h}h ${m}m`;
  if (h > 0) return `${h}h`;
  return `${m}m`;
}

/** Mirror of AdminIntakeStudio's buildSuggestedSku — same INTAKE- convention
 * so assembly SKUs sort next to single-plate intake SKUs. */
const buildSuggestedSku = (name) =>
  `INTAKE-${(name || "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")}`;

/**
 * Component SKU preview: {PARENT-SKU}-P{nn} (nn = 1-based plate_index, zero
 * padded to 2). Derived live from the assembly SKU field so the table always
 * previews exactly what will be POSTed.
 * @param {string} parentSku - the assembly SKU (may be empty while typing).
 * @param {number} plateIndex - the plate's 1-based plate_index.
 * @returns {string} the derived component SKU ("" when no parent SKU yet).
 */
const componentSkuFor = (parentSku, plateIndex) => {
  const base = (parentSku || "").trim().toUpperCase();
  if (!base) return "";
  return `${base}-P${String(plateIndex).padStart(2, "0")}`;
};

/**
 * One catalog material pick for the WHOLE assembly (type → color, sourced
 * from /materials/for-bom). Mirrors AdminIntakeStudio's BareMeshMaterialPicker
 * (not exported there — page module, and importing the page here would be a
 * cycle). A raw .3mf slices with its EMBEDDED settings, so this pick does not
 * drive the slice — it only prices the filament: the chosen purchasable item
 * becomes spool_product_id on every slot of every plate component.
 * @param {object} props
 * @param {Array<object>} props.items - the purchasable catalog (/materials/for-bom).
 * @param {object|null} props.chosen - the currently-chosen catalog item, or null.
 * @param {(item: object) => void} props.onPick - called with the picked catalog item.
 * @returns {JSX.Element}
 */
function AssemblyMaterialPicker({ items, chosen, onPick }) {
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

/**
 * Assembly intake panel: component table (one row per sliced plate) +
 * assembly form → POST /api/v1/pro/intake/assembly.
 *
 * The parent guarantees a fresh mount per slice-all run (assemblyParse is
 * nulled by every reset/new-file path before it can be set again), so all
 * plate-derived state is safely seeded in useState initializers — no effects.
 *
 * @param {object} props
 * @param {object} props.parse - the slice-all parse contract (model_name,
 *   plate_count, plates[] with per-plate slots/grams/time).
 * @param {object|null} props.context - the /context payload (work_centers…),
 *   or null when its fetch failed — the panel then offers a retry.
 * @param {boolean} props.contextLoading - true while /context is being fetched.
 * @param {() => void} props.onRetryContext - re-fetch /context.
 * @param {Array<object>} props.materials - the purchasable catalog
 *   (/materials/for-bom items) backing the single material pick.
 * @param {boolean} props.materialsLoading - true while the catalog fetch is in flight.
 * @param {string|null} props.materialsError - "empty" | "failed" | null.
 * @param {() => void} props.onRetryMaterials - re-fetch the catalog.
 * @param {() => void} props.onStartOver - full wizard reset (back to the drop zone).
 * @returns {JSX.Element}
 */
export default function AssemblyIntakePanel({
  parse,
  context,
  contextLoading,
  onRetryContext,
  materials,
  materialsLoading,
  materialsError,
  onRetryMaterials,
  onStartOver,
}) {
  const api = useApi();
  const toast = useToast();

  const plates = Array.isArray(parse?.plates) ? parse.plates : [];
  const modelName = parse?.model_name || "model";

  // One editable row per sliced plate. plate_index is read VERBATIM from the
  // contract (1-based, value-matched server-side — never synthesized from
  // array position, mirroring the PlatePicker's round-trip rule).
  const [componentRows, setComponentRows] = useState(() =>
    plates.map((p) => ({
      plate_index: p.plate_index,
      name: `${modelName} — Plate ${p.plate_index}`,
      quantity: "1",
    }))
  );

  // Assembly form state.
  const [assemblyName, setAssemblyName] = useState(modelName);
  const [assemblySku, setAssemblySku] = useState(buildSuggestedSku(modelName));
  // Once the operator edits the SKU by hand it stops tracking the name
  // (same skuEdited pattern as Step 4's SKU field).
  const [skuEdited, setSkuEdited] = useState(false);
  const [actualPrice, setActualPrice] = useState("");
  const [pickedMaterial, setPickedMaterial] = useState(null);
  const [printWorkCenterId, setPrintWorkCenterId] = useState("");
  const [assemblyWorkCenterId, setAssemblyWorkCenterId] = useState("");
  const [assemblyRunMinutes, setAssemblyRunMinutes] = useState("");
  const [assemblySetupMinutes, setAssemblySetupMinutes] = useState("");
  // Optional BOM extras, collected via the same OperationMaterialModal used by
  // Step 4's finishing-op materials. Each entry is the modal's onSave payload
  // ({ component_id, quantity, unit, quantity_per, scrap_factor,
  //    component_sku, component_name }).
  const [glueMaterials, setGlueMaterials] = useState([]);
  const [packagingLines, setPackagingLines] = useState([]);
  // Which list the (single, shared) material modal is adding to.
  const [modalTarget, setModalTarget] = useState(null); // "glue" | "packaging" | null
  const [createBusy, setCreateBusy] = useState(false);
  // The 201 response — set switches the panel to the success view.
  const [result, setResult] = useState(null);

  const plateByIndex = (plateIndex) =>
    plates.find((p) => p.plate_index === plateIndex);

  const updateRow = (plateIndex, field, value) => {
    setComponentRows((prev) =>
      prev.map((r) =>
        r.plate_index === plateIndex ? { ...r, [field]: value } : r
      )
    );
  };

  // ---------------------------------------------------------------------------
  // Validation (drives both the disabled state and the pre-submit toasts)
  // ---------------------------------------------------------------------------

  const rowsValid =
    componentRows.length > 0 &&
    componentRows.every(
      (r) => r.name.trim() && Number(r.quantity) >= 0.001
    );
  const canCreate =
    !createBusy &&
    context != null &&
    pickedMaterial != null &&
    printWorkCenterId !== "" &&
    assemblyName.trim() !== "" &&
    Number(actualPrice) > 0 &&
    rowsValid;

  // ---------------------------------------------------------------------------
  // Client-side cost estimate — cheap and purely informational. Sums per-plate
  // material (grams × picked material $/kg) + machine time (hours × print WC
  // rate), each × the row quantity, plus optional assembly labor. Glue and
  // packaging are NOT included (no client-side unit costs); the BOM rollup
  // after creation is authoritative.
  // ---------------------------------------------------------------------------

  const estimatedCost = (() => {
    if (!pickedMaterial || !printWorkCenterId || !context) return null;
    const wcById = new Map(
      (context.work_centers || []).map((wc) => [String(wc.id), wc])
    );
    const printRate =
      Number(wcById.get(String(printWorkCenterId))?.total_rate_per_hour) || 0;
    const costPerKg = Number(pickedMaterial.standard_cost) || 0;
    let total = 0;
    for (const row of componentRows) {
      const plate = plateByIndex(row.plate_index);
      const qty = Number(row.quantity) || 0;
      const grams = Number(plate?.total_weight_g) || 0;
      const hours = (Number(plate?.print_time_seconds) || 0) / 3600;
      total += qty * ((grams * costPerKg) / 1000 + hours * printRate);
    }
    if (assemblyWorkCenterId) {
      const aRate =
        Number(wcById.get(String(assemblyWorkCenterId))?.total_rate_per_hour) ||
        0;
      const minutes =
        (Number(assemblyRunMinutes) || 0) + (Number(assemblySetupMinutes) || 0);
      total += (minutes / 60) * aRate;
    }
    return total;
  })();

  // ---------------------------------------------------------------------------
  // Create → POST /assembly
  // ---------------------------------------------------------------------------

  const handleCreate = async () => {
    if (!canCreate) {
      toast.error(
        "Pick a material, a print work center, a selling price, and give every component a name and a quantity of at least 0.001."
      );
      return;
    }
    setCreateBusy(true);
    try {
      const parentSku = assemblySku.trim();
      const body = {
        assembly: {
          name: assemblyName.trim(),
          sku: parentSku || undefined,
          actual_price: Number(actualPrice),
          unit: "EA",
          glue_materials: glueMaterials.map((m) => ({
            component_product_id: m.component_id,
            quantity: Number(m.quantity) || 0,
            unit: m.unit || "EA",
            quantity_per: m.quantity_per || "unit",
            scrap_factor: Number(m.scrap_factor) || 0,
          })),
          packaging: packagingLines.map((m) => ({
            component_product_id: m.component_id,
            quantity: Number(m.quantity) || 0,
            unit: m.unit || "EA",
          })),
          // Assembly routing op is optional and only meaningful with a work
          // center — minutes without one are ignored at build time (the inputs
          // are disabled in the UI until a work center is chosen).
          ...(assemblyWorkCenterId
            ? {
                assembly_work_center_id: Number(assemblyWorkCenterId),
                assembly_run_time_minutes: Number(assemblyRunMinutes) || 0,
                assembly_setup_minutes: Number(assemblySetupMinutes) || 0,
              }
            : {}),
        },
        components: componentRows.map((row) => {
          const plate = plateByIndex(row.plate_index);
          // Full per-plate slot fan-out: the contract's plates[] carries each
          // plate's real slot breakdown (slot_id/filament_type/color_hex/
          // used_g), so every component gets its true multi-material grams —
          // the ONE picked purchasable material is applied as spool_product_id
          // on every slot (single material pick for the whole assembly).
          // Defensive fallback: a plate whose slots[] is somehow empty fans its
          // total grams into one synthetic slot so its material cost isn't
          // silently dropped.
          const plateSlots =
            Array.isArray(plate?.slots) && plate.slots.length > 0
              ? plate.slots
              : [
                  {
                    slot_id: 0,
                    filament_type: null,
                    color_hex: null,
                    used_g: plate?.total_weight_g ?? 0,
                  },
                ];
          return {
            plate_index: row.plate_index,
            name: row.name.trim(),
            sku: componentSkuFor(parentSku, row.plate_index) || undefined,
            quantity: Number(row.quantity),
            print_work_center_id: Number(printWorkCenterId),
            print_time_seconds: plate?.print_time_seconds ?? 0,
            parts_on_plate: 1,
            // Same SkuSlotMap shape the single-plate /sku payload builds
            // (AdminIntakeStudio buildSlotsPayload).
            slots: plateSlots.map((s) => ({
              slot_id: s.slot_id,
              filament_type: s.filament_type,
              color_hex: s.color_hex,
              used_g: s.used_g,
              spool_product_id: pickedMaterial.id,
            })),
          };
        }),
      };
      const data = await api.post("/api/v1/pro/intake/assembly", body);
      setResult(data);
      toast.success(`Assembly ${data.assembly?.sku || ""} created`);
    } catch (err) {
      // Deploy-ordering: /assembly ships in the PR1 wheel. A 404 means this
      // backend predates it — tell the operator what to deploy, not "failed".
      if (err?.status === 404) {
        toast.error(
          "Assembly intake needs the updated backend — deploy the latest wheel.",
          10000
        );
      } else {
        toast.error(err.message || "Assembly creation failed");
      }
    } finally {
      setCreateBusy(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Success view
  // ---------------------------------------------------------------------------

  if (result) {
    return (
      <div className="space-y-6">
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4 flex items-center gap-3">
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
            <p className="text-green-400 font-semibold">Assembly created</p>
            <p className="text-gray-300 text-sm">
              {result.components?.length ?? 0} component
              {(result.components?.length ?? 0) === 1 ? "" : "s"} + 1 assembly
              BOM
            </p>
          </div>
        </div>

        <div className="bg-gray-800/50 rounded-lg p-4 space-y-2">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
            Assembly
          </h3>
          <p className="text-white font-mono text-lg">
            {result.assembly?.sku}
          </p>
          <p className="text-gray-400 text-sm">
            BOM #{result.assembly?.bom_id} — open the BOM editor to review the
            cost rollup or adjust component lines.
          </p>
        </div>

        <div className="bg-gray-800/50 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-2">
            Components
          </h3>
          <div className="space-y-1">
            {(result.components || []).map((c) => (
              <div
                key={c.plate_index}
                className="flex items-center justify-between text-sm bg-gray-800 rounded px-3 py-1.5"
              >
                <span className="text-gray-400">Plate {c.plate_index}</span>
                <span className="text-white font-mono">{c.sku}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={onStartOver}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
          >
            Intake another file
          </button>
          <a
            href="/admin/bom"
            className="border border-gray-700 text-gray-300 hover:bg-gray-800 px-4 py-2 rounded-lg transition-colors"
          >
            Open BOM editor
          </a>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Form view
  // ---------------------------------------------------------------------------

  const totalGrams = plates.reduce(
    (sum, p) => sum + (Number(p.total_weight_g) || 0),
    0
  );
  const totalSeconds = plates.reduce(
    (sum, p) => sum + (Number(p.print_time_seconds) || 0),
    0
  );

  return (
    <div className="space-y-6">
      {/* Slice-all summary chips */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="px-3 py-1 rounded-full bg-blue-500/20 border border-blue-500/40 text-sm text-blue-300">
          Assembly intake
        </span>
        <span className="px-3 py-1 rounded-full bg-gray-800 border border-gray-700 text-sm text-gray-300">
          {plates.length} plate{plates.length === 1 ? "" : "s"} sliced
        </span>
        <span className="px-3 py-1 rounded-full bg-gray-800 border border-gray-700 text-sm text-gray-300">
          {totalGrams.toFixed(1)} g total
        </span>
        <span className="px-3 py-1 rounded-full bg-gray-800 border border-gray-700 text-sm text-gray-300">
          {secondsToHms(totalSeconds)} total
        </span>
        <span className="text-gray-400 text-sm ml-1 truncate">{modelName}</span>
      </div>

      {/* Material pick — ONE purchasable material for the whole assembly */}
      <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
        <h2 className="text-base font-semibold text-white mb-1">Material</h2>
        <p className="text-gray-500 text-sm mb-4">
          The plates were sliced with the file&apos;s embedded settings — this
          one pick prices the filament and becomes the material BOM line on
          every component.
        </p>
        {materials.length === 0 ? (
          materialsLoading ? (
            <div className="text-gray-400 text-sm bg-gray-800/50 border border-gray-700 rounded-lg p-3 flex items-center gap-3">
              <span className="inline-block w-3 h-3 rounded-full border-2 border-gray-500 border-t-transparent animate-spin" />
              <span>Loading your purchasable materials…</span>
            </div>
          ) : (
            <div className="text-yellow-400/90 text-sm bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3 flex items-center gap-3">
              <span>
                {materialsError === "failed"
                  ? "Couldn't load your purchasable materials catalog. Check your connection and retry."
                  : "No purchasable materials in your catalog. Add materials, then retry."}
              </span>
              <button
                onClick={onRetryMaterials}
                className="ml-auto border border-yellow-500/40 text-yellow-300 hover:bg-yellow-500/10 px-3 py-1 rounded-lg text-xs transition-colors"
              >
                Retry
              </button>
            </div>
          )
        ) : (
          <AssemblyMaterialPicker
            items={materials}
            chosen={pickedMaterial}
            onPick={setPickedMaterial}
          />
        )}
      </div>

      {/* Component table — one row per sliced plate */}
      <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
        <h2 className="text-base font-semibold text-white mb-1">
          Components ({componentRows.length})
        </h2>
        <p className="text-gray-500 text-sm mb-4">
          One printed component per plate. Grams and print time come from the
          slice; quantity is how many of that plate go into one assembly.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-800/50">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase">
                  Plate
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase">
                  Name
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase">
                  SKU
                </th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-400 uppercase">
                  Qty
                </th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-400 uppercase">
                  Grams
                </th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-400 uppercase">
                  Print time
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {componentRows.map((row) => {
                const plate = plateByIndex(row.plate_index);
                const skuPreview = componentSkuFor(
                  assemblySku,
                  row.plate_index
                );
                return (
                  <tr key={row.plate_index} className="hover:bg-gray-800/30">
                    <td className="px-3 py-2 text-gray-300 whitespace-nowrap">
                      Plate {row.plate_index}
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="text"
                        value={row.name}
                        onChange={(e) =>
                          updateRow(row.plate_index, "name", e.target.value)
                        }
                        className="w-full min-w-48 bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-white text-sm focus:outline-none focus:border-blue-500"
                      />
                    </td>
                    <td className="px-3 py-2 text-gray-400 font-mono text-xs whitespace-nowrap">
                      {skuPreview || "(set assembly SKU)"}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <input
                        type="number"
                        min="0.001"
                        step="any"
                        value={row.quantity}
                        onChange={(e) =>
                          updateRow(row.plate_index, "quantity", e.target.value)
                        }
                        className="w-20 bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-white text-sm text-right focus:outline-none focus:border-blue-500"
                      />
                    </td>
                    <td className="px-3 py-2 text-right text-gray-300 whitespace-nowrap">
                      {plate?.total_weight_g != null
                        ? Number(plate.total_weight_g).toFixed(1)
                        : "—"}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-300 whitespace-nowrap">
                      {plate?.print_time_seconds != null
                        ? secondsToHms(plate.print_time_seconds)
                        : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Assembly form */}
      <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 space-y-4">
        <h2 className="text-base font-semibold text-white">Assembly</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Name</label>
            <input
              type="text"
              value={assemblyName}
              onChange={(e) => {
                setAssemblyName(e.target.value);
                // SKU tracks the name until the operator edits it directly
                // (same behavior as Step 4's suggested SKU).
                if (!skuEdited) {
                  setAssemblySku(buildSuggestedSku(e.target.value));
                }
              }}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              SKU code
            </label>
            <input
              type="text"
              value={assemblySku}
              onChange={(e) => {
                setAssemblySku(e.target.value);
                setSkuEdited(true);
              }}
              placeholder="INTAKE-MY-ASSEMBLY"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
            />
            <p className="text-gray-600 text-xs mt-1">
              Component SKUs derive from this: {"{SKU}"}-P01, {"{SKU}"}-P02, …
            </p>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Selling price ($)
            </label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={actualPrice}
              onChange={(e) => setActualPrice(e.target.value)}
              placeholder="0.00"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        {/* Work centers — one print work center applied to ALL components */}
        {context == null ? (
          <div className="text-yellow-400/90 text-sm bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3 flex items-center gap-3">
            <span>
              {contextLoading
                ? "Loading work centers…"
                : "Couldn't load work centers. Check your connection and retry."}
            </span>
            {!contextLoading && (
              <button
                onClick={onRetryContext}
                className="ml-auto border border-yellow-500/40 text-yellow-300 hover:bg-yellow-500/10 px-3 py-1 rounded-lg text-xs transition-colors"
              >
                Retry
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Print work center
                <span className="text-gray-600 font-normal ml-1">
                  (applied to every component)
                </span>
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
                onChange={setPrintWorkCenterId}
                placeholder="Select work center…"
                displayKey="name"
                valueKey="id"
                formatOption={(opt) => opt.name}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Assembly work center
                <span className="text-gray-600 font-normal ml-1">
                  (optional)
                </span>
                {assemblyWorkCenterId && (
                  <button
                    type="button"
                    onClick={() => {
                      setAssemblyWorkCenterId("");
                      setAssemblyRunMinutes("");
                      setAssemblySetupMinutes("");
                    }}
                    className="ml-2 text-xs text-blue-400 hover:text-blue-300"
                  >
                    Clear
                  </button>
                )}
              </label>
              <SearchableSelect
                options={(context.work_centers || [])
                  .filter((wc) => wc.is_active)
                  .map((wc) => ({
                    id: wc.id,
                    name: `${wc.name} (${wc.code}) — $${wc.total_rate_per_hour}/hr`,
                    sku: wc.code,
                  }))}
                value={assemblyWorkCenterId}
                onChange={setAssemblyWorkCenterId}
                placeholder="No assembly operation…"
                displayKey="name"
                valueKey="id"
                formatOption={(opt) => opt.name}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Assembly run time (min)
              </label>
              <input
                type="number"
                min="0"
                value={assemblyRunMinutes}
                onChange={(e) => setAssemblyRunMinutes(e.target.value)}
                disabled={!assemblyWorkCenterId}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Assembly setup (min)
              </label>
              <input
                type="number"
                min="0"
                value={assemblySetupMinutes}
                onChange={(e) => setAssemblySetupMinutes(e.target.value)}
                disabled={!assemblyWorkCenterId}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
              />
            </div>
          </div>
        )}

        {/* Glue / consumables + packaging — optional BOM lines on the assembly */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[
            {
              key: "glue",
              label: "Glue / consumables",
              lines: glueMaterials,
              setLines: setGlueMaterials,
            },
            {
              key: "packaging",
              label: "Packaging",
              lines: packagingLines,
              setLines: setPackagingLines,
            },
          ].map(({ key, label, lines, setLines }) => (
            <div key={key} className="border border-gray-700 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-gray-500">
                  {label}{" "}
                  <span className="text-gray-600 font-normal">(optional)</span>
                </span>
                <button
                  onClick={() => setModalTarget(key)}
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
                  + Add
                </button>
              </div>
              {lines.length === 0 ? (
                <p className="text-gray-600 text-xs">None</p>
              ) : (
                <div className="space-y-1">
                  {lines.map((m, mIdx) => (
                    <div
                      key={mIdx}
                      className="flex items-center justify-between text-xs text-gray-300 bg-gray-800 rounded px-2 py-1"
                    >
                      <span>
                        {m.component_sku} — {m.component_name} · {m.quantity}{" "}
                        {m.unit}
                      </span>
                      <button
                        onClick={() =>
                          setLines(lines.filter((_, i) => i !== mIdx))
                        }
                        className="text-gray-500 hover:text-red-400 ml-2 transition-colors"
                        title="Remove"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Estimated cost — client-side, informational only */}
      <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
        {estimatedCost == null ? (
          <p className="text-gray-500 text-sm">
            Pick a material and a print work center to estimate cost.
          </p>
        ) : (
          <>
            <div className="flex items-baseline gap-3">
              <span className="text-2xl font-bold text-white">
                ${estimatedCost.toFixed(2)}
              </span>
              <span className="text-gray-400 text-sm">
                estimated assembly cost
              </span>
            </div>
            <p className="text-gray-600 text-xs mt-1">
              Client-side estimate (print material + machine time
              {assemblyWorkCenterId ? " + assembly labor" : ""}); glue and
              packaging excluded. The BOM cost rollup after creation is
              authoritative.
            </p>
          </>
        )}
      </div>

      {/* Actions */}
      <div className="flex justify-between">
        <button
          onClick={onStartOver}
          className="border border-gray-700 text-gray-500 hover:bg-gray-800 hover:text-gray-300 px-4 py-2 rounded-lg transition-colors"
        >
          Start over
        </button>
        <button
          onClick={handleCreate}
          disabled={!canCreate}
          className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
        >
          {createBusy && (
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
          )}
          Create {componentRows.length} component
          {componentRows.length === 1 ? "" : "s"} + assembly
        </button>
      </div>

      {/* Shared add-material modal (same component Step 4's finishing ops use) */}
      <OperationMaterialModal
        isOpen={modalTarget !== null}
        operationId={null}
        material={null}
        defaultTypeFilter={modalTarget === "packaging" ? "packaging" : "all"}
        onClose={() => setModalTarget(null)}
        onSave={(mat) => {
          if (mat) {
            if (modalTarget === "glue") {
              setGlueMaterials((prev) => [...prev, mat]);
            } else if (modalTarget === "packaging") {
              setPackagingLines((prev) => [...prev, mat]);
            }
          }
          setModalTarget(null);
        }}
      />
    </div>
  );
}
