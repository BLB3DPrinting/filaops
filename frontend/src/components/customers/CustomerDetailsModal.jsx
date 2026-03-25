/**
 * CustomerDetailsModal - View customer details with tabs (overview, orders, portal).
 *
 * Extracted from AdminCustomers.jsx (ARCHITECT-002)
 */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";
import Modal from "../Modal";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";
import { useFormatCurrency } from "../../hooks/useFormatCurrency";
import { PAYMENT_TERMS_LABELS } from "./constants";

// B2B Portal Settings Tab Component
function PortalSettingsTab({ customerId, portalDetails, loading, onRefresh }) {
  const [priceLevels, setPriceLevels] = useState([]);
  const [customerPriceLevel, setCustomerPriceLevel] = useState(null);
  const [catalogs, setCatalogs] = useState([]);
  const [loadingPro, setLoadingPro] = useState(true);
  const [assigning, setAssigning] = useState(false);

  useEffect(() => {
    const fetchProData = async () => {
      try {
        // Fetch price levels and customer's catalog assignments in parallel
        const [plRes, catRes] = await Promise.all([
          fetch(`${API_URL}/api/v1/pro/catalogs/price-levels`, { credentials: "include" }),
          fetch(`${API_URL}/api/v1/pro/catalogs/by-customer/${customerId}`, { credentials: "include" }),
        ]);

        if (plRes.ok) {
          const levels = await plRes.json();
          setPriceLevels(Array.isArray(levels) ? levels : []);
          // Find which level this customer is assigned to
          const assigned = (Array.isArray(levels) ? levels : []).find((l) =>
            l.customers?.some((c) => c.customer_id === customerId)
          );
          setCustomerPriceLevel(assigned || null);
        }

        if (catRes.ok) {
          const catData = await catRes.json();
          setCatalogs(catData.assigned || []);
        }
      } catch {
        // Silently fail — still show portal details
      } finally {
        setLoadingPro(false);
      }
    };
    fetchProData();
  }, [customerId]);

  const handleAssignPriceLevel = async (levelId) => {
    setAssigning(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/pro/catalogs/price-levels/${levelId}/assign`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ customer_id: customerId }),
        }
      );
      if (res.ok) {
        // Refresh to show updated assignment
        const plRes = await fetch(`${API_URL}/api/v1/pro/catalogs/price-levels`, { credentials: "include" });
        if (plRes.ok) {
          const levels = await plRes.json();
          setPriceLevels(Array.isArray(levels) ? levels : []);
          const assigned = (Array.isArray(levels) ? levels : []).find((l) =>
            l.customers?.some((c) => c.customer_id === customerId)
          );
          setCustomerPriceLevel(assigned || null);
        }
      }
    } catch { /* handled silently */ } finally {
      setAssigning(false);
    }
  };

  const handleRemovePriceLevel = async () => {
    if (!customerPriceLevel) return;
    setAssigning(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/pro/catalogs/price-levels/${customerPriceLevel.id}/customers/${customerId}`,
        { method: "DELETE", credentials: "include" }
      );
      if (!res.ok) return;
      setCustomerPriceLevel(null);
      // Refresh levels
      const plRes = await fetch(`${API_URL}/api/v1/pro/catalogs/price-levels`, { credentials: "include" });
      if (plRes.ok) {
        const levels = await plRes.json();
        setPriceLevels(Array.isArray(levels) ? levels : []);
      }
      onRefresh?.();
    } catch { /* handled silently */ } finally {
      setAssigning(false);
    }
  };

  if (loading || loadingPro) {
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

      {/* Price Level Assignment */}
      <div className="bg-gray-800/50 rounded-lg p-4">
        <h3 className="text-sm font-medium text-white mb-3">Price Level</h3>
        {customerPriceLevel ? (
          <div className="flex items-center justify-between">
            <div>
              <span className="text-white text-sm font-medium">{customerPriceLevel.name}</span>
              <span className="text-green-400 text-sm ml-2">
                ({customerPriceLevel.discount_percent}% off)
              </span>
              <span className="text-gray-500 text-xs ml-2 font-mono">{customerPriceLevel.code}</span>
            </div>
            <button
              onClick={handleRemovePriceLevel}
              disabled={assigning}
              className="text-xs text-gray-400 hover:text-red-400 transition-colors disabled:opacity-50"
            >
              Remove
            </button>
          </div>
        ) : (
          <div>
            <p className="text-gray-500 text-xs mb-2">No price level assigned (base pricing)</p>
            {priceLevels.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {priceLevels.filter((l) => l.active).map((level) => (
                  <button
                    key={level.id}
                    onClick={() => handleAssignPriceLevel(level.id)}
                    disabled={assigning}
                    className="text-xs px-3 py-1.5 bg-gray-700 hover:bg-blue-600 text-gray-300 hover:text-white rounded transition-colors disabled:opacity-50"
                  >
                    {level.name} ({level.discount_percent}%)
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-gray-600 text-xs">
                No price levels created yet.{" "}
                <a href="/admin/price-levels" className="text-blue-400 hover:text-blue-300">
                  Create one
                </a>
              </p>
            )}
          </div>
        )}
      </div>

      {/* Catalog Access */}
      <div className="bg-gray-800/50 rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-white">Catalog Access</h3>
          <a href="/admin/catalogs" className="text-xs text-blue-400 hover:text-blue-300">
            Manage Catalogs
          </a>
        </div>
        {catalogs.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {catalogs.map((cat) => (
              <span
                key={cat.id}
                className="px-2 py-1 bg-gray-700 rounded text-xs text-gray-300"
              >
                {cat.name}
                {cat.is_public && <span className="text-green-400 ml-1">(public)</span>}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-gray-500 text-xs">
            Only public catalogs visible. Assign this customer to private catalogs from the{" "}
            <a href="/admin/catalogs" className="text-blue-400 hover:text-blue-300">
              Catalogs page
            </a>.
          </p>
        )}
      </div>
    </div>
  );
}

export default function CustomerDetailsModal({ customer, onClose, onEdit }) {
  const { isPro } = useFeatureFlags();
  const formatCurrency = useFormatCurrency();
  const [activeTab, setActiveTab] = useState("overview");
  const [orders, setOrders] = useState([]);
  const [loadingOrders, setLoadingOrders] = useState(true);
  const [portalDetails, setPortalDetails] = useState(null);
  const [loadingPortal, setLoadingPortal] = useState(false);

  useEffect(() => {
    fetchOrders();
  }, [customer.id]);

  useEffect(() => {
    if (activeTab === "portal" && isPro && !portalDetails) {
      fetchPortalDetails();
    }
  }, [activeTab, isPro, customer.id]);

  const fetchOrders = async () => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/customers/${customer.id}/orders?limit=10`,
        {
          credentials: "include",
        }
      );
      if (res.ok) {
        const data = await res.json();
        setOrders(Array.isArray(data) ? data : []);
      }
    } catch {
      console.error("Failed to load customer orders");
    } finally {
      setLoadingOrders(false);
    }
  };

  const fetchPortalDetails = async () => {
    setLoadingPortal(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/customers/${customer.id}/portal-details`,
        {
          credentials: "include",
        }
      );
      if (res.ok) {
        const data = await res.json();
        setPortalDetails(data);
      }
    } catch {
      console.error("Failed to load portal details");
    } finally {
      setLoadingPortal(false);
    }
  };

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "orders", label: "Orders" },
  ];

  // Add B2B Portal tab for PRO tier
  if (isPro) {
    tabs.push({ id: "portal", label: "B2B Portal" });
  }

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={customer.full_name || customer.email}
      className="w-full max-w-3xl max-h-[90vh] overflow-auto"
    >
      {/* Header */}
      <div className="p-6 border-b border-gray-800 flex justify-between items-center">
          <div>
            <h2 className="text-xl font-bold text-white">
              {customer.full_name || customer.email}
            </h2>
            {customer.customer_number && (
              <p className="text-gray-400 text-sm font-mono">
                {customer.customer_number}
              </p>
            )}
          </div>
          <button
            onClick={onEdit}
            className="px-4 py-2 bg-gray-800 border border-gray-700 text-gray-300 rounded-lg hover:bg-gray-700 hover:text-white"
          >
            Edit
          </button>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-800">
          <div className="flex px-6">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors ${
                  activeTab === tab.id
                    ? "border-blue-500 text-blue-400"
                    : "border-transparent text-gray-400 hover:text-white"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        <div className="p-6">
          {/* Overview Tab */}
          {activeTab === "overview" && (
            <div className="space-y-6">
              {/* Stats */}
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-gray-800/50 rounded-lg p-4">
                  <p className="text-gray-400 text-sm">Total Orders</p>
                  <p className="text-2xl font-bold text-white">
                    {customer.order_count || 0}
                  </p>
                </div>
                <div className="bg-gray-800/50 rounded-lg p-4">
                  <p className="text-gray-400 text-sm">Total Spent</p>
                  <p className="text-2xl font-bold text-emerald-400">
                    {formatCurrency(customer.total_spent || 0)}
                  </p>
                </div>
                <div className="bg-gray-800/50 rounded-lg p-4">
                  <p className="text-gray-400 text-sm">Last Order</p>
                  <p className="text-lg font-medium text-white">
                    {customer.last_order_date
                      ? new Date(customer.last_order_date).toLocaleDateString()
                      : "Never"}
                  </p>
                </div>
              </div>

              {/* Contact Info */}
              <div>
                <h3 className="text-sm font-medium text-gray-400 uppercase mb-3">
                  Contact Information
                </h3>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-500">Email:</span>{" "}
                    <span className="text-white">{customer.email}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Phone:</span>{" "}
                    <span className="text-white">{customer.phone || "-"}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Company:</span>{" "}
                    <span className="text-white">
                      {customer.company_name || "-"}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500">Status:</span>{" "}
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs ${
                        customer.status === "active"
                          ? "bg-green-500/20 text-green-400"
                          : customer.status === "suspended"
                          ? "bg-red-500/20 text-red-400"
                          : "bg-gray-500/20 text-gray-400"
                      }`}
                    >
                      {customer.status}
                    </span>
                  </div>
                </div>
              </div>

              {/* Payment Terms */}
              <div>
                <h3 className="text-sm font-medium text-gray-400 uppercase mb-3">
                  Payment Terms
                </h3>
                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div>
                    <span className="text-gray-500">Terms:</span>{" "}
                    <span className="text-white">
                      {PAYMENT_TERMS_LABELS[customer.payment_terms] || customer.payment_terms?.toUpperCase() || "COD"}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500">Credit Limit:</span>{" "}
                    <span className="text-white">
                      {customer.credit_limit != null
                        ? formatCurrency(customer.credit_limit)
                        : "No limit"}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500">Approved for Terms:</span>{" "}
                    <span className={customer.approved_for_terms ? "text-green-400" : "text-gray-400"}>
                      {customer.approved_for_terms ? "Yes" : "No"}
                    </span>
                    {customer.approved_for_terms && customer.approved_for_terms_at && (
                      <span className="text-gray-500 text-xs ml-1">
                        ({new Date(customer.approved_for_terms_at).toLocaleDateString()})
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Addresses */}
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <h3 className="text-sm font-medium text-gray-400 uppercase mb-3">
                    Billing Address
                  </h3>
                  <div className="text-sm text-gray-300">
                    {customer.billing_address_line1 ? (
                      <>
                        <p>{customer.billing_address_line1}</p>
                        {customer.billing_address_line2 && (
                          <p>{customer.billing_address_line2}</p>
                        )}
                        <p>
                          {customer.billing_city}, {customer.billing_state}{" "}
                          {customer.billing_zip}
                        </p>
                        <p>{customer.billing_country}</p>
                      </>
                    ) : (
                      <p className="text-gray-500">No billing address</p>
                    )}
                  </div>
                </div>
                <div>
                  <h3 className="text-sm font-medium text-gray-400 uppercase mb-3">
                    Shipping Address
                  </h3>
                  <div className="text-sm text-gray-300">
                    {customer.shipping_address_line1 ? (
                      <>
                        <p>{customer.shipping_address_line1}</p>
                        {customer.shipping_address_line2 && (
                          <p>{customer.shipping_address_line2}</p>
                        )}
                        <p>
                          {customer.shipping_city}, {customer.shipping_state}{" "}
                          {customer.shipping_zip}
                        </p>
                        <p>{customer.shipping_country}</p>
                      </>
                    ) : (
                      <p className="text-gray-500">No shipping address</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Orders Tab */}
          {activeTab === "orders" && (
            <div>
              <h3 className="text-sm font-medium text-gray-400 uppercase mb-3">
                Order History
              </h3>
              {loadingOrders ? (
                <div className="flex items-center justify-center h-20">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
                </div>
              ) : orders.length > 0 ? (
                <div className="bg-gray-800/50 rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-800">
                      <tr>
                        <th className="text-left py-2 px-3 text-gray-400">Order #</th>
                        <th className="text-left py-2 px-3 text-gray-400">Date</th>
                        <th className="text-left py-2 px-3 text-gray-400">Status</th>
                        <th className="text-right py-2 px-3 text-gray-400">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {orders.map((order) => (
                        <tr key={order.id} className="border-t border-gray-700">
                          <td className="py-2 px-3 text-white font-mono">
                            {order.order_number}
                          </td>
                          <td className="py-2 px-3 text-gray-300">
                            {new Date(order.created_at).toLocaleDateString()}
                          </td>
                          <td className="py-2 px-3">
                            <span className="px-2 py-0.5 rounded-full text-xs bg-blue-500/20 text-blue-400">
                              {order.status}
                            </span>
                          </td>
                          <td className="py-2 px-3 text-right text-emerald-400">
                            ${parseFloat(order.grand_total || order.total || 0).toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-gray-500 text-sm">No orders yet</p>
              )}
            </div>
          )}

          {/* B2B Portal Tab (PRO) */}
          {activeTab === "portal" && isPro && (
            <PortalSettingsTab
              customerId={customer.id}
              portalDetails={portalDetails}
              loading={loadingPortal}
              onRefresh={fetchPortalDetails}
            />
          )}
        </div>

        <div className="p-6 border-t border-gray-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-400 hover:text-white"
          >
            Close
          </button>
        </div>
    </Modal>
  );
}
