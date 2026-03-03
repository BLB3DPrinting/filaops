import { useState, useEffect, useCallback } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import ProGate from "../../components/ProGate";

// Inline SVG icons for each integration
const QuickBooksIcon = () => (
  <svg
    className="w-8 h-8 text-green-400"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    aria-hidden="true"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.5}
      d="M4 5a2 2 0 012-2h8a2 2 0 012 2v1h2a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2V5z"
    />
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.5}
      d="M8 3v4m4-4v4m-6 4h8m-8 3h5"
    />
  </svg>
);

const ShopifyIcon = () => (
  <svg
    className="w-8 h-8 text-green-400"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    aria-hidden="true"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.5}
      d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4H6z"
    />
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.5}
      d="M3 6h18"
    />
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.5}
      d="M16 10a4 4 0 01-8 0"
    />
  </svg>
);

function formatDate(dateStr) {
  if (!dateStr) return null;
  try {
    return new Date(dateStr).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

export default function AdminIntegrations() {
  return (
    <ProGate
      feature="Integrations"
      description="Connect QuickBooks Online and Shopify to FilaOps."
      benefits={[
        "QuickBooks Online sync for invoices and payments",
        "Shopify order import and inventory sync",
        "Automated data flow between systems",
        "OAuth-based secure connections",
      ]}
    >
      <IntegrationsContent />
    </ProGate>
  );
}

function IntegrationsContent() {
  const toast = useToast();
  const api = useApi();

  // QuickBooks state
  const [qbStatus, setQbStatus] = useState(null);
  const [qbLoading, setQbLoading] = useState(true);
  const [qbError, setQbError] = useState(null);
  const [qbConnecting, setQbConnecting] = useState(false);
  const [qbDisconnecting, setQbDisconnecting] = useState(false);

  // Shopify state
  const [shopifyStatus, setShopifyStatus] = useState(null);
  const [shopifyLoading, setShopifyLoading] = useState(true);
  const [shopifyError, setShopifyError] = useState(null);
  const [shopifyConnecting, setShopifyConnecting] = useState(false);
  const [shopifyDisconnecting, setShopifyDisconnecting] = useState(false);
  const [shopDomain, setShopDomain] = useState("");

  // Fetch QuickBooks status
  const fetchQbStatus = useCallback(async () => {
    setQbLoading(true);
    setQbError(null);
    try {
      const data = await api.get("/api/v1/pro/quickbooks/status");
      setQbStatus(data);
    } catch (err) {
      setQbError(err.message || "Unable to check status");
    } finally {
      setQbLoading(false);
    }
  }, [api]);

  // Fetch Shopify status
  const fetchShopifyStatus = useCallback(async () => {
    setShopifyLoading(true);
    setShopifyError(null);
    try {
      const data = await api.get("/api/v1/pro/shopify/sync/status");
      setShopifyStatus(data);
    } catch (err) {
      setShopifyError(err.message || "Unable to check status");
    } finally {
      setShopifyLoading(false);
    }
  }, [api]);

  // Fetch both on mount (independently)
  useEffect(() => {
    fetchQbStatus();
    fetchShopifyStatus();
  }, [fetchQbStatus, fetchShopifyStatus]);

  // QuickBooks connect
  const handleQbConnect = useCallback(async () => {
    setQbConnecting(true);
    try {
      const data = await api.post("/api/v1/pro/quickbooks/connect");
      if (data?.auth_url) {
        window.location.href = data.auth_url;
      } else {
        toast.error("No authorization URL returned");
      }
    } catch (err) {
      toast.error(err.message || "Failed to connect QuickBooks");
    } finally {
      setQbConnecting(false);
    }
  }, [api, toast]);

  // QuickBooks disconnect
  const handleQbDisconnect = useCallback(async () => {
    if (!window.confirm("Disconnect QuickBooks? This will remove the integration.")) {
      return;
    }
    setQbDisconnecting(true);
    try {
      await api.del("/api/v1/pro/quickbooks/disconnect");
      toast.success("QuickBooks disconnected");
      await fetchQbStatus();
    } catch (err) {
      toast.error(err.message || "Failed to disconnect QuickBooks");
    } finally {
      setQbDisconnecting(false);
    }
  }, [api, toast, fetchQbStatus]);

  // Shopify connect
  const handleShopifyConnect = useCallback(async () => {
    if (!shopDomain.trim()) return;
    setShopifyConnecting(true);
    try {
      const data = await api.post("/api/v1/pro/shopify/connect", {
        shop_domain: shopDomain.trim(),
      });
      if (data?.auth_url) {
        window.location.href = data.auth_url;
      } else {
        toast.error("No authorization URL returned");
      }
    } catch (err) {
      toast.error(err.message || "Failed to connect Shopify");
    } finally {
      setShopifyConnecting(false);
    }
  }, [api, toast, shopDomain]);

  // Shopify disconnect
  const handleShopifyDisconnect = useCallback(async () => {
    if (!window.confirm("Disconnect Shopify? This will remove the integration.")) {
      return;
    }
    setShopifyDisconnecting(true);
    try {
      await api.post("/api/v1/pro/shopify/disconnect");
      toast.success("Shopify disconnected");
      await fetchShopifyStatus();
    } catch (err) {
      toast.error(err.message || "Failed to disconnect Shopify");
    } finally {
      setShopifyDisconnecting(false);
    }
  }, [api, toast, fetchShopifyStatus]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Integrations</h1>
        <p className="text-gray-400 mt-1">
          Connect external services to sync data with FilaOps
        </p>
      </div>

      {/* Integration Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* QuickBooks Card */}
        <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 sm:p-6 space-y-4">
          <div className="flex items-center gap-3">
            <QuickBooksIcon />
            <div className="flex-1">
              <h2 className="text-lg font-semibold text-white">QuickBooks Online</h2>
            </div>
            {!qbLoading && !qbError && (
              <StatusBadge connected={qbStatus?.connected} />
            )}
          </div>

          {qbLoading && <LoadingSpinner />}

          {qbError && (
            <p className="text-sm text-red-400">{qbError}</p>
          )}

          {!qbLoading && !qbError && qbStatus?.connected && (
            <div className="space-y-2 text-sm">
              {qbStatus.company_name && (
                <div className="flex justify-between">
                  <span className="text-gray-400">Company</span>
                  <span className="text-gray-200">{qbStatus.company_name}</span>
                </div>
              )}
              {qbStatus.connected_at && (
                <div className="flex justify-between">
                  <span className="text-gray-400">Connected</span>
                  <span className="text-gray-200">{formatDate(qbStatus.connected_at)}</span>
                </div>
              )}
              {qbStatus.last_sync && (
                <div className="flex justify-between">
                  <span className="text-gray-400">Last Sync</span>
                  <span className="text-gray-200">{formatDate(qbStatus.last_sync)}</span>
                </div>
              )}
            </div>
          )}

          {!qbLoading && !qbError && (
            <div className="pt-2">
              {qbStatus?.connected ? (
                <button
                  onClick={handleQbDisconnect}
                  disabled={qbDisconnecting}
                  className="px-4 py-2 border border-red-500/50 text-red-400 rounded-lg hover:bg-red-500/10 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                >
                  {qbDisconnecting ? "Disconnecting..." : "Disconnect"}
                </button>
              ) : (
                <button
                  onClick={handleQbConnect}
                  disabled={qbConnecting}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                >
                  {qbConnecting ? "Connecting..." : "Connect"}
                </button>
              )}
            </div>
          )}
        </div>

        {/* Shopify Card */}
        <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 sm:p-6 space-y-4">
          <div className="flex items-center gap-3">
            <ShopifyIcon />
            <div className="flex-1">
              <h2 className="text-lg font-semibold text-white">Shopify</h2>
            </div>
            {!shopifyLoading && !shopifyError && (
              <StatusBadge connected={shopifyStatus?.connected} />
            )}
          </div>

          {shopifyLoading && <LoadingSpinner />}

          {shopifyError && (
            <p className="text-sm text-red-400">{shopifyError}</p>
          )}

          {!shopifyLoading && !shopifyError && shopifyStatus?.connected && (
            <div className="space-y-2 text-sm">
              {shopifyStatus.shop_name && (
                <div className="flex justify-between">
                  <span className="text-gray-400">Store</span>
                  <span className="text-gray-200">{shopifyStatus.shop_name}</span>
                </div>
              )}
              {shopifyStatus.shop_domain && (
                <div className="flex justify-between">
                  <span className="text-gray-400">Domain</span>
                  <span className="text-gray-200">{shopifyStatus.shop_domain}</span>
                </div>
              )}
              {shopifyStatus.connected_at && (
                <div className="flex justify-between">
                  <span className="text-gray-400">Connected</span>
                  <span className="text-gray-200">{formatDate(shopifyStatus.connected_at)}</span>
                </div>
              )}
              {shopifyStatus.last_sync && (
                <div className="flex justify-between">
                  <span className="text-gray-400">Last Sync</span>
                  <span className="text-gray-200">{formatDate(shopifyStatus.last_sync)}</span>
                </div>
              )}
            </div>
          )}

          {!shopifyLoading && !shopifyError && (
            <div className="pt-2 space-y-3">
              {shopifyStatus?.connected ? (
                <button
                  onClick={handleShopifyDisconnect}
                  disabled={shopifyDisconnecting}
                  className="px-4 py-2 border border-red-500/50 text-red-400 rounded-lg hover:bg-red-500/10 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                >
                  {shopifyDisconnecting ? "Disconnecting..." : "Disconnect"}
                </button>
              ) : (
                <>
                  <div>
                    <label htmlFor="shopify-domain" className="block text-sm text-gray-400 mb-1">
                      Shopify Store Domain
                    </label>
                    <input
                      id="shopify-domain"
                      type="text"
                      value={shopDomain}
                      onChange={(e) => setShopDomain(e.target.value)}
                      placeholder="yourstore.myshopify.com"
                      className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm placeholder-gray-500"
                    />
                  </div>
                  <button
                    onClick={handleShopifyConnect}
                    disabled={shopifyConnecting || !shopDomain.trim()}
                    className="w-full sm:w-auto px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                  >
                    {shopifyConnecting ? "Connecting..." : "Connect"}
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ connected }) {
  if (connected) {
    return (
      <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-green-500/20 text-green-400 border border-green-500/30">
        Connected
      </span>
    );
  }
  return (
    <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-gray-500/20 text-gray-400 border border-gray-500/30">
      Not Connected
    </span>
  );
}

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center h-16">
      <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
    </div>
  );
}
