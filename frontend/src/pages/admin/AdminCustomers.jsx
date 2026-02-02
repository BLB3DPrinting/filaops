import { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";
import StatCard from "../../components/StatCard";
import { STATUS_OPTIONS, getStatusStyle } from "../../components/customers/constants";
import CustomerModal from "../../components/customers/CustomerModal";
import CustomerDetailsModal from "../../components/customers/CustomerDetailsModal";
import ImportCSVModal from "../../components/customers/ImportCSVModal";

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

