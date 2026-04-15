import { useState, useEffect, useRef, useCallback } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";

const STATUS_COLORS = {
  idle: { bg: "bg-gray-700", dot: "bg-gray-400", text: "text-gray-400" },
  printing: {
    bg: "bg-emerald-900/30",
    dot: "bg-emerald-400",
    text: "text-emerald-400",
  },
  paused: {
    bg: "bg-yellow-900/30",
    dot: "bg-yellow-400",
    text: "text-yellow-400",
  },
  error: { bg: "bg-red-900/30", dot: "bg-red-400", text: "text-red-400" },
  offline: { bg: "bg-gray-800", dot: "bg-gray-600", text: "text-gray-600" },
};

const JOB_STATUS_COLORS = {
  queued: "text-blue-400",
  assigned: "text-yellow-400",
  printing: "text-emerald-400",
  completed: "text-green-400",
  failed: "text-red-400",
  cancelled: "text-gray-500",
};

// Brand display names + suggested models
const BRANDS = [
  {
    value: "bambulab",
    label: "Bambu Lab",
    models: ["A1", "A1 Mini", "P1S", "P1P", "X1C", "X1E"],
  },
  {
    value: "klipper",
    label: "Klipper / Moonraker",
    models: ["Voron 2.4", "Voron Trident", "Creality K1", "Creality K1 Max", "Custom"],
  },
  {
    value: "octoprint",
    label: "OctoPrint",
    models: ["Ender 3", "Ender 5", "CR-10", "Custom"],
  },
  {
    value: "prusa",
    label: "Prusa (PrusaLink)",
    models: ["MK4", "MK3.9", "XL", "MINI+"],
  },
  {
    value: "generic",
    label: "Other / Generic",
    models: ["Custom"],
  },
];

const EMPTY_FORM = {
  brand: "bambulab",
  name: "",
  model: "",
  ip_address: "",
  serial_number: "",
  location: "",
  connection_config: {},
};

