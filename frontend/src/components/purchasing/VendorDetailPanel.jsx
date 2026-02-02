/**
 * VendorDetailPanel - Slide-out panel showing vendor details and metrics
 *
 * Features:
 * - Full vendor information display
 * - Performance metrics (PO count, total spend, lead time, on-time %)
 * - Recent PO history
 * - Quick actions (edit, create PO)
 */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";

import { statusColors } from "./constants";

export default function VendorDetailPanel({
  vendor,
  onClose,
  onEdit,
  onCreatePO,
  onViewPO,
}) {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (vendor?.id) {
      fetchMetrics();
    }
  }, [vendor?.id]);

  const fetchMetrics = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/vendors/${vendor.id}/metrics`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setMetrics(data);
      }
    } catch {
      // Non-critical: Metrics fetch failure - panel still displays vendor info
    } finally {
      setLoading(false);
    }
  };

  if (!vendor) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/60" onClick={onClose} />

      {/* Slide-out Panel */}
      <div className="fixed inset-y-0 right-0 w-full max-w-lg bg-gray-900 border-l border-gray-700 shadow-xl overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-gray-900 border-b border-gray-800 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-600 to-purple-600 flex items-center justify-center text-white font-bold">
              {vendor.name?.charAt(0).toUpperCase()}
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">{vendor.name}</h2>
              <p className="text-sm text-gray-400">{vendor.code}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Quick Actions */}
          <div className="flex gap-3">
            <button
              onClick={() => onEdit(vendor)}
              className="flex-1 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-white text-sm flex items-center justify-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              Edit
            </button>
            <button
              onClick={() => onCreatePO(vendor)}
              className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white text-sm flex items-center justify-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              New PO
            </button>
          </div>

          {/* Metrics Cards */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-gray-800/50 rounded-lg p-4">
              <div className="text-2xl font-bold text-white">
                {loading ? "..." : metrics?.total_pos || 0}
              </div>
              <div className="text-sm text-gray-400">Total POs</div>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-4">
              <div className="text-2xl font-bold text-green-400">
                {loading ? "..." : `$${(metrics?.total_spend || 0).toLocaleString()}`}
              </div>
              <div className="text-sm text-gray-400">Total Spend</div>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-4">
              <div className="text-2xl font-bold text-white">
                {loading ? "..." : (metrics?.avg_lead_time_days ? `${metrics.avg_lead_time_days}d` : "-")}
              </div>
              <div className="text-sm text-gray-400">Avg Lead Time</div>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-4">
              <div className={`text-2xl font-bold ${
                metrics?.on_time_delivery_pct >= 90 ? 'text-green-400' :
                metrics?.on_time_delivery_pct >= 70 ? 'text-yellow-400' :
                metrics?.on_time_delivery_pct ? 'text-red-400' : 'text-gray-400'
              }`}>
                {loading ? "..." : (metrics?.on_time_delivery_pct ? `${metrics.on_time_delivery_pct}%` : "-")}
              </div>
              <div className="text-sm text-gray-400">On-Time Delivery</div>
            </div>
          </div>

          {/* Contact Information */}
          <div className="bg-gray-800/30 rounded-lg p-4">
            <h3 className="text-sm font-medium text-gray-300 mb-3">Contact Information</h3>
            <div className="space-y-2">
              {vendor.contact_name && (
                <div className="flex items-center gap-2 text-sm">
                  <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                  <span className="text-white">{vendor.contact_name}</span>
                </div>
              )}
              {vendor.email && (
                <div className="flex items-center gap-2 text-sm">
                  <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                  <a href={`mailto:${vendor.email}`} className="text-blue-400 hover:text-blue-300">
                    {vendor.email}
                  </a>
                </div>
              )}
              {vendor.phone && (
                <div className="flex items-center gap-2 text-sm">
                  <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                  </svg>
                  <a href={`tel:${vendor.phone}`} className="text-white">
                    {vendor.phone}
                  </a>
                </div>
              )}
              {vendor.website && (
                <div className="flex items-center gap-2 text-sm">
                  <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                  </svg>
                  <a
                    href={vendor.website.startsWith('http') ? vendor.website : `https://${vendor.website}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-400 hover:text-blue-300"
                  >
                    {vendor.website}
                  </a>
                </div>
              )}
            </div>
          </div>

          {/* Address */}
          {(vendor.address_line1 || vendor.city) && (
            <div className="bg-gray-800/30 rounded-lg p-4">
              <h3 className="text-sm font-medium text-gray-300 mb-3">Address</h3>
              <div className="text-sm text-white space-y-1">
                {vendor.address_line1 && <div>{vendor.address_line1}</div>}
                {vendor.address_line2 && <div>{vendor.address_line2}</div>}
                {(vendor.city || vendor.state || vendor.postal_code) && (
                  <div>
                    {[vendor.city, vendor.state].filter(Boolean).join(", ")}
                    {vendor.postal_code && ` ${vendor.postal_code}`}
                  </div>
                )}
                {vendor.country && vendor.country !== "USA" && (
                  <div>{vendor.country}</div>
                )}
              </div>
            </div>
          )}

          {/* Business Info */}
          {(vendor.payment_terms || vendor.account_number) && (
            <div className="bg-gray-800/30 rounded-lg p-4">
              <h3 className="text-sm font-medium text-gray-300 mb-3">Business Info</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                {vendor.payment_terms && (
                  <div>
                    <div className="text-gray-400">Payment Terms</div>
                    <div className="text-white">{vendor.payment_terms}</div>
                  </div>
                )}
                {vendor.account_number && (
                  <div>
                    <div className="text-gray-400">Account #</div>
                    <div className="text-white">{vendor.account_number}</div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Notes */}
          {vendor.notes && (
            <div className="bg-gray-800/30 rounded-lg p-4">
              <h3 className="text-sm font-medium text-gray-300 mb-2">Notes</h3>
              <p className="text-sm text-gray-400 whitespace-pre-wrap">{vendor.notes}</p>
            </div>
          )}

          {/* Recent POs */}
          <div>
            <h3 className="text-sm font-medium text-gray-300 mb-3">Recent Purchase Orders</h3>
            {loading ? (
              <div className="text-center py-4 text-gray-500">Loading...</div>
            ) : metrics?.recent_pos?.length > 0 ? (
              <div className="space-y-2">
                {metrics.recent_pos.map((po) => (
                  <div
                    key={po.id}
                    onClick={() => onViewPO && onViewPO(po.id)}
                    className="bg-gray-800/50 hover:bg-gray-800 rounded-lg p-3 cursor-pointer transition-colors flex items-center justify-between"
                  >
                    <div>
                      <div className="text-white font-medium text-sm">{po.po_number}</div>
                      <div className="text-xs text-gray-400">
                        {po.order_date ? new Date(po.order_date).toLocaleDateString() : "No date"}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-gray-300">
                        ${po.total_amount.toLocaleString()}
                      </span>
                      <span className={`px-2 py-0.5 rounded text-xs ${statusColors[po.status]}`}>
                        {po.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-4 text-gray-500 text-sm">
                No purchase orders yet
              </div>
            )}
          </div>

          {/* Status */}
          <div className="flex items-center gap-2 text-sm">
            <span className={`w-2 h-2 rounded-full ${vendor.is_active ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-gray-400">
              {vendor.is_active ? "Active Vendor" : "Inactive Vendor"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
