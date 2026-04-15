/**
 * PrinterModal - Form for adding/editing printers with brand-aware model selection.
 *
 * Extracted from AdminPrinters.jsx (ARCHITECT-002)
 */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../Toast";
import Modal from "../Modal";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";
import { brandLabels, CORE_BRANDS } from "./constants";

export default function PrinterModal({ printer, onClose, onSave, brandInfo }) {
  const toast = useToast();
  const { isPro, hasFeature } = useFeatureFlags();
  // Multi-brand (Klipper, OctoPrint, Prusa, Creality) is a PRO feature.
  // Core tier can still view/edit existing non-Core brands if they're
  // already on a printer record, but the dropdown flags them as locked.
  const canAddMultiBrand = isPro && hasFeature("filafarm");
  const [loading, setLoading] = useState(false);
  const [workCenters, setWorkCenters] = useState([]);
  const [form, setForm] = useState({
    code: printer?.code || "",
    name: printer?.name || "",
    model: printer?.model || "",
    brand: printer?.brand || "generic",
    serial_number: printer?.serial_number || "",
    ip_address: printer?.ip_address || "",
    access_code: printer?.connection_config?.access_code || "",
    location: printer?.location || "",
    work_center_id: printer?.work_center_id || "",
    notes: printer?.notes || "",
    active: printer?.active !== false,
    filament_diameters: printer?.capabilities?.filament_diameters || [],
  });

  const isEdit = !!printer;

  // Fetch machine-type work centers on mount
  useEffect(() => {
    const fetchWorkCenters = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/work-centers/?center_type=machine`, {
          credentials: "include",
        });
        if (res.ok) {
          const data = await res.json();
          setWorkCenters(data);
        }
      } catch {
        // Non-critical - work center selection is optional
      }
    };
    fetchWorkCenters();
  }, []);

  // Get models for selected brand
  const selectedBrand = brandInfo.find((b) => b.code === form.brand);
  const models = selectedBrand?.models || [];

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const url = isEdit
        ? `${API_URL}/api/v1/printers/${printer.id}`
        : `${API_URL}/api/v1/printers`;

      // Build payload with connection_config for brand-specific settings
      const { access_code, filament_diameters, ...rest } = form;
      const capabilities = { ...(printer?.capabilities || {}) };
      if (filament_diameters.length > 0) {
        capabilities.filament_diameters = filament_diameters;
      }
      const payload = {
        ...rest,
        connection_config: access_code ? { access_code } : {},
        capabilities,
      };

      const res = await fetch(url, {
        method: isEdit ? "PUT" : "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to save printer");
      }

      toast.success(isEdit ? "Printer updated" : "Printer added");
      onSave();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const toggleDiameter = (d) => {
    setForm((f) => ({
      ...f,
      filament_diameters: f.filament_diameters.includes(d)
        ? f.filament_diameters.filter((x) => x !== d)
        : [...f.filament_diameters, d],
    }));
  };

  const generateCode = async () => {
    try {
      const prefix = form.brand === "generic" ? "PRT" : form.brand.toUpperCase().slice(0, 3);
      const res = await fetch(`${API_URL}/api/v1/printers/generate-code?prefix=${prefix}`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setForm({ ...form, code: data.code });
      }
    } catch {
      // Non-critical
    }
  };

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={isEdit ? "Edit Printer" : "Add Printer"}
      className="w-full max-w-lg max-h-[90vh] overflow-y-auto"
      disableClose={loading}
    >
      <div className="p-6 border-b border-gray-700">
        <h2 className="text-xl font-bold text-white">
          {isEdit ? "Edit Printer" : "Add Printer"}
        </h2>
      </div>

      <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Brand — non-Core brands gated behind PRO+filafarm.
              Options are driven by the /brands/info response (brandInfo)
              so plugin-registered brands (Klipper/OctoPrint/Prusa/Creality
              from filaops-pro) appear automatically when PRO is active. */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Brand</label>
            <select
              value={form.brand}
              onChange={(e) => {
                const next = e.target.value;
                if (!canAddMultiBrand && !CORE_BRANDS.has(next) && next !== printer?.brand) {
                  toast.info("Multi-brand support is a PRO feature. Upgrade to add Klipper, OctoPrint, Prusa, or Creality printers.");
                  return;
                }
                setForm({ ...form, brand: next, model: "" });
              }}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {(() => {
                // Build option list: prefer brandInfo when available so backend/plugin
                // brands surface; otherwise fall back to the static brandLabels map.
                const codesFromApi = brandInfo.map((b) => b.code);
                const codesToRender = codesFromApi.length > 0 ? codesFromApi : Object.keys(brandLabels);
                // If editing a printer whose brand isn't in the current API response
                // (e.g. Klipper record with filafarm later downgraded), make sure the
                // option still exists so the select has a valid value and Save works.
                if (printer?.brand && !codesToRender.includes(printer.brand)) {
                  codesToRender.push(printer.brand);
                }
                return codesToRender.map((value) => {
                  const infoEntry = brandInfo.find((b) => b.code === value);
                  const label = infoEntry?.name || brandLabels[value] || value;
                  const locked = !canAddMultiBrand && !CORE_BRANDS.has(value);
                  // Keep a locked brand selectable only if the printer is already that brand
                  // (edit mode), so existing records don't silently lose their brand.
                  const allowInEditMode = printer?.brand === value;
                  return (
                    <option
                      key={value}
                      value={value}
                      disabled={locked && !allowInEditMode}
                    >
                      {label}{locked ? "  🔒  PRO" : ""}
                    </option>
                  );
                });
              })()}
            </select>
            {!canAddMultiBrand && (
              <p className="text-xs text-gray-500 mt-1">
                Core supports Bambu Lab + Generic. Upgrade to PRO to add Klipper, OctoPrint, Prusa, and Creality.
              </p>
            )}
          </div>

          {/* Model */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Model *</label>
            {models.length > 0 ? (
              <select
                value={form.model}
                onChange={(e) => setForm({ ...form, model: e.target.value })}
                required
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select model...</option>
                {models.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                value={form.model}
                onChange={(e) => setForm({ ...form, model: e.target.value })}
                required
                placeholder="e.g., Ender 3 V2"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            )}
          </div>

          {/* Code */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Code *</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value })}
                required
                placeholder="PRT-001"
                className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {!isEdit && (
                <button
                  type="button"
                  onClick={generateCode}
                  className="px-3 py-2 text-gray-400 hover:text-white border border-gray-700 rounded-lg"
                >
                  Auto
                </button>
              )}
            </div>
          </div>

          {/* Name */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Name *</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
              placeholder="e.g., X1C Bay 1"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* IP Address */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">IP Address</label>
            <input
              type="text"
              value={form.ip_address}
              onChange={(e) => setForm({ ...form, ip_address: e.target.value })}
              placeholder="192.168.1.100"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Access Code - BambuLab only */}
          {form.brand === "bambulab" && (
            <div>
              <label className="block text-sm text-gray-300 mb-1">LAN Access Code</label>
              <input
                type="text"
                value={form.access_code}
                onChange={(e) => setForm({ ...form, access_code: e.target.value })}
                placeholder="8-digit code from printer"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-500 mt-1">
                Find this in your printer's network settings
              </p>
            </div>
          )}

          {/* Serial Number */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Serial Number</label>
            <input
              type="text"
              value={form.serial_number}
              onChange={(e) => setForm({ ...form, serial_number: e.target.value })}
              placeholder="Optional"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Location */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Location</label>
            <input
              type="text"
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
              placeholder="e.g., Farm A, Bay 1"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Work Center (Machine Pool) */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Machine Pool</label>
            <select
              value={form.work_center_id}
              onChange={(e) => setForm({ ...form, work_center_id: e.target.value ? parseInt(e.target.value) : "" })}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">None</option>
              {workCenters.map((wc) => (
                <option key={wc.id} value={wc.id}>{wc.name}</option>
              ))}
            </select>
          </div>

          {/* Supported Filament Diameters */}
          <div>
            <label className="block text-sm text-gray-300 mb-2">Supported Diameters</label>
            <div className="flex gap-6">
              {[1.75, 2.85].map((d) => (
                <label key={d} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.filament_diameters.includes(d)}
                    onChange={() => toggleDiameter(d)}
                    className="w-4 h-4 rounded bg-gray-800 border-gray-700 text-blue-500 focus:ring-blue-500"
                  />
                  <span className="text-sm text-gray-300">{d} mm</span>
                </label>
              ))}
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Notes</label>
            <textarea
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder="Optional notes..."
              rows={2}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Active toggle */}
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="active"
              checked={form.active}
              onChange={(e) => setForm({ ...form, active: e.target.checked })}
              className="w-4 h-4 rounded bg-gray-800 border-gray-700 text-blue-500 focus:ring-blue-500"
            />
            <label htmlFor="active" className="text-gray-300">Active</label>
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
              className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 text-white px-4 py-2 rounded-lg transition-colors"
            >
              {loading ? "Saving..." : isEdit ? "Update" : "Add Printer"}
            </button>
          </div>
      </form>
    </Modal>
  );
}
