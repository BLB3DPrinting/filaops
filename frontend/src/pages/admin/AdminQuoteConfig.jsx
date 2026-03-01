import React, { useState, useEffect, useCallback } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";

// ─── Material display names ────────────────────────────────────────────────
const MATERIAL_LABELS = {
  PLA_BASIC: "PLA Basic",
  PLA_MATTE: "PLA Matte",
  PETG_HF: "PETG HF",
  PETG_BASIC: "PETG Basic",
  ABS: "ABS",
  ASA: "ASA",
  TPU: "TPU",
  PA_CF: "PA-CF (Nylon Carbon Fiber)",
  PLA_SILK: "PLA Silk",
};

// Canonical material key order shown in the UI
const MATERIAL_ORDER = [
  "PLA_BASIC",
  "PLA_MATTE",
  "PLA_SILK",
  "PETG_BASIC",
  "PETG_HF",
  "ABS",
  "ASA",
  "TPU",
  "PA_CF",
];

// Rush multiplier display labels
const RUSH_LABELS = {
  standard: "Standard",
  rush: "Rush",
  super_rush: "Super Rush",
  urgent: "Urgent",
};

const RUSH_ORDER = ["standard", "rush", "super_rush", "urgent"];

// ─── Default config (used as fallback while loading) ──────────────────────
const DEFAULT_CONFIG = {
  material_costs: {
    PLA_BASIC: 0.03,
    PLA_MATTE: 0.035,
    PETG_HF: 0.04,
    PETG_BASIC: 0.038,
    ABS: 0.04,
    ASA: 0.045,
    TPU: 0.055,
    PA_CF: 0.12,
    PLA_SILK: 0.045,
  },
  machine_hour_rate: 3.5,
  markup_percent: 40.0,
  rush_multipliers: {
    standard: 1.0,
    rush: 1.5,
    super_rush: 2.0,
    urgent: 3.0,
  },
  min_quote_price: 5.0,
  estimation_grams_per_hour: 25.0,
};

// ─── Small reusable input ─────────────────────────────────────────────────
function NumberField({ label, value, onChange, min = 0, step = 0.001, suffix = "", hint = "" }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-300 mb-1">
        {label}
      </label>
      <div className="relative flex items-center">
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          min={min}
          step={step}
          className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        />
        {suffix && (
          <span className="absolute right-3 text-gray-400 text-sm pointer-events-none">
            {suffix}
          </span>
        )}
      </div>
      {hint && <p className="text-xs text-gray-500 mt-1">{hint}</p>}
    </div>
  );
}

