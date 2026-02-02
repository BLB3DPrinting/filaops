/**
 * PrinterSetupModal - Printer setup wizard with work center selection and enterprise upsell.
 */
import { useState } from "react";

export default function PrinterSetupModal({ workCenters, onClose, onAddPrinter }) {
  const [selectedWorkCenter, setSelectedWorkCenter] = useState("");

  // Filter to only show Machine Pool type work centers
  const machineWorkCenters = workCenters.filter(
    (wc) => wc.center_type === "machine"
  );

  const handleAddPrinter = () => {
    const wc = workCenters.find((w) => w.id === parseInt(selectedWorkCenter));
    if (wc) {
      onAddPrinter(wc);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-lg border border-gray-700 w-full max-w-lg">
        <div className="p-6 border-b border-gray-800">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <svg
              className="w-6 h-6 text-purple-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"
              />
            </svg>
            Printer Setup
          </h2>
          <p className="text-sm text-gray-400 mt-1">
            Add printers and machines to your work centers for scheduling
          </p>
        </div>

        <div className="p-6 space-y-6">
          {/* Enterprise upsell banner */}
          <div className="bg-gradient-to-r from-purple-900/30 to-blue-900/30 border border-purple-500/30 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-purple-500/20 rounded-lg">
                <svg
                  className="w-5 h-5 text-purple-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13 10V3L4 14h7v7l9-11h-7z"
                  />
                </svg>
              </div>
              <div>
                <h3 className="text-sm font-medium text-purple-300">
                  Automatic Printer Sync
                </h3>
                <p className="text-xs text-gray-400 mt-1">
                  FilaOps Enterprise integrates directly with Bambu Cloud to
                  auto-sync your printers, monitor status, and track jobs in
                  real-time.
                </p>
                <a
                  href="https://filaops.com/enterprise"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-purple-400 hover:text-purple-300 mt-2 inline-block"
                >
                  Learn more →
                </a>
              </div>
            </div>
          </div>

          {/* Manual setup section */}
          <div>
            <h3 className="text-sm font-medium text-white mb-3">
              Manual Setup
            </h3>
            <p className="text-sm text-gray-400 mb-4">
              Select a work center to add a printer or machine:
            </p>

            {machineWorkCenters.length === 0 ? (
              <div className="text-center py-6 bg-gray-800/50 rounded-lg border border-gray-700">
                <p className="text-gray-400 text-sm">
                  No Machine Pool work centers found.
                </p>
                <p className="text-gray-500 text-xs mt-1">
                  Create a work center with type "Machine Pool" first.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                <select
                  value={selectedWorkCenter}
                  onChange={(e) => setSelectedWorkCenter(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-purple-500"
                >
                  <option value="">Select a work center...</option>
                  {machineWorkCenters.map((wc) => (
                    <option key={wc.id} value={wc.id}>
                      {wc.code} - {wc.name}
                    </option>
                  ))}
                </select>

                <button
                  onClick={handleAddPrinter}
                  disabled={!selectedWorkCenter}
                  className="w-full bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:text-gray-500 text-white px-4 py-2 rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 4v16m8-8H4"
                    />
                  </svg>
                  Add Printer to Work Center
                </button>
              </div>
            )}
          </div>

          {/* Quick tip */}
          <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700">
            <p className="text-xs text-gray-400">
              <span className="text-blue-400 font-medium">Tip:</span> You can
              also add printers by clicking on a work center card and selecting
              "Add Resource".
            </p>
          </div>
        </div>

        <div className="p-6 border-t border-gray-800">
          <button
            onClick={onClose}
            className="w-full px-4 py-2 text-gray-400 hover:text-white border border-gray-700 rounded-lg transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
