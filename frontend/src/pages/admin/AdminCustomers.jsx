import { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";
import Modal from "../../components/Modal";
import StatCard from "../../components/StatCard";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";

// Status options
const STATUS_OPTIONS = [
  { value: "active", label: "Active", color: "green" },
  { value: "inactive", label: "Inactive", color: "gray" },
  { value: "suspended", label: "Suspended", color: "red" },
];

// Format phone number as (XXX) XXX-XXXX
const formatPhoneNumber = (value) => {
  const digits = value.replace(/\D/g, "").slice(0, 10);
  if (digits.length === 0) return "";
  if (digits.length <= 3) return `(${digits}`;
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
};

export default function AdminCustomers() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    search: "",
    status: "all",
  });

  // Modal states
  const [showCustomerModal, setShowCustomerModal] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState(null);
  const [viewingCustomer, setViewingCustomer] = useState(null);
  const [showImportModal, setShowImportModal] = useState(false);

  const token = localStorage.getItem("adminToken");

  // Check for action=new parameter and open modal
  useEffect(() => {
    const action = searchParams.get("action");
    const returnTo = searchParams.get("returnTo");

    if (action === "new") {
      setEditingCustomer(null);
      setShowCustomerModal(true);
      // Remove the action parameter from URL
      const newParams = new URLSearchParams(searchParams);
      newParams.delete("action");
      if (returnTo) {
        newParams.set("returnTo", returnTo);
      }
      setSearchParams(newParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    fetchCustomers();
  }, [filters.status]);

  const fetchCustomers = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("limit", "200");
      if (filters.status !== "all") params.set("status", filters.status);

      const res = await fetch(`${API_URL}/api/v1/admin/customers?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to fetch customers");
      const data = await res.json();
      // API returns array directly, not { customers: [...] }
      setCustomers(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const filteredCustomers = customers.filter((customer) => {
    if (!filters.search) return true;
    const search = filters.search.toLowerCase();
    return (
      customer.email?.toLowerCase().includes(search) ||
      customer.customer_number?.toLowerCase().includes(search) ||
      customer.full_name?.toLowerCase().includes(search) ||
      customer.company_name?.toLowerCase().includes(search)
    );
  });

  // Stats calculations
  const stats = {
    total: customers.length,
    active: customers.filter((c) => c.status === "active").length,
    withOrders: customers.filter((c) => c.order_count > 0).length,
    totalRevenue: customers.reduce(
      (sum, c) => sum + (parseFloat(c.total_spent) || 0),
      0
    ),
  };

  const getStatusStyle = (status) => {
    const found = STATUS_OPTIONS.find((s) => s.value === status);
    if (!found) return "bg-gray-500/20 text-gray-400";
    return {
      green: "bg-green-500/20 text-green-400",
      gray: "bg-gray-500/20 text-gray-400",
      red: "bg-red-500/20 text-red-400",
    }[found.color];
  };

  // Save customer
  const handleSaveCustomer = async (customerData) => {
    try {
      const url = editingCustomer
        ? `${API_URL}/api/v1/admin/customers/${editingCustomer.id}`
        : `${API_URL}/api/v1/admin/customers`;
      const method = editingCustomer ? "PATCH" : "POST";

      const res = await fetch(url, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(customerData),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to save customer");
      }

      const savedCustomer = await res.json();

      // Check if we need to return to order creation
      const returnTo = searchParams.get("returnTo");
      if (returnTo === "order" && !editingCustomer) {
        // Store the newly created customer ID for the order modal
        const pendingData = sessionStorage.getItem("pendingOrderData");
        if (pendingData) {
          try {
            const data = JSON.parse(pendingData);
            data.newCustomerId = savedCustomer.id;
            sessionStorage.setItem("pendingOrderData", JSON.stringify(data));
          } catch {
            // Session storage update failure is non-critical - order creation will proceed
          }
        }
        // Navigate back to orders page (which will open the modal)
        navigate("/admin/orders");
        return;
      }

      toast.success(editingCustomer ? "Customer updated" : "Customer created");
      setShowCustomerModal(false);
      setEditingCustomer(null);
      fetchCustomers();
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Edit customer (fetch full details first so address fields are populated)
  const handleEditCustomer = async (customerId) => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/customers/${customerId}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (!res.ok) throw new Error("Failed to fetch customer details");
      const data = await res.json();
      setEditingCustomer(data);
      setShowCustomerModal(true);
    } catch (err) {
      toast.error(err.message);
    }
  };

  // View customer details
  const handleViewCustomer = async (customerId) => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/customers/${customerId}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (!res.ok) throw new Error("Failed to fetch customer details");
      const data = await res.json();
      setViewingCustomer(data);
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">Customers</h1>
          <p className="text-gray-400 mt-1">
            Manage customer accounts and view order history
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setShowImportModal(true)}
            className="px-4 py-2 bg-gray-800 border border-gray-700 text-gray-300 rounded-lg hover:bg-gray-700 hover:text-white flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            Import CSV
          </button>
          <button
            onClick={() => {
              setEditingCustomer(null);
              setShowCustomerModal(true);
            }}
            className="px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500"
          >
            + Add Customer
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard variant="simple" title="Total Customers" value={stats.total} color="neutral" />
        <StatCard variant="simple" title="Active" value={stats.active} color="success" />
        <StatCard variant="simple" title="With Orders" value={stats.withOrders} color="secondary" />
        <StatCard
          variant="simple"
          title="Total Revenue"
          value={`$${stats.totalRevenue.toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
          color="primary"
        />
      </div>

      {/* Filters */}
      <div className="flex gap-4 bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div className="flex-1">
          <input
            type="text"
            placeholder="Search by email, name, company, or customer #..."
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500"
          />
        </div>
        <select
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
        >
          <option value="all">All Status</option>
          {STATUS_OPTIONS.map((status) => (
            <option key={status.value} value={status.value}>
              {status.label}
            </option>
          ))}
        </select>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      )}

      {/* Customers Table */}
      {!loading && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-800/50">
              <tr>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Customer #
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Name
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Email
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Company
                </th>
                <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Orders
                </th>
                <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Total Spent
                </th>
                <th className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Status
                </th>
                <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredCustomers.map((customer) => (
                <tr
                  key={customer.id}
                  className="border-b border-gray-800 hover:bg-gray-800/50"
                >
                  <td className="py-3 px-4 text-white font-mono text-sm">
                    {customer.customer_number || "-"}
                  </td>
                  <td className="py-3 px-4 text-gray-300">
                    {customer.full_name || "-"}
                  </td>
                  <td className="py-3 px-4 text-gray-300">{customer.email}</td>
                  <td className="py-3 px-4 text-gray-400">
                    {customer.company_name || "-"}
                  </td>
                  <td className="py-3 px-4 text-right text-gray-300">
                    {customer.order_count || 0}
                  </td>
                  <td className="py-3 px-4 text-right text-emerald-400">
                    {customer.total_spent
                      ? `$${parseFloat(customer.total_spent).toLocaleString(
                          "en-US",
                          { minimumFractionDigits: 2 }
                        )}`
                      : "$0.00"}
                  </td>
                  <td className="py-3 px-4 text-center">
                    <span
                      className={`px-2 py-1 rounded-full text-xs ${getStatusStyle(
                        customer.status
                      )}`}
                    >
                      {STATUS_OPTIONS.find((s) => s.value === customer.status)
                        ?.label || customer.status}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right">
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => handleViewCustomer(customer.id)}
                        className="text-gray-400 hover:text-white text-sm"
                      >
                        View
                      </button>
                      <button
                        onClick={() => handleEditCustomer(customer.id)}
                        className="text-blue-400 hover:text-blue-300 text-sm"
                      >
                        Edit
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filteredCustomers.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-gray-500">
                    No customers found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Customer Create/Edit Modal */}
      {showCustomerModal && (
        <CustomerModal
          customer={editingCustomer}
          onSave={handleSaveCustomer}
          onClose={() => {
            setShowCustomerModal(false);
            setEditingCustomer(null);
          }}
        />
      )}

      {/* Customer Details Modal */}
      {viewingCustomer && (
        <CustomerDetailsModal
          customer={viewingCustomer}
          onClose={() => setViewingCustomer(null)}
          onEdit={() => {
            setViewingCustomer(null);
            handleEditCustomer(viewingCustomer.id);
          }}
        />
      )}

      {/* CSV Import Modal */}
      {showImportModal && (
        <ImportCSVModal
          onClose={() => setShowImportModal(false)}
          onImportComplete={() => {
            setShowImportModal(false);
            fetchCustomers();
          }}
        />
      )}
    </div>
  );
}

// Customer Create/Edit Modal
function CustomerModal({ customer, onSave, onClose }) {
  const [form, setForm] = useState({
    email: customer?.email || "",
    first_name: customer?.first_name || "",
    last_name: customer?.last_name || "",
    company_name: customer?.company_name || "",
    phone: customer?.phone || "",
    status: customer?.status || "active",
    // Billing
    billing_address_line1: customer?.billing_address_line1 || "",
    billing_address_line2: customer?.billing_address_line2 || "",
    billing_city: customer?.billing_city || "",
    billing_state: customer?.billing_state || "",
    billing_zip: customer?.billing_zip || "",
    billing_country: customer?.billing_country || "USA",
    // Shipping
    shipping_address_line1: customer?.shipping_address_line1 || "",
    shipping_address_line2: customer?.shipping_address_line2 || "",
    shipping_city: customer?.shipping_city || "",
    shipping_state: customer?.shipping_state || "",
    shipping_zip: customer?.shipping_zip || "",
    shipping_country: customer?.shipping_country || "USA",
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave(form);
  };

  const copyBillingToShipping = () => {
    setForm({
      ...form,
      shipping_address_line1: form.billing_address_line1,
      shipping_address_line2: form.billing_address_line2,
      shipping_city: form.billing_city,
      shipping_state: form.billing_state,
      shipping_zip: form.billing_zip,
      shipping_country: form.billing_country,
    });
  };

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={customer ? "Edit Customer" : "Add New Customer"}
      className="w-full max-w-3xl max-h-[90vh] overflow-auto"
    >
      <div className="p-6 border-b border-gray-800">
        <h2 className="text-xl font-bold text-white">
          {customer ? "Edit Customer" : "Add New Customer"}
        </h2>
      </div>

      <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Basic Info */}
          <div>
            <h3 className="text-sm font-medium text-gray-400 uppercase mb-3">
              Basic Information
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Email *
                </label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  required
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Status
                </label>
                <select
                  value={form.status}
                  onChange={(e) => setForm({ ...form, status: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                >
                  {STATUS_OPTIONS.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                First Name
              </label>
              <input
                type="text"
                value={form.first_name}
                onChange={(e) =>
                  setForm({ ...form, first_name: e.target.value })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Last Name
              </label>
              <input
                type="text"
                value={form.last_name}
                onChange={(e) =>
                  setForm({ ...form, last_name: e.target.value })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Phone</label>
              <input
                type="text"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: formatPhoneNumber(e.target.value) })}
                placeholder="(512) 555-9067"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Company Name
            </label>
            <input
              type="text"
              value={form.company_name}
              onChange={(e) =>
                setForm({ ...form, company_name: e.target.value })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
            />
          </div>

          {/* Billing Address */}
          <div>
            <h3 className="text-sm font-medium text-gray-400 uppercase mb-3">
              Billing Address
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Address Line 1
                </label>
                <input
                  type="text"
                  value={form.billing_address_line1}
                  onChange={(e) =>
                    setForm({ ...form, billing_address_line1: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Address Line 2
                </label>
                <input
                  type="text"
                  value={form.billing_address_line2}
                  onChange={(e) =>
                    setForm({ ...form, billing_address_line2: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                />
              </div>
              <div className="grid grid-cols-4 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    City
                  </label>
                  <input
                    type="text"
                    value={form.billing_city}
                    onChange={(e) =>
                      setForm({ ...form, billing_city: e.target.value })
                    }
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    State
                  </label>
                  <input
                    type="text"
                    value={form.billing_state}
                    onChange={(e) =>
                      setForm({ ...form, billing_state: e.target.value })
                    }
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    ZIP
                  </label>
                  <input
                    type="text"
                    value={form.billing_zip}
                    onChange={(e) =>
                      setForm({ ...form, billing_zip: e.target.value })
                    }
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    Country
                  </label>
                  <input
                    type="text"
                    value={form.billing_country}
                    onChange={(e) =>
                      setForm({ ...form, billing_country: e.target.value })
                    }
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Shipping Address */}
          <div>
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-sm font-medium text-gray-400 uppercase">
                Shipping Address
              </h3>
              <button
                type="button"
                onClick={copyBillingToShipping}
                className="text-sm text-blue-400 hover:text-blue-300"
              >
                Copy from Billing
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Address Line 1
                </label>
                <input
                  type="text"
                  value={form.shipping_address_line1}
                  onChange={(e) =>
                    setForm({ ...form, shipping_address_line1: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Address Line 2
                </label>
                <input
                  type="text"
                  value={form.shipping_address_line2}
                  onChange={(e) =>
                    setForm({ ...form, shipping_address_line2: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                />
              </div>
              <div className="grid grid-cols-4 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    City
                  </label>
                  <input
                    type="text"
                    value={form.shipping_city}
                    onChange={(e) =>
                      setForm({ ...form, shipping_city: e.target.value })
                    }
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    State
                  </label>
                  <input
                    type="text"
                    value={form.shipping_state}
                    onChange={(e) =>
                      setForm({ ...form, shipping_state: e.target.value })
                    }
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    ZIP
                  </label>
                  <input
                    type="text"
                    value={form.shipping_zip}
                    onChange={(e) =>
                      setForm({ ...form, shipping_zip: e.target.value })
                    }
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    Country
                  </label>
                  <input
                    type="text"
                    value={form.shipping_country}
                    onChange={(e) =>
                      setForm({ ...form, shipping_country: e.target.value })
                    }
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-4 pt-4 border-t border-gray-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-400 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500"
            >
              {customer ? "Save Changes" : "Create Customer"}
            </button>
          </div>
      </form>
    </Modal>
  );
}

// Customer Details Modal with Tabs
function CustomerDetailsModal({ customer, onClose, onEdit }) {
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

// B2B Portal Settings Tab Component (Community Edition - Read Only)
function PortalSettingsTab({ customerId, portalDetails, loading, onRefresh }) {
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

// CSV Import Modal
function ImportCSVModal({ onClose, onImportComplete }) {
  const token = localStorage.getItem("adminToken");
  const [step, setStep] = useState("upload"); // upload, preview, importing, complete
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleFile = async (selectedFile) => {
    if (!selectedFile.name.endsWith(".csv")) {
      setError("Please select a CSV file");
      return;
    }
    setFile(selectedFile);
    setError(null);

    // Preview the file
    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const res = await fetch(`${API_URL}/api/v1/admin/customers/import/preview`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to preview file");
      }

      const data = await res.json();
      setPreview(data);
      setStep("preview");
    } catch (err) {
      setError(err.message);
    }
  };

  const handleImport = async () => {
    if (!file) return;
    setImporting(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_URL}/api/v1/admin/customers/import`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Import failed");
      }

      const data = await res.json();
      setResult(data);
      setStep("complete");
    } catch (err) {
      setError(err.message);
    } finally {
      setImporting(false);
    }
  };

  const downloadTemplate = () => {
    window.open(`${API_URL}/api/v1/admin/customers/import/template`, "_blank");
  };

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title="Import Customers from CSV"
      className="w-full max-w-4xl max-h-[90vh] overflow-auto"
      disableClose={importing}
    >
      <div className="p-6 border-b border-gray-800 flex justify-between items-center">
        <h2 className="text-xl font-bold text-white">Import Customers from CSV</h2>
        <button onClick={onClose} className="text-gray-400 hover:text-white">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="p-6">
          {/* Upload Step */}
          {step === "upload" && (
            <div className="space-y-6">
              <div className="flex justify-between items-center">
                <p className="text-gray-400">Upload a CSV file with your customer data</p>
                <button
                  onClick={downloadTemplate}
                  className="text-blue-400 hover:text-blue-300 text-sm flex items-center gap-1"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Download Template
                </button>
              </div>

              {/* Drag & Drop Zone */}
              <div
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                className={`border-2 border-dashed rounded-xl p-12 text-center transition-colors ${
                  dragActive
                    ? "border-blue-500 bg-blue-500/10"
                    : "border-gray-700 hover:border-gray-600"
                }`}
              >
                <svg className="w-12 h-12 mx-auto text-gray-500 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p className="text-gray-400 mb-2">Drag and drop your CSV file here, or</p>
                <label className="cursor-pointer">
                  <span className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-300 hover:bg-gray-700 hover:text-white inline-block">
                    Browse Files
                  </span>
                  <input
                    type="file"
                    accept=".csv"
                    onChange={(e) => e.target.files[0] && handleFile(e.target.files[0])}
                    className="hidden"
                  />
                </label>
              </div>

              {/* Expected Format */}
              <div className="bg-gray-800/50 rounded-lg p-4">
                <h3 className="text-sm font-medium text-gray-300 mb-2">Supported Formats:</h3>
                <p className="text-xs text-gray-400 mb-2">
                  Automatically detects exports from <span className="text-blue-400">Shopify</span>,{" "}
                  <span className="text-purple-400">WooCommerce</span>,{" "}
                  <span className="text-orange-400">Squarespace</span>,{" "}
                  <span className="text-green-400">Etsy</span>, and generic CSV files.
                </p>
                <p className="text-xs text-gray-500 font-mono">
                  Required: email • Optional: first_name, last_name, company, phone, address fields
                </p>
              </div>

              {error && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
                  {error}
                </div>
              )}
            </div>
          )}

          {/* Preview Step */}
          {step === "preview" && preview && (
            <div className="space-y-6">
              {/* Detected Format */}
              {preview.detected_format && (
                <div className="bg-gray-800/50 rounded-lg px-4 py-2 flex items-center gap-2">
                  <span className="text-gray-400 text-sm">Detected format:</span>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    preview.detected_format === "Shopify" ? "bg-blue-500/20 text-blue-400" :
                    preview.detected_format === "WooCommerce" ? "bg-purple-500/20 text-purple-400" :
                    preview.detected_format === "Etsy" ? "bg-green-500/20 text-green-400" :
                    preview.detected_format === "Generic/Squarespace" ? "bg-orange-500/20 text-orange-400" :
                    "bg-gray-500/20 text-gray-400"
                  }`}>
                    {preview.detected_format}
                  </span>
                </div>
              )}

              {/* Summary */}
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-gray-800/50 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-white">{preview.total_rows}</p>
                  <p className="text-sm text-gray-400">Total Rows</p>
                </div>
                <div className="bg-gray-800/50 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-green-400">{preview.valid_rows}</p>
                  <p className="text-sm text-gray-400">Valid</p>
                </div>
                <div className="bg-gray-800/50 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-red-400">{preview.error_rows}</p>
                  <p className="text-sm text-gray-400">Errors</p>
                </div>
              </div>

              {preview.truncated && (
                <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3 text-yellow-400 text-sm">
                  Showing first 100 rows. Full file contains {preview.total_rows} rows.
                </div>
              )}

              {/* Preview Table */}
              <div className="bg-gray-800/30 rounded-lg overflow-hidden">
                <div className="overflow-x-auto max-h-80">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-800 sticky top-0">
                      <tr>
                        <th className="text-left py-2 px-3 text-gray-400">Row</th>
                        <th className="text-left py-2 px-3 text-gray-400">Status</th>
                        <th className="text-left py-2 px-3 text-gray-400">Email</th>
                        <th className="text-left py-2 px-3 text-gray-400">Name</th>
                        <th className="text-left py-2 px-3 text-gray-400">Company</th>
                        <th className="text-left py-2 px-3 text-gray-400">Errors</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.map((row) => (
                        <tr
                          key={row.row_number}
                          className={`border-t border-gray-700 ${!row.valid ? "bg-red-500/5" : ""}`}
                        >
                          <td className="py-2 px-3 text-gray-500">{row.row_number}</td>
                          <td className="py-2 px-3">
                            {row.valid ? (
                              <span className="text-green-400">✓</span>
                            ) : (
                              <span className="text-red-400">✗</span>
                            )}
                          </td>
                          <td className="py-2 px-3 text-white">{row.data.email || "-"}</td>
                          <td className="py-2 px-3 text-gray-300">
                            {row.data.first_name} {row.data.last_name}
                          </td>
                          <td className="py-2 px-3 text-gray-400">{row.data.company_name || "-"}</td>
                          <td className="py-2 px-3 text-red-400 text-xs">
                            {row.errors.join(", ")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {error && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
                  {error}
                </div>
              )}

              {/* Actions */}
              <div className="flex justify-between">
                <button
                  onClick={() => {
                    setStep("upload");
                    setFile(null);
                    setPreview(null);
                  }}
                  className="px-4 py-2 text-gray-400 hover:text-white"
                >
                  ← Back
                </button>
                <button
                  onClick={handleImport}
                  disabled={importing || preview.valid_rows === 0}
                  className="px-6 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {importing ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      Importing...
                    </>
                  ) : (
                    `Import ${preview.valid_rows} Customers`
                  )}
                </button>
              </div>
            </div>
          )}

          {/* Complete Step */}
          {step === "complete" && result && (
            <div className="text-center py-8 space-y-6">
              <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center mx-auto">
                <svg className="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h3 className="text-xl font-bold text-white">Import Complete!</h3>
              <div className="grid grid-cols-2 gap-4 max-w-xs mx-auto">
                <div className="bg-gray-800/50 rounded-lg p-4">
                  <p className="text-2xl font-bold text-green-400">{result.imported}</p>
                  <p className="text-sm text-gray-400">Imported</p>
                </div>
                <div className="bg-gray-800/50 rounded-lg p-4">
                  <p className="text-2xl font-bold text-gray-400">{result.skipped}</p>
                  <p className="text-sm text-gray-400">Skipped</p>
                </div>
              </div>
              {result.errors && result.errors.length > 0 && (
                <div className="bg-gray-800/50 rounded-lg p-4 text-left max-w-md mx-auto">
                  <p className="text-sm text-gray-400 mb-2">Skipped rows:</p>
                  <ul className="text-xs text-gray-500 space-y-1">
                    {result.errors.slice(0, 5).map((err, i) => (
                      <li key={i}>Row {err.row}: {err.reason}</li>
                    ))}
                    {result.errors.length > 5 && (
                      <li>...and {result.errors.length - 5} more</li>
                    )}
                  </ul>
                </div>
              )}
              <button
                onClick={onImportComplete}
                className="px-6 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500"
              >
                Done
              </button>
            </div>
          )}
      </div>
    </Modal>
  );
}
