/**
 * MaintenanceModal - Log past maintenance OR schedule a maintenance window.
 *
 * Extracted from AdminPrinters.jsx (ARCHITECT-002).
 *
 * SCHED-7: adds a "Schedule Window" tab — planned downtime becomes a
 * first-class block the scheduler treats as busy time. The tab also lists
 * upcoming (blocking) windows with cancel / complete actions; completing a
 * window writes the MaintenanceLog entry server-side.
 *
 * datetime-local convention: inputs are seeded ONLY via toLocalInputValue
 * (local wall time) and submitted via new Date(localValue).toISOString().
 *
 * Props:
 *   printers          — printer list for the selector
 *   selectedPrinterId — preselected printer (optional)
 *   initialMode       — "log" | "schedule" (default "log")
 *   onClose           — () => void
 *   onSave            — () => void (maintenance logged; parent closes + refreshes)
 *   onWindowsChanged  — () => void (optional; a window was created/cancelled/completed)
 */
import { useState, useEffect, useCallback } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../Toast";
import { toLocalInputValue, parseDateTime } from "../../utils/formatting";
import Modal from "../Modal";

const maintenanceTypes = [
  { value: "routine", label: "Routine Maintenance", description: "Regular scheduled maintenance" },
  { value: "repair", label: "Repair", description: "Fixing a broken component" },
  { value: "calibration", label: "Calibration", description: "Bed leveling, extrusion tuning" },
  { value: "cleaning", label: "Cleaning", description: "Nozzle, bed, or general cleaning" },
];

const inputClass =
  "w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-orange-500";
const placeholderInputClass = `${inputClass} placeholder-gray-500`;

