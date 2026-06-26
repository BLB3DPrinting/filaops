import { useState, useEffect } from "react";
import { API_URL } from "../config/api";
import { useToast } from "./Toast";
import Modal from "./Modal";

// Result options. Explicit Tailwind class strings (no dynamic class names, which
// Tailwind would purge). Pass/Fail are the common path; Waive (accept despite a
// defect, attributed to the operator) and Conditional are the full-QMS additions.
const RESULTS = [
  { value: "passed", label: "Pass", hint: "Quality acceptable",
    sel: "border-green-500 bg-green-500/10", txt: "text-green-400", btn: "bg-green-600 hover:bg-green-500" },
  { value: "failed", label: "Fail", hint: "Quality issues found",
    sel: "border-red-500 bg-red-500/10", txt: "text-red-400", btn: "bg-red-600 hover:bg-red-500" },
  { value: "waived", label: "Waive", hint: "Accept despite a defect",
    sel: "border-amber-500 bg-amber-500/10", txt: "text-amber-400", btn: "bg-amber-600 hover:bg-amber-500" },
  { value: "conditional", label: "Conditional", hint: "Accept with conditions",
    sel: "border-blue-500 bg-blue-500/10", txt: "text-blue-400", btn: "bg-blue-600 hover:bg-blue-500" },
];

