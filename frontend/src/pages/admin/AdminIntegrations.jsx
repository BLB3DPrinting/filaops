import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";
import AiSettingsSection from "../../components/settings/AiSettingsSection";

/**
 * AdminIntegrations — settings page for third-party integrations.
 *
 * PR-05 ships this page as the framework that PR-06/07 (Shopify, QuickBooks)
 * extend. The IntegrationCard component below is the pattern future integrations
 * follow: title, description, status badge, and a children slot for the actual
 * configuration form.
 *
 * For PR-05:
 * - AI Assistant card wraps the existing AiSettingsSection (now backed by
 *   the EncryptedString-typed `ai_api_key` column — the encryption is
 *   transparent, no UI changes required).
 * - Shopify and QuickBooks cards render placeholder content describing
 *   what those integrations will do.
 */
export default function AdminIntegrations() {
  const api = useApi();
  const { isPro, hasFeature, loading: featuresLoading } = useFeatureFlags();
  const [aiStatus, setAiStatus] = useState("loading");
  const [bambuddyStatus, setBambuddyStatus] = useState("loading");
  const bambuddyAvailable = !featuresLoading && isPro && hasFeature("bambu_integration");

  const refreshAiStatus = useCallback(async () => {
    try {
      const data = await api.get("/api/v1/settings/ai");
      // The backend reports ai_status directly: "configured" | "error" | "not_configured".
      // Falling back to ai_api_key_set covers older backends that didn't return ai_status.
      if (data?.ai_status === "configured" || data?.ai_status === "error") {
        setAiStatus(data.ai_status);
      } else if (data?.ai_api_key_set || data?.ai_provider) {
        setAiStatus("configured");
      } else {
        setAiStatus("not_configured");
      }
    } catch (err) {
      // A network or server error is NOT the same as "not configured" —
      // treating them the same hides real problems and makes the "error"
      // badge state unreachable. Log + surface an explicit error state.
      console.error("Failed to fetch AI integration status:", err);
      setAiStatus("error");
    }
  }, [api]);

  const refreshBambuddyStatus = useCallback(async () => {
    if (!bambuddyAvailable) {
      setBambuddyStatus("locked");
      return;
    }
    try {
      const data = await api.get("/api/v1/pro/integrations/bambuddy/status");
      setBambuddyStatus(data?.connected ? "configured" : "not_configured");
    } catch (err) {
      console.error("Failed to fetch Bambuddy integration status:", err);
      setBambuddyStatus("error");
    }
  }, [api, bambuddyAvailable]);

  useEffect(() => {
    refreshAiStatus();
    refreshBambuddyStatus();
  }, [refreshAiStatus, refreshBambuddyStatus]);

  return (
    <div className="space-y-6">
      <Header />

      <IntegrationCard
        title="AI Assistant"
        description="Configure AI-powered features like invoice parsing. API keys are encrypted at rest."
        status={aiStatus}
        testId="integration-card-ai"
      >
        <AiSettingsSection />
      </IntegrationCard>

      <IntegrationCard
        title="Bambuddy"
        description={
          bambuddyAvailable
            ? "Connect the managed Bambuddy service to FilaOps printer operations."
            : "Bambu printer support is included with FilaOps PRO."
        }
        status={bambuddyStatus}
        testId="integration-card-bambuddy"
      >
        {bambuddyAvailable ? (
          <div className="bg-gray-900/40 border border-gray-700/60 rounded-md p-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-gray-400">
              Configure the Bambuddy URL, API key, printer sync, and machine view.
            </p>
            <Link
              to="/admin/bambuddy"
              className="inline-flex justify-center px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium whitespace-nowrap"
            >
              Open Bambuddy
            </Link>
          </div>
        ) : (
          <div className="bg-gray-900/40 border border-gray-700/60 rounded-md p-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-gray-400">
              Activate PRO to start Bambuddy, connect its API key, and link Bambu
              machines to existing FilaOps printers.
            </p>
            <Link
              to="/admin/license"
              className="inline-flex justify-center px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium whitespace-nowrap"
            >
              Upgrade to PRO
            </Link>
          </div>
        )}
      </IntegrationCard>

      <IntegrationCard
        title="Shopify"
        description="Sync orders, inventory, and customers with your Shopify store."
        status="not_configured"
        testId="integration-card-shopify"
      >
        <ComingSoonBody
          headline="Coming in a future update."
          bullets={[
            "Pull paid Shopify orders into FilaOps as production orders",
            "Push inventory levels back to Shopify when items are produced",
            "Map Shopify customers to FilaOps customer records",
          ]}
        />
      </IntegrationCard>

      <IntegrationCard
        title="QuickBooks Online"
        description="Sync invoices, payments, and chart of accounts."
        status="not_configured"
        testId="integration-card-qbo"
      >
        <ComingSoonBody
          headline="Coming in a future update."
          bullets={[
            "Push FilaOps invoices to QuickBooks Online",
            "Reconcile QuickBooks payments back to FilaOps invoices",
            "Map FilaOps GL accounts to your QuickBooks chart of accounts",
          ]}
        />
      </IntegrationCard>
    </div>
  );
}

function Header() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-white">
        Integrations &amp; Connections
      </h1>
      <p className="text-gray-400 mt-1">
        Connect FilaOps to outside services. Each integration stores its
        credentials encrypted at rest.
      </p>
    </div>
  );
}

/**
 * IntegrationCard — reusable pattern for an integration section.
 *
 * Future integrations (PR-06 Shopify, PR-07 QBO) follow this same shape:
 *   <IntegrationCard title=... description=... status=... testId=...>
 *     <ConfigForm />
 *   </IntegrationCard>
 *
 * Status values: "configured" | "not_configured" | "error" | "loading".
 */
export function IntegrationCard({
  title,
  description,
  status = "not_configured",
  testId,
  children,
}) {
  return (
    <div
      data-testid={testId}
      className="bg-gray-800/40 border border-gray-700 rounded-lg p-6 space-y-4"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-white">{title}</h2>
          <p className="text-sm text-gray-400">{description}</p>
        </div>
        <StatusBadge status={status} />
      </div>
      <div>{children}</div>
    </div>
  );
}

function StatusBadge({ status }) {
  const variants = {
    configured: {
      label: "Configured",
      classes: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    },
    not_configured: {
      label: "Not configured",
      classes: "bg-gray-500/15 text-gray-300 border-gray-500/30",
    },
    error: {
      label: "Error",
      classes: "bg-red-500/15 text-red-300 border-red-500/30",
    },
    loading: {
      label: "Loading…",
      classes: "bg-gray-500/15 text-gray-400 border-gray-500/30",
    },
    locked: {
      label: "PRO feature",
      classes: "bg-blue-500/15 text-blue-300 border-blue-500/30",
    },
  };
  const v = variants[status] || variants.not_configured;
  return (
    <span
      role="status"
      aria-label={`Status: ${v.label}`}
      className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold border whitespace-nowrap ${v.classes}`}
    >
      {v.label}
    </span>
  );
}

function ComingSoonBody({ headline, bullets }) {
  return (
    <div className="bg-gray-900/40 border border-gray-700/60 rounded-md p-4 space-y-2">
      <p className="text-sm font-medium text-gray-200">{headline}</p>
      <ul className="text-sm text-gray-400 list-disc pl-5 space-y-1">
        {bullets.map((b) => (
          <li key={b}>{b}</li>
        ))}
      </ul>
    </div>
  );
}