// ─── PRO gate upgrade prompt ──────────────────────────────────────────────
function UpgradePrompt() {
  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <div>
        <h1 className="text-3xl font-bold text-white mb-2">Quote Engine</h1>
        <p className="text-gray-400">
          Configure pricing for the customer-facing quote tool
        </p>
      </div>
      <div className="bg-gray-800 rounded-lg p-8 text-center border border-blue-500/30">
        <div className="flex justify-center mb-4">
          <svg
            className="w-12 h-12 text-blue-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
        </div>
        <h2 className="text-xl font-semibold text-white mb-2">
          FilaOps PRO Required
        </h2>
        <p className="text-gray-400 mb-6 max-w-md mx-auto">
          The Quote Engine is a PRO feature. Upgrade to configure material
          costs, pricing rules, and the customer-facing quote tool.
        </p>
        <a
          href="/pricing"
          className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold px-6 py-3 rounded-lg transition-colors"
        >
          View Pricing
        </a>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────
const AdminQuoteConfig = () => {
  const api = useApi();
  const toast = useToast();
  const { isPro, loading: flagsLoading } = useFeatureFlags();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Config state — mirrors the shape of the API response
  const [config, setConfig] = useState(DEFAULT_CONFIG);

  // Preview calculator state
  const [previewGrams, setPreviewGrams] = useState("100");
  const [previewHours, setPreviewHours] = useState("2");

  // ── Fetch ──────────────────────────────────────────────────────────────
  const fetchConfig = useCallback(async () => {
    try {
      const data = await api.get("/api/v1/pro/quotes/config/pricing");
      setConfig(data);
    } catch (err) {
      // If the endpoint isn't yet available (e.g. PRO not fully wired),
      // fall back silently to defaults rather than crashing the page.
      console.warn("Quote config fetch failed:", err.message);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    if (!flagsLoading && isPro) {
      fetchConfig();
    } else if (!flagsLoading && !isPro) {
      setLoading(false);
    }
  }, [flagsLoading, isPro, fetchConfig]);

  // ── Helpers to update nested config keys ──────────────────────────────
  const setMaterialCost = (key, value) => {
    setConfig((prev) => ({
      ...prev,
      material_costs: { ...prev.material_costs, [key]: value },
    }));
  };

  const setRushMultiplier = (key, value) => {
    setConfig((prev) => ({
      ...prev,
      rush_multipliers: { ...prev.rush_multipliers, [key]: value },
    }));
  };

  const setTopLevel = (key, value) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  // ── Save ───────────────────────────────────────────────────────────────
  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);

    // Coerce all string values from inputs back to floats
    const payload = {
      material_costs: Object.fromEntries(
        Object.entries(config.material_costs).map(([k, v]) => [k, parseFloat(v) || 0])
      ),
      machine_hour_rate: parseFloat(config.machine_hour_rate) || 0,
      markup_percent: parseFloat(config.markup_percent) || 0,
      min_quote_price: parseFloat(config.min_quote_price) || 0,
      estimation_grams_per_hour: parseFloat(config.estimation_grams_per_hour) || 1,
      rush_multipliers: Object.fromEntries(
        Object.entries(config.rush_multipliers).map(([k, v]) => [k, parseFloat(v) || 1])
      ),
    };

    try {
      const updated = await api.put("/api/v1/pro/quotes/config/pricing", payload);
      setConfig(updated);
      toast.success("Quote engine config saved successfully!");
    } catch (err) {
      toast.error("Failed to save config: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  // ── Preview calculator ─────────────────────────────────────────────────
  const calcPreview = (rushKey = "standard") => {
    const grams = parseFloat(previewGrams) || 0;
    const hours = parseFloat(previewHours) || 0;
    const costPerGram = parseFloat(config.material_costs?.PLA_BASIC) || 0.03;
    const hourRate = parseFloat(config.machine_hour_rate) || 0;
    const markup = parseFloat(config.markup_percent) || 0;
    const minPrice = parseFloat(config.min_quote_price) || 0;
    const multiplier = parseFloat(config.rush_multipliers?.[rushKey]) || 1;

    const base = grams * costPerGram + hours * hourRate;
    const withMarkup = base * (1 + markup / 100);
    const withRush = withMarkup * multiplier;
    return Math.max(withRush, minPrice).toFixed(2);
  };

  // ── Render guards ──────────────────────────────────────────────────────
  if (flagsLoading || loading) {
    return (
      <div className="p-6 text-white flex items-center gap-3">
        <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500" />
        Loading…
      </div>
    );
  }

  if (!isPro) {
    return <UpgradePrompt />;
  }

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      {/* Page header */}
      <div>
        <h1 className="text-3xl font-bold text-white mb-2">Quote Engine</h1>
        <p className="text-gray-400">
          Configure pricing for the customer-facing quote tool
        </p>
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        {/* ── Section 1: Material Costs ───────────────────────────────── */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-1">
            Material Costs
          </h2>
          <p className="text-sm text-gray-400 mb-4">
            Cost per gram ($/g) used to calculate the raw material portion of each quote.
          </p>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="text-left text-xs font-semibold text-gray-400 uppercase tracking-wider py-2 pr-4">
                    Material
                  </th>
                  <th className="text-left text-xs font-semibold text-gray-400 uppercase tracking-wider py-2 w-40">
                    Cost per gram ($)
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {MATERIAL_ORDER.map((key) => (
                  <tr key={key}>
                    <td className="py-3 pr-4">
                      <span className="text-white font-medium">
                        {MATERIAL_LABELS[key] ?? key}
                      </span>
                      <span className="ml-2 text-xs text-gray-500 font-mono">
                        {key}
                      </span>
                    </td>
                    <td className="py-3">
                      <input
                        type="number"
                        value={config.material_costs?.[key] ?? ""}
                        onChange={(e) => setMaterialCost(key, e.target.value)}
                        min={0}
                        step={0.001}
                        className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* ── Section 2: Pricing Settings ────────────────────────────── */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-1">
            Pricing Settings
          </h2>
          <p className="text-sm text-gray-400 mb-4">
            Global pricing parameters applied to every quote calculation.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <NumberField
              label="Machine Hour Rate ($/hr)"
              value={config.machine_hour_rate}
              onChange={(v) => setTopLevel("machine_hour_rate", v)}
              step={0.1}
              hint="Cost charged per machine-hour of print time"
            />
            <NumberField
              label="Markup Percent (%)"
              value={config.markup_percent}
              onChange={(v) => setTopLevel("markup_percent", v)}
              step={0.1}
              hint="Applied on top of material + machine cost"
            />
            <NumberField
              label="Minimum Quote Price ($)"
              value={config.min_quote_price}
              onChange={(v) => setTopLevel("min_quote_price", v)}
              step={0.5}
              hint="No quote will be priced below this floor"
            />
            <NumberField
              label="Estimation Grams / Hour"
              value={config.estimation_grams_per_hour}
              onChange={(v) => setTopLevel("estimation_grams_per_hour", v)}
              step={1}
              min={1}
              hint="Default print speed assumption when hours are not specified"
            />
          </div>
        </div>

        {/* ── Section 3: Rush Multipliers ────────────────────────────── */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-1">
            Rush Multipliers
          </h2>
          <p className="text-sm text-gray-400 mb-4">
            Pricing multipliers applied to the base quote for each turnaround tier.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
            {RUSH_ORDER.map((key) => {
              const val = config.rush_multipliers?.[key] ?? "";
              const displayVal =
                parseFloat(val) > 0 ? `${parseFloat(val).toFixed(1)}×` : "";
              return (
                <div key={key}>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    {RUSH_LABELS[key]}
                  </label>
                  <div className="relative flex items-center">
                    <input
                      type="number"
                      value={val}
                      onChange={(e) => setRushMultiplier(key, e.target.value)}
                      min={0.1}
                      step={0.1}
                      className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  {displayVal && (
                    <p className="text-xs text-blue-400 mt-1 font-mono">
                      {displayVal} multiplier
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Section 4: Preview Calculator ──────────────────────────── */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-1">
            Preview Calculator
          </h2>
          <p className="text-sm text-gray-400 mb-4">
            Estimate a quote price using the current settings (PLA Basic as the
            reference material).
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
            <NumberField
              label="Weight (grams)"
              value={previewGrams}
              onChange={setPreviewGrams}
              step={1}
              hint="Estimated print weight"
            />
            <NumberField
              label="Machine Time (hours)"
              value={previewHours}
              onChange={setPreviewHours}
              step={0.5}
              hint="Estimated machine hours"
            />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {RUSH_ORDER.map((key) => (
              <div
                key={key}
                className="bg-gray-700 rounded-lg p-3 text-center border border-gray-600"
              >
                <p className="text-xs text-gray-400 mb-1">{RUSH_LABELS[key]}</p>
                <p className="text-lg font-bold text-white">
                  ${calcPreview(key)}
                </p>
                <p className="text-xs text-gray-500 font-mono">
                  {parseFloat(config.rush_multipliers?.[key] || 1).toFixed(1)}×
                </p>
              </div>
            ))}
          </div>

          <p className="text-xs text-gray-500 mt-3">
            Calculation: (grams × PLA Basic cost + hours × machine rate) × (1 +
            markup%) × rush multiplier, floored at minimum price.
          </p>
        </div>

        {/* ── Save button ─────────────────────────────────────────────── */}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white font-semibold px-6 py-3 rounded-lg transition-colors"
          >
            {saving ? "Saving…" : "Save Configuration"}
          </button>
        </div>
      </form>
    </div>
  );
};

export default AdminQuoteConfig;
