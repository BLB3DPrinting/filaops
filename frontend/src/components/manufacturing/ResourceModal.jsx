/**
 * ResourceModal - Form for creating/editing work center resources with Bambu printer auto-fill.
 */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";
import { RESOURCE_STATUSES } from "./constants";

export default function ResourceModal({ resource, workCenter, onClose, onSave }) {
  const [form, setForm] = useState({
    code: resource?.code || "",
    name: resource?.name || "",
    machine_type: resource?.machine_type || "",
    serial_number: resource?.serial_number || "",
    bambu_device_id: resource?.bambu_device_id || "",
    bambu_ip_address: resource?.bambu_ip_address || "",
    capacity_hours_per_day: resource?.capacity_hours_per_day || "",
    status: resource?.status || "available",
    is_active: resource?.is_active ?? true,
    printer_id: resource?.printer_id || null,
  });
  const [printers, setPrinters] = useState([]);
  const [existingResources, setExistingResources] = useState([]);
  const [loadingPrinters, setLoadingPrinters] = useState(false);

  // Fetch printers and existing resources for this work center
  useEffect(() => {
    if (!resource && workCenter?.center_type === "machine") {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Setting loading state before async fetch is valid
      setLoadingPrinters(true);

      // Fetch both printers and existing resources
      Promise.all([
        fetch(
          `${API_URL}/api/v1/work-centers/${workCenter.id}/printers?active_only=true`,
          { credentials: "include" }
        ).then((res) => (res.ok ? res.json() : [])),
        fetch(
          `${API_URL}/api/v1/work-centers/${workCenter.id}/resources?active_only=false`,
          { credentials: "include" }
        ).then((res) => (res.ok ? res.json() : [])),
      ])
        .then(([printersData, resourcesData]) => {
          setPrinters(printersData);
          setExistingResources(resourcesData);
        })
        .catch(() => {
          setPrinters([]);
          setExistingResources([]);
        })
        .finally(() => setLoadingPrinters(false));
    }
  }, [workCenter, resource]);

  // Filter out printers that are already added as resources
  const availablePrinters = printers.filter(
    (p) => !existingResources.some((r) => r.code === p.code)
  );

  const handlePrinterSelect = (printerId) => {
    if (!printerId) {
      // Clear form if "Manual Entry" selected
      setForm({
        code: "",
        name: "",
        machine_type: "",
        serial_number: "",
        bambu_device_id: "",
        bambu_ip_address: "",
        capacity_hours_per_day: "",
        status: "available",
        is_active: true,
        printer_id: null,
      });
      return;
    }
    const printer = printers.find((p) => p.id === parseInt(printerId));
    if (printer) {
      setForm({
        code: printer.code || "",
        name: printer.name || "",
        machine_type: printer.model || "",
        serial_number: printer.serial_number || "",
        bambu_device_id: printer.device_id || "",
        bambu_ip_address: printer.ip_address || "",
        capacity_hours_per_day: "",
        status:
          printer.status === "idle"
            ? "available"
            : printer.status === "printing"
            ? "busy"
            : printer.status === "error"
            ? "offline"
            : ["available", "busy", "maintenance", "offline"].includes(
                printer.status
              )
            ? printer.status
            : "available",
        is_active: printer.is_active ?? true,
        printer_id: printer.id,
      });
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave({
      ...form,
      capacity_hours_per_day: form.capacity_hours_per_day || null,
    });
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-lg border border-gray-700 w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-800">
          <h2 className="text-xl font-bold text-white">
            {resource ? "Edit Resource" : "New Resource"}
          </h2>
          <p className="text-sm text-gray-400 mt-1">
            Adding to: {workCenter?.name}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Printer Selection Dropdown - only show for new resources on machine-type work centers */}
          {!resource &&
            workCenter?.center_type === "machine" &&
            availablePrinters.length > 0 && (
              <div className="pb-4 border-b border-gray-800">
                <label className="block text-sm text-gray-400 mb-1">
                  Quick Add from Assigned Printer
                </label>
                <select
                  onChange={(e) => handlePrinterSelect(e.target.value)}
                  className="w-full bg-gray-800 border border-green-600 rounded px-3 py-2 text-white"
                  defaultValue=""
                >
                  <option value="">
                    -- Select a printer or enter manually --
                  </option>
                  {availablePrinters.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.code} - {p.name} ({p.model || "Unknown model"})
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  Select a printer to auto-fill the form, or leave blank for
                  manual entry
                </p>
              </div>
            )}

          {!resource &&
            workCenter?.center_type === "machine" &&
            printers.length > 0 &&
            availablePrinters.length === 0 &&
            !loadingPrinters && (
              <div className="p-3 bg-green-900/30 border border-green-700 rounded text-green-400 text-sm">
                ✓ All assigned printers have been added as resources. Enter
                details manually below if needed.
              </div>
            )}

          {!resource &&
            workCenter?.center_type === "machine" &&
            printers.length === 0 &&
            !loadingPrinters && (
              <div className="p-3 bg-yellow-900/30 border border-yellow-700 rounded text-yellow-400 text-sm">
                No printers assigned to this work center. Assign printers from
                the Printers page first, or enter details manually below.
              </div>
            )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Code *</label>
              <input
                type="text"
                value={form.code}
                onChange={(e) =>
                  setForm({ ...form, code: e.target.value.toUpperCase() })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                placeholder="PRINTER-01"
                required
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Status</label>
              <select
                value={form.status}
                onChange={(e) => setForm({ ...form, status: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
              >
                {RESOURCE_STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Name *</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
              placeholder="Donatello"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Machine Type
              </label>
              <input
                type="text"
                value={form.machine_type}
                onChange={(e) =>
                  setForm({ ...form, machine_type: e.target.value })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                placeholder="X1C, P1S, A1..."
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Serial Number
              </label>
              <input
                type="text"
                value={form.serial_number}
                onChange={(e) =>
                  setForm({ ...form, serial_number: e.target.value })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
              />
            </div>
          </div>

          <div className="border-t border-gray-800 pt-4">
            <h3 className="text-sm font-medium text-purple-400 mb-3">
              Bambu Integration
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Device ID
                </label>
                <input
                  type="text"
                  value={form.bambu_device_id}
                  onChange={(e) =>
                    setForm({ ...form, bambu_device_id: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                  placeholder="From Bambu Studio"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  IP Address
                </label>
                <input
                  type="text"
                  value={form.bambu_ip_address}
                  onChange={(e) =>
                    setForm({ ...form, bambu_ip_address: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                  placeholder="192.168.1.100"
                />
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex-1">
              <label className="block text-sm text-gray-400 mb-1">
                Capacity Hours/Day
              </label>
              <input
                type="number"
                step="0.5"
                value={form.capacity_hours_per_day}
                onChange={(e) =>
                  setForm({ ...form, capacity_hours_per_day: e.target.value })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                placeholder="Inherit from work center"
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-gray-300 pt-6">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) =>
                  setForm({ ...form, is_active: e.target.checked })
                }
                className="rounded bg-gray-800 border-gray-700"
              />
              Active
            </label>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-400 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg"
            >
              {resource ? "Save Changes" : "Add Resource"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
