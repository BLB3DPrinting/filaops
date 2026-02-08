import { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import ProductionOrderModal from "../../components/production/ProductionOrderModal";
import ProductionQueueList from "../../components/production/ProductionQueueList";
import SplitOrderModal from "../../components/SplitOrderModal";
import ScrapOrderModal from "../../components/ScrapOrderModal";
import CompleteOrderModal from "../../components/CompleteOrderModal";
import QCInspectionModal from "../../components/QCInspectionModal";
import Modal from "../../components/Modal";
import { useApi } from "../../hooks/useApi";

// Production Trend Chart Component
function ProductionChart({ data, period, onPeriodChange, loading }) {
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
      filledData.push(dataMap[dateKey] || { date: dateKey, completed: 0, units: 0 });
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
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-purple-500"></div>
      </div>
    );
  }

  const dataPoints = fillDateRange(data?.data, data?.start_date, data?.end_date);

  const cumulativeData = dataPoints.reduce((acc, d) => {
    const prev = acc[acc.length - 1] || { cumulativeUnits: 0, cumulativeCompleted: 0 };
    acc.push({
      ...d,
      cumulativeUnits: prev.cumulativeUnits + (d.units || 0),
      cumulativeCompleted: prev.cumulativeCompleted + (d.completed || 0),
    });
    return acc;
  }, []);

  const maxCumulativeUnits = cumulativeData.length > 0 ? cumulativeData[cumulativeData.length - 1].cumulativeUnits : 1;
  const maxDailyCompleted = Math.max(...dataPoints.map(d => d.completed || 0), 1);

  const generateUnitsPath = () => {
    if (cumulativeData.length === 0) return "";
    const points = cumulativeData.map((d, i) => {
      const x = (i / Math.max(cumulativeData.length - 1, 1)) * 100;
      const y = 100 - (d.cumulativeUnits / Math.max(maxCumulativeUnits, 1)) * 100;
      return `${x},${y}`;
    });
    return `M ${points.join(" L ")}`;
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
      completed: d.completed || 0,
      dailyUnits: d.units || 0,
      cumulativeCompleted: d.cumulativeCompleted,
      cumulativeUnits: d.cumulativeUnits,
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
                period === p.key ? "bg-purple-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="flex gap-4 text-right">
          <div>
            <p className="text-sm font-semibold text-purple-400">{data?.total_completed || 0}</p>
            <p className="text-xs text-gray-500">orders</p>
          </div>
          <div>
            <p className="text-sm font-semibold text-green-400">{data?.total_units || 0}</p>
            <p className="text-xs text-gray-500">units</p>
          </div>
          {(data?.pipeline_in_progress > 0 || data?.pipeline_scheduled > 0) && (
            <div>
              <p className="text-sm font-semibold text-yellow-400">{(data?.pipeline_in_progress || 0) + (data?.pipeline_scheduled || 0)}</p>
              <p className="text-xs text-gray-500">in pipeline</p>
            </div>
          )}
        </div>
      </div>

      <div className="flex gap-4 mb-2 text-xs">
        <div className="flex items-center gap-1">
          <div className="w-2 h-3 bg-purple-500/30 rounded-sm"></div>
          <span className="text-gray-500">Daily Completed</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-0.5 bg-green-500"></div>
          <span className="text-gray-400">Cumulative Units</span>
        </div>
      </div>

      {dataPoints.length > 0 ? (
        <div ref={chartRef} className="relative" style={{ height: chartHeight }} onMouseLeave={() => setHoveredIndex(null)}>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
            <line x1="0" y1="50" x2="100" y2="50" stroke="#374151" strokeWidth="0.5" />
            {dataPoints.map((d, i) => {
              const barWidth = 100 / Math.max(dataPoints.length, 1) * 0.6;
              const x = (i / Math.max(dataPoints.length - 1, 1)) * 100 - barWidth / 2;
              const barHeight = ((d.completed || 0) / maxDailyCompleted) * 100;
              return (
                <rect key={`bar-${i}`} x={Math.max(0, x)} y={100 - barHeight} width={barWidth} height={barHeight} fill="url(#productionBarGradient)" opacity="0.4" />
              );
            })}
            <path d={generateUnitsPath()} fill="none" stroke="#22c55e" strokeWidth="2" vectorEffect="non-scaling-stroke" />
            {dataPoints.map((_, i) => {
              const sliceWidth = 100 / dataPoints.length;
              return <rect key={`hover-${i}`} x={i * sliceWidth} y={0} width={sliceWidth} height={100} fill="transparent" onMouseMove={(e) => handleMouseMove(e, i)} style={{ cursor: 'crosshair' }} />;
            })}
            {hoveredIndex !== null && cumulativeData[hoveredIndex] && (
              <circle cx={(hoveredIndex / Math.max(cumulativeData.length - 1, 1)) * 100} cy={100 - (cumulativeData[hoveredIndex].cumulativeUnits / Math.max(maxCumulativeUnits, 1)) * 100} r="3" fill="#22c55e" stroke="white" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            )}
            <defs>
              <linearGradient id="productionBarGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#a855f7" />
                <stop offset="100%" stopColor="#a855f7" stopOpacity="0.2" />
              </linearGradient>
            </defs>
          </svg>
          {hoveredIndex !== null && getHoveredData() && (
            <div className="absolute z-10 bg-gray-800 border border-gray-700 rounded-lg shadow-lg p-3 pointer-events-none" style={{ left: Math.min(mousePos.x + 10, chartWidth - 150), top: Math.max(mousePos.y - 70, 0), minWidth: '140px' }}>
              {(() => {
                const d = getHoveredData();
                return (
                  <>
                    <div className="text-white font-medium text-sm mb-2">{d.date}</div>
                    <div className="space-y-1 text-xs">
                      <div className="flex justify-between gap-4"><span className="text-purple-400">Completed:</span><span className="text-white font-medium">{d.completed}</span></div>
                      <div className="flex justify-between gap-4"><span className="text-green-400">Units:</span><span className="text-white">{d.dailyUnits}</span></div>
                      <div className="border-t border-gray-700 my-1 pt-1">
                        <div className="flex justify-between gap-4"><span className="text-gray-400">Total Orders:</span><span className="text-white">{d.cumulativeCompleted}</span></div>
                        <div className="flex justify-between gap-4"><span className="text-gray-400">Total Units:</span><span className="text-white">{d.cumulativeUnits}</span></div>
                      </div>
                    </div>
                  </>
                );
              })()}
            </div>
          )}
        </div>
      ) : (
        <div className="h-24 flex items-center justify-center text-gray-500 text-sm">No production completions for this period</div>
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

// Helper to render MTO/MTS badge showing linked SO or STOCK
const SoLinkBadge = ({ order }) => {
  if (order.sales_order_code) {
    return (
      <span className="text-xs px-1.5 py-0.5 bg-blue-500/20 text-blue-400 rounded">
        {order.sales_order_code}
      </span>
    );
  }
  return (
    <span className="text-xs px-1.5 py-0.5 bg-purple-500/20 text-purple-400 rounded">
      STOCK
    </span>
  );
};

export default function AdminProduction() {
  const api = useApi();
  const [searchParams] = useSearchParams();
  const [productionOrders, setProductionOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    status: "in_progress",  // Default to in-progress orders
    search: searchParams.get("search") || "",
  });

  // Create order modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [products, setProducts] = useState([]);
  const [createForm, setCreateForm] = useState({
    product_id: "",
    quantity_ordered: 1,
    priority: 3,
    due_date: "",
    notes: "",
  });
  const [creating, setCreating] = useState(false);

  // Scheduling modal state
  const [showSchedulingModal, setShowSchedulingModal] = useState(false);
  const [selectedOrderForScheduling, setSelectedOrderForScheduling] =
    useState(null);

  // Split modal state
  const [showSplitModal, setShowSplitModal] = useState(false);
  const [selectedOrderForSplit, setSelectedOrderForSplit] = useState(null);

  // Scrap modal state
  const [showScrapModal, setShowScrapModal] = useState(false);
  const [selectedOrderForScrap, setSelectedOrderForScrap] = useState(null);

  // Complete modal state
  const [showCompleteModal, setShowCompleteModal] = useState(false);
  const [selectedOrderForComplete, setSelectedOrderForComplete] =
    useState(null);

  // QC Inspection modal state
  const [showQCModal, setShowQCModal] = useState(false);
  const [selectedOrderForQC, setSelectedOrderForQC] = useState(null);

  // Trend chart state
  const [productionTrend, setProductionTrend] = useState(null);
  const [trendPeriod, setTrendPeriod] = useState("MTD");
  const [trendLoading, setTrendLoading] = useState(false);

  const fetchProductionTrend = useCallback(async (period) => {
    setTrendLoading(true);
    try {
      const data = await api.get(`/api/v1/admin/dashboard/production-trend?period=${period}`);
      setProductionTrend(data);
    } catch (err) {
      console.error("Failed to fetch production trend:", err);
    } finally {
      setTrendLoading(false);
    }
  }, [api]);

  const fetchProductionOrders = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      // "active" is a frontend-only filter (excludes complete/short), don't send to backend
      if (filters.status !== "all" && filters.status !== "active") {
        params.set("status", filters.status);
      }
      params.set("limit", "100");

      const data = await api.get(`/api/v1/production-orders/?${params}`);
      setProductionOrders(data.items || data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [api, filters.status]);

  const fetchProducts = useCallback(async () => {
    try {
      const data = await api.get(`/api/v1/products?limit=500&active=true`);
      setProducts(data.items || data || []);
    } catch {
      // Products fetch failure is non-critical - product selector will just be empty
    }
  }, [api]);

  useEffect(() => {
    fetchProductionOrders();
  }, [fetchProductionOrders]);

  useEffect(() => {
    fetchProductionTrend(trendPeriod);
  }, [trendPeriod, fetchProductionTrend]);

  // Update filters if search param changes (e.g., from deep link)
  useEffect(() => {
    const searchFromParams = searchParams.get("search");
    if (searchFromParams && searchFromParams !== filters.search) {
      setFilters((prev) => ({ ...prev, search: searchFromParams }));
    }
  }, [searchParams]);

  // Fetch products when modal opens
  useEffect(() => {
    if (showCreateModal && products.length === 0) {
      fetchProducts();
    }
  }, [showCreateModal, products.length, fetchProducts]);

  const handleCreateOrder = async (e) => {
    e.preventDefault();
    if (!createForm.product_id) {
      setError("Please select a product");
      return;
    }

    setCreating(true);
    try {
      await api.post(`/api/v1/production-orders/`, {
        product_id: parseInt(createForm.product_id),
        quantity_ordered: parseInt(createForm.quantity_ordered) || 1,
        priority: parseInt(createForm.priority) || 3,
        due_date: createForm.due_date || null,
        notes: createForm.notes || null,
      });

      setShowCreateModal(false);
      setCreateForm({
        product_id: "",
        quantity_ordered: 1,
        priority: 3,
        due_date: "",
        notes: "",
      });
      fetchProductionOrders();
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  // handleStatusUpdate removed - status updates are handled via ProductionOrderModal

  const filteredOrders = productionOrders.filter((o) => {
    if (!filters.search) return true;
    const search = filters.search.toLowerCase();
    return (
      o.code?.toLowerCase().includes(search) ||
      o.product_name?.toLowerCase().includes(search) ||
      o.sales_order_code?.toLowerCase().includes(search)
    );
  });

  // Group by status for kanban view
  const groupedOrders = {
    draft: filteredOrders.filter((o) => o.status === "draft"),
    released: filteredOrders.filter((o) => o.status === "released"),
    in_progress: filteredOrders.filter((o) => o.status === "in_progress"),
    complete: filteredOrders.filter((o) => o.status === "complete"),
    scrapped: filteredOrders.filter((o) => o.status === "scrapped"),
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Production</h1>
          <p className="text-gray-400 mt-1">
            Track print jobs and production orders
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500"
        >
          + Create Production Order
        </button>
      </div>

      {/* Production Trend Chart */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <ProductionChart
          data={productionTrend}
          period={trendPeriod}
          onPeriodChange={setTrendPeriod}
          loading={trendLoading}
        />
      </div>

      {/* Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-4">
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <p className="text-gray-400 text-sm">Draft</p>
              <p className="text-2xl font-bold text-gray-400">
                {groupedOrders.draft.length}
              </p>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <p className="text-gray-400 text-sm">Released</p>
              <p className="text-2xl font-bold text-blue-400">
                {groupedOrders.released.length}
              </p>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <p className="text-gray-400 text-sm">In Progress</p>
              <p className="text-2xl font-bold text-purple-400">
                {groupedOrders.in_progress.length}
              </p>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <p className="text-gray-400 text-sm">Completed Today</p>
              <p className="text-2xl font-bold text-green-400">
                {
                  groupedOrders.complete.filter((o) => {
                    const today = new Date().toDateString();
                    return (
                      o.completed_at &&
                      new Date(o.completed_at).toDateString() === today
                    );
                  }).length
                }
              </p>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <p className="text-gray-400 text-sm">Scrapped Today</p>
              <p className="text-2xl font-bold text-red-400">
                {
                  groupedOrders.scrapped.filter((o) => {
                    const today = new Date().toDateString();
                    return (
                      o.scrapped_at &&
                      new Date(o.scrapped_at).toDateString() === today
                    );
                  }).length
                }
              </p>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <p className="text-gray-400 text-sm">Total Active</p>
              <p className="text-2xl font-bold text-white">
                {groupedOrders.released.length +
                  groupedOrders.in_progress.length}
              </p>
            </div>
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

      {/* Production Queue List */}
      <ProductionQueueList
        orders={productionOrders}
        loading={loading}
        filters={filters}
        onFiltersChange={setFilters}
        onOrderClick={(order) => {
          setSelectedOrderForScheduling(order);
          setShowSchedulingModal(true);
        }}
      />

      {/* Scheduling Modal */}
      {showSchedulingModal && selectedOrderForScheduling && (
        <ProductionOrderModal
          productionOrder={selectedOrderForScheduling}
          onClose={() => {
            setShowSchedulingModal(false);
            setSelectedOrderForScheduling(null);
          }}
          onUpdated={() => {
            fetchProductionOrders();
            setShowSchedulingModal(false);
            setSelectedOrderForScheduling(null);
          }}
        />
      )}

      {/* Split Order Modal */}
      {showSplitModal && selectedOrderForSplit && (
        <SplitOrderModal
          productionOrder={selectedOrderForSplit}
          onClose={() => {
            setShowSplitModal(false);
            setSelectedOrderForSplit(null);
          }}
          onSplit={() => {
            fetchProductionOrders();
            setShowSplitModal(false);
            setSelectedOrderForSplit(null);
          }}
        />
      )}

      {/* Scrap Order Modal */}
      {showScrapModal && selectedOrderForScrap && (
        <ScrapOrderModal
          productionOrder={selectedOrderForScrap}
          onClose={() => {
            setShowScrapModal(false);
            setSelectedOrderForScrap(null);
          }}
          onScrap={() => {
            fetchProductionOrders();
            setShowScrapModal(false);
            setSelectedOrderForScrap(null);
          }}
        />
      )}

      {/* Complete Order Modal */}
      {showCompleteModal && selectedOrderForComplete && (
        <CompleteOrderModal
          productionOrder={selectedOrderForComplete}
          onClose={() => {
            setShowCompleteModal(false);
            setSelectedOrderForComplete(null);
          }}
          onComplete={() => {
            fetchProductionOrders();
            setShowCompleteModal(false);
            setSelectedOrderForComplete(null);
          }}
        />
      )}

      {/* QC Inspection Modal */}
      {showQCModal && selectedOrderForQC && (
        <QCInspectionModal
          productionOrder={selectedOrderForQC}
          onClose={() => {
            setShowQCModal(false);
            setSelectedOrderForQC(null);
          }}
          onComplete={() => {
            fetchProductionOrders();
            setShowQCModal(false);
            setSelectedOrderForQC(null);
          }}
        />
      )}

      {/* Create Production Order Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create Production Order"
        className="w-full max-w-md"
        disableClose={creating}
      >
        <div className="p-6">
            <h2 className="text-xl font-bold text-white mb-4">Create Production Order</h2>
            <form onSubmit={handleCreateOrder} className="space-y-4">
              {/* Product Selection */}
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Product *
                </label>
                <select
                  value={createForm.product_id}
                  onChange={(e) =>
                    setCreateForm({ ...createForm, product_id: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  required
                >
                  <option value="">Select a product...</option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.sku} - {p.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Quantity */}
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Quantity *
                </label>
                <input
                  type="number"
                  min="1"
                  value={createForm.quantity_ordered}
                  onChange={(e) =>
                    setCreateForm({
                      ...createForm,
                      quantity_ordered: e.target.value,
                    })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  required
                />
              </div>

              {/* Priority */}
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Priority
                </label>
                <select
                  value={createForm.priority}
                  onChange={(e) =>
                    setCreateForm({ ...createForm, priority: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                >
                  <option value="1">1 - Urgent</option>
                  <option value="2">2 - High</option>
                  <option value="3">3 - Normal</option>
                  <option value="4">4 - Low</option>
                  <option value="5">5 - Lowest</option>
                </select>
              </div>

              {/* Due Date */}
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Due Date
                </label>
                <input
                  type="date"
                  value={createForm.due_date}
                  onChange={(e) =>
                    setCreateForm({ ...createForm, due_date: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  min={new Date().toISOString().split("T")[0]}
                  max="2099-12-31"
                />
              </div>

              {/* Notes */}
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Notes
                </label>
                <textarea
                  value={createForm.notes}
                  onChange={(e) =>
                    setCreateForm({ ...createForm, notes: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white h-20"
                  placeholder="Optional notes..."
                />
              </div>

              {/* Buttons */}
              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="flex-1 px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="flex-1 px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500 disabled:opacity-50"
                >
                  {creating ? "Creating..." : "Create Order"}
                </button>
              </div>
            </form>
        </div>
      </Modal>
    </div>
  );
}
