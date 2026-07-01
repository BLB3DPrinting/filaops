import { useState, useEffect, useRef } from "react";
import { useFormatCurrency } from "../../hooks/useFormatCurrency";
import { useLocale } from "../../contexts/LocaleContext";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import { API_URL } from "../../config/api";

// Shipping Trend Chart Component
function ShippingChart({ data, period, onPeriodChange, loading }) {
  const { currency_code, locale } = useLocale();
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
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[var(--orange)]"></div>
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

  const formatCurrency = (value) =>
    new Intl.NumberFormat(locale, {
      style: "currency",
      currency: currency_code,
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(value);

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
                  ? "bg-[var(--ink)] text-[var(--paper)]"
                  : "bg-[var(--paper-sunk)] text-[var(--ink-3)] hover:text-[var(--ink)]"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="flex gap-4 text-right">
          <div>
            <p className="text-sm font-semibold text-[var(--ink)]">{data?.total_shipped || 0}</p>
            <p className="text-xs text-[var(--ink-4)]">shipped</p>
          </div>
          <div>
            <p className="text-sm font-semibold text-[var(--status-green)]">{formatCurrency(data?.total_value || 0)}</p>
            <p className="text-xs text-[var(--ink-4)]">value</p>
          </div>
          {(data?.pipeline_ready > 0 || data?.pipeline_packaging > 0) && (
            <div>
              <p className="text-sm font-semibold text-[var(--status-amber)]">{(data?.pipeline_ready || 0) + (data?.pipeline_packaging || 0)}</p>
              <p className="text-xs text-[var(--ink-4)]">in pipeline</p>
            </div>
          )}
        </div>
      </div>

      <div className="flex gap-4 mb-2 text-xs">
        <div className="flex items-center gap-1">
          <div className="w-2 h-3 bg-[var(--orange-tint)] rounded-sm"></div>
          <span className="text-[var(--ink-4)]">Daily Shipped</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-0.5 bg-[var(--status-green)]"></div>
          <span className="text-[var(--ink-3)]">Cumulative Value</span>
        </div>
      </div>

      {dataPoints.length > 0 ? (
        <div ref={chartRef} className="relative" style={{ height: chartHeight }} onMouseLeave={() => setHoveredIndex(null)}>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
            <line x1="0" y1="50" x2="100" y2="50" stroke="var(--rule-hair)" strokeWidth="0.5" />

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
                  opacity="0.6"
                />
              );
            })}

            <path d={generateValuePath()} fill="none" stroke="var(--status-green)" strokeWidth="2" vectorEffect="non-scaling-stroke" />

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
                r="3" fill="var(--status-green)" stroke="var(--paper)" strokeWidth="1" vectorEffect="non-scaling-stroke"
              />
            )}

            <defs>
              <linearGradient id="shippingBarGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="var(--orange)" />
                <stop offset="100%" stopColor="var(--orange)" stopOpacity="0.15" />
              </linearGradient>
            </defs>
          </svg>

          {hoveredIndex !== null && getHoveredData() && (
            <div
              className="absolute z-10 bg-[var(--paper)] border border-[var(--rule-hair)] rounded-lg shadow-[var(--shadow-pop)] p-3 pointer-events-none"
              style={{ left: Math.min(mousePos.x + 10, chartWidth - 150), top: Math.max(mousePos.y - 70, 0), minWidth: '140px' }}
            >
              {(() => {
                const d = getHoveredData();
                return (
                  <>
                    <div className="text-[var(--ink)] font-medium text-sm mb-2">{d.date}</div>
                    <div className="space-y-1 text-xs">
                      <div className="flex justify-between gap-4">
                        <span className="text-[var(--ink-3)]">Shipped:</span>
                        <span className="text-[var(--ink)] font-medium font-mono-data">{d.shipped}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span className="text-[var(--status-green)]">Value:</span>
                        <span className="text-[var(--ink)] font-mono-data">${d.dailyValue.toFixed(2)}</span>
                      </div>
                      <div className="border-t border-[var(--rule-hair)] my-1 pt-1">
                        <div className="flex justify-between gap-4">
                          <span className="text-[var(--ink-3)]">Total Shipped:</span>
                          <span className="text-[var(--ink)] font-mono-data">{d.cumulativeShipped}</span>
                        </div>
                        <div className="flex justify-between gap-4">
                          <span className="text-[var(--ink-3)]">Total Value:</span>
                          <span className="text-[var(--ink)] font-mono-data">${d.cumulativeValue.toFixed(2)}</span>
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
        <div className="h-24 flex items-center justify-center text-[var(--ink-4)] text-sm">No shipments for this period</div>
      )}

      {dataPoints.length > 0 && (
        <div className="flex justify-between text-xs text-[var(--ink-4)] mt-2">
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
  const formatCurrency = useFormatCurrency();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const orderIdParam = searchParams.get("orderId");

  const [orders, setOrders] = useState([]);
  const [shippedToday, setShippedToday] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [productionStatus, setProductionStatus] = useState({});
  const [canShip, setCanShip] = useState({}); // #845: order_id -> {can_ship, reasons[]}
  const [canShipUnavailable, setCanShipUnavailable] = useState(false); // preflight fetch failed — surfaced via a banner (fail-visible)
  const canShipReqRef = useRef(0); // monotonic guard: only the latest fetch writes state
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
      // Fetch orders ready to ship. (qc_passed removed — not a SalesOrder
      // status; it matched zero rows. #845)
      const data = await api.get(
        `/api/v1/sales-orders/?status=confirmed&status=in_production&status=ready_to_ship&limit=100`
      );

      const orderList = data.items || data || [];
      setOrders(orderList);

      // Fetch production status for all orders in one batch call
      fetchAllProductionStatuses(orderList);

      // Fetch the can-ship preflight for every ready_to_ship order in one
      // batch call (#845) — this is the same gate ship_order() itself
      // enforces, so the UI never disagrees with the backend.
      fetchCanShip();

      // Fetch shipped today for metrics
      fetchShippedToday();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchCanShip = async () => {
    // Guard against stale overlapping refreshes (initial load / manual refresh /
    // post-ship reload can race): only the newest request may write state.
    const requestId = ++canShipReqRef.current;
    try {
      const data = await api.get(`/api/v1/sales-orders/can-ship`);
      if (requestId !== canShipReqRef.current) return;
      setCanShip(data || {});
      setCanShipUnavailable(false);
    } catch {
      if (requestId !== canShipReqRef.current) return;
      // Fail VISIBLE, not closed: show a banner but keep Ship enabled.
      // ship_order() is the authoritative gate, so a preflight outage must not
      // block shipping of orders that are actually shippable — it only costs
      // the pre-click warning, which the banner explains.
      setCanShip({});
      setCanShipUnavailable(true);
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
    // Ship through POST /ship (relieves inventory + posts COGS), not a bare
    // status flip. The button only shows for orders that already have a
    // tracking number, so reuse the order's saved carrier/tracking (#838).
    const order = orders.find((o) => o.id === orderId);
    if (!order?.tracking_number) {
      toast.error("Add a tracking number before shipping");
      return;
    }
    if (!order.carrier) {
      toast.error("Add a carrier before shipping");
      return;
    }
    // Preflight check (#845) — surface the backend's real blocker before
    // firing the request, instead of only reacting to a 409 after the fact.
    const preflight = canShip[orderId] ?? canShip[String(orderId)];
    if (preflight && !preflight.can_ship) {
      toast.error(preflight.reasons?.[0] || "Order is not ready to ship");
      return;
    }
    setSaving(true);
    try {
      await api.post(`/api/v1/sales-orders/${orderId}/ship`, {
        carrier: order.carrier,
        tracking_number: order.tracking_number,
      });
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

  // Categorize orders into workflow stages. This is the physical packaging
  // workflow (where is the order in the packing/labeling process) — distinct
  // from the backend's can-ship gate, which augments the ready_to_ship tab
  // below rather than replacing this bucketing (#845).
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
    { key: "packaging", label: "Ready for Packaging", count: packaging.length, color: "amber" },
    { key: "needs_label", label: "Needs Label", count: needsLabel.length, color: "amber" },
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


  return (
    <div className="space-y-4">
      {/* Header — wrapped in its own paper card: the AdminLayout shell behind
          this page is still the un-migrated dark Neo background (a later
          #846 slice), so ink-toned text needs its own light surface here
          rather than floating directly on the shell. */}
      <div className="bg-[var(--paper)] border border-[var(--rule-hair)] rounded-xl p-4 shadow-[var(--shadow-pop)] flex flex-col sm:flex-row items-start sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-[var(--ink)]">Shipping</h1>
          <p className="text-[var(--ink-4)] text-sm">Package, label, and ship orders</p>
        </div>
        <button
          onClick={fetchOrders}
          className="px-3 py-1.5 bg-[var(--paper-sunk)] text-[var(--ink-2)] rounded-lg text-sm hover:bg-[var(--rule-hair)]"
        >
          Refresh
        </button>
      </div>

      {/* Shipping Trend Chart */}
      <div className="bg-[var(--paper)] border border-[var(--rule-hair)] rounded-xl p-4 shadow-[var(--shadow-pop)]">
        <ShippingChart
          data={shippingTrend}
          period={shippingPeriod}
          onPeriodChange={setShippingPeriod}
          loading={trendLoading}
        />
      </div>

      {/* Metrics Row - Compact */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
        <div className="bg-[var(--paper)] border border-[var(--rule-hair)] rounded-lg p-3 shadow-[var(--shadow-pop)]">
          <p className="text-[var(--ink-4)] text-xs">Total Pending</p>
          <p className="text-xl font-bold text-[var(--ink)]">{orders.length}</p>
        </div>
        <div className="bg-[var(--paper)] border border-[var(--status-amber-tint)] rounded-lg p-3 shadow-[var(--shadow-pop)]">
          <p className="text-[var(--status-amber)] text-xs">Packaging</p>
          <p className="text-xl font-bold text-[var(--ink)]">{packaging.length}</p>
        </div>
        <div className="bg-[var(--paper)] border border-[var(--status-amber-tint)] rounded-lg p-3 shadow-[var(--shadow-pop)]">
          <p className="text-[var(--status-amber)] text-xs">Needs Label</p>
          <p className="text-xl font-bold text-[var(--ink)]">{needsLabel.length}</p>
        </div>
        <div className="bg-[var(--paper)] border border-[var(--status-green-tint)] rounded-lg p-3 shadow-[var(--shadow-pop)]">
          <p className="text-[var(--status-green)] text-xs">Ready to Ship</p>
          <p className="text-xl font-bold text-[var(--ink)]">{readyToShip.length}</p>
        </div>
        <div className="bg-[var(--paper)] border border-[var(--rule-hair)] rounded-lg p-3 shadow-[var(--shadow-pop)]">
          <p className="text-[var(--ink-4)] text-xs">Shipped Today</p>
          <p className="text-xl font-bold text-[var(--ink)]">{shippedToday.length}</p>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-[var(--status-red-tint)] border border-[var(--status-red)]/30 rounded-lg p-3 text-[var(--status-red)] text-sm">
          {error}
        </div>
      )}

      {/* Deep-link banner: orderId param present but order not in ready-to-ship set */}
      {!loading && orderIdParam && !orders.find((o) => o.id === parseInt(orderIdParam)) && (
        <div className="bg-[var(--status-amber-tint)] border border-[var(--status-amber)]/30 rounded-lg px-4 py-3 flex items-start gap-3">
          <svg className="w-5 h-5 text-[var(--status-amber)] mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
          </svg>
          <p className="text-[var(--status-amber)] text-sm">
            Order isn&apos;t in an active shipping stage — it may already be shipped, cancelled, or not yet confirmed.
          </p>
        </div>
      )}

      {/* Tabs */}
      {/* TAB_STYLES: literal class map so Tailwind's purger can detect all classes. */}
      {/* Dynamic class construction (e.g. `border-${color}-500`) is invisible to the */}
      {/* purger and will be stripped from the production bundle. */}
      {(() => {
        const TAB_STYLES = {
          amber: { border: "border-[var(--status-amber)] text-[var(--status-amber)]", badge: "bg-[var(--status-amber-tint)]" },
          green: { border: "border-[var(--status-green)] text-[var(--status-green)]", badge: "bg-[var(--status-green-tint)]" },
        };
        return (
          <div className="flex gap-1 border-b border-[var(--rule-hair)]">
            {tabs.map((tab) => {
              const styles = TAB_STYLES[tab.color] ?? TAB_STYLES.amber;
              return (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === tab.key
                      ? styles.border
                      : "border-transparent text-[var(--ink-4)] hover:text-[var(--ink-2)]"
                  }`}
                >
                  {tab.label}
                  <span className={`ml-2 px-1.5 py-0.5 rounded text-xs font-mono-data ${
                    activeTab === tab.key ? styles.badge : "bg-[var(--paper-sunk)]"
                  }`}>
                    {tab.count}
                  </span>
                </button>
              );
            })}
          </div>
        );
      })()}

      {/* Preflight degraded-state warning — make a can-ship fetch failure
          VISIBLE rather than silently re-enabling Ship with no protection.
          ship_order() still fully validates server-side either way; this is
          advisory so the operator isn't caught off guard by a 409. */}
      {canShipUnavailable && activeTab === "ready_to_ship" && (
        <div className="bg-[var(--status-amber-tint)] border border-[var(--status-amber)]/30 rounded-lg px-4 py-2.5 text-[var(--status-amber)] text-sm">
          Couldn&apos;t verify which orders are ready to ship — the eligibility check didn&apos;t load. Shipping will still be validated when you click Ship.
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[var(--orange)]"></div>
        </div>
      )}

      {/* Orders Table */}
      {!loading && (
        <div className="bg-[var(--paper)] border border-[var(--rule-hair)] rounded-lg overflow-hidden shadow-[var(--shadow-pop)]">
          <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="bg-[var(--paper-sunk)]">
              <tr className="text-left text-[var(--ink-3)] text-xs uppercase">
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
            <tbody className="divide-y divide-[var(--rule-hair)]">
              {getCurrentOrders().map((order) => {
                const ps = productionStatus[order.id];
                const isExpanded = expandedOrder === order.id;
                const dueDateInfo = getDueDateInfo(order);
                const preflight = canShip[order.id] ?? canShip[String(order.id)];
                const blocked = activeTab === "ready_to_ship" && preflight && !preflight.can_ship;

                // Color classes for due date urgency
                const dueDateColorClass = {
                  overdue: "text-[var(--status-red)] font-medium",
                  today: "text-[var(--status-amber)] font-medium",
                  soon: "text-[var(--status-amber)]",
                  normal: "text-[var(--ink-3)]",
                  none: "text-[var(--ink-4)]",
                }[dueDateInfo.status];

                return (
                  <tr key={order.id} className="hover:bg-[var(--paper-sunk)]">
                    <td className="px-4 py-3">
                      <button
                        onClick={() => navigate(`/admin/orders/${order.id}`)}
                        className="text-[var(--ink)] hover:text-[var(--orange)] font-medium font-mono-data"
                      >
                        {order.order_number}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-[var(--ink)]">
                      <div className="max-w-[200px] truncate" title={order.product_name}>
                        {order.product_name}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-[var(--ink-3)]">
                      {hasShippingAddress(order) ? (
                        formatAddressShort(order)
                      ) : (
                        <span className="text-[var(--status-red)]">No address</span>
                      )}
                    </td>
                    <td className={`px-4 py-3 ${dueDateColorClass}`}>
                      {dueDateInfo.text}
                    </td>
                    <td className="px-4 py-3 text-right text-[var(--ink)] font-mono-data">{order.quantity}</td>
                    <td className="px-4 py-3 text-right text-[var(--status-green)] font-mono-data">
                      {formatCurrency(order.grand_total)}
                    </td>
                    <td className="px-4 py-3">
                      {activeTab === "packaging" && ps && (
                        <span className="text-[var(--status-amber)] text-xs">
                          {ps.anyInProgress
                            ? `${Math.round(ps.completionPercent)}% done`
                            : "Not started"}
                        </span>
                      )}
                      {activeTab === "needs_label" && (
                        <span className="text-[var(--status-amber)] text-xs">Ready to label</span>
                      )}
                      {activeTab === "ready_to_ship" && order.tracking_number && (
                        <div>
                          <span className="font-mono-data text-xs text-[var(--ink-3)]" title={order.tracking_number}>
                            {order.carrier}: {order.tracking_number.slice(0, 12)}...
                          </span>
                          {blocked && (
                            <div className="text-[var(--status-red)] text-xs mt-0.5" title={preflight.reasons?.join("; ")}>
                              {preflight.reasons?.[0] || "Cannot ship yet"}
                            </div>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex gap-2 justify-end">
                        {activeTab === "packaging" && (
                          <>
                            <button
                              onClick={() => handlePackingSlip(order.id)}
                              className="px-3 py-1 bg-[var(--paper-sunk)] text-[var(--ink-2)] border border-[var(--rule-hair)] rounded text-xs hover:bg-[var(--rule-hair)]"
                              title="Print packing slip"
                            >
                              Packing Slip
                            </button>
                            <span className="text-[var(--ink-4)] text-xs italic">Awaiting production</span>
                          </>
                        )}
                        {activeTab === "needs_label" && (
                          <>
                            <button
                              onClick={() => handlePackingSlip(order.id)}
                              className="px-3 py-1 bg-[var(--paper-sunk)] text-[var(--ink-2)] border border-[var(--rule-hair)] rounded text-xs hover:bg-[var(--rule-hair)]"
                              title="Print packing slip"
                            >
                              Packing Slip
                            </button>
                            <button
                              onClick={() => setExpandedOrder(isExpanded ? null : order.id)}
                              className="px-3 py-1 bg-[var(--orange)] text-white rounded text-xs hover:bg-[var(--orange-press)]"
                            >
                              {isExpanded ? "Cancel" : "Add Label"}
                            </button>
                          </>
                        )}
                        {activeTab === "ready_to_ship" && (
                          <>
                            <button
                              onClick={() => handlePackingSlip(order.id)}
                              className="px-3 py-1 bg-[var(--paper-sunk)] text-[var(--ink-2)] border border-[var(--rule-hair)] rounded text-xs hover:bg-[var(--rule-hair)]"
                              title="Print packing slip"
                            >
                              Packing Slip
                            </button>
                            <button
                              onClick={() => handleMarkShipped(order.id)}
                              disabled={saving || blocked}
                              title={blocked ? preflight.reasons?.join("; ") : undefined}
                              className="px-3 py-1 bg-[var(--orange)] text-white rounded text-xs hover:bg-[var(--orange-press)] disabled:opacity-50 disabled:cursor-not-allowed"
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
                <tr className="bg-[var(--status-amber-tint)]">
                  <td colSpan={8} className="px-4 py-4">
                    <div className="flex items-center gap-4">
                      <div className="flex-1 flex items-center gap-3">
                        <span className="text-[var(--ink-3)] text-sm">Carrier:</span>
                        <select
                          value={trackingForm.carrier}
                          onChange={(e) => setTrackingForm({ ...trackingForm, carrier: e.target.value })}
                          className="bg-[var(--paper)] border border-[var(--rule-hair)] rounded px-2 py-1.5 text-[var(--ink)] text-sm"
                        >
                          <option value="USPS">USPS</option>
                          <option value="FedEx">FedEx</option>
                          <option value="UPS">UPS</option>
                          <option value="DHL">DHL</option>
                          <option value="Other">Other</option>
                        </select>
                        <span className="text-[var(--ink-3)] text-sm">Tracking:</span>
                        <input
                          type="text"
                          value={trackingForm.tracking_number}
                          onChange={(e) => setTrackingForm({ ...trackingForm, tracking_number: e.target.value })}
                          placeholder="Enter tracking number..."
                          className="flex-1 bg-[var(--paper)] border border-[var(--rule-hair)] rounded px-3 py-1.5 text-[var(--ink)] text-sm placeholder-[var(--ink-4)]"
                          autoFocus
                        />
                      </div>
                      <div className="flex gap-2">
                        <a
                          href="https://www.usps.com/ship/"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-2 py-1.5 bg-[var(--paper-sunk)] text-[var(--ink-2)] border border-[var(--rule-hair)] rounded text-xs hover:bg-[var(--rule-hair)]"
                        >
                          USPS ↗
                        </a>
                        <a
                          href="https://www.pirateship.com/"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-2 py-1.5 bg-[var(--paper-sunk)] text-[var(--ink-2)] border border-[var(--rule-hair)] rounded text-xs hover:bg-[var(--rule-hair)]"
                        >
                          PirateShip ↗
                        </a>
                        <button
                          onClick={() => handleSaveTracking(expandedOrder)}
                          disabled={saving || !trackingForm.tracking_number.trim()}
                          className="px-4 py-1.5 bg-[var(--orange)] text-white rounded text-sm hover:bg-[var(--orange-press)] disabled:opacity-50"
                        >
                          {saving ? "Saving..." : "Save & Ship"}
                        </button>
                        <button
                          onClick={() => {
                            setExpandedOrder(null);
                            setTrackingForm({ carrier: "USPS", tracking_number: "" });
                          }}
                          className="px-3 py-1.5 bg-[var(--paper-sunk)] text-[var(--ink-2)] border border-[var(--rule-hair)] rounded text-sm hover:bg-[var(--rule-hair)]"
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
                  <td colSpan={8} className="px-4 py-8 text-center text-[var(--ink-4)]">
                    {activeTab === "packaging" && "No orders awaiting packaging"}
                    {activeTab === "needs_label" && "No orders need labels"}
                    {activeTab === "ready_to_ship" && "No orders ready to ship"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </div>
  );
}
