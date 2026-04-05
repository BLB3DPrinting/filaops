import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import { useFormatCurrency } from "../../hooks/useFormatCurrency";
import StatCard from "../../components/StatCard";
import { API_URL } from "../../config/api";

const STATUS_TABS = [
  { value: "", label: "All" },
  { value: "draft", label: "Draft" },
  { value: "sent", label: "Sent" },
  { value: "paid", label: "Paid" },
  { value: "overdue", label: "Overdue" },
];

const STATUS_STYLES = {
  draft: "bg-gray-500/20 text-gray-400",
  sent: "bg-blue-500/20 text-blue-400",
  paid: "bg-green-500/20 text-green-400",
  overdue: "bg-red-500/20 text-red-400",
  partially_paid: "bg-yellow-500/20 text-yellow-400",
  void: "bg-gray-500/20 text-gray-500",
};

const PAYMENT_METHODS = [
  { value: "check", label: "Check" },
  { value: "cash", label: "Cash" },
  { value: "credit_card", label: "Credit Card" },
  { value: "bank_transfer", label: "Bank Transfer" },
  { value: "other", label: "Other" },
];

export default function AdminInvoices() {
  const api = useApi();
  const toast = useToast();
  const formatCurrency = useFormatCurrency();
  const [searchParams, setSearchParams] = useSearchParams();

  const statusFilter = searchParams.get("status") || "";
  const searchQuery = searchParams.get("search") || "";

  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [summary, setSummary] = useState(null);

  // Detail modal state
  const [selectedInvoice, setSelectedInvoice] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Payment sub-form state
  const [showPaymentForm, setShowPaymentForm] = useState(false);
  const [paymentForm, setPaymentForm] = useState({
    amount: "",
    method: "bank_transfer",
    reference: "",
  });
  const [recordingPayment, setRecordingPayment] = useState(false);

  // Send invoice state
  const [sendingInvoice, setSendingInvoice] = useState(false);

  useEffect(() => {
    fetchInvoices();
    fetchSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const fetchInvoices = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("limit", "200");
      if (statusFilter) {
        params.set("status", statusFilter);
      }
      const data = await api.get(`/api/v1/invoices?${params}`);
      setInvoices(data.items || data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchSummary = async () => {
    try {
      const data = await api.get("/api/v1/invoices/summary");
      setSummary(data);
    } catch {
      // Summary fetch failure is non-critical
    }
  };

  const handleViewInvoice = async (invoice) => {
    setDetailLoading(true);
    try {
      const data = await api.get(`/api/v1/invoices/${invoice.id}`);
      setSelectedInvoice(data);
    } catch (err) {
      toast.error(err.message || "Failed to load invoice details");
    } finally {
      setDetailLoading(false);
    }
  };

  const handleSendInvoice = async () => {
    if (!selectedInvoice) return;
    setSendingInvoice(true);
    try {
      const updated = await api.post(`/api/v1/invoices/${selectedInvoice.id}/send`);
      toast.success("Invoice sent");
      setSelectedInvoice(updated);
      fetchInvoices();
      fetchSummary();
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || "Failed to send invoice");
    } finally {
      setSendingInvoice(false);
    }
  };

  const handleRecordPayment = async () => {
    if (!selectedInvoice) return;
    if (!paymentForm.amount || parseFloat(paymentForm.amount) <= 0) {
      toast.error("Please enter a valid payment amount");
      return;
    }
    setRecordingPayment(true);
    try {
      const updated = await api.patch(`/api/v1/invoices/${selectedInvoice.id}`, {
        amount_paid: parseFloat(paymentForm.amount),
        payment_method: paymentForm.method,
        payment_reference: paymentForm.reference,
      });
      toast.success("Payment recorded");
      setSelectedInvoice(updated);
      setShowPaymentForm(false);
      setPaymentForm({ amount: "", method: "bank_transfer", reference: "" });
      fetchInvoices();
      fetchSummary();
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || "Failed to record payment");
    } finally {
      setRecordingPayment(false);
    }
  };

  const handleDownloadPDF = async (invoiceId, invoiceNumber) => {
    try {
      const response = await fetch(`${API_URL}/api/v1/invoices/${invoiceId}/pdf`, {
        credentials: "include",
      });
      if (!response.ok) throw new Error("Failed to download PDF");
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${invoiceNumber}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err.message || "Failed to download PDF");
    }
  };

  // Client-side search filter
  const filteredInvoices = invoices.filter((inv) => {
    if (!searchQuery) return true;
    const search = searchQuery.toLowerCase();
    return (
      inv.invoice_number?.toLowerCase().includes(search) ||
      inv.customer_name?.toLowerCase().includes(search) ||
      inv.order_number?.toLowerCase().includes(search)
    );
  });

  const handleStatusFilterChange = (newStatus) => {
    const newParams = new URLSearchParams(searchParams);
    if (newStatus) {
      newParams.set("status", newStatus);
    } else {
      newParams.delete("status");
    }
    setSearchParams(newParams);
  };

  const handleSearchChange = (newSearch) => {
    const newParams = new URLSearchParams(searchParams);
    if (newSearch) {
      newParams.set("search", newSearch);
    } else {
      newParams.delete("search");
    }
    setSearchParams(newParams);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Invoices</h1>
          <p className="text-gray-400 mt-1">
            Manage invoices and track accounts receivable
          </p>
        </div>
        <button
          onClick={() => { fetchInvoices(); fetchSummary(); }}
          disabled={loading}
          className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 disabled:opacity-50"
          title="Refresh invoices"
        >
          {loading ? "Loading..." : "\u21BB Refresh"}
        </button>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard
          variant="simple"
          title="Total AR"
          value={formatCurrency(summary?.total_ar || 0)}
          color="primary"
        />
        <StatCard
          variant="simple"
          title="Overdue"
          value={summary?.overdue_count || 0}
          color={summary?.overdue_count > 0 ? "danger" : "success"}
        />
        <StatCard
          variant="simple"
          title="Open Invoices"
          value={summary?.open_count || 0}
          color="secondary"
        />
        <StatCard
          variant="simple"
          title="Paid (30 Days)"
          value={formatCurrency(summary?.paid_last_30_days || 0)}
          color="success"
        />
      </div>

      {/* Status Filter Tabs */}
      <div className="flex flex-col sm:flex-row gap-4 bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div className="flex gap-1 flex-wrap">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => handleStatusFilterChange(tab.value)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                statusFilter === tab.value
                  ? "bg-blue-600 text-white"
                  : "bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="flex-1">
          <input
            type="text"
            placeholder="Search by invoice #, customer, or order #..."
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500"
          />
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400">
          {error}
          <button
            onClick={() => setError(null)}
            className="ml-4 text-red-300 hover:text-white"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      )}

      {/* Invoices Table */}
      {!loading && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px]">
              <thead className="bg-gray-800/50">
                <tr>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Invoice #
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Order #
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Customer
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Terms
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Due Date
                  </th>
                  <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Total
                  </th>
                  <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Paid
                  </th>
                  <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Balance
                  </th>
                  <th className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredInvoices.map((invoice) => (
                  <tr
                    key={invoice.id}
                    onClick={() => handleViewInvoice(invoice)}
                    className="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer"
                  >
                    <td className="py-3 px-4 text-white font-mono text-sm">
                      {invoice.invoice_number || "-"}
                    </td>
                    <td className="py-3 px-4 text-gray-300 font-mono text-sm">
                      {invoice.order_number || "-"}
                    </td>
                    <td className="py-3 px-4 text-gray-300">
                      {invoice.customer_name || "-"}
                    </td>
                    <td className="py-3 px-4 text-gray-400 text-sm">
                      {invoice.payment_terms || "-"}
                    </td>
                    <td className="py-3 px-4 text-gray-300 text-sm">
                      {formatDate(invoice.due_date)}
                    </td>
                    <td className="py-3 px-4 text-right text-white">
                      {formatCurrency(invoice.total || 0)}
                    </td>
                    <td className="py-3 px-4 text-right text-emerald-400">
                      {formatCurrency(invoice.amount_paid || 0)}
                    </td>
                    <td className="py-3 px-4 text-right text-white font-medium">
                      {formatCurrency(invoice.balance_due || 0)}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span
                        className={`px-2 py-1 rounded-full text-xs ${
                          STATUS_STYLES[invoice.status] || STATUS_STYLES.draft
                        }`}
                      >
                        {invoice.status?.charAt(0).toUpperCase() +
                          invoice.status?.slice(1).replace(/_/g, " ")}
                      </span>
                    </td>
                  </tr>
                ))}
                {filteredInvoices.length === 0 && (
                  <tr>
                    <td colSpan={9} className="py-12 text-center text-gray-500">
                      No invoices found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Invoice Detail Modal */}
      {(selectedInvoice || detailLoading) && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20">
            <div
              className="fixed inset-0 bg-black/70"
              onClick={() => {
                setSelectedInvoice(null);
                setShowPaymentForm(false);
              }}
            />
            <div className="relative bg-gray-900 border border-gray-700 rounded-xl shadow-xl max-w-3xl w-full mx-auto p-6 max-h-[90vh] overflow-y-auto">
              {detailLoading ? (
                <div className="flex items-center justify-center h-32">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                </div>
              ) : selectedInvoice ? (
                <>
                  {/* Modal Header */}
                  <div className="flex justify-between items-start mb-6">
                    <div>
                      <h3 className="text-lg font-semibold text-white">
                        {selectedInvoice.invoice_number}
                      </h3>
                      <div className="flex items-center gap-3 mt-1">
                        <span
                          className={`px-2 py-1 rounded-full text-xs ${
                            STATUS_STYLES[selectedInvoice.status] || STATUS_STYLES.draft
                          }`}
                        >
                          {selectedInvoice.status?.charAt(0).toUpperCase() +
                            selectedInvoice.status?.slice(1).replace(/_/g, " ")}
                        </span>
                        {selectedInvoice.payment_terms && (
                          <span className="text-sm text-gray-400">
                            Terms: {selectedInvoice.payment_terms}
                          </span>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => {
                        setSelectedInvoice(null);
                        setShowPaymentForm(false);
                      }}
                      className="text-gray-400 hover:text-white p-1"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>

                  {/* Invoice Dates */}
                  <div className="grid grid-cols-3 gap-4 mb-6 text-sm">
                    <div>
                      <span className="text-gray-400">Invoice Date</span>
                      <p className="text-white">{formatDate(selectedInvoice.invoice_date)}</p>
                    </div>
                    <div>
                      <span className="text-gray-400">Due Date</span>
                      <p className="text-white">{formatDate(selectedInvoice.due_date)}</p>
                    </div>
                    <div>
                      <span className="text-gray-400">Order #</span>
                      <p className="text-white">{selectedInvoice.order_number || "-"}</p>
                    </div>
                  </div>

                  {/* Customer Info */}
                  {(selectedInvoice.customer_name || selectedInvoice.billing_address) && (
                    <div className="bg-gray-800 rounded-lg p-4 mb-6">
                      <h4 className="text-sm font-medium text-gray-300 mb-2">Customer</h4>
                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                          <p className="text-white">{selectedInvoice.customer_name || "-"}</p>
                          {selectedInvoice.customer_company && (
                            <p className="text-gray-400">{selectedInvoice.customer_company}</p>
                          )}
                        </div>
                        {selectedInvoice.billing_address && (
                          <div>
                            <p className="text-gray-400 whitespace-pre-line">
                              {selectedInvoice.billing_address}
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Line Items */}
                  {selectedInvoice.lines && selectedInvoice.lines.length > 0 && (
                    <div className="mb-6">
                      <h4 className="text-sm font-medium text-gray-300 mb-2">Line Items</h4>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead className="bg-gray-800/50">
                            <tr>
                              <th className="text-left py-2 px-3 text-xs font-medium text-gray-400 uppercase">
                                SKU
                              </th>
                              <th className="text-left py-2 px-3 text-xs font-medium text-gray-400 uppercase">
                                Description
                              </th>
                              <th className="text-right py-2 px-3 text-xs font-medium text-gray-400 uppercase">
                                Qty
                              </th>
                              <th className="text-right py-2 px-3 text-xs font-medium text-gray-400 uppercase">
                                Unit Price
                              </th>
                              <th className="text-right py-2 px-3 text-xs font-medium text-gray-400 uppercase">
                                Total
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedInvoice.lines.map((line, idx) => (
                              <tr key={line.id || idx} className="border-b border-gray-800">
                                <td className="py-2 px-3 text-gray-300 font-mono">
                                  {line.sku || "-"}
                                </td>
                                <td className="py-2 px-3 text-white">
                                  {line.description || line.product_name || "-"}
                                </td>
                                <td className="py-2 px-3 text-right text-gray-300">
                                  {line.quantity}
                                </td>
                                <td className="py-2 px-3 text-right text-gray-300">
                                  {formatCurrency(line.unit_price || 0)}
                                </td>
                                <td className="py-2 px-3 text-right text-white">
                                  {formatCurrency(line.total || line.line_total || 0)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Totals */}
                  <div className="bg-gray-800 rounded-lg p-4 mb-6">
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-400">Subtotal</span>
                        <span className="text-white">
                          {formatCurrency(selectedInvoice.subtotal || 0)}
                        </span>
                      </div>
                      {parseFloat(selectedInvoice.discount_amount || 0) > 0 && (
                        <div className="flex justify-between">
                          <span className="text-gray-400">Discount</span>
                          <span className="text-red-400">
                            -{formatCurrency(selectedInvoice.discount_amount)}
                          </span>
                        </div>
                      )}
                      {parseFloat(selectedInvoice.tax_amount || 0) > 0 && (
                        <div className="flex justify-between">
                          <span className="text-gray-400">Tax</span>
                          <span className="text-white">
                            {formatCurrency(selectedInvoice.tax_amount)}
                          </span>
                        </div>
                      )}
                      {parseFloat(selectedInvoice.shipping_amount || 0) > 0 && (
                        <div className="flex justify-between">
                          <span className="text-gray-400">Shipping</span>
                          <span className="text-white">
                            {formatCurrency(selectedInvoice.shipping_amount)}
                          </span>
                        </div>
                      )}
                      <div className="flex justify-between border-t border-gray-700 pt-2 font-medium">
                        <span className="text-white">Total</span>
                        <span className="text-white">
                          {formatCurrency(selectedInvoice.total || 0)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Amount Paid</span>
                        <span className="text-emerald-400">
                          {formatCurrency(selectedInvoice.amount_paid || 0)}
                        </span>
                      </div>
                      <div className="flex justify-between border-t border-gray-700 pt-2 font-semibold">
                        <span className="text-white">Balance Due</span>
                        <span className={parseFloat(selectedInvoice.balance_due || 0) > 0 ? "text-red-400" : "text-green-400"}>
                          {formatCurrency(selectedInvoice.balance_due || 0)}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex flex-wrap gap-3 pt-4 border-t border-gray-800">
                    {selectedInvoice.status === "draft" && (
                      <button
                        onClick={handleSendInvoice}
                        disabled={sendingInvoice}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                        </svg>
                        {sendingInvoice ? "Sending..." : "Send Invoice"}
                      </button>
                    )}
                    <button
                      onClick={() => setShowPaymentForm(!showPaymentForm)}
                      className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center gap-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Record Payment
                    </button>
                    <button
                      onClick={() => handleDownloadPDF(selectedInvoice.id, selectedInvoice.invoice_number)}
                      className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 flex items-center gap-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      Download PDF
                    </button>
                  </div>

                  {/* Record Payment Sub-Form */}
                  {showPaymentForm && (
                    <div className="mt-4 bg-gray-800 rounded-lg p-4">
                      <h4 className="text-sm font-medium text-white mb-3">Record Payment</h4>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">Amount</label>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            value={paymentForm.amount}
                            onChange={(e) =>
                              setPaymentForm({ ...paymentForm, amount: e.target.value })
                            }
                            placeholder={`${parseFloat(selectedInvoice.balance_due || 0).toFixed(2)}`}
                            className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white placeholder-gray-500 text-sm"
                          />
                        </div>
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">Method</label>
                          <select
                            value={paymentForm.method}
                            onChange={(e) =>
                              setPaymentForm({ ...paymentForm, method: e.target.value })
                            }
                            className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm"
                          >
                            {PAYMENT_METHODS.map((m) => (
                              <option key={m.value} value={m.value}>
                                {m.label}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">Reference</label>
                          <input
                            type="text"
                            value={paymentForm.reference}
                            onChange={(e) =>
                              setPaymentForm({ ...paymentForm, reference: e.target.value })
                            }
                            placeholder="Check #, txn ID, etc."
                            className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white placeholder-gray-500 text-sm"
                          />
                        </div>
                      </div>
                      <div className="flex justify-end gap-2 mt-3">
                        <button
                          onClick={() => setShowPaymentForm(false)}
                          className="px-3 py-1.5 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600 text-sm"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={handleRecordPayment}
                          disabled={recordingPayment}
                          className="px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm"
                        >
                          {recordingPayment ? "Recording..." : "Submit Payment"}
                        </button>
                      </div>
                    </div>
                  )}
                </>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