function formatTime(seconds) {
  if (seconds == null) return "--";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

// ─── Brand-specific connection field sets ──────────────────────────────────

function BambuFields({ form, setField }) {
  return (
    <>
      <div>
        <label className="block text-xs text-gray-400 mb-1">
          Serial Number <span className="text-red-400">*</span>
          <span className="text-gray-500 ml-1">(from printer LCD or Bambu app)</span>
        </label>
        <input
          type="text"
          value={form.serial_number}
          onChange={(e) => setField("serial_number", e.target.value)}
          placeholder="e.g. 01P00A123456789"
          className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
      </div>
      <div>
        <label className="block text-xs text-gray-400 mb-1">
          Access Code <span className="text-red-400">*</span>
          <span className="text-gray-500 ml-1">(8-char code from printer LCD)</span>
        </label>
        <input
          type="text"
          value={form.connection_config?.access_code || ""}
          onChange={(e) =>
            setField("connection_config", {
              ...form.connection_config,
              access_code: e.target.value,
            })
          }
          placeholder="e.g. 12345678"
          maxLength={8}
          className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 font-mono"
        />
      </div>
    </>
  );
}

function KlipperFields({ form, setField }) {
  return (
    <>
      <div>
        <label className="block text-xs text-gray-400 mb-1">
          Moonraker Port
          <span className="text-gray-500 ml-1">(default 7125)</span>
        </label>
        <input
          type="number"
          value={form.connection_config?.port ?? 7125}
          onChange={(e) =>
            setField("connection_config", {
              ...form.connection_config,
              port: parseInt(e.target.value) || 7125,
            })
          }
          className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
        />
      </div>
      <div>
        <label className="block text-xs text-gray-400 mb-1">
          API Key
          <span className="text-gray-500 ml-1">(optional)</span>
        </label>
        <input
          type="text"
          value={form.connection_config?.api_key || ""}
          onChange={(e) =>
            setField("connection_config", {
              ...form.connection_config,
              api_key: e.target.value,
            })
          }
          placeholder="Moonraker API key"
          className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
      </div>
    </>
  );
}

function OctoPrintFields({ form, setField }) {
  return (
    <>
      <div>
        <label className="block text-xs text-gray-400 mb-1">
          OctoPrint Port
          <span className="text-gray-500 ml-1">(default 5000)</span>
        </label>
        <input
          type="number"
          value={form.connection_config?.port ?? 5000}
          onChange={(e) =>
            setField("connection_config", {
              ...form.connection_config,
              port: parseInt(e.target.value) || 5000,
            })
          }
          className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
        />
      </div>
      <div>
        <label className="block text-xs text-gray-400 mb-1">
          API Key <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          value={form.connection_config?.api_key || ""}
          onChange={(e) =>
            setField("connection_config", {
              ...form.connection_config,
              api_key: e.target.value,
            })
          }
          placeholder="OctoPrint API key"
          className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
      </div>
    </>
  );
}

function PrusaFields({ form, setField }) {
  return (
    <>
      <div>
        <label className="block text-xs text-gray-400 mb-1">
          PrusaLink Port
          <span className="text-gray-500 ml-1">(default 8080)</span>
        </label>
        <input
          type="number"
          value={form.connection_config?.port ?? 8080}
          onChange={(e) =>
            setField("connection_config", {
              ...form.connection_config,
              port: parseInt(e.target.value) || 8080,
            })
          }
          className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
        />
      </div>
      <div>
        <label className="block text-xs text-gray-400 mb-1">Username</label>
        <input
          type="text"
          value={form.connection_config?.username || "maker"}
          onChange={(e) =>
            setField("connection_config", {
              ...form.connection_config,
              username: e.target.value,
            })
          }
          className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
        />
      </div>
      <div>
        <label className="block text-xs text-gray-400 mb-1">
          Password <span className="text-red-400">*</span>
        </label>
        <input
          type="password"
          value={form.connection_config?.password || ""}
          onChange={(e) =>
            setField("connection_config", {
              ...form.connection_config,
              password: e.target.value,
            })
          }
          className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
        />
      </div>
    </>
  );
}

// ─── Add / Edit modal ──────────────────────────────────────────────────────

function PrinterModal({ printer, onClose, onSave }) {
  const api = useApi();
  const toast = useToast();
  const isEdit = !!printer;

  const [form, setFormState] = useState(
    printer
      ? {
          brand: printer.brand || "bambulab",
          name: printer.name || "",
          model: printer.model || "",
          ip_address: printer.ip_address || "",
          serial_number: printer.serial_number || "",
          location: printer.location || "",
          connection_config: printer.connection_config || {},
        }
      : { ...EMPTY_FORM }
  );

  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);

  const setField = (key, value) =>
    setFormState((prev) => ({ ...prev, [key]: value }));

  const handleBrandChange = (brand) => {
    setFormState((prev) => ({
      ...prev,
      brand,
      model: "",
      connection_config: {},
    }));
    setTestResult(null);
  };

  const handleTest = async () => {
    if (!printer?.id) {
      toast.error("Save the printer first, then test the connection.");
      return;
    }
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.post(
        `/api/v1/pro/filafarm/printers/${printer.id}/test-connection`
      );
      setTestResult(res);
    } catch (err) {
      setTestResult({ reachable: false, message: err.message });
    } finally {
      setTesting(false);
    }
  };

  const validate = () => {
    if (!form.name.trim()) return "Printer name is required";
    if (!form.model.trim() || form.model === "__custom")
      return "Select or enter a printer model";
    if (!form.ip_address.trim()) return "IP address is required";
    if (form.brand === "bambulab") {
      if (!form.serial_number.trim())
        return "Serial number is required for Bambu Lab printers";
      if (!form.connection_config?.access_code?.trim())
        return "Access code is required for Bambu Lab printers";
    }
    if (form.brand === "octoprint" && !form.connection_config?.api_key?.trim())
      return "API key is required for OctoPrint";
    if (form.brand === "prusa" && !form.connection_config?.password?.trim())
      return "Password is required for PrusaLink";
    return null;
  };

  const handleSave = async () => {
    const err = validate();
    if (err) {
      toast.error(err);
      return;
    }
    setSaving(true);
    try {
      const payload = {
        brand: form.brand,
        name: form.name.trim(),
        model: form.model.trim(),
        ip_address: form.ip_address.trim(),
        serial_number: form.serial_number.trim() || null,
        location: form.location.trim() || null,
        connection_config: form.connection_config || {},
      };
      if (isEdit) {
        await api.put(`/api/v1/pro/filafarm/printers/${printer.id}`, payload);
        toast.success(`${form.name} updated`);
      } else {
        await api.post("/api/v1/pro/filafarm/printers", payload);
        toast.success(`${form.name} added — fleet connecting shortly`);
      }
      onSave();
      onClose();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  const brandMeta = BRANDS.find((b) => b.value === form.brand);
  const showCustomModelInput = form.model === "__custom";

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold text-white">
            {isEdit ? "Edit Printer" : "Add Printer"}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
          {/* Brand grid — add mode only */}
          {!isEdit && (
            <div>
              <label className="block text-xs text-gray-400 mb-2">Brand</label>
              <div className="grid grid-cols-2 gap-2">
                {BRANDS.map((b) => (
                  <button
                    key={b.value}
                    type="button"
                    onClick={() => handleBrandChange(b.value)}
                    className={`px-3 py-2 rounded text-sm text-left transition-colors ${
                      form.brand === b.value
                        ? "bg-blue-600 text-white"
                        : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                    }`}
                  >
                    {b.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Printer name */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Printer Name <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setField("name", e.target.value)}
              placeholder='e.g. "BLB-A1-01"'
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Model */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Model <span className="text-red-400">*</span>
            </label>
            {brandMeta?.models.length > 1 ? (
              <select
                value={showCustomModelInput ? "__custom" : form.model}
                onChange={(e) => setField("model", e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              >
                <option value="">Select model…</option>
                {brandMeta.models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
                <option value="__custom">Custom…</option>
              </select>
            ) : (
              <input
                type="text"
                value={form.model}
                onChange={(e) => setField("model", e.target.value)}
                placeholder="Printer model"
                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              />
            )}
            {showCustomModelInput && (
              <input
                type="text"
                autoFocus
                placeholder="Enter model name"
                onChange={(e) => setField("model", e.target.value)}
                className="mt-1 w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              />
            )}
          </div>

          {/* IP address */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              IP Address <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={form.ip_address}
              onChange={(e) => setField("ip_address", e.target.value)}
              placeholder="e.g. 192.168.1.42"
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 font-mono"
            />
          </div>

          {/* Brand-specific fields */}
          {form.brand === "bambulab" && (
            <BambuFields form={form} setField={setField} />
          )}
          {form.brand === "klipper" && (
            <KlipperFields form={form} setField={setField} />
          )}
          {form.brand === "octoprint" && (
            <OctoPrintFields form={form} setField={setField} />
          )}
          {form.brand === "prusa" && (
            <PrusaFields form={form} setField={setField} />
          )}

          {/* Location (optional) */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Location
              <span className="text-gray-500 ml-1">(optional)</span>
            </label>
            <input
              type="text"
              value={form.location}
              onChange={(e) => setField("location", e.target.value)}
              placeholder='e.g. "Farm Room A"'
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Test connection result */}
          {testResult && (
            <div
              className={`rounded px-3 py-2 text-sm ${
                testResult.reachable
                  ? "bg-emerald-900/30 border border-emerald-700 text-emerald-300"
                  : "bg-red-900/30 border border-red-700 text-red-300"
              }`}
            >
              {testResult.reachable ? "✓ " : "✗ "}
              {testResult.message}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center px-6 py-4 border-t border-gray-700 gap-3">
          {isEdit && (
            <button
              onClick={handleTest}
              disabled={testing}
              className="px-3 py-1.5 text-sm bg-gray-700 text-gray-300 rounded hover:bg-gray-600 disabled:opacity-50"
            >
              {testing ? "Testing…" : "Test Connection"}
            </button>
          )}
          <div className="flex gap-2 ml-auto">
            <button
              onClick={onClose}
              className="px-4 py-1.5 text-sm text-gray-400 hover:text-white rounded"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-500 disabled:opacity-50"
            >
              {saving ? "Saving…" : isEdit ? "Save Changes" : "Add Printer"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Remove confirmation dialog ────────────────────────────────────────────

function RemoveConfirm({ printer, onConfirm, onCancel }) {
  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-sm p-6">
        <h3 className="text-base font-semibold text-white mb-2">
          Remove Printer
        </h3>
        <p className="text-sm text-gray-400 mb-6">
          Remove{" "}
          <span className="text-white font-medium">{printer.name}</span> from
          FilaFarm? Print job history is preserved. You can re-add it at any
          time.
        </p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-1.5 text-sm text-gray-400 hover:text-white rounded"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-1.5 text-sm bg-red-600 text-white rounded hover:bg-red-500"
          >
            Remove
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Printer card ──────────────────────────────────────────────────────────

function PrinterCard({ printer, onCommand, onEdit, onRemove }) {
  const colors = STATUS_COLORS[printer.status] || STATUS_COLORS.offline;
  const isPrinting = printer.status === "printing";

  return (
    <div
      className={`${colors.bg} border border-gray-700 rounded-lg p-4 hover:border-gray-500 transition-colors`}
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1 min-w-0">
          <h3 className="font-medium text-white truncate">{printer.name}</h3>
          <p className="text-xs text-gray-500 mt-0.5">{printer.model}</p>
        </div>
        <div className="flex items-center gap-2 ml-2 shrink-0">
          <span className={`flex items-center gap-1.5 text-xs ${colors.text}`}>
            <span
              className={`w-2 h-2 rounded-full ${colors.dot} ${isPrinting ? "animate-pulse" : ""}`}
            />
            {printer.status}
          </span>
          <button
            onClick={() => onEdit(printer)}
            title="Edit printer"
            className="text-gray-500 hover:text-gray-300 text-sm p-0.5"
          >
            ✎
          </button>
          <button
            onClick={() => onRemove(printer)}
            title="Remove printer"
            className="text-gray-600 hover:text-red-400 text-sm p-0.5"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Temps */}
      <div className="flex gap-4 text-xs text-gray-400 mb-2">
        <span>🔥 {printer.nozzle_temp?.toFixed(0) ?? "--"}°C</span>
        <span>🛏️ {printer.bed_temp?.toFixed(0) ?? "--"}°C</span>
      </div>

      {/* Progress bar */}
      {isPrinting && (
        <div className="mt-2">
          <div className="flex justify-between text-xs mb-1">
            <span className="text-gray-400 truncate">
              {printer.current_job || "Printing..."}
            </span>
            <span className="text-emerald-400">
              {(printer.progress ?? 0).toFixed(0)}%
            </span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-1.5">
            <div
              className="bg-emerald-500 h-1.5 rounded-full transition-all"
              style={{ width: `${printer.progress ?? 0}%` }}
            />
          </div>
        </div>
      )}

      {/* AMS slots */}
      {printer.ams_slots && printer.ams_slots.length > 0 && (
        <div className="mt-3 pt-2 border-t border-gray-700">
          <span className="text-xs text-gray-500">AMS:</span>
          <div className="flex gap-1 mt-1">
            {printer.ams_slots.map((slot, i) => (
              <div
                key={i}
                className="w-4 h-4 rounded-sm border border-gray-600"
                style={{ backgroundColor: slot.color || "#666" }}
                title={`Slot ${i + 1}: ${slot.material || "empty"}`}
              />
            ))}
          </div>
        </div>
      )}

      {/* Print controls */}
      {(printer.status === "printing" || printer.status === "paused") && (
        <div className="mt-3 pt-2 border-t border-gray-700 flex gap-2">
          {printer.status === "printing" && (
            <button
              onClick={() => onCommand(printer.id, "pause")}
              className="text-xs px-2 py-1 bg-yellow-800/50 text-yellow-300 rounded hover:bg-yellow-800"
            >
              Pause
            </button>
          )}
          {printer.status === "paused" && (
            <button
              onClick={() => onCommand(printer.id, "resume")}
              className="text-xs px-2 py-1 bg-emerald-800/50 text-emerald-300 rounded hover:bg-emerald-800"
            >
              Resume
            </button>
          )}
          <button
            onClick={() => onCommand(printer.id, "cancel")}
            className="text-xs px-2 py-1 bg-red-800/50 text-red-300 rounded hover:bg-red-800"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Job row ───────────────────────────────────────────────────────────────

function JobRow({ job }) {
  const statusColor = JOB_STATUS_COLORS[job.status] || "text-gray-400";
  return (
    <tr className="border-b border-gray-800 hover:bg-gray-800/50">
      <td className="py-2 px-3 text-sm text-white">{job.name}</td>
      <td className={`py-2 px-3 text-sm ${statusColor}`}>{job.status}</td>
      <td className="py-2 px-3 text-sm text-gray-400">
        {job.printer_id || "—"}
      </td>
      <td className="py-2 px-3 text-sm text-gray-400">
        {(job.progress ?? 0).toFixed(0)}%
      </td>
      <td className="py-2 px-3 text-sm text-gray-400">
        {formatTime(job.estimated_time)}
      </td>
      <td className="py-2 px-3 text-sm text-gray-400">{job.priority}</td>
    </tr>
  );
}

// ─── Main page ─────────────────────────────────────────────────────────────

export default function AdminFilaFarm() {
  const api = useApi();
  const toast = useToast();
  const { isPro, hasFeature, loading: flagsLoading } = useFeatureFlags();
  const hasFilaFarmAccess = isPro && hasFeature("filafarm");

  const [printers, setPrinters] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("printers");

  const [showAddModal, setShowAddModal] = useState(false);
  const [editingPrinter, setEditingPrinter] = useState(null);
  const [removingPrinter, setRemovingPrinter] = useState(null);

  const refreshRef = useRef(null);
  const commandTimeoutRef = useRef(null);

  const fetchData = useCallback(async () => {
    try {
      const [printersRes, jobsRes, statsRes] = await Promise.allSettled([
        api.get("/api/v1/pro/filafarm/printers"),
        api.get("/api/v1/pro/filafarm/jobs"),
        api.get("/api/v1/pro/filafarm/stats/today"),
      ]);

      setPrinters(
        printersRes.status === "fulfilled"
          ? printersRes.value?.printers || []
          : []
      );
      setJobs(jobsRes.status === "fulfilled" ? jobsRes.value?.jobs || [] : []);
      setStats(statsRes.status === "fulfilled" ? statsRes.value : null);

      const anyFailed =
        printersRes.status === "rejected" ||
        jobsRes.status === "rejected" ||
        statsRes.status === "rejected";
      setError(anyFailed ? "Some FilaFarm data could not be loaded." : null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    if (!hasFilaFarmAccess) return;
    fetchData();
    refreshRef.current = setInterval(fetchData, 15000);
    return () => clearInterval(refreshRef.current);
  }, [fetchData, hasFilaFarmAccess]);

  useEffect(() => {
    return () => {
      if (commandTimeoutRef.current) clearTimeout(commandTimeoutRef.current);
    };
  }, []);

  const handleCommand = async (printerId, command) => {
    try {
      await api.post(`/api/v1/pro/filafarm/printers/${printerId}/command`, {
        command,
      });
      toast.success(`Sent "${command}" to printer`);
      if (commandTimeoutRef.current) clearTimeout(commandTimeoutRef.current);
      commandTimeoutRef.current = setTimeout(fetchData, 1000);
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleRemoveConfirm = async () => {
    if (!removingPrinter) return;
    try {
      await api.del(
        `/api/v1/pro/filafarm/printers/${removingPrinter.id}`
      );
      toast.success(`${removingPrinter.name} removed`);
      setRemovingPrinter(null);
      fetchData();
    } catch (err) {
      toast.error(err.message);
    }
  };

  if (flagsLoading) {
    return (
      <div className="p-6 flex justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  if (!hasFilaFarmAccess) {
    return (
      <div className="p-6 text-center">
        <div className="bg-gray-800 rounded-lg p-8 max-w-md mx-auto">
          <svg
            className="w-12 h-12 text-gray-600 mx-auto mb-3"
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
          <h2 className="text-lg font-medium text-white mb-2">PRO Feature</h2>
          <p className="text-gray-400 text-sm">
            FilaFarm printer automation requires a PRO license with the
            FilaFarm feature enabled.
          </p>
        </div>
      </div>
    );
  }

  const printingCount = printers.filter((p) => p.status === "printing").length;
  const idleCount = printers.filter((p) => p.status === "idle").length;
  const errorCount = printers.filter((p) => p.status === "error").length;

  return (
    <div className="p-6 space-y-6">
      {/* Modals */}
      {(showAddModal || editingPrinter) && (
        <PrinterModal
          printer={editingPrinter}
          onClose={() => {
            setShowAddModal(false);
            setEditingPrinter(null);
          }}
          onSave={fetchData}
        />
      )}
      {removingPrinter && (
        <RemoveConfirm
          printer={removingPrinter}
          onConfirm={handleRemoveConfirm}
          onCancel={() => setRemovingPrinter(null)}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">FilaFarm</h1>
          <p className="text-gray-400 text-sm">
            Printer automation & job management
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={fetchData}
            className="px-3 py-1.5 text-sm bg-gray-700 text-gray-300 rounded hover:bg-gray-600"
          >
            ↻ Refresh
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-500"
          >
            + Add Printer
          </button>
        </div>
      </div>

      {/* Stats row */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-white">
              {stats.jobs_completed ?? 0}
            </div>
            <div className="text-xs text-gray-400">Jobs Completed</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-emerald-400">
              {stats.jobs_printing ?? 0}
            </div>
            <div className="text-xs text-gray-400">Currently Printing</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-blue-400">
              {stats.jobs_queued ?? 0}
            </div>
            <div className="text-xs text-gray-400">In Queue</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-yellow-400">
              {formatTime(stats.total_print_time ?? 0)}
            </div>
            <div className="text-xs text-gray-400">Total Print Time</div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-800 rounded-lg p-1 w-fit">
        {[
          { id: "printers", label: `Printers (${printers.length})` },
          { id: "jobs", label: `Jobs (${jobs.length})` },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-1.5 text-sm rounded ${
              activeTab === tab.id
                ? "bg-blue-600 text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
        </div>
      )}

      {/* Printers tab */}
      {!loading && activeTab === "printers" && (
        <div>
          {printers.length === 0 ? (
            <div className="bg-gray-800 rounded-lg p-10 text-center">
              <svg
                className="w-10 h-10 text-gray-600 mx-auto mb-3"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18"
                />
              </svg>
              <p className="text-gray-300 font-medium mb-1">No printers yet</p>
              <p className="text-gray-500 text-sm mb-4">
                Add your first printer to start automating your print farm.
              </p>
              <button
                onClick={() => setShowAddModal(true)}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-500"
              >
                + Add Printer
              </button>
            </div>
          ) : (
            <>
              <div className="flex gap-4 mb-4 text-sm">
                <span className="text-emerald-400">{printingCount} printing</span>
                <span className="text-gray-400">{idleCount} idle</span>
                {errorCount > 0 && (
                  <span className="text-red-400">{errorCount} error</span>
                )}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {printers.map((printer) => (
                  <PrinterCard
                    key={printer.id}
                    printer={printer}
                    onCommand={handleCommand}
                    onEdit={setEditingPrinter}
                    onRemove={setRemovingPrinter}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Jobs tab */}
      {!loading && activeTab === "jobs" && (
        <div>
          {jobs.length === 0 ? (
            <div className="bg-gray-800 rounded-lg p-8 text-center">
              <p className="text-gray-400">No print jobs</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-700 text-left">
                    <th className="py-2 px-3 text-xs font-medium text-gray-500 uppercase">
                      Job
                    </th>
                    <th className="py-2 px-3 text-xs font-medium text-gray-500 uppercase">
                      Status
                    </th>
                    <th className="py-2 px-3 text-xs font-medium text-gray-500 uppercase">
                      Printer
                    </th>
                    <th className="py-2 px-3 text-xs font-medium text-gray-500 uppercase">
                      Progress
                    </th>
                    <th className="py-2 px-3 text-xs font-medium text-gray-500 uppercase">
                      Est. Time
                    </th>
                    <th className="py-2 px-3 text-xs font-medium text-gray-500 uppercase">
                      Priority
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <JobRow key={job.id} job={job} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
