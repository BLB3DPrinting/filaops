import { useState, useEffect } from "react";
import { API_URL } from "../config/api";
import { useToast } from "./Toast";
import Modal from "./Modal";
import QCInspectionPhotos from "./QCInspectionPhotos";

// Result options. Explicit Tailwind class strings (no dynamic class names, which
// Tailwind would purge). Pass/Fail are the common path; Waive (accept despite a
// defect, attributed to the operator) and Conditional are the full-QMS additions.
const RESULTS = [
  { value: "passed", label: "Pass", hint: "Quality acceptable",
    sel: "border-[var(--status-green)] bg-[var(--status-green-tint)]", txt: "text-[var(--status-green)]", fade: "text-[var(--status-green)]/70", btn: "bg-[var(--orange)] hover:bg-[var(--orange-press)]" },
  { value: "failed", label: "Fail", hint: "Quality issues found",
    sel: "border-[var(--status-red)] bg-[var(--status-red-tint)]", txt: "text-[var(--status-red)]", fade: "text-[var(--status-red)]/70", btn: "bg-[var(--orange)] hover:bg-[var(--orange-press)]" },
  { value: "waived", label: "Waive", hint: "Accept despite a defect",
    sel: "border-[var(--status-amber)] bg-[var(--status-amber-tint)]", txt: "text-[var(--status-amber)]", fade: "text-[var(--status-amber)]/70", btn: "bg-[var(--orange)] hover:bg-[var(--orange-press)]" },
  { value: "conditional", label: "Conditional", hint: "Accept with conditions",
    sel: "border-[var(--ink-3)] bg-[var(--paper-sunk)]", txt: "text-[var(--ink)]", fade: "text-[var(--ink-3)]", btn: "bg-[var(--orange)] hover:bg-[var(--orange-press)]" },
];

const emptyMeasurement = () => ({
  characteristic: "", characteristic_type: "variable",
  nominal: "", lower_limit: "", upper_limit: "", measured_value: "", unit: "",
  quality_plan_characteristic_id: null, characteristic_code: null,
  acceptance_criteria: null, conforms: null, locked: false,
});

// A measurement row seeded from a plan characteristic: the spec is locked (it
// comes from the plan), the inspector only fills the reading (measured_value for
// variable, conforms for attribute). Numeric specs are kept as strings to match
// the form inputs; the backend re-derives the authoritative characteristic_code.
const rowFromPlanChar = (c) => ({
  characteristic: c.characteristic ?? "",
  characteristic_type: c.characteristic_type ?? "variable",
  nominal: c.nominal ?? "",
  lower_limit: c.lower_limit ?? "",
  upper_limit: c.upper_limit ?? "",
  measured_value: "",
  unit: c.unit ?? "",
  quality_plan_characteristic_id: c.id,
  characteristic_code: c.code ?? null,
  acceptance_criteria: c.acceptance_criteria ?? null,
  conforms: null,
  locked: true,
});

// Client-side mirror of the backend's computed is_within_spec, for a live hint.
function withinSpec(m) {
  const v = parseFloat(m.measured_value);
  if (m.measured_value === "" || Number.isNaN(v)) return null;
  const lo = m.lower_limit === "" ? null : parseFloat(m.lower_limit);
  const hi = m.upper_limit === "" ? null : parseFloat(m.upper_limit);
  if (lo === null && hi === null) return null;
  if (lo !== null && v < lo) return false;
  if (hi !== null && v > hi) return false;
  return true;
}

const numOrNull = (s) => (s === "" || s === null ? null : Number(s));

