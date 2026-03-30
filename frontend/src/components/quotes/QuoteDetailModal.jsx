/**
 * QuoteDetailModal - View quote details with image, actions, and status management.
 *
 * Extracted from AdminQuotes.jsx (ARCHITECT-002)
 */
import { useState, useEffect, useRef } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../Toast";

export default function QuoteDetailModal({
  quote,
  onClose,
  onEdit,
  onUpdateStatus,
  onConvert,
  onDownloadPDF,
  onPrintPDF,
  onDuplicate,
  onCopyLink,
  onDelete,
  getStatusStyle,
  onRefresh,
}) {
  const toast = useToast();
  const [uploadingImage, setUploadingImage] = useState(false);
  const [imageUrl, setImageUrl] = useState(null);
  const imageUrlRef = useRef(null);

  // Fetch full quote detail (with lines) since list items don't include them
  const [fullQuote, setFullQuote] = useState(quote);
  useEffect(() => {
    setFullQuote(quote); // Reset immediately when quote prop changes
    fetch(`${API_URL}/api/v1/quotes/${quote.id}`, { credentials: "include" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => { if (data) setFullQuote(data); })
      .catch(() => {});
  }, [quote.id]);

  // Use fullQuote for display (has lines), fall back to prop for fields not yet loaded
  const q = fullQuote;

  const isExpired = new Date(q.expires_at) < new Date();
  const canConvert =
    (q.status === "approved" || q.status === "accepted") && !isExpired && !q.sales_order_id;

  // Load image if quote has one (fetch with auth and create blob URL)
  useEffect(() => {
    if (q.has_image) {
      fetch(`${API_URL}/api/v1/quotes/${q.id}/image`, {
        credentials: "include",
      })
        .then((res) => {
          if (res.ok) return res.blob();
          throw new Error("Failed to load image");
        })
        .then((blob) => {
          const url = URL.createObjectURL(blob);
          imageUrlRef.current = url;
          setImageUrl(url);
        })
        .catch(() => setImageUrl(null));
    } else {
      setImageUrl(null);
    }

    // Cleanup blob URL on unmount (use ref to avoid stale closure)
    return () => {
      if (imageUrlRef.current) {
        URL.revokeObjectURL(imageUrlRef.current);
        imageUrlRef.current = null;
      }
    };
  }, [q.id, q.has_image]);

  const handleImageUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith("image/")) {
      toast.error("Please select an image file");
      return;
    }

    // Validate file size (5MB)
    if (file.size > 5 * 1024 * 1024) {
      toast.error("Image must be less than 5MB");
      return;
    }

    setUploadingImage(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_URL}/api/v1/quotes/${quote.id}/image`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to upload image");
      }

      toast.success("Image uploaded successfully");
      // Refresh image by fetching with auth
      const imgRes = await fetch(`${API_URL}/api/v1/quotes/${quote.id}/image`, {
        credentials: "include",
      });
      if (imgRes.ok) {
        const blob = await imgRes.blob();
        if (imageUrlRef.current) {
          URL.revokeObjectURL(imageUrlRef.current);
        }
        const url = URL.createObjectURL(blob);
        imageUrlRef.current = url;
        setImageUrl(url);
      }
      if (onRefresh) onRefresh();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setUploadingImage(false);
    }
  };

  const handleImageDelete = async () => {
    if (!confirm("Delete this product image?")) return;

    try {
      const res = await fetch(`${API_URL}/api/v1/quotes/${quote.id}/image`, {
        method: "DELETE",
        credentials: "include",
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to delete image");
      }

      toast.success("Image deleted");
      if (imageUrlRef.current) {
        URL.revokeObjectURL(imageUrlRef.current);
        imageUrlRef.current = null;
      }
      setImageUrl(null);
      if (onRefresh) onRefresh();
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20">
        <div className="fixed inset-0 bg-black/70" onClick={onClose} />
        <div className="relative bg-gray-900 border border-gray-700 rounded-xl shadow-xl max-w-2xl w-full mx-auto p-6">
          <div className="flex justify-between items-start mb-6">
            <div>
              <h3 className="text-lg font-semibold text-white">{q.quote_number}</h3>
              <p className="text-gray-400 text-sm">
                Created {new Date(q.created_at).toLocaleDateString()}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className={`px-3 py-1 rounded-full text-sm ${getStatusStyle(q.status)}`}>
                {q.status}
              </span>
              {isExpired && q.status !== "converted" && (
                <span className="px-3 py-1 rounded-full text-sm bg-red-500/20 text-red-400">Expired</span>
              )}
              <button onClick={onClose} className="text-gray-400 hover:text-white ml-2">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Quote Details */}
          <div className="space-y-4">
            <div className="bg-gray-800 rounded-lg p-4">
              <h4 className="text-sm font-medium text-gray-300 mb-3">
                {q.lines?.length > 0 ? `Items (${q.lines.length})` : "Product Details"}
              </h4>

              {/* Multi-line items */}
              {q.lines?.length > 0 ? (
                <div className="space-y-2 mb-4">
                  {q.lines.map((line) => (
                    <div key={line.id} className="flex justify-between items-center text-sm py-2 border-b border-gray-700 last:border-0">
                      <div className="flex-1 min-w-0">
                        <span className="text-white">{line.product_name}</span>
                        {(line.material_type || line.color) && (
                          <span className="text-gray-500 ml-2 text-xs">
                            {[line.material_type, line.color].filter(Boolean).join(" / ")}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-4 text-right">
                        <span className="text-gray-400">x{line.quantity}</span>
                        <span className="text-gray-400">@ ${parseFloat(line.unit_price).toFixed(2)}</span>
                        <span className="text-white font-medium w-20">${parseFloat(line.total).toFixed(2)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                /* Legacy single-item display */
                <div className="grid grid-cols-2 gap-4 text-sm mb-4">
                  <div>
                    <span className="text-gray-400">Product:</span>
                    <span className="text-white ml-2">{q.product_name || "—"}</span>
                  </div>
                  <div>
                    <span className="text-gray-400">Quantity:</span>
                    <span className="text-white ml-2">{q.quantity}</span>
                  </div>
                  {q.material_type && (
                    <div>
                      <span className="text-gray-400">Material:</span>
                      <span className="text-white ml-2">
                        {q.material_type}
                        {q.color ? ` / ${q.color}` : ""}
                      </span>
                    </div>
                  )}
                  <div>
                    <span className="text-gray-400">Unit Price:</span>
                    <span className="text-white ml-2">${parseFloat(q.unit_price || 0).toFixed(2)}</span>
                  </div>
                </div>
              )}

              {/* Price Breakdown */}
              <div className="border-t border-gray-700 pt-3 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Subtotal:</span>
                  <span className="text-white">
                    ${parseFloat(q.subtotal || (q.unit_price * q.quantity) || 0).toFixed(2)}
                  </span>
                </div>
                {q.discount_percent && parseFloat(q.discount_percent) > 0 && (
                  <div className="flex justify-between text-sm">
                    <span className="text-green-400">
                      Customer Discount ({parseFloat(q.discount_percent)}%):
                    </span>
                    <span className="text-green-400">Applied per line</span>
                  </div>
                )}
                {q.tax_rate && q.tax_amount && (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">
                      Tax ({(parseFloat(q.tax_rate) * 100).toFixed(2)}%):
                    </span>
                    <span className="text-white">${parseFloat(q.tax_amount).toFixed(2)}</span>
                  </div>
                )}
                {q.shipping_cost && parseFloat(q.shipping_cost) > 0 && (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">Shipping:</span>
                    <span className="text-white">${parseFloat(q.shipping_cost).toFixed(2)}</span>
                  </div>
                )}
                <div className="flex justify-between text-sm font-medium pt-2 border-t border-gray-700">
                  <span className="text-white">Total:</span>
                  <span className="text-green-400 text-lg font-bold">
                    ${parseFloat(q.total_price || 0).toFixed(2)}
                  </span>
                </div>
              </div>
            </div>

            {/* Customer */}
            <div className="bg-gray-800 rounded-lg p-4">
              <h4 className="text-sm font-medium text-gray-300 mb-3">Customer</h4>
              <div className="text-sm">
                <p className="text-white">{q.customer_name || "No name"}</p>
                <p className="text-gray-400">{q.customer_email || "No email"}</p>
                {q.customer_id && (
                  <p className="text-blue-400 text-xs mt-1">Linked to Customer #{q.customer_id}</p>
                )}
              </div>
            </div>

            {/* Product Image */}
            <div className="bg-gray-800 rounded-lg p-4">
              <h4 className="text-sm font-medium text-gray-300 mb-3">Product Image</h4>
              {imageUrl ? (
                <div className="space-y-3">
                  <img
                    src={imageUrl}
                    alt="Product"
                    className="max-h-48 rounded-lg object-contain bg-gray-900"
                    onError={() => setImageUrl(null)}
                  />
                  <div className="flex gap-2">
                    <label className="px-3 py-1.5 text-sm bg-gray-700 text-white rounded cursor-pointer hover:bg-gray-600">
                      Replace
                      <input
                        type="file"
                        accept="image/*"
                        onChange={handleImageUpload}
                        className="hidden"
                        disabled={uploadingImage}
                      />
                    </label>
                    <button
                      onClick={handleImageDelete}
                      className="px-3 py-1.5 text-sm bg-red-600/20 text-red-400 rounded hover:bg-red-600/30"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ) : (
                <div className="border-2 border-dashed border-gray-700 rounded-lg p-4 text-center">
                  <label className="cursor-pointer">
                    <div className="text-gray-400 mb-2">
                      {uploadingImage ? (
                        "Uploading..."
                      ) : (
                        <>
                          <svg className="w-8 h-8 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                          </svg>
                          Click to upload product image
                        </>
                      )}
                    </div>
                    <input
                      type="file"
                      accept="image/*"
                      onChange={handleImageUpload}
                      className="hidden"
                      disabled={uploadingImage}
                    />
                    <span className="text-xs text-gray-500">PNG, JPG, WebP up to 5MB</span>
                  </label>
                </div>
              )}
            </div>

            {/* Validity */}
            <div className="bg-gray-800 rounded-lg p-4">
              <h4 className="text-sm font-medium text-gray-300 mb-2">Validity</h4>
              <p className={`text-sm ${isExpired ? "text-red-400" : "text-white"}`}>
                {isExpired ? "Expired on " : "Valid until "}
                {new Date(q.expires_at).toLocaleDateString()}
              </p>
            </div>

            {/* Notes */}
            {(q.customer_notes || q.admin_notes) && (
              <div className="bg-gray-800 rounded-lg p-4">
                <h4 className="text-sm font-medium text-gray-300 mb-2">Notes</h4>
                {q.customer_notes && (
                  <p className="text-sm text-white mb-2">
                    <span className="text-gray-400">Customer: </span>
                    {q.customer_notes}
                  </p>
                )}
                {q.admin_notes && (
                  <p className="text-sm text-white">
                    <span className="text-gray-400">Internal: </span>
                    {q.admin_notes}
                  </p>
                )}
              </div>
            )}

            {/* Linked Order */}
            {q.sales_order_id && (
              <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
                <p className="text-green-400 text-sm">
                  Converted to Order #{q.sales_order_id}
                  {q.converted_at && ` on ${new Date(q.converted_at).toLocaleDateString()}`}
                </p>
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="mt-6 pt-4 border-t border-gray-700 space-y-3">
            {/* Primary Actions */}
            <div className="flex flex-wrap gap-2">
              {q.status === "pending" && (
                <>
                  <button
                    onClick={() => onUpdateStatus(quote.id, "approved")}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => {
                      const reason = prompt("Rejection reason:");
                      if (reason !== null) {
                        onUpdateStatus(quote.id, "rejected", reason);
                      }
                    }}
                    className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
                  >
                    Reject
                  </button>
                </>
              )}

              {q.status === "approved" && (
                <button
                  onClick={() => onUpdateStatus(quote.id, "accepted")}
                  className="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-700"
                >
                  Mark as Accepted
                </button>
              )}

              {canConvert && (
                <button
                  onClick={() => onConvert(quote.id)}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center gap-2"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                  </svg>
                  Convert to Order
                </button>
              )}
            </div>

            {/* Secondary Actions */}
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => onPrintPDF(quote)}
                className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
                </svg>
                Print
              </button>
              <button
                onClick={() => onDownloadPDF(quote)}
                className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Download PDF
              </button>
              <button
                onClick={() => onCopyLink(quote)}
                className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                Copy Link
              </button>
              <button
                onClick={() => onDuplicate(quote)}
                className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2" />
                </svg>
                Duplicate
              </button>

              {q.status !== "converted" && (
                <>
                  <button
                    onClick={onEdit}
                    className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 flex items-center gap-2"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                    Edit
                  </button>
                  <button
                    onClick={() => onDelete(quote.id)}
                    className="px-4 py-2 bg-red-600/20 text-red-400 rounded-lg hover:bg-red-600/30 flex items-center gap-2"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                    Delete
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
