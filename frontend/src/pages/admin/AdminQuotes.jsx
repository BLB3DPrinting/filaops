/**
 * AdminQuotes - Quote management orchestrator.
 *
 * Sub-components extracted per ARCHITECT-002:
 *   QuoteFormModal, QuoteDetailModal, constants
 */
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";
import { STATUS_OPTIONS, getStatusStyle } from "../../components/quotes/constants";
import QuoteFormModal from "../../components/quotes/QuoteFormModal";
import QuoteDetailModal from "../../components/quotes/QuoteDetailModal";

export default function AdminQuotes() {
  const navigate = useNavigate();
  const toast = useToast();
  const [quotes, setQuotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [filters, setFilters] = useState({
    search: "",
    status: "all",
  });

  // Modal states
  const [showQuoteModal, setShowQuoteModal] = useState(false);
  const [editingQuote, setEditingQuote] = useState(null);
  const [viewingQuote, setViewingQuote] = useState(null);

  useEffect(() => {
    fetchQuotes();
    fetchStats();
  }, [filters.status]);

  const fetchQuotes = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("limit", "200");
      if (filters.status !== "all") params.set("status", filters.status);

      const res = await fetch(`${API_URL}/api/v1/quotes?${params}`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error("Failed to fetch quotes");
      const data = await res.json();
      setQuotes(Array.isArray(data) ? data : []);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/quotes/stats`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch {
      // Stats fetch failure is non-critical
    }
  };

  const filteredQuotes = quotes.filter((quote) => {
    if (!filters.search) return true;
    const search = filters.search.toLowerCase();
    return (
      quote.quote_number?.toLowerCase().includes(search) ||
      quote.product_name?.toLowerCase().includes(search) ||
      quote.customer_name?.toLowerCase().includes(search) ||
      quote.customer_email?.toLowerCase().includes(search)
    );
  });

  const handleSaveQuote = async (quoteData) => {
    try {
      const url = editingQuote
        ? `${API_URL}/api/v1/quotes/${editingQuote.id}`
        : `${API_URL}/api/v1/quotes`;
      const method = editingQuote ? "PATCH" : "POST";

      const res = await fetch(url, {
        method,
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(quoteData),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to save quote");
      }

      toast.success(editingQuote ? "Quote updated" : "Quote created");
      setShowQuoteModal(false);
      setEditingQuote(null);
      fetchQuotes();
      fetchStats();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleUpdateStatus = async (quoteId, newStatus, rejectionReason = null) => {
    try {
      const res = await fetch(`${API_URL}/api/v1/quotes/${quoteId}/status`, {
        method: "PATCH",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          status: newStatus,
          rejection_reason: rejectionReason,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to update status");
      }

      const updated = await res.json();
      toast.success(`Quote ${newStatus}`);
      fetchQuotes();
      fetchStats();
      if (viewingQuote?.id === quoteId) {
        setViewingQuote(updated);
      }
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleConvertToOrder = async (quoteId) => {
    try {
      const res = await fetch(`${API_URL}/api/v1/quotes/${quoteId}/convert`, {
        method: "POST",
        credentials: "include",
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to convert quote");
      }

      const data = await res.json();
      toast.success(`Converted to ${data.order_number}`);
      setViewingQuote(null);
      fetchQuotes();
      fetchStats();

      // Navigate to the new order
      navigate(`/admin/orders/${data.order_id}`);
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleDownloadPDF = async (quote) => {
    try {
      const res = await fetch(`${API_URL}/api/v1/quotes/${quote.id}/pdf`, {
        credentials: "include",
      });

      if (!res.ok) throw new Error("Failed to generate PDF");

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${quote.quote_number}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      a.remove();

      toast.success("Quote PDF downloaded");
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handlePrintPDF = async (quote) => {
    try {
      const res = await fetch(`${API_URL}/api/v1/quotes/${quote.id}/pdf`, {
        credentials: "include",
      });

      if (!res.ok) throw new Error("Failed to generate PDF");

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);

      // Open in new window for printing
      const printWindow = window.open(url, "_blank");
      if (printWindow) {
        printWindow.onload = () => {
          printWindow.print();
        };
      } else {
        // Fallback: just open in new tab if popup blocked
        window.open(url, "_blank");
        toast.info("PDF opened in new tab. Use browser print (Ctrl+P) to print.");
      }
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleDuplicateQuote = async (quote) => {
    try {
      // Create a new quote based on the existing one
      const newQuoteData = {
        product_id: quote.product_id || null,
        product_name: quote.product_name,
        quantity: quote.quantity,
        unit_price: parseFloat(quote.unit_price || 0),
        customer_id: quote.customer_id || null,
        customer_name: quote.customer_name || null,
        customer_email: quote.customer_email || null,
        material_type: quote.material_type || null,
        color: quote.color || null,
        customer_notes: quote.customer_notes || null,
        admin_notes: `Duplicated from ${quote.quote_number}`,
        apply_tax: quote.tax_rate ? true : false,
        valid_days: 30,
      };

      const res = await fetch(`${API_URL}/api/v1/quotes`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(newQuoteData),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to duplicate quote");
      }

      const newQuote = await res.json();
      toast.success(`Quote duplicated as ${newQuote.quote_number}`);
      fetchQuotes();
      fetchStats();
      setViewingQuote(newQuote);
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleCopyQuoteLink = (quote) => {
    // Create a shareable link - could be customer portal link or just quote reference
    const quoteLink = `${window.location.origin}/quote/${quote.quote_number}`;
    navigator.clipboard.writeText(quoteLink).then(() => {
      toast.success("Quote link copied to clipboard");
    }).catch(() => {
      // Fallback - copy quote number
      navigator.clipboard.writeText(quote.quote_number);
      toast.success("Quote number copied to clipboard");
    });
  };

  const handleDeleteQuote = async (quoteId) => {
    if (!confirm("Are you sure you want to delete this quote?")) return;

    try {
      const res = await fetch(`${API_URL}/api/v1/quotes/${quoteId}`, {
        method: "DELETE",
        credentials: "include",
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to delete quote");
      }

      toast.success("Quote deleted");
      setViewingQuote(null);
      fetchQuotes();
      fetchStats();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const isExpired = (quote) => {
    return new Date(quote.expires_at) < new Date();
  };

  const isExpiringSoon = (quote) => {
    const expiresAt = new Date(quote.expires_at);
    const now = new Date();
    const sevenDaysFromNow = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
    return expiresAt > now && expiresAt <= sevenDaysFromNow;
  };

  const getDaysUntilExpiry = (quote) => {
    const expiresAt = new Date(quote.expires_at);
    const now = new Date();
    const diffTime = expiresAt.getTime() - now.getTime();
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return diffDays;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">Quote Management</h1>
          <p className="text-gray-400 mt-1">Create and manage customer quotes</p>
        </div>
        <button
          onClick={() => {
            setEditingQuote(null);
            setShowQuoteModal(true);
          }}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Quote
        </button>
      </div>

      {/* Stats Cards - Clickable to filter */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
          <button
            onClick={() => setFilters((f) => ({ ...f, status: "pending" }))}
            className={`text-left bg-gradient-to-br from-yellow-600/20 to-yellow-600/5 border rounded-xl p-4 transition-all hover:scale-[1.02] ${
              filters.status === "pending" ? "border-yellow-400 ring-1 ring-yellow-400" : "border-yellow-500/30"
            }`}
          >
            <p className="text-gray-400 text-sm">Pending</p>
            <p className="text-2xl font-bold text-white">{stats.pending}</p>
            <p className="text-yellow-400 text-xs mt-1">
              ${parseFloat(stats.pending_value || 0).toLocaleString()}
            </p>
          </button>
          <button
            onClick={() => setFilters((f) => ({ ...f, status: "approved" }))}
            className={`text-left bg-gradient-to-br from-blue-600/20 to-blue-600/5 border rounded-xl p-4 transition-all hover:scale-[1.02] ${
              filters.status === "approved" ? "border-blue-400 ring-1 ring-blue-400" : "border-blue-500/30"
            }`}
          >
            <p className="text-gray-400 text-sm">Approved</p>
            <p className="text-2xl font-bold text-white">{stats.approved}</p>
            <p className="text-blue-400 text-xs mt-1">Ready to accept</p>
          </button>
          <button
            onClick={() => setFilters((f) => ({ ...f, status: "accepted" }))}
            className={`text-left bg-gradient-to-br from-cyan-600/20 to-cyan-600/5 border rounded-xl p-4 transition-all hover:scale-[1.02] ${
              filters.status === "accepted" ? "border-cyan-400 ring-1 ring-cyan-400" : "border-cyan-500/30"
            }`}
          >
            <p className="text-gray-400 text-sm">Accepted</p>
            <p className="text-2xl font-bold text-white">{stats.accepted}</p>
            <p className="text-cyan-400 text-xs mt-1">Ready to convert</p>
          </button>
          <button
            onClick={() => setFilters((f) => ({ ...f, status: "converted" }))}
            className={`text-left bg-gradient-to-br from-green-600/20 to-green-600/5 border rounded-xl p-4 transition-all hover:scale-[1.02] ${
              filters.status === "converted" ? "border-green-400 ring-1 ring-green-400" : "border-green-500/30"
            }`}
          >
            <p className="text-gray-400 text-sm">Converted</p>
            <p className="text-2xl font-bold text-white">{stats.converted}</p>
            <p className="text-green-400 text-xs mt-1">Became orders</p>
          </button>
          <div className="bg-gradient-to-br from-emerald-600/20 to-emerald-600/5 border border-emerald-500/30 rounded-xl p-4">
            <p className="text-gray-400 text-sm">Conversion Rate</p>
            <p className="text-2xl font-bold text-white">
              {stats.total > 0 ? ((stats.converted / stats.total) * 100).toFixed(1) : 0}%
            </p>
            <p className="text-emerald-400 text-xs mt-1">
              {stats.converted} of {stats.total} quotes
            </p>
          </div>
          <button
            onClick={() => setFilters((f) => ({ ...f, status: "all" }))}
            className={`text-left bg-gradient-to-br from-purple-600/20 to-purple-600/5 border rounded-xl p-4 transition-all hover:scale-[1.02] ${
              filters.status === "all" ? "border-purple-400 ring-1 ring-purple-400" : "border-purple-500/30"
            }`}
          >
            <p className="text-gray-400 text-sm">Total Value</p>
            <p className="text-2xl font-bold text-white">
              ${parseFloat(stats.total_value || 0).toLocaleString()}
            </p>
            <p className="text-purple-400 text-xs mt-1">{stats.total} quotes</p>
          </button>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-4">
        <div className="flex-1 relative">
          <input
            type="text"
            placeholder="Search quotes..."
            value={filters.search}
            onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white pl-10"
          />
          <svg
            className="w-5 h-5 absolute left-3 top-2.5 text-gray-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </div>
        <select
          value={filters.status}
          onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
          className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
        >
          <option value="all">All Status</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>

      {/* Quotes Table */}
      {loading ? (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-800 bg-gray-800/50">
                <th className="text-left px-4 py-3 text-gray-400 font-medium text-sm">Quote #</th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium text-sm">Product</th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium text-sm">Customer</th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium text-sm">Qty</th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium text-sm">Total</th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium text-sm">Status</th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium text-sm">Expires</th>
                <th className="text-right px-4 py-3 text-gray-400 font-medium text-sm">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {filteredQuotes.map((quote) => {
                const expired = isExpired(quote) && quote.status !== "converted";
                const expiringSoon = !expired && isExpiringSoon(quote) && quote.status !== "converted";
                const daysLeft = getDaysUntilExpiry(quote);

                return (
                  <tr
                    key={quote.id}
                    className={`hover:bg-gray-800/50 cursor-pointer ${expired ? "opacity-60" : ""}`}
                    onClick={() => setViewingQuote(quote)}
                  >
                    <td className="px-4 py-3">
                      <span className="text-white font-mono">{quote.quote_number}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-white">{quote.product_name || "—"}</span>
                      {quote.material_type && (
                        <span className="text-gray-500 text-sm ml-2">
                          ({quote.material_type}
                          {quote.color ? ` / ${quote.color}` : ""})
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-white">{quote.customer_name || "—"}</span>
                      {quote.customer_email && (
                        <span className="text-gray-500 text-sm block">{quote.customer_email}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-white">{quote.quantity}</td>
                    <td className="px-4 py-3 text-green-400 font-medium">
                      ${parseFloat(quote.total_price || 0).toFixed(2)}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-full text-xs ${getStatusStyle(quote.status)}`}>
                        {quote.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {quote.status === "converted" ? (
                        <span className="text-gray-500 text-sm">—</span>
                      ) : expired ? (
                        <span className="text-red-400 text-sm font-medium">Expired</span>
                      ) : expiringSoon ? (
                        <span className="text-yellow-400 text-sm font-medium">
                          {daysLeft} day{daysLeft !== 1 ? "s" : ""} left
                        </span>
                      ) : (
                        <span className="text-gray-400 text-sm">
                          {new Date(quote.expires_at).toLocaleDateString()}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end gap-1">
                        <button
                          onClick={() => handleDownloadPDF(quote)}
                          className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-700 rounded"
                          title="Download PDF"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                            />
                          </svg>
                        </button>
                        <button
                          onClick={() => handlePrintPDF(quote)}
                          className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-700 rounded"
                          title="Print Quote"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"
                            />
                          </svg>
                        </button>
                        {quote.status === "pending" && (
                          <button
                            onClick={() => handleUpdateStatus(quote.id, "approved")}
                            className="p-1.5 text-blue-400 hover:text-blue-300 hover:bg-blue-900/30 rounded"
                            title="Approve"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                          </button>
                        )}
                        {(quote.status === "approved" || quote.status === "accepted") && !expired && (
                          <button
                            onClick={() => handleConvertToOrder(quote.id)}
                            className="p-1.5 text-green-400 hover:text-green-300 hover:bg-green-900/30 rounded"
                            title="Convert to Order"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                              />
                            </svg>
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {filteredQuotes.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                    No quotes found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Create/Edit Quote Modal */}
      {showQuoteModal && (
        <QuoteFormModal
          quote={editingQuote}
          onSave={handleSaveQuote}
          onClose={() => {
            setShowQuoteModal(false);
            setEditingQuote(null);
          }}
        />
      )}

      {/* View Quote Modal */}
      {viewingQuote && (
        <QuoteDetailModal
          quote={viewingQuote}
          onClose={() => setViewingQuote(null)}
          onEdit={() => {
            setEditingQuote(viewingQuote);
            setShowQuoteModal(true);
            setViewingQuote(null);
          }}
          onUpdateStatus={handleUpdateStatus}
          onConvert={handleConvertToOrder}
          onDownloadPDF={handleDownloadPDF}
          onPrintPDF={handlePrintPDF}
          onDuplicate={handleDuplicateQuote}
          onCopyLink={handleCopyQuoteLink}
          onDelete={handleDeleteQuote}
          getStatusStyle={getStatusStyle}
          onRefresh={async () => {
            // Refresh the viewing quote to get updated has_image flag
            const res = await fetch(`${API_URL}/api/v1/quotes/${viewingQuote.id}`, {
              credentials: "include",
            });
            if (res.ok) {
              const updated = await res.json();
              setViewingQuote(updated);
            }
            fetchQuotes();
          }}
        />
      )}
    </div>
  );
}

