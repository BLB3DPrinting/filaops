import { useState, useEffect, useRef } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import { API_URL } from "../../config/api";

// Shipping Trend Chart Component
function ShippingChart({ data, period, onPeriodChange, loading }) {
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const [chartWidth, setChartWidth] = useState(300);
  const chartRef = useRef(null);

  const parseLocalDate = (dateStr) => {
    if (!dateStr) return null;
    const [year, month, day] = dateStr.split('-').map(Number);
    return new Date(year, month - 1, day);
  };

  const formatDateKey = (date) => {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  };

  const fillDateRange = (rawData, startDate, endDate) => {
    if (!startDate || !endDate) return rawData || [];
    const dataMap = {};
    (rawData || []).forEach(d => { dataMap[d.date] = d; });
    const start = parseLocalDate(startDate.split('T')[0]);
    const end = parseLocalDate(endDate.split('T')[0]);
    if (!start || !end) return rawData || [];
    const filledData = [];
    const current = new Date(start);
    while (current <= end) {
      const dateKey = formatDateKey(current);
      filledData.push(dataMap[dateKey] || { date: dateKey, shipped: 0, value: 0 });
      current.setDate(current.getDate() + 1);
    }
    return filledData;
  };

  const periods = [
    { key: "WTD", label: "Week" },
    { key: "MTD", label: "Month" },
    { key: "QTD", label: "Quarter" },
    { key: "YTD", label: "Year" },
  ];

  const chartHeight = 100;

  if (loading) {
    return (
      <div className="h-32 flex items-center justify-center">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-cyan-500"></div>
      </div>
    );
  }

  const dataPoints = fillDateRange(data?.data, data?.start_date, data?.end_date);

  // Calculate cumulative values
  const cumulativeData = dataPoints.reduce((acc, d) => {
    const prev = acc[acc.length - 1] || { cumulativeValue: 0, cumulativeShipped: 0 };
    acc.push({
      ...d,
      cumulativeValue: prev.cumulativeValue + (d.value || 0),
      cumulativeShipped: prev.cumulativeShipped + (d.shipped || 0),
    });
    return acc;
  }, []);

  const maxCumulativeValue = cumulativeData.length > 0 ? cumulativeData[cumulativeData.length - 1].cumulativeValue : 1;
  const maxDailyShipped = Math.max(...dataPoints.map(d => d.shipped || 0), 1);

  const generateValuePath = () => {
    if (cumulativeData.length === 0) return "";
    const points = cumulativeData.map((d, i) => {
      const x = (i / Math.max(cumulativeData.length - 1, 1)) * 100;
      const y = 100 - (d.cumulativeValue / Math.max(maxCumulativeValue, 1)) * 100;
      return `${x},${y}`;
    });
    return `M ${points.join(" L ")}`;
  };

  const formatCurrency = (value) => {
    if (value >= 1000) return `$${(value / 1000).toFixed(1)}k`;
    return `$${value.toFixed(0)}`;
  };

  const handleMouseMove = (e, index) => {
    if (chartRef.current) {
      const rect = chartRef.current.getBoundingClientRect();
      setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
      setChartWidth(chartRef.current.offsetWidth);
    }
    setHoveredIndex(index);
  };

  const getHoveredData = () => {
    if (hoveredIndex === null || !cumulativeData[hoveredIndex]) return null;
    const d = cumulativeData[hoveredIndex];
    const localDate = parseLocalDate(d.date);
    return {
      date: localDate ? localDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '',
      shipped: d.shipped || 0,
      dailyValue: d.value || 0,
      cumulativeShipped: d.cumulativeShipped,
      cumulativeValue: d.cumulativeValue,
    };
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="flex gap-1">
          {periods.map((p) => (
            <button
              key={p.key}
              onClick={() => onPeriodChange(p.key)}
              className={`px-3 py-1 text-xs rounded-md transition-colors ${
                period === p.key
                  ? "bg-cyan-600 text-white"
                  : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="flex gap-4 text-right">
          <div>
            <p className="text-sm font-semibold text-cyan-400">{data?.total_shipped || 0}</p>
            <p className="text-xs text-gray-500">shipped</p>
          </div>
          <div>
            <p className="text-sm font-semibold text-green-400">{formatCurrency(data?.total_value || 0)}</p>
            <p className="text-xs text-gray-500">value</p>
          </div>
          {(data?.pipeline_ready > 0 || data?.pipeline_packaging > 0) && (
            <div>
              <p className="text-sm font-semibold text-yellow-400">{(data?.pipeline_ready || 0) + (data?.pipeline_packaging || 0)}</p>
              <p className="text-xs text-gray-500">in pipeline</p>
            </div>
          )}
        </div>
      </div>

      <div className="flex gap-4 mb-2 text-xs">
        <div className="flex items-center gap-1">
          <div className="w-2 h-3 bg-cyan-500/30 rounded-sm"></div>
          <span className="text-gray-500">Daily Shipped</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-0.5 bg-green-500"></div>
          <span className="text-gray-400">Cumulative Value</span>
        </div>
      </div>

      {dataPoints.length > 0 ? (
        <div ref={chartRef} className="relative" style={{ height: chartHeight }} onMouseLeave={() => setHoveredIndex(null)}>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
            <line x1="0" y1="50" x2="100" y2="50" stroke="#374151" strokeWidth="0.5" />

            {dataPoints.map((d, i) => {
              const barWidth = 100 / Math.max(dataPoints.length, 1) * 0.6;
              const x = (i / Math.max(dataPoints.length - 1, 1)) * 100 - barWidth / 2;
              const barHeight = ((d.shipped || 0) / maxDailyShipped) * 100;
              return (
                <rect
                  key={`bar-${i}`}
                  x={Math.max(0, x)}
                  y={100 - barHeight}
                  width={barWidth}
                  height={barHeight}
                  fill="url(#shippingBarGradient)"
                  opacity="0.4"
                />
              );
            })}

            <path d={generateValuePath()} fill="none" stroke="#22c55e" strokeWidth="2" vectorEffect="non-scaling-stroke" />

            {dataPoints.map((_, i) => {
              const sliceWidth = 100 / dataPoints.length;
              return (
                <rect key={`hover-${i}`} x={i * sliceWidth} y={0} width={sliceWidth} height={100} fill="transparent" onMouseMove={(e) => handleMouseMove(e, i)} style={{ cursor: 'crosshair' }} />
              );
            })}

            {hoveredIndex !== null && cumulativeData[hoveredIndex] && (
              <circle
                cx={(hoveredIndex / Math.max(cumulativeData.length - 1, 1)) * 100}
                cy={100 - (cumulativeData[hoveredIndex].cumulativeValue / Math.max(maxCumulativeValue, 1)) * 100}
                r="3" fill="#22c55e" stroke="white" strokeWidth="1" vectorEffect="non-scaling-stroke"
              />
            )}

            <defs>
              <linearGradient id="shippingBarGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#06b6d4" />
                <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.2" />
              </linearGradient>
            </defs>
          </svg>

          {hoveredIndex !== null && getHoveredData() && (
            <div
              className="absolute z-10 bg-gray-800 border border-gray-700 rounded-lg shadow-lg p-3 pointer-events-none"
              style={{ left: Math.min(mousePos.x + 10, chartWidth - 150), top: Math.max(mousePos.y - 70, 0), minWidth: '140px' }}
            >
              {(() => {
                const d = getHoveredData();
                return (
                  <>
                    <div className="text-white font-medium text-sm mb-2">{d.date}</div>
                    <div className="space-y-1 text-xs">
                      <div className="flex justify-between gap-4">
                        <span className="text-cyan-400">Shipped:</span>
                        <span className="text-white font-medium">{d.shipped}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span className="text-green-400">Value:</span>
                        <span className="text-white">${d.dailyValue.toFixed(2)}</span>
                      </div>
                      <div className="border-t border-gray-700 my-1 pt-1">
                        <div className="flex justify-between gap-4">
                          <span className="text-gray-400">Total Shipped:</span>
                          <span className="text-white">{d.cumulativeShipped}</span>
                        </div>
                        <div className="flex justify-between gap-4">
                          <span className="text-gray-400">Total Value:</span>
                          <span className="text-white">${d.cumulativeValue.toFixed(2)}</span>
                        </div>
                      </div>
                    </div>
                  </>
                );
              })()}
            </div>
          )}
        </div>
      ) : (
        <div className="h-24 flex items-center justify-center text-gray-500 text-sm">No shipments for this period</div>
      )}

      {dataPoints.length > 0 && (
        <div className="flex justify-between text-xs text-gray-500 mt-2">
          <span>{dataPoints[0]?.date ? parseLocalDate(dataPoints[0].date)?.toLocaleDateString() : ""}</span>
          <span>{dataPoints[dataPoints.length - 1]?.date ? parseLocalDate(dataPoints[dataPoints.length - 1].date)?.toLocaleDateString() : ""}</span>
        </div>
      )}
    </div>
  );
}

// Helper to format shipping address compactly
const formatAddressShort = (order) => {
  const city = order.shipping_city || "";
  const state = order.shipping_state || "";
  return city && state ? `${city}, ${state}` : city || state || "No address";
};

// Helper to check if order has a shipping address
const hasShippingAddress = (order) => {
  return !!(order.shipping_address_line1 || order.shipping_city);
};

// Helper to format due date and get urgency status
const getDueDateInfo = (order) => {
  const dueDate = order.due_date || order.requested_date;
  if (!dueDate) return { text: "No date", status: "none", sortValue: Infinity };

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const due = new Date(dueDate);
  due.setHours(0, 0, 0, 0);

  const diffDays = Math.ceil((due - today) / (1000 * 60 * 60 * 24));

  // Format date as MM/DD
  const formatted = `${due.getMonth() + 1}/${due.getDate()}`;

  if (diffDays < 0) {
    return { text: `${formatted} (${Math.abs(diffDays)}d late)`, status: "overdue", sortValue: diffDays };
  } else if (diffDays === 0) {
    return { text: `${formatted} (Today)`, status: "today", sortValue: diffDays };
  } else if (diffDays <= 2) {
    return { text: `${formatted} (${diffDays}d)`, status: "soon", sortValue: diffDays };
  }
  return { text: formatted, status: "normal", sortValue: diffDays };
};

// Sort orders by due date (most urgent first)
const sortByDueDate = (orders) => {
  return [...orders].sort((a, b) => {
    const aInfo = getDueDateInfo(a);
    const bInfo = getDueDateInfo(b);
    return aInfo.sortValue - bInfo.sortValue;
  });
};

export default function AdminShipping() {
  const api = useApi();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const orderIdParam = searchParams.get("orderId");

  const [orders, setOrders] = useState([]);
  const [shippedToday, setShippedToday] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [productionStatus, setProductionStatus] = useState({});
  const [activeTab, setActiveTab] = useState("packaging"); // packaging, needs_label, ready_to_ship
  const [expandedOrder, setExpandedOrder] = useState(null);
  const [trackingForm, setTrackingForm] = useState({ carrier: "USPS", tracking_number: "" });
  const [saving, setSaving] = useState(false);
  const [shippingTrend, setShippingTrend] = useState(null);
  const [shippingPeriod, setShippingPeriod] = useState("MTD");
  const [trendLoading, setTrendLoading] = useState(false);

  useEffect(() => {
    fetchOrders();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    fetchShippingTrend(shippingPeriod);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shippingPeriod]);

  const fetchShippingTrend = async (period) => {
    setTrendLoading(true);
    try {
      const data = await api.get(`/api/v1/admin/dashboard/shipping-trend?period=${period}`);
      setShippingTrend(data);
    } catch (err) {
      console.error("Failed to fetch shipping trend:", err);
    } finally {
      setTrendLoading(false);
    }
  };

  // If orderId param provided, expand that order
  useEffect(() => {
    if (orderIdParam && orders.length > 0) {
      const order = orders.find((o) => o.id === parseInt(orderIdParam));
      if (order) {
        setExpandedOrder(order.id);
        // Switch to appropriate tab
        if (order.tracking_number) {
          setActiveTab("ready_to_ship");
        } else if (productionStatus[order.id]?.allComplete || !productionStatus[order.id]?.hasProductionOrders) {
          setActiveTab("needs_label");
        } else {
          setActiveTab("packaging");
        }
      }
    }

  }, [orderIdParam, orders, productionStatus]);

  const fetchOrders = async () => {
    setLoading(true);
    try {
      // Fetch orders ready to ship
      const data = await api.get(
        `/api/v1/sales-orders/?status=confirmed&status=in_production&status=ready_to_ship&status=qc_passed&limit=100`
      );

      const orderList = data.items || data || [];
      setOrders(orderList);

      // Fetch production status for all orders in one batch call
      fetchAllProductionStatuses(orderList);

      // Fetch shipped today for metrics
      fetchShippedToday();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchShippedToday = async () => {
    try {
      const today = new Date().toISOString().split("T")[0];
      const data = await api.get(
        `/api/v1/sales-orders/?status=shipped&shipped_after=${today}&limit=100`
      );
      setShippedToday(data.items || data || []);
    } catch {
      // Non-critical
    }
  };

  const computeProductionStatus = (pos) => {
    const allComplete = pos.length > 0 && pos.every((po) => po.status === "complete" || po.status === "closed");
    const anyInProgress = pos.some((po) => po.status === "in_progress");
    const totalOrdered = pos.reduce((sum, po) => sum + parseFloat(po.quantity_ordered || 0), 0);
    const totalCompleted = pos.reduce((sum, po) => sum + parseFloat(po.quantity_completed || 0), 0);
    return {
      hasProductionOrders: pos.length > 0,
      allComplete,
      anyInProgress,
      totalOrdered,
      totalCompleted,
      completionPercent: totalOrdered > 0 ? (totalCompleted / totalOrdered) * 100 : 0,
    };
  };

  // Batch fetch: one API call for all production orders, group by sales_order_id
  const fetchAllProductionStatuses = async (orderList) => {
    if (orderList.length === 0) return;
    try {
      const data = await api.get(`/api/v1/production-orders?limit=500`);
      const allPOs = data.items || data || [];
      const orderIds = new Set(orderList.map((o) => o.id));
      // Group production orders by sales_order_id
      const grouped = {};
      for (const po of allPOs) {
        if (po.sales_order_id && orderIds.has(po.sales_order_id)) {
          if (!grouped[po.sales_order_id]) grouped[po.sales_order_id] = [];
          grouped[po.sales_order_id].push(po);
        }
      }
      const statusMap = {};
      for (const order of orderList) {
        statusMap[order.id] = computeProductionStatus(grouped[order.id] || []);
      }
      setProductionStatus(statusMap);
    } catch {
      // Non-critical - production status just won't show
    }
  };

  // Single order fetch (used for individual refresh)
  const fetchProductionStatus = async (orderId) => {
    try {
      const data = await api.get(`/api/v1/production-orders?sales_order_id=${orderId}`);
      const pos = data.items || data || [];
      setProductionStatus((prev) => ({
        ...prev,
        [orderId]: computeProductionStatus(pos),
      }));
    } catch {
      // Non-critical
    }
  };

  const handleSaveTracking = async (orderId) => {
    if (!trackingForm.tracking_number.trim()) {
      toast.error("Please enter a tracking number");
      return;
    }

    setSaving(true);
    try {
      await api.post(`/api/v1/sales-orders/${orderId}/ship`, {
        carrier: trackingForm.carrier,
        tracking_number: trackingForm.tracking_number.trim(),
      });

      toast.success("Tracking saved! Order marked as shipped.");
      setTrackingForm({ carrier: "USPS", tracking_number: "" });
      setExpandedOrder(null);
      fetchOrders();
      if (orderIdParam) navigate("/admin/shipping");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleMarkShipped = async (orderId) => {
    setSaving(true);
    try {
      await api.patch(`/api/v1/sales-orders/${orderId}/status`, { status: "shipped" });
      toast.success("Order marked as shipped");
      fetchOrders();
      setExpandedOrder(null);
    } catch (err) {
      toast.error(`Failed: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handlePackingSlip = (orderId) => {
    window.open(`${API_URL}/api/v1/sales-orders/${orderId}/packing-slip/pdf`, "_blank");
  };

  // Categorize orders into workflow stages
  const categorizeOrders = () => {
    const packaging = []; // Production not complete
    const needsLabel = []; // Production complete, no tracking
    const readyToShip = []; // Has tracking, not shipped yet

    orders.forEach((order) => {
      const ps = productionStatus[order.id];
      const productionComplete = !ps?.hasProductionOrders || ps?.allComplete;

      if (order.tracking_number) {
        readyToShip.push(order);
      } else if (productionComplete) {
        needsLabel.push(order);
      } else {
        packaging.push(order);
      }
    });

    return { packaging, needsLabel, readyToShip };
  };

  const { packaging, needsLabel, readyToShip } = categorizeOrders();

  const tabs = [
    { key: "packaging", label: "Ready for Packaging", count: packaging.length, color: "blue" },
    { key: "needs_label", label: "Needs Label", count: needsLabel.length, color: "yellow" },
    { key: "ready_to_ship", label: "Ready to Ship", count: readyToShip.length, color: "green" },
  ];

  const getCurrentOrders = () => {
    switch (activeTab) {
      case "packaging": return sortByDueDate(packaging);
      case "needs_label": return sortByDueDate(needsLabel);
      case "ready_to_ship": return sortByDueDate(readyToShip);
      default: return [];
    }
  };

  const formatCurrency = (val) => `$${parseFloat(val || 0).toFixed(2)}`;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-xl font-bold text-white">Shipping</h1>
          <p className="text-gray-500 text-sm">Package, label, and ship orders</p>
        </div>
        <button
          onClick={fetchOrders}
          className="px-3 py-1.5 bg-gray-800 text-gray-300 rounded-lg text-sm hover:bg-gray-700"
        >
          Refresh
        </button>
      </div>

      {/* Shipping Trend Chart */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <ShippingChart
          data={shippingTrend}
          period={shippingPeriod}
          onPeriodChange={setShippingPeriod}
          loading={trendLoading}
        />
      </div>

      {/* Metrics Row - Compact */}
      <div className="grid grid-cols-5 gap-3">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-3">
          <p className="text-gray-500 text-xs">Total Pending</p>
          <p className="text-xl font-bold text-white">{orders.length}</p>
        </div>
        <div className="bg-gray-900 border border-blue-800/50 rounded-lg p-3">
          <p className="text-blue-400 text-xs">Packaging</p>
          <p className="text-xl font-bold text-white">{packaging.length}</p>
        </div>
        <div className="bg-gray-900 border border-yellow-800/50 rounded-lg p-3">
          <p className="text-yellow-400 text-xs">Needs Label</p>
          <p className="text-xl font-bold text-white">{needsLabel.length}</p>
        </div>
        <div className="bg-gray-900 border border-green-800/50 rounded-lg p-3">
          <p className="text-green-400 text-xs">Ready to Ship</p>
          <p className="text-xl font-bold text-white">{readyToShip.length}</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-3">
          <p className="text-gray-500 text-xs">Shipped Today</p>
          <p className="text-xl font-bold text-white">{shippedToday.length}</p>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.key
                ? `border-${tab.color}-500 text-${tab.color}-400`
                : "border-transparent text-gray-500 hover:text-gray-300"
            }`}
          >
            {tab.label}
            <span className={`ml-2 px-1.5 py-0.5 rounded text-xs ${
              activeTab === tab.key ? `bg-${tab.color}-500/20` : "bg-gray-800"
            }`}>
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
        </div>
      )}

      {/* Orders Table */}
      {!loading && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-800/50">
              <tr className="text-left text-gray-400 text-xs uppercase">
                <th className="px-4 py-3 font-medium">Order</th>
                <th className="px-4 py-3 font-medium">Product</th>
                <th className="px-4 py-3 font-medium">Ship To</th>
                <th className="px-4 py-3 font-medium">Due Date</th>
                <th className="px-4 py-3 font-medium text-right">Qty</th>
                <th className="px-4 py-3 font-medium text-right">Total</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {getCurrentOrders().map((order) => {
                const ps = productionStatus[order.id];
                const isExpanded = expandedOrder === order.id;
                const dueDateInfo = getDueDateInfo(order);

                // Color classes for due date urgency
                const dueDateColorClass = {
                  overdue: "text-red-400 font-medium",
                  today: "text-yellow-400 font-medium",
                  soon: "text-orange-400",
                  normal: "text-gray-400",
                  none: "text-gray-600",
                }[dueDateInfo.status];

                return (
                  <tr key={order.id} className="hover:bg-gray-800/50">
                    <td className="px-4 py-3">
                      <button
                        onClick={() => navigate(`/admin/orders/${order.id}`)}
                        className="text-blue-400 hover:text-blue-300 font-medium"
                      >
                        {order.order_number}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-white">
                      <div className="max-w-[200px] truncate" title={order.product_name}>
                        {order.product_name}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-400">
                      {hasShippingAddress(order) ? (
                        formatAddressShort(order)
                      ) : (
                        <span className="text-red-400">No address</span>
                      )}
                    </td>
                    <td className={`px-4 py-3 ${dueDateColorClass}`}>
                      {dueDateInfo.text}
                    </td>
                    <td className="px-4 py-3 text-right text-white">{order.quantity}</td>
                    <td className="px-4 py-3 text-right text-green-400">
                      {formatCurrency(order.grand_total)}
                    </td>
                    <td className="px-4 py-3">
                      {activeTab === "packaging" && ps && (
                        <span className="text-yellow-400 text-xs">
                          {ps.anyInProgress
                            ? `${Math.round(ps.completionPercent)}% done`
                            : "Not started"}
                        </span>
                      )}
                      {activeTab === "needs_label" && (
                        <span className="text-blue-400 text-xs">Ready to label</span>
                      )}
                      {activeTab === "ready_to_ship" && order.tracking_number && (
                        <span className="font-mono text-xs text-gray-400" title={order.tracking_number}>
                          {order.carrier}: {order.tracking_number.slice(0, 12)}...
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex gap-2 justify-end">
                        {activeTab === "packaging" && (
                          <>
                            <button
                              onClick={() => handlePackingSlip(order.id)}
                              className="px-3 py-1 bg-gray-700 text-gray-300 rounded text-xs hover:bg-gray-600"
                              title="Print packing slip"
                            >
                              Packing Slip
                            </button>
                            <span className="text-gray-500 text-xs italic">Awaiting production</span>
                          </>
                        )}
                        {activeTab === "needs_label" && (
                          <>
                            <button
                              onClick={() => handlePackingSlip(order.id)}
                              className="px-3 py-1 bg-gray-700 text-gray-300 rounded text-xs hover:bg-gray-600"
                              title="Print packing slip"
                            >
                              Packing Slip
                            </button>
                            <button
                              onClick={() => setExpandedOrder(isExpanded ? null : order.id)}
                              className="px-3 py-1 bg-yellow-600 text-white rounded text-xs hover:bg-yellow-700"
                            >
                              {isExpanded ? "Cancel" : "Add Label"}
                            </button>
                          </>
                        )}
                        {activeTab === "ready_to_ship" && (
                          <>
                            <button
                              onClick={() => handlePackingSlip(order.id)}
                              className="px-3 py-1 bg-gray-700 text-gray-300 rounded text-xs hover:bg-gray-600"
                              title="Print packing slip"
                            >
                              Packing Slip
                            </button>
                            <button
                              onClick={() => handleMarkShipped(order.id)}
                              disabled={saving}
                              className="px-3 py-1 bg-green-600 text-white rounded text-xs hover:bg-green-700 disabled:opacity-50"
                            >
                              {saving ? "..." : "Ship"}
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}

              {/* Inline Label Entry Row */}
              {expandedOrder && activeTab === "needs_label" && (
                <tr className="bg-yellow-900/10">
                  <td colSpan={8} className="px-4 py-4">
                    <div className="flex items-center gap-4">
                      <div className="flex-1 flex items-center gap-3">
                        <span className="text-gray-400 text-sm">Carrier:</span>
                        <select
                          value={trackingForm.carrier}
                          onChange={(e) => setTrackingForm({ ...trackingForm, carrier: e.target.value })}
                          className="bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                        >
                          <option value="USPS">USPS</option>
                          <option value="FedEx">FedEx</option>
                          <option value="UPS">UPS</option>
                          <option value="DHL">DHL</option>
                          <option value="Other">Other</option>
                        </select>
                        <span className="text-gray-400 text-sm">Tracking:</span>
                        <input
                          type="text"
                          value={trackingForm.tracking_number}
                          onChange={(e) => setTrackingForm({ ...trackingForm, tracking_number: e.target.value })}
                          placeholder="Enter tracking number..."
                          className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm placeholder-gray-500"
                          autoFocus
                        />
                      </div>
                      <div className="flex gap-2">
                        <a
                          href="https://www.usps.com/ship/"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-2 py-1.5 bg-gray-700 text-gray-300 rounded text-xs hover:bg-gray-600"
                        >
                          USPS ↗
                        </a>
                        <a
                          href="https://www.pirateship.com/"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-2 py-1.5 bg-gray-700 text-gray-300 rounded text-xs hover:bg-gray-600"
                        >
                          PirateShip ↗
                        </a>
                        <button
                          onClick={() => handleSaveTracking(expandedOrder)}
                          disabled={saving || !trackingForm.tracking_number.trim()}
                          className="px-4 py-1.5 bg-green-600 text-white rounded text-sm hover:bg-green-700 disabled:opacity-50"
                        >
                          {saving ? "Saving..." : "Save & Ship"}
                        </button>
                        <button
                          onClick={() => {
                            setExpandedOrder(null);
                            setTrackingForm({ carrier: "USPS", tracking_number: "" });
                          }}
                          className="px-3 py-1.5 bg-gray-700 text-gray-300 rounded text-sm hover:bg-gray-600"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  </td>
                </tr>
              )}

              {getCurrentOrders().length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                    {activeTab === "packaging" && "No orders awaiting packaging"}
                    {activeTab === "needs_label" && "No orders need labels"}
                    {activeTab === "ready_to_ship" && "No orders ready to ship"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
