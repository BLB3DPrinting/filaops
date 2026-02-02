/**
 * CustomerDetailsModal - View customer details with tabs (overview, orders, portal).
 *
 * Extracted from AdminCustomers.jsx (ARCHITECT-002)
 */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";
import Modal from "../Modal";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";

// B2B Portal Settings Tab Component (Community Edition - Read Only)
function PortalSettingsTab({ customerId: _customerId, portalDetails, loading, onRefresh: _onRefresh }) {
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

      {/* PRO Features Notice */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <svg className="w-5 h-5 text-blue-400 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p className="text-sm font-medium text-blue-400">B2B Portal Features</p>
            <p className="text-xs text-gray-400 mt-1">
              Advanced B2B portal features including price levels, catalog access control, and wholesale pricing
              are available in FilaOps PRO.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function CustomerDetailsModal({ customer, onClose, onEdit }) {
  const token = localStorage.getItem("adminToken");
  const { isPro } = useFeatureFlags();
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
          headers: { Authorization: `Bearer ${token}` },
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
          headers: { Authorization: `Bearer ${token}` },
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
                    $
                    {parseFloat(customer.total_spent || 0).toLocaleString("en-US", {
                      minimumFractionDigits: 2,
                    })}
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
