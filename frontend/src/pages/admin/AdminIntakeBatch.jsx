import { useRef, useState } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";
import { API_URL } from "../../config/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function secondsToHms(s) {
  if (!s) return "—";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0 && m > 0) return `${h}h ${m}m`;
  if (h > 0) return `${h}h`;
  return `${m}m`;
}

function deriveName(filename) {
  // Strip .gcode.3mf first, then .3mf
  let n = filename;
  if (n.toLowerCase().endsWith(".gcode.3mf")) n = n.slice(0, -10);
  else if (n.toLowerCase().endsWith(".3mf")) n = n.slice(0, -4);
  return n;
}

function Spinner({ small = false }) {
  const cls = small
    ? "animate-spin rounded-full h-4 w-4 border-b-2 border-blue-400"
    : "animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500";
  return <div className={cls} />;
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

function StatusBadge({ status, unmatchedCount }) {
  if (status === "queued") {
    return (
      <span className="text-xs text-gray-400 bg-gray-700 px-2 py-0.5 rounded-full">
        queued
      </span>
    );
  }
  if (status === "parsing") {
    return (
      <span className="flex items-center gap-1 text-xs text-blue-300">
        <Spinner small />
        parsing…
      </span>
    );
  }
  if (status === "matching") {
    return (
      <span className="flex items-center gap-1 text-xs text-blue-300">
        <Spinner small />
        matching…
      </span>
    );
  }
  if (status === "ready") {
    return (
      <span className="text-xs text-green-400 bg-green-500/10 border border-green-500/30 px-2 py-0.5 rounded-full">
        ✓ ready
      </span>
    );
  }
  if (status === "needs-attention") {
    return (
      <span className="text-xs text-yellow-400 bg-yellow-500/10 border border-yellow-500/30 px-2 py-0.5 rounded-full">
        {unmatchedCount} unmatched
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 px-2 py-0.5 rounded-full">
        error
      </span>
    );
  }
  return null;
}

// Render per-slot match column cell
function MatchCell({ item }) {
  const { status, matchResults, matchChoices } = item;

  if (status === "queued" || status === "parsing" || status === "matching") {
    return <span className="text-gray-500">—</span>;
  }
  if (status === "error") {
    return (
      <span className="text-red-400 text-sm truncate max-w-xs" title={item.error}>
        {item.error}
      </span>
    );
  }

  if (!matchResults) return <span className="text-gray-500">—</span>;

  const total = matchResults.length;
  const unmatched = matchResults.filter(
    (r) => !matchChoices[r.slot_id]?.product_id
  );
  const unmatchedCount = unmatched.length;
  const matched = total - unmatchedCount;

  if (unmatchedCount === 0) {
    return (
      <span className="text-green-400 text-sm font-medium">
        {matched}/{total} ✓
      </span>
    );
  }

  return (
    <div className="space-y-1">
      <span className="text-yellow-400 text-sm">
        {matched}/{total} matched
      </span>
      {unmatched.map((r) => (
        <div key={r.slot_id} className="flex items-center gap-1.5">
          <span
            className="inline-block w-3 h-3 rounded-sm border border-gray-600 flex-shrink-0"
            style={{ backgroundColor: r.color_hex || "#888" }}
          />
          <span className="text-xs text-gray-400">
            {r.filament_type || `Slot ${r.slot_id}`}
            {r.color_hex ? ` · ${r.color_hex}` : ""}
            {" — no match"}
          </span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function AdminIntakeBatch() {
  const toast = useToast();
  const api = useApi();
  const { isPro, loading: flagsLoading } = useFeatureFlags();

  const [items, setItems] = useState([]);
  const [context, setContext] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [dragActive, setDragActive] = useState(false);

  // Ref so sequential processor reads current context without stale closure
  const contextRef = useRef(null);

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
          <h1 className="text-2xl font-bold text-white">Intake Batch</h1>
          <p className="text-gray-400 mt-1">
            Drop multiple sliced files and review them all at once
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
            Intake Batch lets you drop multiple sliced .gcode.3mf files at
            once, auto-parse and match filament spools for each, and triage the
            full set before committing any SKUs.
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
  // Helpers for updating a single item row in state
  // ---------------------------------------------------------------------------

  const updateItem = (id, patch) => {
    setItems((prev) =>
      prev.map((it) => (it.id === id ? { ...it, ...patch } : it))
    );
  };

  // ---------------------------------------------------------------------------
  // Context fetch (once per session)
  // ---------------------------------------------------------------------------

  const ensureContext = async () => {
    if (contextRef.current) return contextRef.current;
    const data = await api.get("/api/v1/pro/intake/context");
    contextRef.current = data;
    setContext(data);
    return data;
  };

  // ---------------------------------------------------------------------------
  // Per-file parse + match pipeline
  // ---------------------------------------------------------------------------

  const processFile = async (item, ctx) => {
    const { id, file } = item;

    // --- PARSE ---
    updateItem(id, { status: "parsing" });
    let parseResult;
    try {
      const formData = new FormData();
      formData.append("file", file);
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
        updateItem(id, {
          status: "error",
          error: data.detail || `Parse failed (${res.status})`,
        });
        return;
      }
      parseResult = data;
      updateItem(id, { parseResult });
    } catch (err) {
      updateItem(id, {
        status: "error",
        error: err.message || "Parse failed",
      });
      return;
    }

    // --- MATCH ---
    updateItem(id, { status: "matching" });
    let matchResults;
    let matchChoices;
    try {
      const body = {
        slots: (parseResult.slots || []).map((s) => ({
          slot_id: s.slot_id,
          filament_type: s.filament_type,
          color_hex: s.color_hex,
          used_g: s.used_g,
        })),
        top_n: 5,
      };
      const data = await api.post("/api/v1/pro/intake/match", body);
      matchResults = data.results || [];

      // Auto-fill choices: sticky or top ranked suggestion
      const defaults = {};
      matchResults.forEach((r) => {
        if (r.suggestions && r.suggestions.length > 0) {
          // result.sticky === true means a confirmed colour-map hit;
          // the first suggestion IS that known spool — pick it confidently.
          // Without sticky, suggestions[0] is the closest colour-distance match.
          const s = r.suggestions[0];
          if (s.product_id) {
            defaults[r.slot_id] = {
              product_id: s.product_id,
              sku: s.sku,
              name: s.name,
            };
          }
        }
      });
      matchChoices = defaults;
    } catch (err) {
      updateItem(id, {
        status: "error",
        error: err.message || "Match failed",
      });
      return;
    }

    // --- Determine work center from printer model ---
    let workCenterId = null;
    if (ctx && parseResult.printer_model) {
      const mapped = ctx.printer_work_center_map?.[parseResult.printer_model];
      if (mapped?.work_center_id) {
        workCenterId = String(mapped.work_center_id);
      }
    }

    // Determine final status: any slot with no product_id choice = needs-attention
    const unmatchedCount = matchResults.filter(
      (r) => !matchChoices[r.slot_id]?.product_id
    ).length;

    const finalStatus = unmatchedCount === 0 ? "ready" : "needs-attention";

    updateItem(id, {
      status: finalStatus,
      matchResults,
      matchChoices,
      workCenterId,
    });
  };

  // ---------------------------------------------------------------------------
  // Drop / file input handlers
  // ---------------------------------------------------------------------------

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") setDragActive(true);
    else if (e.type === "dragleave") setDragActive(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(Array.from(e.target.files));
      // Reset so the same files can be re-added if needed
      e.target.value = "";
    }
  };

  const handleFiles = async (rawFiles) => {
    if (processing) {
      toast.error("A batch is already processing — wait for it to finish.");
      return;
    }

    const validFiles = rawFiles.filter((f) => {
      const n = f.name.toLowerCase();
      return n.endsWith(".3mf") || n.endsWith(".gcode.3mf");
    });

    if (validFiles.length === 0) {
      toast.error("Please select .3mf or .gcode.3mf files");
      return;
    }
    if (validFiles.length < rawFiles.length) {
      toast.warn(
        `${rawFiles.length - validFiles.length} file(s) skipped (not .3mf)`
      );
    }

    // Fetch context once if not already loaded
    let ctx;
    try {
      ctx = await ensureContext();
    } catch (err) {
      toast.error(err.message || "Failed to load context");
      // Continue anyway — work center will just be null
    }

    // Seed item rows
    const newItems = validFiles.map((f, i) => ({
      id: `${Date.now()}-${i}`,
      file: f,
      filename: f.name,
      name: deriveName(f.name),
      status: "queued",
      parseResult: null,
      matchResults: null,
      matchChoices: {},
      workCenterId: null,
      error: null,
    }));

    setItems((prev) => [...prev, ...newItems]);
    setProcessing(true);
    setProgress({ done: 0, total: newItems.length });

    // Sequential processing — one file at a time so slicer-worker isn't flooded
    for (let i = 0; i < newItems.length; i++) {
      await processFile(newItems[i], ctx);
      setProgress({ done: i + 1, total: newItems.length });
    }

    setProcessing(false);
  };

  // ---------------------------------------------------------------------------
  // Editable name handler
  // ---------------------------------------------------------------------------

  const handleNameChange = (id, val) => {
    updateItem(id, { name: val });
  };

  // ---------------------------------------------------------------------------
  // Summary stats
  // ---------------------------------------------------------------------------

  const totalItems = items.length;
  const readyCount = items.filter((it) => it.status === "ready").length;
  const attentionCount = items.filter(
    (it) => it.status === "needs-attention"
  ).length;
  const errorCount = items.filter((it) => it.status === "error").length;
  const processingCount = items.filter(
    (it) => it.status === "parsing" || it.status === "matching"
  ).length;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Intake Batch</h1>
        <p className="text-gray-400 mt-1">
          Drop multiple sliced files to parse, match, and triage before
          creating SKUs
        </p>
      </div>

      {/* Drop zone */}
      <div
        className={`border-2 border-dashed rounded-lg p-10 text-center transition-colors cursor-pointer ${
          dragActive
            ? "border-blue-500 bg-blue-500/10"
            : "border-gray-700 hover:border-gray-600 bg-gray-900/50"
        }`}
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        onClick={() => document.getElementById("batch-file-input").click()}
        role="button"
        tabIndex={0}
        aria-label="Upload sliced .gcode.3mf files"
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            document.getElementById("batch-file-input").click();
          }
        }}
      >
        <input
          id="batch-file-input"
          type="file"
          accept=".3mf,.gcode.3mf"
          multiple
          className="hidden"
          onChange={handleFileInput}
        />
        <svg
          className="w-10 h-10 text-gray-500 mx-auto mb-3"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          />
        </svg>
        <p className="text-gray-300 font-medium mb-1">
          Drop .gcode.3mf files here
        </p>
        <p className="text-gray-500 text-sm">
          or click to select multiple files
        </p>
      </div>

      {/* Summary header — only shown once items exist */}
      {totalItems > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="flex flex-wrap items-center gap-4">
            {processing && (
              <span className="flex items-center gap-2 text-blue-300 text-sm font-medium">
                <Spinner small />
                Processing {Math.min(progress.done + 1, progress.total)} of {progress.total}…
              </span>
            )}
            {!processing && processingCount === 0 && (
              <span className="text-gray-400 text-sm">
                All files processed
              </span>
            )}
            <div className="flex items-center gap-4 ml-auto flex-wrap">
              <span className="text-gray-400 text-sm">
                Total:{" "}
                <span className="text-white font-medium">{totalItems}</span>
              </span>
              {readyCount > 0 && (
                <span className="text-green-400 text-sm">
                  Ready:{" "}
                  <span className="font-medium">{readyCount}</span>
                </span>
              )}
              {attentionCount > 0 && (
                <span className="text-yellow-400 text-sm">
                  Needs attention:{" "}
                  <span className="font-medium">{attentionCount}</span>
                </span>
              )}
              {errorCount > 0 && (
                <span className="text-red-400 text-sm">
                  Errors:{" "}
                  <span className="font-medium">{errorCount}</span>
                </span>
              )}
            </div>
          </div>

          {/* Progress bar while running */}
          {processing && (
            <div className="mt-3 h-1.5 bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full transition-all duration-300"
                style={{
                  width: `${
                    progress.total > 0
                      ? Math.round((progress.done / progress.total) * 100)
                      : 0
                  }%`,
                }}
              />
            </div>
          )}
        </div>
      )}

      {/* Triage table */}
      {totalItems > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-gray-400 text-xs uppercase tracking-wider">
                  <th className="px-4 py-3 text-left font-medium">
                    Filename
                  </th>
                  <th className="px-4 py-3 text-right font-medium whitespace-nowrap">
                    Weight
                  </th>
                  <th className="px-4 py-3 text-right font-medium whitespace-nowrap">
                    Print time
                  </th>
                  <th className="px-4 py-3 text-center font-medium">
                    Slots
                  </th>
                  <th className="px-4 py-3 text-left font-medium">Match</th>
                  <th className="px-4 py-3 text-left font-medium">
                    Name
                  </th>
                  <th className="px-4 py-3 text-left font-medium whitespace-nowrap">
                    Work Center
                  </th>
                  <th className="px-4 py-3 text-left font-medium">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const { parseResult, matchResults, matchChoices } = item;
                  const totalUsedG = parseResult?.slots
                    ? parseResult.slots.reduce(
                        (sum, s) => sum + (s.used_g || 0),
                        0
                      )
                    : null;
                  const printTime = parseResult?.print_time_seconds ?? null;
                  const slotCount = parseResult?.slots?.length ?? null;

                  // Work center name lookup
                  let wcName = "—";
                  if (item.workCenterId && context?.work_centers) {
                    const wc = context.work_centers.find(
                      (w) => String(w.id) === String(item.workCenterId)
                    );
                    if (wc) wcName = wc.name;
                  }

                  // Unmatched count for status badge
                  const unmatchedCount =
                    matchResults
                      ? matchResults.filter(
                          (r) => !matchChoices[r.slot_id]?.product_id
                        ).length
                      : 0;

                  return (
                    <tr
                      key={item.id}
                      className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors"
                    >
                      {/* Filename */}
                      <td className="px-4 py-3 text-gray-300 max-w-xs">
                        <span
                          className="block truncate font-mono text-xs"
                          title={item.filename}
                        >
                          {item.filename}
                        </span>
                      </td>

                      {/* Weight */}
                      <td className="px-4 py-3 text-right text-gray-300 whitespace-nowrap">
                        {totalUsedG != null
                          ? `${totalUsedG.toFixed(1)} g`
                          : "—"}
                      </td>

                      {/* Print time */}
                      <td className="px-4 py-3 text-right text-gray-300 whitespace-nowrap">
                        {printTime != null ? secondsToHms(printTime) : "—"}
                      </td>

                      {/* Slots count */}
                      <td className="px-4 py-3 text-center text-gray-300">
                        {slotCount != null ? slotCount : "—"}
                      </td>

                      {/* Match summary */}
                      <td className="px-4 py-3">
                        <MatchCell item={item} />
                      </td>

                      {/* Editable name */}
                      <td className="px-4 py-3">
                        <input
                          type="text"
                          value={item.name}
                          onChange={(e) =>
                            handleNameChange(item.id, e.target.value)
                          }
                          className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-sm w-full min-w-32 focus:outline-none focus:border-blue-500"
                          placeholder="Product name"
                        />
                      </td>

                      {/* Work center */}
                      <td className="px-4 py-3 text-gray-400 whitespace-nowrap text-sm">
                        {wcName}
                      </td>

                      {/* Status badge */}
                      <td className="px-4 py-3 whitespace-nowrap">
                        <StatusBadge
                          status={item.status}
                          unmatchedCount={unmatchedCount}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Empty state */}
      {totalItems === 0 && (
        <div className="text-center py-16 text-gray-500">
          <svg
            className="w-12 h-12 mx-auto mb-3 opacity-40"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          <p className="text-sm">
            Drop .gcode.3mf files above to start the review queue
          </p>
        </div>
      )}
    </div>
  );
}
