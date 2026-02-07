import { useState } from "react";
import { API_URL } from "../../config/api";

export default function AdminMaterialImport() {
  const [step, setStep] = useState("upload"); // upload, importing, complete
  const [file, setFile] = useState(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [updateExisting, setUpdateExisting] = useState(false);
  const [importCategories, setImportCategories] = useState(true);

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

  const handleFile = (selectedFile) => {
    if (!selectedFile.name.endsWith(".csv")) {
      setError("Please select a CSV file");
      return;
    }
    setFile(selectedFile);
    setError(null);
    setResult(null);
  };

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0]);
    }
  };

  const downloadTemplate = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/materials/import/template`, {
        credentials: "include",
      });

      if (!res.ok) {
        throw new Error("Failed to download template");
      }

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "material_inventory_template.csv";
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError(err.message || "Failed to download template");
    }
  };

  const handleImport = async () => {
    if (!file) {
      setError("Please select a file first");
      return;
    }

    setImporting(true);
    setError(null);
    setStep("importing");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const params = new URLSearchParams();
      if (updateExisting) {
        params.set("update_existing", "true");
      }
      params.set("import_categories", importCategories ? "true" : "false");

      const url = `${API_URL}/api/v1/materials/import?${params}`;
      
      const res = await fetch(url, {
        method: "POST",
        credentials: "include",
        body: formData,
      });

      if (!res.ok) {
        let errorMessage = "Import failed";
        try {
          const errorData = await res.json();
          errorMessage = errorData.detail || errorData.message || errorMessage;
        } catch {
          errorMessage = `Server error: ${res.status} ${res.statusText}`;
        }
        throw new Error(errorMessage);
      }

      const data = await res.json();

      setResult(data);
      setStep("complete");
    } catch (err) {
      if (err.message === "Failed to fetch") {
        setError("Cannot connect to server. Please ensure the backend is running and check the browser console for details.");
      } else {
        setError(err.message || "Import failed");
      }
      setStep("upload");
    } finally {
      setImporting(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setResult(null);
    setError(null);
    setStep("upload");
    setUpdateExisting(false);
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Import Material Inventory</h1>
          <p className="text-gray-400">
            Import your material inventory from CSV. This will create material types, colors, products, and inventory records.
          </p>
        </div>

        {/* Template Download */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold mb-2">Need a Template?</h2>
              <p className="text-gray-400 text-sm">
                Download our CSV template to see the required format. Fill it with your material data and upload it here.
              </p>
            </div>
            <button
              onClick={downloadTemplate}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-medium transition-colors"
            >
              Download Template
            </button>
          </div>
        </div>

        {/* Upload Section */}
        {step === "upload" && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <h2 className="text-xl font-semibold mb-4">Upload CSV File</h2>

            {/* Drag and Drop Area */}
            <div
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-lg p-12 text-center transition-colors ${
                dragActive
                  ? "border-blue-500 bg-blue-500/10"
                  : "border-gray-700 hover:border-gray-600"
              }`}
            >
              {file ? (
                <div className="space-y-4">
                  <div className="text-green-400">
                    <svg
                      className="w-16 h-16 mx-auto mb-4"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    <p className="text-lg font-medium">{file.name}</p>
                    <p className="text-sm text-gray-400 mt-2">
                      {(file.size / 1024).toFixed(2)} KB
                    </p>
                  </div>
                  <button
                    onClick={() => setFile(null)}
                    className="text-gray-400 hover:text-white text-sm"
                  >
                    Remove file
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  <svg
                    className="w-16 h-16 mx-auto text-gray-500"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                    />
                  </svg>
                  <div>
                    <p className="text-lg font-medium mb-2">
                      Drag and drop your CSV file here
                    </p>
                    <p className="text-gray-400 text-sm">or</p>
                  </div>
                  <label className="inline-block bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-medium cursor-pointer transition-colors">
                    Browse Files
                    <input
                      type="file"
                      accept=".csv"
                      onChange={handleFileInput}
                      className="hidden"
                    />
                  </label>
                </div>
              )}
            </div>

            {/* Options */}
            {file && (
              <div className="mt-6 space-y-4">
                <label className="flex items-center space-x-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={updateExisting}
                    onChange={(e) => setUpdateExisting(e.target.checked)}
                    className="w-5 h-5 rounded border-gray-600 bg-gray-800 text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-gray-300">
                    Update existing materials if SKU already exists
                  </span>
                </label>

                <label className="flex items-center space-x-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={importCategories}
                    onChange={(e) => setImportCategories(e.target.checked)}
                    className="w-5 h-5 rounded border-gray-600 bg-gray-800 text-blue-600 focus:ring-blue-500"
                  />
                  <div>
                    <span className="text-gray-300">
                      Import categories from CSV
                    </span>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Creates categories nested under "Filament" (e.g., Filament → PLA Matte)
                    </p>
                  </div>
                </label>

                <button
                  onClick={handleImport}
                  disabled={!file || importing}
                  className="w-full bg-green-600 hover:bg-green-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white px-6 py-3 rounded-lg font-medium transition-colors"
                >
                  {importing ? "Importing..." : "Import Materials"}
                </button>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="mt-4 bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
                {error}
              </div>
            )}
          </div>
        )}

        {/* Importing */}
        {step === "importing" && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-12 text-center">
            <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-500 mx-auto mb-4"></div>
            <p className="text-xl font-medium">Importing materials...</p>
            <p className="text-gray-400 mt-2">This may take a moment for large files</p>
          </div>
        )}

        {/* Results */}
        {step === "complete" && result && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold">Import Complete</h2>
              <button
                onClick={handleReset}
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm"
              >
                Import Another File
              </button>
            </div>

            {/* Summary Stats */}
            <div className="grid grid-cols-4 gap-4 mb-6">
              <div className="bg-gray-800 rounded-lg p-4">
                <p className="text-gray-400 text-sm mb-1">Total Rows</p>
                <p className="text-2xl font-bold text-white">{result.total_rows}</p>
              </div>
              <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
                <p className="text-green-400 text-sm mb-1">Created</p>
                <p className="text-2xl font-bold text-green-400">{result.created}</p>
              </div>
              <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
                <p className="text-blue-400 text-sm mb-1">Updated</p>
                <p className="text-2xl font-bold text-blue-400">{result.updated}</p>
              </div>
              <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4">
                <p className="text-yellow-400 text-sm mb-1">Skipped</p>
                <p className="text-2xl font-bold text-yellow-400">{result.skipped}</p>
              </div>
            </div>

            {/* Errors */}
            {result.errors && result.errors.length > 0 && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
                <h3 className="text-red-400 font-semibold mb-3">
                  Errors ({result.errors.length})
                </h3>
                <div className="max-h-64 overflow-y-auto space-y-2">
                  {result.errors.map((err, idx) => (
                    <div
                      key={idx}
                      className="bg-gray-800 rounded p-3 text-sm text-gray-300"
                    >
                      <div className="font-medium text-red-400">
                        Row {err.row}: {err.error}
                      </div>
                      {err.sku && (
                        <div className="text-gray-500 mt-1">SKU: {err.sku}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Success Message */}
            {result.errors.length === 0 && (
              <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4 text-green-400">
                <p className="font-medium">✓ All materials imported successfully!</p>
              </div>
            )}
          </div>
        )}

        {/* Instructions */}
        <div className="mt-6 bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h2 className="text-xl font-semibold mb-4">CSV Format Requirements</h2>
          <div className="space-y-3 text-gray-300 text-sm">
            <div>
              <p className="font-medium text-white mb-1">Required Columns:</p>
              <ul className="list-disc list-inside space-y-1 ml-4">
                <li><code className="bg-gray-800 px-2 py-1 rounded">SKU</code> - Product SKU (e.g., MAT-FDM-PLA-MATTE-CHAR)</li>
                <li><code className="bg-gray-800 px-2 py-1 rounded">Material Type</code> - Material type code (e.g., PLA_MATTE, PLA_BASIC)</li>
                <li><code className="bg-gray-800 px-2 py-1 rounded">Material Color Name</code> - Color name (e.g., Charcoal, Red)</li>
              </ul>
            </div>
            <div>
              <p className="font-medium text-white mb-1">Optional Columns:</p>
              <ul className="list-disc list-inside space-y-1 ml-4">
                <li><code className="bg-gray-800 px-2 py-1 rounded">Category</code> - Category name (e.g., "PLA Matte", "PETG HF") - nested under Filament</li>
                <li><code className="bg-gray-800 px-2 py-1 rounded">Name</code> - Product name (auto-generated if not provided)</li>
                <li><code className="bg-gray-800 px-2 py-1 rounded">HEX Code</code> - Color hex code (e.g., #0C0C0C)</li>
                <li><code className="bg-gray-800 px-2 py-1 rounded">Price</code> - Price per kg (e.g., 19.99)</li>
                <li><code className="bg-gray-800 px-2 py-1 rounded">On Hand (g)</code> - Quantity in grams (converted to kg automatically)</li>
              </ul>
            </div>
            <div className="mt-4 p-4 bg-blue-500/10 border border-blue-500/30 rounded-lg">
              <p className="text-blue-400 text-xs">
                <strong>Tip:</strong> The system will automatically create material types and colors if they don't exist. 
                Material types will be created with default settings that you can update later.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

