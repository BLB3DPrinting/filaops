import { useRef, useState } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";
import { API_URL } from "../../config/api";
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
// Main page
// ---------------------------------------------------------------------------

export default function AdminIntakeStudio() {
  const toast = useToast();
  const api = useApi();
  const { isPro, loading: flagsLoading } = useFeatureFlags();

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

  // Step 2 — Review
  const [parseResult, setParseResult] = useState(null);
  const [productName, setProductName] = useState("");

  // Step 3 — Match
  const [matchResults, setMatchResults] = useState(null);
  const [matchBusy, setMatchBusy] = useState(false);
  // map slot_id -> { product_id, sku, name }
  const [matchChoices, setMatchChoices] = useState({});

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
    setSliceMaterial("PLA Basic");
    setSlicePrinter("X1C");
    setSliceQuality("standard");
    // Step 2 — Review
    setParseResult(null);
    setProductName("");
    // Step 3 — Match
    setMatchResults(null);
    setMatchBusy(false);
    setMatchChoices({});
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
    if (isBareMesh(name)) {
      // Stage the mesh and reveal the slicing-profile picker; don't POST yet —
      // the slice needs a material/printer/quality first.
      setPendingMesh(f);
      return;
    }
    // .3mf / .gcode.3mf keep the immediate behavior.
    uploadIntakeFile(f);
  };

  // Shared upload → /parse. When a mesh profile is supplied, append the
  // material/printer/quality form fields the server uses to slice the bare mesh.
  const uploadIntakeFile = async (f, profile = null) => {
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
      if (!res.ok) {
        toast.error(data.detail || `Parse failed (${res.status})`);
        return;
      }
      setPendingMesh(null);
      setParseResult(data);
      setProductName(data.model_name || "");
      setStep(2);
    } catch (err) {
      toast.error(err.message || "Upload failed");
    } finally {
      setUploadBusy(false);
    }
  };

  const sliceAndContinue = () => {
    if (!pendingMesh) return;
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
      toast.error(err.message || "Spool match failed");
    } finally {
      setMatchBusy(false);
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
    setParseResult(null);
    setProductName("");
    setMatchResults(null);
    setMatchBusy(false);
    setMatchChoices({});
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
              <p className="text-gray-500 text-sm">
                A bare model has no embedded profile, so it&apos;s sliced on the
                server using a reference profile. Pick the material, printer and
                quality to slice against.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Material — most important */}
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
                  className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-medium transition-colors"
                >
                  Slice &amp; continue
                </button>
                <button
                  onClick={() => setPendingMesh(null)}
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
              Next: match spools
            </button>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* STEP 3 — Match                                                      */}
      {/* ------------------------------------------------------------------ */}
      {step === 3 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <StepHeader step={3} total={5} label="Match spools" />

          {matchBusy || matchResults == null ? (
            <div className="flex items-center justify-center py-12">
              <Spinner />
            </div>
          ) : (
            <>
              <div className="space-y-4 mb-6">
                {matchResults.map((result) => {
                  const slot = parseResult.slots.find(
                    (s) => s.slot_id === result.slot_id
                  );
                  const options = result.suggestions.map((s) => ({
                    id: s.product_id,
                    name: `${s.name} (${s.sku}) — ${s.color_name} · Δ${Math.round(s.color_distance)}`,
                    sku: s.sku,
                  }));
                  const chosen = matchChoices[result.slot_id];

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
                        "Every slot must have a spool selected before continuing"
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
