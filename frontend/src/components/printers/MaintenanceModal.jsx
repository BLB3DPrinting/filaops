/**
 * MaintenanceModal - Form for logging printer maintenance activities.
 *
 * Extracted from AdminPrinters.jsx (ARCHITECT-002)
 */
import { useState } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../Toast";
import Modal from "../Modal";

const maintenanceTypes = [
  { value: "routine", label: "Routine Maintenance", description: "Regular scheduled maintenance" },
  { value: "repair", label: "Repair", description: "Fixing a broken component" },
  { value: "calibration", label: "Calibration", description: "Bed leveling, extrusion tuning" },
  { value: "cleaning", label: "Cleaning", description: "Nozzle, bed, or general cleaning" },
];

export default function MaintenanceModal({ printers, selectedPrinterId, onClose, onSave }) {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    printer_id: selectedPrinterId || "",
    maintenance_type: "routine",
    description: "",
    performed_by: "",
    performed_at: new Date().toISOString().slice(0, 16),
    next_due_at: "",
    cost: "",
    downtime_minutes: "",
    parts_used: "",
    notes: "",
  });

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

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title="Log Maintenance"
      className="w-full max-w-lg max-h-[90vh] overflow-y-auto"
      disableClose={loading}
    >
      <div className="p-6 border-b border-gray-700">
        <h2 className="text-xl font-bold text-white">Log Maintenance</h2>
        <p className="text-gray-400 text-sm mt-1">Track maintenance activities, costs, and downtime</p>
      </div>

      <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Printer Selection */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Printer *</label>
            <select
              value={form.printer_id}
              onChange={(e) => setForm({ ...form, printer_id: e.target.value })}
              required
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
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
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
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
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500"
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
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500"
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
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">Next Due</label>
              <input
                type="datetime-local"
                value={form.next_due_at}
                onChange={(e) => setForm({ ...form, next_due_at: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
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
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500"
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
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500"
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
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500"
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
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500"
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
    </Modal>
  );
}