export default function QCInspectionModal({ productionOrder, onClose, onComplete }) {
  const toast = useToast();
  const [result, setResult] = useState("passed");
  const [quantityPassed, setQuantityPassed] = useState("");
  const [quantityFailed, setQuantityFailed] = useState("");
  const [defectReasonId, setDefectReasonId] = useState("");
  const [operationId, setOperationId] = useState("");
  const [measurements, setMeasurements] = useState([]);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [recordedId, setRecordedId] = useState(null); // inspection id after a successful record

  const [defectReasons, setDefectReasons] = useState([]);
  const [operations, setOperations] = useState([]);
  const [seededPlan, setSeededPlan] = useState(null); // {code, name} when the grid was seeded from a plan

  const selected = RESULTS.find((r) => r.value === result) || RESULTS[0];
  const needsDefect = result !== "passed"; // fail/waive/conditional may carry a defect

  useEffect(() => {
    let cancelled = false;
    (async () => {
      // Clear any prior order's seeded rows before loading the new order — a
      // reused modal (productionOrder.id change without unmount) must not submit
      // stale measurements against a different order. Runs synchronously before
      // the first await, so it resets immediately on an id change.
      setMeasurements([]);
      setSeededPlan(null);
      try {
        const [drRes, poRes] = await Promise.all([
          fetch(`${API_URL}/api/v1/production-orders/defect-reasons`, { credentials: "include" }),
          fetch(`${API_URL}/api/v1/production-orders/${productionOrder.id}`, { credentials: "include" }),
        ]);
        if (!cancelled && drRes.ok) {
          const data = await drRes.json();
          setDefectReasons(data.details || []);
        }
        let productId = null;
        if (!cancelled && poRes.ok) {
          const data = await poRes.json();
          setOperations(data.operations || []);
          productId = data.product_id ?? null;
        }

        // Plan-driven seeding (Full mode only): pre-fill the grid from the
        // product's active quality plan. Best-effort — any failure just leaves
        // today's empty grid, and basic/off mode never seeds.
        if (!cancelled && productId != null) {
          const polRes = await fetch(`${API_URL}/api/v1/quality/policy`, { credentials: "include" });
          const policy = polRes.ok ? await polRes.json() : null;
          if (!cancelled && policy?.plan_driven) {
            const planRes = await fetch(
              `${API_URL}/api/v1/quality-plans/active?product_id=${productId}`,
              { credentials: "include" },
            );
            const plan = planRes.ok ? await planRes.json() : null;
            if (!cancelled && plan?.characteristics?.length) {
              // Don't clobber rows the user may have added during the fetch gap,
              // and only show the "seeded" banner if the seed actually happened.
              setMeasurements((prev) => {
                if (prev.length) return prev;
                setSeededPlan({ code: plan.code, name: plan.name });
                return plan.characteristics.map(rowFromPlanChar);
              });
            }
          }
        }
      } catch {
        /* non-critical — the dropdowns/seed just stay empty */
      }
    })();
    return () => { cancelled = true; };
  }, [productionOrder.id]);

  const setMeasurement = (idx, field, value) => {
    setMeasurements((prev) =>
      prev.map((m, i) => (i === idx ? { ...m, [field]: value } : m)),
    );
  };
  const addMeasurement = () => setMeasurements((prev) => [...prev, emptyMeasurement()]);
  const removeMeasurement = (idx) =>
    setMeasurements((prev) => prev.filter((_, i) => i !== idx));

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      // Decide which rows to record. Attribute rows count once a Pass/Fail is
      // chosen; a seeded (locked) variable row needs an actual reading; a manual
      // row counts if it carries any data. A counted row must name a
      // characteristic, otherwise we'd silently drop the reading.
      const entered = measurements.filter((m) => {
        if (m.characteristic_type === "attribute") return m.conforms !== null;
        if (m.locked) return String(m.measured_value ?? "").trim() !== "";
        return [m.characteristic, m.nominal, m.lower_limit, m.upper_limit, m.measured_value, m.unit]
          .some((v) => String(v ?? "").trim());
      });
      // Only MANUAL rows must name a characteristic — a plan-seeded row's
      // identity is its quality_plan_characteristic_id, and its (read-only)
      // name comes from the plan, so it must never block submit.
      if (entered.some((m) => m.quality_plan_characteristic_id == null && !m.characteristic.trim())) {
        toast.error("Add a characteristic for each measurement row, or remove the row.");
        return; // the finally block re-enables the submit button
      }

      const payload = {
        result,
        quantity_passed: numOrNull(quantityPassed),
        quantity_failed: numOrNull(quantityFailed),
        // A clean pass carries no defect — the backend rejects one. Gate on
        // needsDefect so switching back to Pass doesn't submit a stale pick.
        defect_reason_id: needsDefect && defectReasonId ? Number(defectReasonId) : null,
        operation_id: operationId ? Number(operationId) : null,
        notes: notes.trim() || null,
        measurements: entered
          .map((m) => ({
            characteristic: m.characteristic.trim(),
            nominal: numOrNull(m.nominal),
            lower_limit: numOrNull(m.lower_limit),
            upper_limit: numOrNull(m.upper_limit),
            // Attribute rows have no measured value; their result is `conforms`.
            measured_value:
              m.characteristic_type === "attribute" ? null : numOrNull(m.measured_value),
            unit: (m.unit || "").trim() || null,
            quality_plan_characteristic_id: m.quality_plan_characteristic_id ?? null,
            characteristic_code: m.characteristic_code ?? null,
            conforms: m.characteristic_type === "attribute" ? m.conforms : null,
          })),
      };
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/qc`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      if (res.ok) {
        const data = await res.json();
        if (result === "failed") {
          toast.warning(data.message || "QC inspection failed");
        } else {
          toast.success(data.message || "QC inspection recorded");
        }
        if (data.warnings?.length) {
          data.warnings.forEach((w) => toast.warning(w));
        }
        if (data.inspection_id) {
          setRecordedId(data.inspection_id); // advance to the optional photos step
        } else {
          onComplete();
        }
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Failed to submit QC inspection");
      }
    } catch (catchErr) {
      toast.error(catchErr.message || "Network error");
    } finally {
      setSubmitting(false);
    }
  };

  const inputCls =
    "w-full bg-[var(--paper)] border border-[var(--rule-hair)] rounded-lg px-3 py-2 text-[var(--ink)] text-sm";

  // After recording, switch to an optional photo-attachment step for the new
  // inspection (photos need the inspection_id the POST just returned).
  if (recordedId !== null) {
    // The inspection is already saved, so ANY exit here (Done, header ×, backdrop,
    // Escape) must run onComplete so the parent refetches and shows fresh QC state.
    return (
      <Modal isOpen={true} onClose={onComplete} title="QC Inspection" variant="workbench" className="w-full max-w-2xl p-6">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-xl font-bold text-[var(--ink)]">Inspection recorded</h2>
            <p className="text-[var(--ink-3)] text-sm mt-1">
              {productionOrder.code} — attach photos (optional)
            </p>
          </div>
          <button onClick={onComplete} className="text-[var(--ink-3)] hover:text-[var(--ink)] text-xl">
            &times;
          </button>
        </div>
        <QCInspectionPhotos inspectionId={recordedId} />
        <div className="flex justify-end mt-6">
          <button
            onClick={onComplete}
            className="px-4 py-2 bg-[var(--orange)] hover:bg-[var(--orange-press)] text-white rounded-lg"
          >
            Done
          </button>
        </div>
      </Modal>
    );
  }

  return (
    <Modal isOpen={true} onClose={onClose} title="QC Inspection" variant="workbench" className="w-full max-w-2xl p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-bold text-[var(--ink)]">QC Inspection</h2>
          <p className="text-[var(--ink-3)] text-sm mt-1">
            {productionOrder.code} -{" "}
            {productionOrder.product_name || productionOrder.product_sku}
          </p>
        </div>
        <button onClick={onClose} className="text-[var(--ink-3)] hover:text-[var(--ink)] text-xl">
          &times;
        </button>
      </div>

      {/* Order details */}
      <div className="bg-[var(--paper-sunk)] border border-[var(--rule-hair)] rounded-lg p-4 mb-6">
        <div className="flex justify-between text-sm mb-2">
          <span className="text-[var(--ink-3)]">Quantity Completed:</span>
          <span className="text-[var(--ink)] font-medium">
            {productionOrder.quantity_completed || productionOrder.quantity_ordered} units
          </span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-[var(--ink-3)]">Status:</span>
          <span className="text-[var(--status-green)] font-medium">{productionOrder.status}</span>
        </div>
      </div>

      {/* Result selection */}
      <div className="mb-6">
        <label className="block text-sm text-[var(--ink-3)] mb-3">Inspection Result *</label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {RESULTS.map((r) => (
            <button
              key={r.value}
              type="button"
              onClick={() => setResult(r.value)}
              className={`p-3 rounded-lg border-2 transition-all text-center ${
                result === r.value ? r.sel : "border-[var(--rule-hair)] bg-[var(--paper-sunk)] hover:border-[var(--ink-4)]"
              }`}
            >
              <span className={`font-medium ${result === r.value ? r.txt : "text-[var(--ink-2)]"}`}>
                {r.label}
              </span>
              <p className={`text-xs mt-1 ${result === r.value ? r.fade : "text-[var(--ink-4)]"}`}>
                {r.hint}
              </p>
            </button>
          ))}
        </div>
      </div>

      {/* Quantities (optional) */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div>
          <label className="block text-sm text-[var(--ink-3)] mb-1">Quantity Passed</label>
          <input type="number" min="0" value={quantityPassed}
            onChange={(e) => setQuantityPassed(e.target.value)}
            placeholder="(whole order)" className={inputCls} />
        </div>
        <div>
          <label className="block text-sm text-[var(--ink-3)] mb-1">Quantity Failed</label>
          <input type="number" min="0" value={quantityFailed}
            onChange={(e) => setQuantityFailed(e.target.value)}
            placeholder="(whole order)" className={inputCls} />
        </div>
        <p className="col-span-2 text-xs text-[var(--ink-4)] -mt-2">
          Leave blank for a whole-order result; the unspecified side is derived.
        </p>
      </div>

      {/* Operation (optional) */}
      {operations.length > 0 && (
        <div className="mb-6">
          <label className="block text-sm text-[var(--ink-3)] mb-1">Operation inspected</label>
          <select value={operationId} onChange={(e) => setOperationId(e.target.value)} className={inputCls}>
            <option value="">Default (the order&apos;s QC step)</option>
            {operations.map((op) => (
              <option key={op.id} value={op.id}>
                #{op.sequence} {op.operation_name || op.operation_code}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Defect reason (when not a clean pass) */}
      {needsDefect && (
        <div className="mb-6">
          <label className="block text-sm text-[var(--ink-3)] mb-1">
            Defect Reason {result === "failed" ? "(recommended)" : "(optional)"}
          </label>
          <select value={defectReasonId} onChange={(e) => setDefectReasonId(e.target.value)} className={inputCls}>
            <option value="">Select a defect reason…</option>
            {defectReasons.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}{d.severity ? ` — ${d.severity}` : ""}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Measurements grid */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <label className="block text-sm text-[var(--ink-3)]">
            {seededPlan ? "Characteristics (from plan)" : "Measurements (SPC)"}
          </label>
          <button type="button" onClick={addMeasurement}
            className="text-sm text-[var(--ink-2)] hover:text-[var(--ink)]">+ Add measurement</button>
        </div>
        {seededPlan && (
          <p className="text-xs text-[var(--ink-3)] mb-2">
            Seeded from plan{" "}
            <span className="font-mono text-[var(--ink-2)]">{seededPlan.code}</span>
            {seededPlan.name ? ` — ${seededPlan.name}` : ""}. Record a reading for each characteristic.
          </p>
        )}
        {measurements.length === 0 ? (
          <p className="text-xs text-[var(--ink-4)]">No measurements. Add one to record a dimensional/SPC reading.</p>
        ) : (
          <div className="space-y-2">
            {measurements.map((m, idx) => {
              // Attribute (Go/No-Go) row: a Pass/Fail toggle, no numeric inputs.
              if (m.characteristic_type === "attribute") {
                return (
                  <div key={idx} className="grid grid-cols-12 gap-2 items-center">
                    <div className="col-span-5">
                      <div className="px-3 py-2 text-sm text-[var(--ink)] truncate" title={m.characteristic}>
                        {m.characteristic}
                      </div>
                      {m.acceptance_criteria && (
                        <p className="text-xs text-[var(--ink-4)] px-3 -mt-1">{m.acceptance_criteria}</p>
                      )}
                    </div>
                    <div className="col-span-6 flex gap-2" role="group"
                      aria-label={`${m.characteristic} result`}>
                      <button type="button" aria-pressed={m.conforms === true}
                        aria-label={`${m.characteristic}: pass`}
                        onClick={() => setMeasurement(idx, "conforms", m.conforms === true ? null : true)}
                        className={`flex-1 px-3 py-2 rounded-lg border text-sm ${
                          m.conforms === true ? "border-[var(--status-green)] bg-[var(--status-green-tint)] text-[var(--status-green)]"
                            : "border-[var(--rule-hair)] bg-[var(--paper-sunk)] text-[var(--ink-2)] hover:border-[var(--ink-4)]"}`}>
                        Pass
                      </button>
                      <button type="button" aria-pressed={m.conforms === false}
                        aria-label={`${m.characteristic}: fail`}
                        onClick={() => setMeasurement(idx, "conforms", m.conforms === false ? null : false)}
                        className={`flex-1 px-3 py-2 rounded-lg border text-sm ${
                          m.conforms === false ? "border-[var(--status-red)] bg-[var(--status-red-tint)] text-[var(--status-red)]"
                            : "border-[var(--rule-hair)] bg-[var(--paper-sunk)] text-[var(--ink-2)] hover:border-[var(--ink-4)]"}`}>
                        Fail
                      </button>
                    </div>
                    <div className="col-span-1" />
                  </div>
                );
              }
              // Variable row: locked spec (from plan) is read-only, only the
              // measured value is editable; a manual row is fully editable.
              const ok = withinSpec(m);
              const ro = m.locked ? "bg-[var(--paper-sunk)] text-[var(--ink-3)] cursor-default" : "";
              return (
                <div key={idx} className="grid grid-cols-12 gap-2 items-center">
                  <input className={`${inputCls} col-span-3 ${ro}`} placeholder="Characteristic"
                    aria-label="Characteristic" tabIndex={m.locked ? -1 : undefined}
                    value={m.characteristic} readOnly={m.locked}
                    onChange={(e) => setMeasurement(idx, "characteristic", e.target.value)} />
                  <input className={`${inputCls} col-span-2 ${ro}`} type="number" step="any" placeholder="Nominal"
                    aria-label="Nominal" tabIndex={m.locked ? -1 : undefined}
                    value={m.nominal} readOnly={m.locked}
                    onChange={(e) => setMeasurement(idx, "nominal", e.target.value)} />
                  <input className={`${inputCls} col-span-1 ${ro}`} type="number" step="any" placeholder="LSL"
                    aria-label="Lower spec limit" tabIndex={m.locked ? -1 : undefined}
                    value={m.lower_limit} readOnly={m.locked}
                    onChange={(e) => setMeasurement(idx, "lower_limit", e.target.value)} />
                  <input className={`${inputCls} col-span-1 ${ro}`} type="number" step="any" placeholder="USL"
                    aria-label="Upper spec limit" tabIndex={m.locked ? -1 : undefined}
                    value={m.upper_limit} readOnly={m.locked}
                    onChange={(e) => setMeasurement(idx, "upper_limit", e.target.value)} />
                  <input className={`${inputCls} col-span-2`} type="number" step="any" placeholder="Measured"
                    aria-label={`${m.characteristic || "measurement"} measured value`}
                    value={m.measured_value} onChange={(e) => setMeasurement(idx, "measured_value", e.target.value)} />
                  <input className={`${inputCls} col-span-2 ${ro}`} placeholder="Unit"
                    aria-label="Unit" tabIndex={m.locked ? -1 : undefined}
                    value={m.unit} readOnly={m.locked}
                    onChange={(e) => setMeasurement(idx, "unit", e.target.value)} />
                  <div className="col-span-1 flex items-center justify-end gap-1">
                    {ok === true && <span role="img" aria-label="In spec"
                      className="w-2.5 h-2.5 rounded-full bg-[var(--status-green)]" title="In spec" />}
                    {ok === false && <span role="img" aria-label="Out of spec"
                      className="w-2.5 h-2.5 rounded-full bg-[var(--status-red)]" title="Out of spec" />}
                    {!m.locked && (
                      <button type="button" onClick={() => removeMeasurement(idx)}
                        className="text-[var(--ink-4)] hover:text-[var(--status-red)]" title="Remove">&times;</button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Notes */}
      <div className="mb-6">
        <label className="block text-sm text-[var(--ink-3)] mb-2">
          Inspection Notes {result === "failed" ? "(recommended)" : "(optional)"}
        </label>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2}
          placeholder={result === "failed"
            ? "Describe the quality issues found"
            : "Add any notes about the inspection"}
          className="w-full bg-[var(--paper)] border border-[var(--rule-hair)] rounded-lg px-4 py-3 text-[var(--ink)] placeholder-[var(--ink-4)] text-sm resize-none" />
      </div>

      {/* Actions */}
      <div className="flex gap-3">
        <button onClick={onClose}
          className="flex-1 px-4 py-2 bg-[var(--paper-sunk)] border border-[var(--rule-hair)] text-[var(--ink-2)] rounded-lg hover:text-[var(--ink)]">
          Cancel
        </button>
        <button onClick={handleSubmit} disabled={submitting}
          className={`flex-1 px-4 py-2 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed ${selected.btn}`}>
          {submitting ? "Submitting…" : `Record ${selected.label}`}
        </button>
      </div>
    </Modal>
  );
}
