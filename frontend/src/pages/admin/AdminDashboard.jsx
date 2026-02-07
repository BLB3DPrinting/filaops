import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { API_URL } from "../../config/api";
import StatCard from "../../components/StatCard";
import RecentOrderRow from "../../components/dashboard/RecentOrderRow";
import SalesChart from "../../components/dashboard/SalesChart";
import ProductionPipeline from "../../components/dashboard/ProductionPipeline";

export default function AdminDashboard() {
  const [stats, setStats] = useState(null);
  const [recentOrders, setRecentOrders] = useState([]);
  const [pendingPOs, setPendingPOs] = useState([]);
  const [salesData, setSalesData] = useState(null);
  const [salesPeriod, setSalesPeriod] = useState("MTD");
  const [salesLoading, setSalesLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  // Fetch sales trend data when period changes
  useEffect(() => {
    fetchSalesData(salesPeriod);
  }, [salesPeriod]);

  const fetchSalesData = async (period) => {
    setSalesLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/dashboard/sales-trend?period=${period}`,
        { credentials: "include" }
      );
      if (res.ok) {
        const data = await res.json();
        setSalesData(data);
      }
    } catch (err) {
      console.error("Failed to fetch sales data:", err);
    } finally {
      setSalesLoading(false);
    }
  };

  // Format revenue with smart display (show actual $ under 1k, otherwise Xk)
  const formatRevenue = (amount) => {
    if (amount < 1000) {
      return `$${amount.toFixed(0)}`;
    }
    return `$${(amount / 1000).toFixed(1)}k`;
  };

  const fetchDashboardData = async () => {
    try {
      setLoading(true);

      // Fetch summary stats
      const summaryRes = await fetch(
        `${API_URL}/api/v1/admin/dashboard/summary`,
        {
          credentials: "include",
        }
      );

      if (!summaryRes.ok) throw new Error("Failed to fetch dashboard summary");
      const summaryData = await summaryRes.json();
      setStats(summaryData);

      // Fetch recent orders
      const ordersRes = await fetch(
        `${API_URL}/api/v1/admin/dashboard/recent-orders?limit=5`,
        {
          credentials: "include",
        }
      );

      if (ordersRes.ok) {
        const ordersData = await ordersRes.json();
        setRecentOrders(ordersData);
      }

      // Fetch pending purchase orders
      const posRes = await fetch(
        `${API_URL}/api/v1/purchase-orders?status=draft,ordered&limit=5`,
        {
          credentials: "include",
        }
      );

      if (posRes.ok) {
        const posData = await posRes.json();
        setPendingPOs(posData.items || posData || []);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-red-400 flex flex-col">
        <h3 className="font-semibold mb-2">Error loading dashboard</h3>
        <p className="text-sm">{error}</p>
        <button
          onClick={fetchDashboardData}
          className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-gray-400 mt-1">Welcome to the FilaOps Admin Panel</p>
      </div>

      {/* Sales Trend Chart - Primary KPI */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <SalesChart
          data={salesData}
          period={salesPeriod}
          onPeriodChange={setSalesPeriod}
          loading={salesLoading}
        />
      </div>

      {/* Action Items Section */}
      {(stats?.orders?.overdue > 0 ||
        stats?.inventory?.low_stock_count > 0 ||
        stats?.production?.ready_to_start > 0 ||
        stats?.orders?.ready_to_ship > 0 ||
        stats?.quotes?.pending > 0) && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
            <svg
              className="w-5 h-5 text-blue-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
              />
            </svg>
            <h3 className="font-semibold text-white">Action Items</h3>
          </div>
          <div className="divide-y divide-gray-800">
            {/* Critical - Overdue */}
            {stats?.orders?.overdue > 0 && (
              <Link
                to="/admin/orders?status=overdue"
                className="flex items-center justify-between px-4 py-3 hover:bg-gray-800/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="w-2 h-2 rounded-full bg-red-500"></span>
                  <span className="text-white">
                    {stats.orders.overdue} Overdue Order{stats.orders.overdue !== 1 ? "s" : ""}
                  </span>
                </div>
                <span className="text-xs text-red-400 font-medium">URGENT</span>
              </Link>
            )}
            {/* Warning - Low Stock */}
            {stats?.inventory?.low_stock_count > 0 && (
              <Link
                to="/admin/purchasing?tab=low-stock"
                className="flex items-center justify-between px-4 py-3 hover:bg-gray-800/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="w-2 h-2 rounded-full bg-yellow-500"></span>
                  <span className="text-white">
                    {stats.inventory.low_stock_count} Low Stock Item{stats.inventory.low_stock_count !== 1 ? "s" : ""}
                  </span>
                </div>
                <span className="text-xs text-yellow-400">Reorder needed</span>
              </Link>
            )}
            {/* Action - Quotes */}
            {stats?.quotes?.pending > 0 && (
              <Link
                to="/admin/quotes"
                className="flex items-center justify-between px-4 py-3 hover:bg-gray-800/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                  <span className="text-white">
                    {stats.quotes.pending} Pending Quote{stats.quotes.pending !== 1 ? "s" : ""}
                  </span>
                </div>
                <span className="text-xs text-blue-400">Respond</span>
              </Link>
            )}
            {/* Ready - Production */}
            {stats?.production?.ready_to_start > 0 && (
              <Link
                to="/admin/production?status=released"
                className="flex items-center justify-between px-4 py-3 hover:bg-gray-800/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="w-2 h-2 rounded-full bg-green-500"></span>
                  <span className="text-white">
                    {stats.production.ready_to_start} Order{stats.production.ready_to_start !== 1 ? "s" : ""} Ready to Start
                  </span>
                </div>
                <span className="text-xs text-green-400">Start production</span>
              </Link>
            )}
            {/* Ready - Shipping */}
            {stats?.orders?.ready_to_ship > 0 && (
              <Link
                to="/admin/shipping"
                className="flex items-center justify-between px-4 py-3 hover:bg-gray-800/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="w-2 h-2 rounded-full bg-cyan-500"></span>
                  <span className="text-white">
                    {stats.orders.ready_to_ship} Order{stats.orders.ready_to_ship !== 1 ? "s" : ""} Ready to Ship
                  </span>
                </div>
                <span className="text-xs text-cyan-400">Ship</span>
              </Link>
            )}
          </div>
        </div>
      )}

      {/* SALES Section */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Sales
          </h2>
          <div className="flex-1 h-px bg-gray-800"></div>
          <Link
            to="/admin/orders"
            className="text-xs text-blue-400 hover:text-blue-300"
            aria-label="View all Sales"
          >
            View all →
          </Link>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            title="Pending Quotes"
            value={stats?.quotes?.pending || 0}
            subtitle="Awaiting review"
            color="warning"
            to="/admin/quotes"
          />
          <StatCard
            title="Orders in Progress"
            value={
              (stats?.orders?.confirmed || 0) +
              (stats?.orders?.in_production || 0)
            }
            subtitle={`${stats?.orders?.confirmed || 0} confirmed, ${
              stats?.orders?.in_production || 0
            } in production`}
            color="primary"
            to="/admin/orders"
          />
          <StatCard
            title="Ready to Ship"
            value={stats?.orders?.ready_to_ship || 0}
            subtitle={`${stats?.orders?.overdue || 0} overdue`}
            color={stats?.orders?.overdue > 0 ? "danger" : "success"}
            to="/admin/shipping"
          />
          <StatCard
            title="Revenue (30 Days)"
            value={formatRevenue(stats?.revenue?.last_30_days || 0)}
            subtitle={`${stats?.revenue?.orders_last_30_days || 0} orders`}
            color="success"
            to="/admin/payments"
          />
        </div>
      </div>

      {/* INVENTORY Section */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Inventory
          </h2>
          <div className="flex-1 h-px bg-gray-800"></div>
          <Link
            to="/admin/items"
            className="text-xs text-blue-400 hover:text-blue-300"
            aria-label="View all Inventory"
          >
            View all →
          </Link>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <StatCard
            title="Low Stock Items"
            value={stats?.inventory?.low_stock_count || 0}
            subtitle="Below reorder point or MRP shortage"
            color={stats?.inventory?.low_stock_count > 0 ? "danger" : "success"}
            to="/admin/purchasing?tab=low-stock"
          />
          <StatCard
            title="Active BOMs"
            value={stats?.boms?.active || 0}
            subtitle={`${stats?.boms?.needs_review || 0} need review`}
            color="secondary"
            to="/admin/bom"
          />
          <StatCard
            title="Orders Needing Materials"
            value={stats?.inventory?.active_orders || 0}
            subtitle="For MRP planning"
            color="neutral"
            to="/admin/purchasing"
          />
        </div>
      </div>

      {/* PRODUCTION Section */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Production
          </h2>
          <div className="flex-1 h-px bg-gray-800"></div>
          <Link
            to="/admin/production"
            className="text-xs text-blue-400 hover:text-blue-300"
            aria-label="View all Production"
          >
            View all →
          </Link>
        </div>

        {/* Production Pipeline Chart */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 mb-4">
          <h3 className="text-sm font-medium text-gray-400 mb-3">Production Pipeline</h3>
          <ProductionPipeline stats={stats} />
          {!stats?.production?.in_progress && !stats?.production?.scheduled && !stats?.production?.draft && !stats?.production?.released && (
            <p className="text-gray-500 text-sm text-center py-4">No active production orders</p>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <StatCard
            title="Work Orders In Progress"
            value={stats?.production?.in_progress || 0}
            subtitle={`${stats?.production?.ready_to_start || 0} ready to start`}
            color="primary"
            to="/admin/production?status=in_progress"
          />
          <StatCard
            title="Completed Today"
            value={stats?.production?.complete_today || 0}
            subtitle="Units finished"
            color="success"
            to="/admin/manufacturing"
          />
        </div>
      </div>

      {/* Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Orders */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-800 flex justify-between items-center">
            <h3 className="font-semibold text-white">Recent Orders</h3>
            <Link
              to="/admin/orders"
              className="text-sm text-blue-400 hover:text-blue-300"
              aria-label="View all Orders"
            >
              View all →
            </Link>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-800/50">
                <tr>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Order
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Product
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Status
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Total
                  </th>
                  <th className="w-8"></th>
                </tr>
              </thead>
              <tbody>
                {recentOrders.length > 0 ? (
                  recentOrders.map((order) => (
                    <RecentOrderRow key={order.id} order={order} />
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="py-8 text-center text-gray-500">
                      No recent orders
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Pending Purchase Orders */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-800 flex justify-between items-center">
            <h3 className="font-semibold text-white">Pending Purchases</h3>
            <Link
              to="/admin/purchasing"
              aria-label="View all Purchases"
              className="text-sm text-blue-400 hover:text-blue-300"
            >
              View all →
            </Link>
          </div>
          <div className="divide-y divide-gray-800">
            {pendingPOs.length > 0 ? (
              pendingPOs.map((po) => (
                <Link
                  key={po.id}
                  to={`/admin/purchasing?po=${po.id}`}
                  className="block px-6 py-4 hover:bg-gray-800/50 transition-colors cursor-pointer"
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="text-white font-medium">{po.po_number || `PO-${po.id}`}</p>
                      <p className="text-sm text-gray-400">{po.vendor_name || "No vendor"}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs px-2 py-1 rounded-full ${
                        po.status === "draft"
                          ? "bg-gray-500/20 text-gray-400"
                          : po.status === "ordered"
                          ? "bg-blue-500/20 text-blue-400"
                          : "bg-purple-500/20 text-purple-400"
                      }`}>
                        {po.status?.charAt(0).toUpperCase() + po.status?.slice(1)}
                      </span>
                      <svg className="w-4 h-4 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                  </div>
                  <div className="mt-2 flex gap-4 text-xs text-gray-500">
                    <span>{po.line_count || po.lines?.length || 0} items</span>
                    <span>
                      ${parseFloat(po.total_amount || po.total || 0).toFixed(2)}
                    </span>
                    {po.expected_date && (
                      <span>Due: {new Date(po.expected_date).toLocaleDateString()}</span>
                    )}
                  </div>
                </Link>
              ))
            ) : (
              <div className="px-6 py-8 text-center text-gray-500">
                No pending purchase orders
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
