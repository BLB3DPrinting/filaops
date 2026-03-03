import { useState, useEffect, useCallback } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import ProGate from "../../components/ProGate";

export default function AdminQuoteConfig() {
  return (
    <ProGate
      feature="Quote Config"
      description="Configure pricing parameters for the auto-quoter."
      benefits={[
        "Material cost per gram configuration",
        "Machine hour rate and markup settings",
        "Rush order multiplier management",
        "Minimum quote price controls",
      ]}
    >
      <QuoteConfigContent />
    </ProGate>
  );
}

/** Format a snake_case key as Title Case with spaces. */
function formatLabel(key) {
  return key
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function QuoteConfigContent() {
  const toast = useToast();
  const api = useApi();

  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get("/api/v1/pro/quotes/config/pricing");
      setConfig(data);
    } catch (err) {
      setError(err.message || "Failed to load quote configuration");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleScalarChange = (field, value) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
  };

  const handleMaterialCostChange = (material, value) => {
    setConfig((prev) => ({
      ...prev,
      material_costs: { ...prev.material_costs, [material]: value },
    }));
  };

  const handleRushMultiplierChange = (key, value) => {
    setConfig((prev) => ({
      ...prev,
      rush_multipliers: { ...prev.rush_multipliers, [key]: value },
    }));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      // Coerce all numeric fields to numbers before sending
      const payload = {
        material_costs: Object.fromEntries(
          Object.entries(config.material_costs).map(([k, v]) => [k, Number(v)])
        ),
        machine_hour_rate: Number(config.machine_hour_rate),
        markup_percent: Number(config.markup_percent),
        min_quote_price: Number(config.min_quote_price),
        estimation_grams_per_hour: Number(config.estimation_grams_per_hour),
        rush_multipliers: Object.fromEntries(
          Object.entries(config.rush_multipliers).map(([k, v]) => [
            k,
            Number(v),
          ])
        ),
      };
      await api.put("/api/v1/pro/quotes/config/pricing", payload);
      toast.success("Quote configuration saved");
    } catch (err) {
      toast.error(err.message || "Failed to save quote configuration");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Quote Configuration</h1>
        <p className="text-gray-400 mt-1">
          Configure pricing parameters for the auto-quoter
        </p>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400">
          {error}
        </div>
      )}

      {/* Loading spinner */}
      {loading && (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      )}

      {/* Config form */}
      {!loading && config && (
        <form onSubmit={handleSave} className="space-y-6">
          {/* Section 1 — Material Costs */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold text-white mb-4">
              Material Costs ($/gram)
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.entries(config.material_costs).map(
                ([material, cost]) => (
                  <div key={material}>
                    <label className="block text-sm font-medium text-gray-300 mb-1">
                      {formatLabel(material)}
                    </label>
                    <input
                      type="number"
                      value={cost}
                      onChange={(e) =>
                        handleMaterialCostChange(material, e.target.value)
                      }
                      step="any"
                      min="0"
                      className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                    />
                  </div>
                )
              )}
            </div>
          </div>

          {/* Section 2 — Machine & Pricing */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold text-white mb-4">
              Machine &amp; Pricing
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Machine Rate ($/hour)
                </label>
                <input
                  type="number"
                  value={config.machine_hour_rate}
                  onChange={(e) =>
                    handleScalarChange("machine_hour_rate", e.target.value)
                  }
                  step="any"
                  min="0"
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Markup %
                </label>
                <input
                  type="number"
                  value={config.markup_percent}
                  onChange={(e) =>
                    handleScalarChange("markup_percent", e.target.value)
                  }
                  step="any"
                  min="0"
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Minimum Quote Price ($)
                </label>
                <input
                  type="number"
                  value={config.min_quote_price}
                  onChange={(e) =>
                    handleScalarChange("min_quote_price", e.target.value)
                  }
                  step="any"
                  min="0"
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Estimation Speed (grams/hour)
                </label>
                <input
                  type="number"
                  value={config.estimation_grams_per_hour}
                  onChange={(e) =>
                    handleScalarChange(
                      "estimation_grams_per_hour",
                      e.target.value
                    )
                  }
                  step="any"
                  min="0"
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                />
              </div>
            </div>
          </div>

          {/* Section 3 — Rush Multipliers */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold text-white mb-4">
              Rush Multipliers
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.entries(config.rush_multipliers).map(([key, value]) => (
                <div key={key}>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    {formatLabel(key)}
                  </label>
                  <input
                    type="number"
                    value={value}
                    onChange={(e) =>
                      handleRushMultiplierChange(key, e.target.value)
                    }
                    step="any"
                    min="0"
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                  />
                </div>
              ))}
            </div>
          </div>

          {/* Save button */}
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={saving}
              className="px-6 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? "Saving..." : "Save Configuration"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