function fmtWindowTime(value) {
  const d = parseDateTime(value);
  if (!d || Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function MaintenanceModal({
  printers,
  selectedPrinterId,
  initialMode = "log",
  onClose,
  onSave,
  onWindowsChanged,
}) {
  const toast = useToast();
  const [mode, setMode] = useState(initialMode); // log | schedule
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    printer_id: selectedPrinterId || "",
    maintenance_type: "routine",
    description: "",
    performed_by: "",
    performed_at: toLocalInputValue(new Date()),
    next_due_at: "",
    cost: "",
    downtime_minutes: "",
    parts_used: "",
    notes: "",
  });

  // --- Schedule Window state (SCHED-7) ---
  // Lazy initializer: seeds start = now, end = +1h, both as local wall
  // time via toLocalInputValue (the datetime-local contract).
  const [windowForm, setWindowForm] = useState(() => {
    const seed = new Date();
    return {
      printer_id: selectedPrinterId || "",
      starts_at: toLocalInputValue(seed),
      ends_at: toLocalInputValue(new Date(seed.getTime() + 60 * 60 * 1000)),
      reason: "",
    };
  });
  const [windows, setWindows] = useState([]);
  // Starts true (list fetch fires when the schedule tab opens) and is only
  // flipped from async continuations — no synchronous setState in effects.
  const [windowsLoading, setWindowsLoading] = useState(true);
  // window id with an action (cancel/complete) in flight — disables its buttons
  const [windowActionId, setWindowActionId] = useState(null);

  const fetchWindows = useCallback(async () => {
    try {
      // Default listing = blocking windows only (scheduled / in_progress)
      const res = await fetch(`${API_URL}/api/v1/maintenance-windows`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error("Failed to load maintenance windows");
      const data = await res.json();
      setWindows(data.items || []);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setWindowsLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (mode === "schedule") {
      fetchWindows();
    }
  }, [mode, fetchWindows]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!form.printer_id) {
      toast.error("Please select a printer");
      return;
    }

    setLoading(true);

    try {
      const payload = {
        maintenance_type: form.maintenance_type,
        description: form.description || null,
        performed_by: form.performed_by || null,
        performed_at: form.performed_at ? new Date(form.performed_at).toISOString() : new Date().toISOString(),
        next_due_at: form.next_due_at ? new Date(form.next_due_at).toISOString() : null,
        cost: form.cost ? parseFloat(form.cost) : null,
        downtime_minutes: form.downtime_minutes ? parseInt(form.downtime_minutes) : null,
        parts_used: form.parts_used || null,
        notes: form.notes || null,
      };

      const res = await fetch(`${API_URL}/api/v1/maintenance/printers/${form.printer_id}/maintenance`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to log maintenance");
      }

      toast.success("Maintenance logged successfully");
      onSave();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleScheduleSubmit = async (e) => {
    e.preventDefault();

    if (!windowForm.printer_id) {
      toast.error("Please select a printer");
      return;
    }
    if (!windowForm.starts_at || !windowForm.ends_at) {
      toast.error("Start and end times are required");
      return;
    }
    if (new Date(windowForm.ends_at) <= new Date(windowForm.starts_at)) {
      toast.error("End time must be after start time");
      return;
    }

    setLoading(true);
    try {
      const payload = {
        printer_id: parseInt(windowForm.printer_id),
        starts_at: new Date(windowForm.starts_at).toISOString(),
        ends_at: new Date(windowForm.ends_at).toISOString(),
        reason: windowForm.reason || null,
      };

      const res = await fetch(`${API_URL}/api/v1/maintenance-windows`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to schedule maintenance window");
      }

      toast.success("Maintenance window scheduled");
      await fetchWindows();
      onWindowsChanged?.();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleWindowAction = async (windowId, action) => {
    setWindowActionId(windowId);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/maintenance-windows/${windowId}/${action}`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          // complete: server defaults (routine type, current user, window-span
          // downtime) — the detailed MaintenanceLog form stays on the Log tab.
          body: JSON.stringify({}),
        }
      );
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || `Failed to ${action} window`);
      }
      toast.success(
        action === "cancel" ? "Maintenance window cancelled" : "Maintenance window completed"
      );
      await fetchWindows();
      onWindowsChanged?.();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setWindowActionId(null);
    }
  };

  const printerName = (printerId) => {
    const p = printers.find((x) => x.id === printerId);
    return p ? `${p.name} (${p.code})` : `Printer #${printerId}`;
  };

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title="Maintenance"
      className="w-full max-w-lg max-h-[90vh] overflow-y-auto"
      disableClose={loading}
    >
      <div className="p-6 border-b border-gray-700">
        <h2 className="text-xl font-bold text-white">
          {mode === "log" ? "Log Maintenance" : "Schedule Maintenance Window"}
        </h2>
        <p className="text-gray-400 text-sm mt-1">
          {mode === "log"
            ? "Track maintenance activities, costs, and downtime"
            : "Block out planned downtime — the scheduler treats it as busy time"}
        </p>
        {/* Mode tabs */}
        <div className="flex gap-1 mt-4 bg-gray-800 rounded-lg p-1 w-fit" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "log"}
            onClick={() => setMode("log")}
            className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
              mode === "log" ? "bg-orange-600 text-white" : "text-gray-400 hover:text-white"
            }`}
          >
            Log Maintenance
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "schedule"}
            onClick={() => setMode("schedule")}
            className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
              mode === "schedule" ? "bg-orange-600 text-white" : "text-gray-400 hover:text-white"
            }`}
          >
            Schedule Window
          </button>
        </div>
      </div>

      {mode === "log" ? (
      <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Printer Selection */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Printer *</label>
            <select
              value={form.printer_id}
              onChange={(e) => setForm({ ...form, printer_id: e.target.value })}
              required
              className={inputClass}
            >
              <option value="">Select printer...</option>
              {printers.map((p) => (
                <option key={p.id} value={p.id}>{p.name} ({p.code})</option>
              ))}
            </select>
          </div>

          {/* Maintenance Type */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Type *</label>
            <select
              value={form.maintenance_type}
              onChange={(e) => setForm({ ...form, maintenance_type: e.target.value })}
              required
              className={inputClass}
            >
              {maintenanceTypes.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Description</label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="e.g., Replaced nozzle, cleaned bed"
              className={placeholderInputClass}
            />
          </div>

          {/* Performed By */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Performed By</label>
            <input
              type="text"
              value={form.performed_by}
              onChange={(e) => setForm({ ...form, performed_by: e.target.value })}
              placeholder="Your name"
              className={placeholderInputClass}
            />
          </div>

          {/* Date/Time Row */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-300 mb-1">Performed At *</label>
              <input
                type="datetime-local"
                value={form.performed_at}
                onChange={(e) => setForm({ ...form, performed_at: e.target.value })}
                required
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">Next Due</label>
              <input
                type="datetime-local"
                value={form.next_due_at}
                onChange={(e) => setForm({ ...form, next_due_at: e.target.value })}
                className={inputClass}
              />
            </div>
          </div>

          {/* Cost and Downtime Row */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-300 mb-1">Cost ($)</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.cost}
                onChange={(e) => setForm({ ...form, cost: e.target.value })}
                placeholder="0.00"
                className={placeholderInputClass}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">Downtime (minutes)</label>
              <input
                type="number"
                min="0"
                value={form.downtime_minutes}
                onChange={(e) => setForm({ ...form, downtime_minutes: e.target.value })}
                placeholder="0"
                className={placeholderInputClass}
              />
            </div>
          </div>

          {/* Parts Used */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Parts Used</label>
            <input
              type="text"
              value={form.parts_used}
              onChange={(e) => setForm({ ...form, parts_used: e.target.value })}
              placeholder="e.g., Hardened nozzle 0.4mm, PTFE tube"
              className={placeholderInputClass}
            />
            <p className="text-xs text-gray-500 mt-1">Comma-separated list of parts used</p>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Notes</label>
            <textarea
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder="Additional notes..."
              rows={2}
              className={placeholderInputClass}
            />
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-4 border-t border-gray-700">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 text-gray-400 hover:text-white border border-gray-700 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 bg-orange-600 hover:bg-orange-500 disabled:bg-orange-600/50 text-white px-4 py-2 rounded-lg transition-colors"
            >
              {loading ? "Saving..." : "Log Maintenance"}
            </button>
          </div>
      </form>
      ) : (
      <div className="p-6 space-y-6">
        {/* Schedule Window form (SCHED-7) */}
        <form onSubmit={handleScheduleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-300 mb-1">Printer *</label>
            <select
              value={windowForm.printer_id}
              onChange={(e) => setWindowForm({ ...windowForm, printer_id: e.target.value })}
              required
              className={inputClass}
            >
              <option value="">Select printer...</option>
              {printers.map((p) => (
                <option key={p.id} value={p.id}>{p.name} ({p.code})</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-300 mb-1">Starts *</label>
              <input
                type="datetime-local"
                aria-label="Window start"
                value={windowForm.starts_at}
                onChange={(e) => setWindowForm({ ...windowForm, starts_at: e.target.value })}
                required
                className={inputClass}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">Ends *</label>
              <input
                type="datetime-local"
                aria-label="Window end"
                value={windowForm.ends_at}
                onChange={(e) => setWindowForm({ ...windowForm, ends_at: e.target.value })}
                required
                className={inputClass}
              />
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-300 mb-1">Reason</label>
            <input
              type="text"
              value={windowForm.reason}
              onChange={(e) => setWindowForm({ ...windowForm, reason: e.target.value })}
              placeholder="e.g., Hotend swap, belt tensioning"
              maxLength={255}
              className={placeholderInputClass}
            />
          </div>

          <div className="flex gap-3 pt-4 border-t border-gray-700">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 text-gray-400 hover:text-white border border-gray-700 rounded-lg transition-colors"
            >
              Close
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 bg-orange-600 hover:bg-orange-500 disabled:bg-orange-600/50 text-white px-4 py-2 rounded-lg transition-colors"
            >
              {loading ? "Saving..." : "Schedule Window"}
            </button>
          </div>
        </form>

        {/* Upcoming windows list */}
        <div>
          <h3 className="text-sm font-semibold text-white mb-2">Upcoming Windows</h3>
          {windowsLoading ? (
            <p className="text-xs text-gray-500">Loading windows...</p>
          ) : windows.length === 0 ? (
            <p className="text-xs text-gray-500">No maintenance windows scheduled.</p>
          ) : (
            <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
              {windows.map((w) => (
                <div
                  key={w.id}
                  className="bg-gray-800 border border-gray-700 rounded-lg p-3 flex items-start justify-between gap-3"
                  data-testid={`maintenance-window-${w.id}`}
                >
                  <div className="min-w-0">
                    <div className="text-sm text-white truncate">
                      {w.printer_id != null
                        ? printerName(w.printer_id)
                        : `Resource #${w.resource_id}`}
                    </div>
                    <div className="text-xs text-gray-400">
                      {fmtWindowTime(w.starts_at)} → {fmtWindowTime(w.ends_at)}
                    </div>
                    <div className="text-[11px] text-gray-500 truncate">
                      {w.status === "in_progress" ? "In progress" : "Scheduled"}
                      {w.reason && ` · ${w.reason}`}
                    </div>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={() => handleWindowAction(w.id, "complete")}
                      disabled={windowActionId === w.id}
                      title="Mark done — writes a maintenance log entry"
                      className="px-2 py-1 text-xs rounded bg-green-600/80 hover:bg-green-600 disabled:opacity-50 text-white transition-colors"
                    >
                      Complete
                    </button>
                    <button
                      type="button"
                      onClick={() => handleWindowAction(w.id, "cancel")}
                      disabled={windowActionId === w.id}
                      title="Cancel this window"
                      className="px-2 py-1 text-xs rounded border border-gray-600 text-gray-300 hover:text-white hover:border-gray-500 disabled:opacity-50 transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      )}
    </Modal>
  );
}
