/**
 * QualitySettingsSection — the QC rigor "dial" (#784 QMS).
 *
 * The whole Quality module is selectable. This reads the resolved policy from
 * GET /quality/policy and writes the `quality_mode` + `quality_gate_action`
 * system settings (admin-only). Casual shops can leave it off/basic; regulated
 * shops turn on full inspection with a configurable inspection gate.
 *
 * Self-contained (own fetch/save + type="button" controls), mirroring
 * AiSettingsSection, so it composes cleanly inside the AdminSettings form.
 */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../Toast";

const MODES = [
  {
    value: "off",
    label: "Off",
    desc: "No quality surfaces. The Quality module is hidden everywhere.",
  },
  {
    value: "basic",
    label: "Basic",
    desc: "Simple pass / fail + notes on a work order. The historical behavior.",
  },
  {
    value: "full",
    label: "Full",
    desc: "Plan-driven inspection: characteristics, measurements, defect reasons, photos, and a configurable inspection gate.",
  },
];

// What the inspection gate does when a PASS is recorded against an incomplete
// or out-of-spec inspection. Only meaningful in full mode.
const GATE_ACTIONS = [
  { value: "off", label: "Off", desc: "Record results; never block. No enforcement." },
  { value: "warn", label: "Warn", desc: "Flag an incomplete or out-of-spec pass, but allow it." },
  { value: "block", label: "Block", desc: "Reject the pass unless every characteristic is measured and in spec." },
];

export default function QualitySettingsSection() {
  const toast = useToast();
  const [mode, setMode] = useState("basic");
  const [gateAction, setGateAction] = useState("warn");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const fetchPolicy = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/quality/policy`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setMode(data.mode || "basic");
        setGateAction(data.gate_action || "warn");
      }
    } catch (error) {
      console.error("Failed to load quality policy:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPolicy();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const putSetting = async (key, value) => {
    const res = await fetch(`${API_URL}/api/v1/system/settings/${key}`, {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to save ${key}`);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await putSetting("quality_mode", mode);
      await putSetting("quality_gate_action", gateAction);
      toast.success("Quality settings saved");
    } catch (error) {
      toast.error(error.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-6 text-gray-400">
        Loading quality settings…
      </div>
    );
  }

  return (
    <div className="bg-gray-800 rounded-lg p-6">
      <h2 className="text-xl font-semibold text-white mb-1">Quality (QC)</h2>
      <p className="text-sm text-gray-400 mb-4">
        Choose how much quality rigor this shop runs. Casual shops can leave it
        off or basic; regulated shops turn on full inspection.
      </p>

      {/* Mode selector — radio cards */}
      <div className="space-y-3">
        {MODES.map((m) => (
          <label
            key={m.value}
            className={`flex items-start gap-3 p-4 rounded-lg border-2 cursor-pointer transition-colors ${
              mode === m.value
                ? "border-blue-600 bg-blue-900/20"
                : "border-gray-600 bg-gray-700/40 hover:border-gray-500"
            }`}
          >
            <input
              type="radio"
              name="quality_mode"
              value={m.value}
              checked={mode === m.value}
              onChange={() => setMode(m.value)}
              className="mt-1 w-4 h-4 text-blue-600"
            />
            <div>
              <div className="text-white font-medium">{m.label}</div>
              <p className="text-sm text-gray-400 mt-0.5">{m.desc}</p>
            </div>
          </label>
        ))}
      </div>

      {/* Gate action selector — only meaningful in full mode */}
      <div className={`mt-5 ${mode === "full" ? "" : "opacity-50 pointer-events-none"}`}>
        <h3 className="text-sm font-medium text-white mb-1">Inspection Gate</h3>
        <p className="text-sm text-gray-400 mb-3">
          What happens when a pass is recorded against an incomplete or
          out-of-spec inspection. Only applies in Full mode.
        </p>
        <div className="space-y-2">
          {GATE_ACTIONS.map((g) => (
            <label
              key={g.value}
              className={`flex items-start gap-3 p-3 rounded-lg border-2 cursor-pointer transition-colors ${
                gateAction === g.value
                  ? "border-blue-600 bg-blue-900/20"
                  : "border-gray-600 bg-gray-700/40 hover:border-gray-500"
              }`}
            >
              <input
                type="radio"
                name="quality_gate_action"
                value={g.value}
                checked={gateAction === g.value}
                disabled={mode !== "full"}
                onChange={() => setGateAction(g.value)}
                className="mt-0.5 w-4 h-4 text-blue-600"
              />
              <div>
                <div className="text-white font-medium text-sm">{g.label}</div>
                <p className="text-xs text-gray-400 mt-0.5">{g.desc}</p>
              </div>
            </label>
          ))}
        </div>
      </div>

      <div className="flex justify-end pt-4">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg transition-colors"
        >
          {saving ? "Saving…" : "Save Quality Settings"}
        </button>
      </div>
    </div>
  );
}
