import React, { useState } from "react";
import { useToast } from "./Toast";
import { API_URL } from "../config/api";

const ExportImport = ({ type }) => {
  const toast = useToast();
  const [importing, setImporting] = useState(false);
  const [_file, setFile] = useState(null); // Used via setFile in file input
  const [result, setResult] = useState(null);

  const handleExport = async () => {
    try {
      const response = await fetch(`${API_URL}/api/v1/admin/export/${type}`, {
        credentials: "include",
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${type}_export_${
          new Date().toISOString().split("T")[0]
        }.csv`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      }
    } catch (error) {
      toast.error(
        `Export failed: ${error.message || "Unknown error. Please try again."}`
      );
    }
  };

  const handleImport = async (e) => {
    const selectedFile = e.target.files[0];
    if (!selectedFile) return;

    setImporting(true);
    setFile(selectedFile);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await fetch(`${API_URL}/api/v1/admin/import/${type}`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });

      const data = await response.json();
      setResult(data);
    } catch (error) {
      setResult({ errors: [error.message] });
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-4">
        <button
          onClick={handleExport}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded"
        >
          Export {type} to CSV
        </button>

        <label className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded cursor-pointer inline-block">
          {importing ? "Importing..." : `Import ${type} from CSV`}
          <input
            type="file"
            accept=".csv"
            onChange={handleImport}
            className="hidden"
            disabled={importing}
          />
        </label>
      </div>

      {result && (
        <div
          className={`p-4 rounded ${
            result.errors?.length > 0 ? "bg-red-900" : "bg-green-900"
          }`}
        >
          <div className="text-white">
            <div>Created: {result.created || 0}</div>
            <div>Updated: {result.updated || 0}</div>
            {result.errors?.length > 0 && (
              <div className="mt-2">
                <div className="font-bold">Errors:</div>
                <ul className="list-disc list-inside">
                  {result.errors.map((error, idx) => (
                    <li key={idx} className="text-sm">
                      {error}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ExportImport;
