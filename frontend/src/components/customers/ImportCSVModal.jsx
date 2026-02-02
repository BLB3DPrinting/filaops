/**
 * ImportCSVModal - CSV import with drag-drop, preview, and batch import.
 *
 * Extracted from AdminCustomers.jsx (ARCHITECT-002)
 */
import { useState } from "react";
import { API_URL } from "../../config/api";
import Modal from "../Modal";

export default function ImportCSVModal({ onClose, onImportComplete }) {
  const token = localStorage.getItem("adminToken");
  const [step, setStep] = useState("upload"); // upload, preview, importing, complete
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleFile = async (selectedFile) => {
    if (!selectedFile.name.endsWith(".csv")) {
      setError("Please select a CSV file");
      return;
    }
    setFile(selectedFile);
    setError(null);

    // Preview the file
    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const res = await fetch(`${API_URL}/api/v1/admin/customers/import/preview`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to preview file");
      }

      const data = await res.json();
      setPreview(data);
      setStep("preview");
    } catch (err) {
      setError(err.message);
    }
  };

  const handleImport = async () => {
    if (!file) return;
    setImporting(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_URL}/api/v1/admin/customers/import`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Import failed");
      }

      const data = await res.json();
      setResult(data);
      setStep("complete");
    } catch (err) {
      setError(err.message);
    } finally {
      setImporting(false);
    }
  };

  const downloadTemplate = () => {
    window.open(`${API_URL}/api/v1/admin/customers/import/template`, "_blank");
  };

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title="Import Customers from CSV"
      className="w-full max-w-4xl max-h-[90vh] overflow-auto"
      disableClose={importing}
    >
      <div className="p-6 border-b border-gray-800 flex justify-between items-center">
        <h2 className="text-xl font-bold text-white">Import Customers from CSV</h2>
        <button onClick={onClose} className="text-gray-400 hover:text-white">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="p-6">
          {/* Upload Step */}
          {step === "upload" && (
            <div className="space-y-6">
              <div className="flex justify-between items-center">
                <p className="text-gray-400">Upload a CSV file with your customer data</p>
                <button
                  onClick={downloadTemplate}
                  className="text-blue-400 hover:text-blue-300 text-sm flex items-center gap-1"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Download Template
                </button>
              </div>

              {/* Drag & Drop Zone */}
              <div
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                className={`border-2 border-dashed rounded-xl p-12 text-center transition-colors ${
                  dragActive
                    ? "border-blue-500 bg-blue-500/10"
                    : "border-gray-700 hover:border-gray-600"
                }`}
              >
                <svg className="w-12 h-12 mx-auto text-gray-500 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p className="text-gray-400 mb-2">Drag and drop your CSV file here, or</p>
                <label className="cursor-pointer">
                  <span className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-300 hover:bg-gray-700 hover:text-white inline-block">
                    Browse Files
                  </span>
                  <input
                    type="file"
                    accept=".csv"
                    onChange={(e) => e.target.files[0] && handleFile(e.target.files[0])}
                    className="hidden"
                  />
                </label>
              </div>

              {/* Expected Format */}
              <div className="bg-gray-800/50 rounded-lg p-4">
                <h3 className="text-sm font-medium text-gray-300 mb-2">Supported Formats:</h3>
                <p className="text-xs text-gray-400 mb-2">
                  Automatically detects exports from <span className="text-blue-400">Shopify</span>,{" "}
                  <span className="text-purple-400">WooCommerce</span>,{" "}
                  <span className="text-orange-400">Squarespace</span>,{" "}
                  <span className="text-green-400">Etsy</span>, and generic CSV files.
                </p>
                <p className="text-xs text-gray-500 font-mono">
                  Required: email • Optional: first_name, last_name, company, phone, address fields
                </p>
              </div>

              {error && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
                  {error}
                </div>
              )}
            </div>
          )}

          {/* Preview Step */}
          {step === "preview" && preview && (
            <div className="space-y-6">
              {/* Detected Format */}
              {preview.detected_format && (
                <div className="bg-gray-800/50 rounded-lg px-4 py-2 flex items-center gap-2">
                  <span className="text-gray-400 text-sm">Detected format:</span>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    preview.detected_format === "Shopify" ? "bg-blue-500/20 text-blue-400" :
                    preview.detected_format === "WooCommerce" ? "bg-purple-500/20 text-purple-400" :
                    preview.detected_format === "Etsy" ? "bg-green-500/20 text-green-400" :
                    preview.detected_format === "Generic/Squarespace" ? "bg-orange-500/20 text-orange-400" :
                    "bg-gray-500/20 text-gray-400"
                  }`}>
                    {preview.detected_format}
                  </span>
                </div>
              )}

              {/* Summary */}
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-gray-800/50 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-white">{preview.total_rows}</p>
                  <p className="text-sm text-gray-400">Total Rows</p>
                </div>
                <div className="bg-gray-800/50 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-green-400">{preview.valid_rows}</p>
                  <p className="text-sm text-gray-400">Valid</p>
                </div>
                <div className="bg-gray-800/50 rounded-lg p-4 text-center">
                  <p className="text-2xl font-bold text-red-400">{preview.error_rows}</p>
                  <p className="text-sm text-gray-400">Errors</p>
                </div>
              </div>

              {preview.truncated && (
                <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3 text-yellow-400 text-sm">
                  Showing first 100 rows. Full file contains {preview.total_rows} rows.
                </div>
              )}

              {/* Preview Table */}
              <div className="bg-gray-800/30 rounded-lg overflow-hidden">
                <div className="overflow-x-auto max-h-80">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-800 sticky top-0">
                      <tr>
                        <th className="text-left py-2 px-3 text-gray-400">Row</th>
                        <th className="text-left py-2 px-3 text-gray-400">Status</th>
                        <th className="text-left py-2 px-3 text-gray-400">Email</th>
                        <th className="text-left py-2 px-3 text-gray-400">Name</th>
                        <th className="text-left py-2 px-3 text-gray-400">Company</th>
                        <th className="text-left py-2 px-3 text-gray-400">Errors</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.map((row) => (
                        <tr
                          key={row.row_number}
                          className={`border-t border-gray-700 ${!row.valid ? "bg-red-500/5" : ""}`}
                        >
                          <td className="py-2 px-3 text-gray-500">{row.row_number}</td>
                          <td className="py-2 px-3">
                            {row.valid ? (
                              <span className="text-green-400">✓</span>
                            ) : (
                              <span className="text-red-400">✗</span>
                            )}
                          </td>
                          <td className="py-2 px-3 text-white">{row.data.email || "-"}</td>
                          <td className="py-2 px-3 text-gray-300">
                            {row.data.first_name} {row.data.last_name}
                          </td>
                          <td className="py-2 px-3 text-gray-400">{row.data.company_name || "-"}</td>
                          <td className="py-2 px-3 text-red-400 text-xs">
                            {row.errors.join(", ")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {error && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
                  {error}
                </div>
              )}

              {/* Actions */}
              <div className="flex justify-between">
                <button
                  onClick={() => {
                    setStep("upload");
                    setFile(null);
                    setPreview(null);
                  }}
                  className="px-4 py-2 text-gray-400 hover:text-white"
                >
                  ← Back
                </button>
                <button
                  onClick={handleImport}
                  disabled={importing || preview.valid_rows === 0}
                  className="px-6 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {importing ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      Importing...
                    </>
                  ) : (
                    `Import ${preview.valid_rows} Customers`
                  )}
                </button>
              </div>
            </div>
          )}

          {/* Complete Step */}
          {step === "complete" && result && (
            <div className="text-center py-8 space-y-6">
              <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center mx-auto">
                <svg className="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h3 className="text-xl font-bold text-white">Import Complete!</h3>
              <div className="grid grid-cols-2 gap-4 max-w-xs mx-auto">
                <div className="bg-gray-800/50 rounded-lg p-4">
                  <p className="text-2xl font-bold text-green-400">{result.imported}</p>
                  <p className="text-sm text-gray-400">Imported</p>
                </div>
                <div className="bg-gray-800/50 rounded-lg p-4">
                  <p className="text-2xl font-bold text-gray-400">{result.skipped}</p>
                  <p className="text-sm text-gray-400">Skipped</p>
                </div>
              </div>
              {result.errors && result.errors.length > 0 && (
                <div className="bg-gray-800/50 rounded-lg p-4 text-left max-w-md mx-auto">
                  <p className="text-sm text-gray-400 mb-2">Skipped rows:</p>
                  <ul className="text-xs text-gray-500 space-y-1">
                    {result.errors.slice(0, 5).map((err, i) => (
                      <li key={i}>Row {err.row}: {err.reason}</li>
                    ))}
                    {result.errors.length > 5 && (
                      <li>...and {result.errors.length - 5} more</li>
                    )}
                  </ul>
                </div>
              )}
              <button
                onClick={onImportComplete}
                className="px-6 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500"
              >
                Done
              </button>
            </div>
          )}
      </div>
    </Modal>
  );
}
