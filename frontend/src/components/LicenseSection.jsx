import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { useToast } from "./Toast";
import { useFeatureFlags } from "../hooks/useFeatureFlags";
import { PRICING_URL } from "../config/pricing";

function tierLabel(tier) {
  if (tier === "enterprise") return "Enterprise";
  if (tier === "professional") return "Professional";
  return "Community";
}

export default function LicenseSection() {
  const api = useApi();
  const toast = useToast();
  const { tier, features, isPro, loading } = useFeatureFlags();
  const [opening, setOpening] = useState(false);

  const handleManage = async () => {
    setOpening(true);
    try {
      const data = await api.post("/api/v1/pro/system/manage-subscription", {
        return_url: window.location.href,
      });
      if (data?.url) {
        const popup = window.open(data.url, "_blank", "noopener,noreferrer");
        if (!popup) {
          toast.error("Popup blocked — please allow popups to open the subscription portal");
        }
      } else {
        toast.error("Could not open subscription portal");
      }
    } catch (err) {
      toast.error("Failed to open subscription portal: " + err.message);
    } finally {
      setOpening(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-6">
        <h2 className="text-xl font-semibold text-white mb-4">License</h2>
        <p className="text-sm text-gray-400">Loading license info…</p>
      </div>
    );
  }

  return (
    <div className="bg-gray-800 rounded-lg p-6">
      <h2 className="text-xl font-semibold text-white mb-4">License</h2>
      <div className="space-y-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div>
            <p className="text-sm text-gray-400">Edition</p>
            <p className="text-lg font-semibold text-white">{tierLabel(tier)}</p>
          </div>
          {isPro && features?.length > 0 && (
            <span className="px-2 py-1 bg-blue-600/20 border border-blue-500/40 text-blue-300 text-xs rounded-md font-medium">
              {features.length} {features.length === 1 ? "feature" : "features"} enabled
            </span>
          )}
        </div>

        {isPro ? (
          <div className="flex items-center gap-3 pt-2 flex-wrap">
            <button
              type="button"
              onClick={handleManage}
              disabled={opening}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg transition-colors text-sm font-medium"
            >
              {opening ? "Opening…" : "Manage Subscription ↗"}
            </button>
            <span className="text-xs text-gray-500">
              Opens the secure Stripe portal in a new tab
            </span>
          </div>
        ) : (
          <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
            <p className="text-sm text-gray-300 mb-3">
              Unlock the B2B Portal, Quote Engine, GL Accounting, Schedule C reports,
              Shopify sync, and QuickBooks export.
            </p>
            <div className="flex items-center gap-3 flex-wrap">
              <a
                href={PRICING_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors text-sm font-medium"
              >
                Upgrade to PRO
              </a>
              <span className="text-sm text-gray-400">$49 / month</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
