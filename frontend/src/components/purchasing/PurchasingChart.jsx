/**
 * PurchasingChart - Trend chart showing purchasing receive/spend data.
 *
 * Extracted from AdminPurchasing.jsx (ARCHITECT-002)
 */
import { useState, useRef } from "react";

export default function PurchasingChart({ data, period, onPeriodChange, loading }) {
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
      filledData.push(dataMap[dateKey] || { date: dateKey, received: 0, spend: 0 });
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
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-orange-500"></div>
      </div>
    );
  }

  const dataPoints = fillDateRange(data?.data, data?.start_date, data?.end_date);

  const cumulativeData = dataPoints.reduce((acc, d) => {
    const prev = acc[acc.length - 1] || { cumulativeSpend: 0, cumulativeReceived: 0 };
    acc.push({
      ...d,
      cumulativeSpend: prev.cumulativeSpend + (d.spend || 0),
      cumulativeReceived: prev.cumulativeReceived + (d.received || 0),
    });
    return acc;
  }, []);

  const maxCumulativeSpend = cumulativeData.length > 0 ? cumulativeData[cumulativeData.length - 1].cumulativeSpend : 1;
  const maxDailyReceived = Math.max(...dataPoints.map(d => d.received || 0), 1);

  const generateSpendPath = () => {
    if (cumulativeData.length === 0) return "";
    const points = cumulativeData.map((d, i) => {
      const x = (i / Math.max(cumulativeData.length - 1, 1)) * 100;
      const y = 100 - (d.cumulativeSpend / Math.max(maxCumulativeSpend, 1)) * 100;
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
      received: d.received || 0,
      dailySpend: d.spend || 0,
      cumulativeReceived: d.cumulativeReceived,
      cumulativeSpend: d.cumulativeSpend,
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
                period === p.key ? "bg-orange-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="flex gap-4 text-right">
          <div>
            <p className="text-sm font-semibold text-orange-400">{data?.total_received || 0}</p>
            <p className="text-xs text-gray-500">POs received</p>
          </div>
          <div>
            <p className="text-sm font-semibold text-green-400">{formatCurrency(data?.total_spend || 0)}</p>
            <p className="text-xs text-gray-500">spend</p>
          </div>
          {(data?.pipeline_ordered > 0) && (
            <div>
              <p className="text-sm font-semibold text-yellow-400">{data?.pipeline_ordered || 0}</p>
              <p className="text-xs text-gray-500">pending</p>
            </div>
          )}
        </div>
      </div>

      <div className="flex gap-4 mb-2 text-xs">
        <div className="flex items-center gap-1">
          <div className="w-2 h-3 bg-orange-500/30 rounded-sm"></div>
          <span className="text-gray-500">Daily Received</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-0.5 bg-green-500"></div>
          <span className="text-gray-400">Cumulative Spend</span>
        </div>
      </div>

      {dataPoints.length > 0 ? (
        <div ref={chartRef} className="relative" style={{ height: chartHeight }} onMouseLeave={() => setHoveredIndex(null)}>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
            <line x1="0" y1="50" x2="100" y2="50" stroke="#374151" strokeWidth="0.5" />
            {dataPoints.map((d, i) => {
              const barWidth = 100 / Math.max(dataPoints.length, 1) * 0.6;
              const x = (i / Math.max(dataPoints.length - 1, 1)) * 100 - barWidth / 2;
              const barHeight = ((d.received || 0) / maxDailyReceived) * 100;
              return (
                <rect key={`bar-${i}`} x={Math.max(0, x)} y={100 - barHeight} width={barWidth} height={barHeight} fill="url(#purchasingBarGradient)" opacity="0.4" />
              );
            })}
            <path d={generateSpendPath()} fill="none" stroke="#22c55e" strokeWidth="2" vectorEffect="non-scaling-stroke" />
            {dataPoints.map((_, i) => {
              const sliceWidth = 100 / dataPoints.length;
              return <rect key={`hover-${i}`} x={i * sliceWidth} y={0} width={sliceWidth} height={100} fill="transparent" onMouseMove={(e) => handleMouseMove(e, i)} style={{ cursor: 'crosshair' }} />;
            })}
            {hoveredIndex !== null && cumulativeData[hoveredIndex] && (
              <circle cx={(hoveredIndex / Math.max(cumulativeData.length - 1, 1)) * 100} cy={100 - (cumulativeData[hoveredIndex].cumulativeSpend / Math.max(maxCumulativeSpend, 1)) * 100} r="3" fill="#22c55e" stroke="white" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            )}
            <defs>
              <linearGradient id="purchasingBarGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#f97316" />
                <stop offset="100%" stopColor="#f97316" stopOpacity="0.2" />
              </linearGradient>
            </defs>
          </svg>
          {hoveredIndex !== null && getHoveredData() && (
            <div className="absolute z-10 bg-gray-800 border border-gray-700 rounded-lg shadow-lg p-3 pointer-events-none" style={{ left: Math.max(0, Math.min(mousePos.x + 10, chartWidth - 150)), top: Math.max(mousePos.y - 70, 0), minWidth: '140px' }}>
              {(() => {
                const d = getHoveredData();
                return (
                  <>
                    <div className="text-white font-medium text-sm mb-2">{d.date}</div>
                    <div className="space-y-1 text-xs">
                      <div className="flex justify-between gap-4"><span className="text-orange-400">Received:</span><span className="text-white font-medium">{d.received}</span></div>
                      <div className="flex justify-between gap-4"><span className="text-green-400">Spend:</span><span className="text-white">${d.dailySpend.toFixed(2)}</span></div>
                      <div className="border-t border-gray-700 my-1 pt-1">
                        <div className="flex justify-between gap-4"><span className="text-gray-400">Total POs:</span><span className="text-white">{d.cumulativeReceived}</span></div>
                        <div className="flex justify-between gap-4"><span className="text-gray-400">Total Spend:</span><span className="text-white">${d.cumulativeSpend.toFixed(2)}</span></div>
                      </div>
                    </div>
                  </>
                );
              })()}
            </div>
          )}
        </div>
      ) : (
        <div className="h-24 flex items-center justify-center text-gray-500 text-sm">No POs received for this period</div>
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
