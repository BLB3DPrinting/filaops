/**
 * PortalSettingsTab — B2B Portal settings for a customer.
 *
 * Extracted from CustomerDetailsModal.jsx. Shows portal access status,
 * and when PRO is active, adds price level assignment and catalog
 * assignment management.
 *
 * Props unchanged from original:
 *   customerId, portalDetails, loading, onRefresh
 */
import { useState, useEffect, useCallback } from "react";
import { useToast } from "../Toast";
import { useApi } from "../../hooks/useApi";

export default function PortalSettingsTab({ customerId, portalDetails, loading, onRefresh }) {
  const toast = useToast();
  const api = useApi();

  // Price level state
  const [priceLevels, setPriceLevels] = useState([]);
  const [loadingLevels, setLoadingLevels] = useState(true);
  const [selectedLevelId, setSelectedLevelId] = useState("");
  const [assigningLevel, setAssigningLevel] = useState(false);

  // Catalog state
  const [customerCatalogs, setCustomerCatalogs] = useState([]);
  const [allCatalogs, setAllCatalogs] = useState([]);
  const [loadingCatalogs, setLoadingCatalogs] = useState(true);
  const [selectedCatalogId, setSelectedCatalogId] = useState("");
  const [assigningCatalog, setAssigningCatalog] = useState(false);

  // Find which price level this customer belongs to
  const currentLevel = priceLevels.find((level) =>
    level.customers?.some((c) => c.id === customerId)
  );

  // Fetch price levels
  const fetchPriceLevels = useCallback(async () => {
    try {
      const data = await api.get("/api/v1/pro/catalogs/price-levels");
      setPriceLevels(Array.isArray(data) ? data : []);
    } catch {
      // PRO endpoint may not be available — silently fail
    } finally {
      setLoadingLevels(false);
    }
  }, [api]);

  // Fetch catalogs assigned to this customer
  const fetchCustomerCatalogs = useCallback(async () => {
    try {
      const data = await api.get(`/api/v1/pro/catalogs/by-customer/${customerId}`);
      setCustomerCatalogs(Array.isArray(data) ? data : []);
    } catch {
      // PRO endpoint may not be available
    }
  }, [api, customerId]);

  // Fetch all catalogs (for the assignment dropdown)
  const fetchAllCatalogs = useCallback(async () => {
    try {
      const data = await api.get("/api/v1/pro/catalogs");
      setAllCatalogs(Array.isArray(data) ? data : []);
    } catch {
      // PRO endpoint may not be available
    } finally {
      setLoadingCatalogs(false);
    }
  }, [api]);

  useEffect(() => {
    fetchPriceLevels();
    fetchCustomerCatalogs();
    fetchAllCatalogs();
  }, [fetchPriceLevels, fetchCustomerCatalogs, fetchAllCatalogs]);

  // Assign customer to a price level
  const handleAssignLevel = async () => {
    if (!selectedLevelId) return;
    setAssigningLevel(true);
    try {
      // If already on a level, remove from old one first
      if (currentLevel) {
        await api.del(`/api/v1/pro/catalogs/price-levels/${currentLevel.id}/customers/${customerId}`);
      }
      await api.post(`/api/v1/pro/catalogs/price-levels/${selectedLevelId}/assign`, {
        customer_id: customerId,
      });
      toast.success("Price level assigned");
      setSelectedLevelId("");
      await fetchPriceLevels();
    } catch {
      toast.error("Failed to assign price level");
    } finally {
      setAssigningLevel(false);
    }
  };

  // Remove customer from current price level
  const handleRemoveLevel = async () => {
    if (!currentLevel) return;
    try {
      await api.del(`/api/v1/pro/catalogs/price-levels/${currentLevel.id}/customers/${customerId}`);
      toast.success("Price level removed");
      await fetchPriceLevels();
    } catch {
      toast.error("Failed to remove price level");
    }
  };

  // Assign customer to a catalog
  const handleAssignCatalog = async () => {
    if (!selectedCatalogId) return;
    setAssigningCatalog(true);
    try {
      await api.post(`/api/v1/pro/catalogs/${selectedCatalogId}/customers`, {
        customer_id: customerId,
      });
      toast.success("Catalog assigned");
      setSelectedCatalogId("");
      await fetchCustomerCatalogs();
    } catch {
      toast.error("Failed to assign catalog");
    } finally {
      setAssigningCatalog(false);
    }
  };

  // Remove customer from a catalog
  const handleRemoveCatalog = async (catalogId) => {
    try {
      await api.del(`/api/v1/pro/catalogs/${catalogId}/customers/${customerId}`);
      toast.success("Removed from catalog");
      await fetchCustomerCatalogs();
    } catch {
      toast.error("Failed to remove from catalog");
    }
  };

  // Catalogs not yet assigned to this customer
  const unassignedCatalogs = allCatalogs.filter(
    (cat) => !customerCatalogs.some((cc) => cc.id === cat.id)
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-40">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Portal Access Status */}
      <div className="bg-gray-800/50 rounded-lg p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-medium text-white">Portal Access</h3>
            <p className="text-xs text-gray-400 mt-1">
              {portalDetails?.has_portal_access
                ? `Linked to organization: ${portalDetails.customer_organization_name}`
                : "No portal organization linked"}
            </p>
          </div>
          <span
            className={`px-3 py-1 rounded-full text-xs font-medium ${
              portalDetails?.has_portal_access
                ? "bg-green-500/20 text-green-400"
                : "bg-gray-500/20 text-gray-400"
            }`}
          >
            {portalDetails?.has_portal_access ? "Active" : "Not Configured"}
          </span>
        </div>
        {portalDetails?.portal_users_count > 0 && (
          <p className="text-xs text-gray-500 mt-2">
            {portalDetails.portal_users_count} portal user(s) linked
          </p>
        )}
      </div>

      {/* Pending Access Request */}
      {portalDetails?.pending_access_request && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <svg className="w-5 h-5 text-yellow-400 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div>
              <p className="text-sm font-medium text-yellow-400">Pending Access Request</p>
              <p className="text-xs text-yellow-400/80 mt-1">
                {portalDetails.pending_access_request.business_name} - {portalDetails.pending_access_request.contact_email}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                Submitted {new Date(portalDetails.pending_access_request.created_at).toLocaleDateString()}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Price Level Section */}
      <div className="bg-gray-800/50 rounded-lg p-4">
        <h3 className="text-sm font-medium text-white mb-3">Price Level</h3>
        {loadingLevels ? (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500"></div>
            Loading...
          </div>
        ) : currentLevel ? (
          <div className="flex items-center justify-between">
            <div>
              <span className="text-white font-medium">{currentLevel.name}</span>
              <span className="text-gray-400 text-sm ml-2">
                ({Number(currentLevel.discount_percent || 0).toFixed(1)}% discount)
              </span>
            </div>
            <div className="flex items-center gap-2">
              <select
                value={selectedLevelId}
                onChange={(e) => setSelectedLevelId(e.target.value)}
                className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm text-white"
              >
                <option value="">Change level...</option>
                {priceLevels
                  .filter((l) => l.id !== currentLevel.id && l.is_active)
                  .map((l) => (
                    <option key={l.id} value={l.id}>{l.name}</option>
                  ))}
              </select>
              {selectedLevelId && (
                <button
                  onClick={handleAssignLevel}
                  disabled={assigningLevel}
                  className="text-xs bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded disabled:opacity-50"
                >
                  {assigningLevel ? "..." : "Change"}
                </button>
              )}
              <button
                onClick={handleRemoveLevel}
                className="text-xs text-red-400 hover:text-red-300 px-2 py-1"
              >
                Remove
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-gray-500 text-sm">No price level assigned</span>
            <select
              value={selectedLevelId}
              onChange={(e) => setSelectedLevelId(e.target.value)}
              className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm text-white ml-auto"
            >
              <option value="">Select level...</option>
              {priceLevels
                .filter((l) => l.is_active)
                .map((l) => (
                  <option key={l.id} value={l.id}>{l.name}</option>
                ))}
            </select>
            {selectedLevelId && (
              <button
                onClick={handleAssignLevel}
                disabled={assigningLevel}
                className="text-xs bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded disabled:opacity-50"
              >
                {assigningLevel ? "..." : "Assign"}
              </button>
            )}
          </div>
        )}
      </div>

      {/* Catalog Assignments Section */}
      <div className="bg-gray-800/50 rounded-lg p-4">
        <h3 className="text-sm font-medium text-white mb-3">Catalog Assignments</h3>
        {loadingCatalogs ? (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500"></div>
            Loading...
          </div>
        ) : (
          <>
            {customerCatalogs.length > 0 ? (
              <div className="space-y-2 mb-3">
                {customerCatalogs.map((catalog) => (
                  <div
                    key={catalog.id}
                    className="flex items-center justify-between bg-gray-700/50 rounded px-3 py-2"
                  >
                    <div>
                      <span className="text-white text-sm">{catalog.name}</span>
                      {catalog.description && (
                        <span className="text-gray-500 text-xs ml-2">
                          {catalog.description.length > 40
                            ? catalog.description.slice(0, 40) + "..."
                            : catalog.description}
                        </span>
                      )}
                    </div>
                    <button
                      onClick={() => handleRemoveCatalog(catalog.id)}
                      className="text-red-400 hover:text-red-300 text-sm px-2"
                      title="Remove from catalog"
                    >
                      &times;
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-gray-500 text-sm mb-3">No catalogs assigned</p>
            )}

            {/* Add to catalog */}
            <div className="flex items-center gap-2">
              <select
                value={selectedCatalogId}
                onChange={(e) => setSelectedCatalogId(e.target.value)}
                className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm text-white flex-1"
              >
                <option value="">Add to catalog...</option>
                {unassignedCatalogs.map((cat) => (
                  <option key={cat.id} value={cat.id}>{cat.name}</option>
                ))}
              </select>
              <button
                onClick={handleAssignCatalog}
                disabled={!selectedCatalogId || assigningCatalog}
                className="text-xs bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded disabled:opacity-50"
              >
                {assigningCatalog ? "..." : "Add"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