const emptyMeasurement = () => ({
  characteristic: "", nominal: "", lower_limit: "", upper_limit: "",
  measured_value: "", unit: "",
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

  const [defectReasons, setDefectReasons] = useState([]);
  const [operations, setOperations] = useState([]);

  const selected = RESULTS.find((r) => r.value === result) || RESULTS[0];
  const needsDefect = result !== "passed"; // fail/waive/conditional may carry a defect

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [drRes, poRes] = await Promise.all([
          fetch(`${API_URL}/api/v1/production-orders/defect-reasons`, { credentials: "include" }),
          fetch(`${API_URL}/api/v1/production-orders/${productionOrder.id}`, { credentials: "include" }),
        ]);
        if (!cancelled && drRes.ok) {
          const data = await drRes.json();
          setDefectReasons(data.details || []);
        }
        if (!cancelled && poRes.ok) {
          const data = await poRes.json();
          setOperations(data.operations || []);
        }
      } catch {
        /* non-critical — the dropdowns just stay empty */
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
      const payload = {
        result,
        quantity_passed: numOrNull(quantityPassed),
        quantity_failed: numOrNull(quantityFailed),
        defect_reason_id: defectReasonId ? Number(defectReasonId) : null,
        operation_id: operationId ? Number(operationId) : null,
        notes: notes.trim() || null,
        measurements: measurements
          .filter((m) => m.characteristic.trim())
          .map((m) => ({
            characteristic: m.characteristic.trim(),
            nominal: numOrNull(m.nominal),
            lower_limit: numOrNull(m.lower_limit),
            upper_limit: numOrNull(m.upper_limit),
            measured_value: numOrNull(m.measured_value),
            unit: m.unit.trim() || null,
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
        onComplete();
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
    "w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm";

  return (
    <Modal isOpen={true} onClose={onClose} title="QC Inspection" className="w-full max-w-2xl p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-bold text-white">QC Inspection</h2>
          <p className="text-gray-400 text-sm mt-1">
            {productionOrder.code} -{" "}
            {productionOrder.product_name || productionOrder.product_sku}
          </p>
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-white text-xl">
          &times;
        </button>
      </div>

      {/* Order details */}
      <div className="bg-gray-800/50 rounded-lg p-4 mb-6">
        <div className="flex justify-between text-sm mb-2">
          <span className="text-gray-400">Quantity Completed:</span>
          <span className="text-white font-medium">
            {productionOrder.quantity_completed || productionOrder.quantity_ordered} units
          </span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Status:</span>
          <span className="text-green-400 font-medium">{productionOrder.status}</span>
        </div>
      </div>

      {/* Result selection */}
      <div className="mb-6">
        <label className="block text-sm text-gray-400 mb-3">Inspection Result *</label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {RESULTS.map((r) => (
            <button
              key={r.value}
              type="button"
              onClick={() => setResult(r.value)}
              className={`p-3 rounded-lg border-2 transition-all text-center ${
                result === r.value ? r.sel : "border-gray-700 bg-gray-800 hover:border-gray-600"
              }`}
            >
              <span className={`font-medium ${result === r.value ? r.txt : "text-gray-300"}`}>
                {r.label}
              </span>
              <p className={`text-xs mt-1 ${result === r.value ? r.txt + "/70" : "text-gray-500"}`}>
                {r.hint}
              </p>
            </button>
          ))}
        </div>
      </div>

      {/* Quantities (optional) */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div>
          <label className="block text-sm text-gray-400 mb-1">Quantity Passed</label>
          <input type="number" min="0" value={quantityPassed}
            onChange={(e) => setQuantityPassed(e.target.value)}
            placeholder="(whole order)" className={inputCls} />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Quantity Failed</label>
          <input type="number" min="0" value={quantityFailed}
            onChange={(e) => setQuantityFailed(e.target.value)}
            placeholder="(whole order)" className={inputCls} />
        </div>
        <p className="col-span-2 text-xs text-gray-500 -mt-2">
          Leave blank for a whole-order result; the unspecified side is derived.
        </p>
      </div>

      {/* Operation (optional) */}
      {operations.length > 0 && (
        <div className="mb-6">
          <label className="block text-sm text-gray-400 mb-1">Operation inspected</label>
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
          <label className="block text-sm text-gray-400 mb-1">
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
          <label className="block text-sm text-gray-400">Measurements (SPC)</label>
          <button type="button" onClick={addMeasurement}
            className="text-sm text-blue-400 hover:text-blue-300">+ Add measurement</button>
        </div>
        {measurements.length === 0 ? (
          <p className="text-xs text-gray-500">No measurements. Add one to record a dimensional/SPC reading.</p>
        ) : (
          <div className="space-y-2">
            {measurements.map((m, idx) => {
              const ok = withinSpec(m);
              return (
                <div key={idx} className="grid grid-cols-12 gap-2 items-center">
                  <input className={`${inputCls} col-span-3`} placeholder="Characteristic"
                    value={m.characteristic} onChange={(e) => setMeasurement(idx, "characteristic", e.target.value)} />
                  <input className={`${inputCls} col-span-2`} type="number" placeholder="Nominal"
                    value={m.nominal} onChange={(e) => setMeasurement(idx, "nominal", e.target.value)} />
                  <input className={`${inputCls} col-span-1`} type="number" placeholder="LSL"
                    value={m.lower_limit} onChange={(e) => setMeasurement(idx, "lower_limit", e.target.value)} />
                  <input className={`${inputCls} col-span-1`} type="number" placeholder="USL"
                    value={m.upper_limit} onChange={(e) => setMeasurement(idx, "upper_limit", e.target.value)} />
                  <input className={`${inputCls} col-span-2`} type="number" placeholder="Measured"
                    value={m.measured_value} onChange={(e) => setMeasurement(idx, "measured_value", e.target.value)} />
                  <input className={`${inputCls} col-span-2`} placeholder="Unit"
                    value={m.unit} onChange={(e) => setMeasurement(idx, "unit", e.target.value)} />
                  <div className="col-span-1 flex items-center justify-end gap-1">
                    {ok === true && <span className="w-2.5 h-2.5 rounded-full bg-green-500" title="In spec" />}
                    {ok === false && <span className="w-2.5 h-2.5 rounded-full bg-red-500" title="Out of spec" />}
                    <button type="button" onClick={() => removeMeasurement(idx)}
                      className="text-gray-500 hover:text-red-400" title="Remove">&times;</button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Notes */}
      <div className="mb-6">
        <label className="block text-sm text-gray-400 mb-2">
          Inspection Notes {result === "failed" ? "(recommended)" : "(optional)"}
        </label>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2}
          placeholder={result === "failed"
            ? "Describe the quality issues found"
            : "Add any notes about the inspection"}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white text-sm resize-none" />
      </div>

      {/* Actions */}
      <div className="flex gap-3">
        <button onClick={onClose}
          className="flex-1 px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600">
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
