import { Link } from "react-router-dom";
import Modal from "../../../components/Modal";

export function LinkPrinterModal({
  linking,
  machine,
  printers,
  selectedPrinterId,
  onClose,
  onPrinterChange,
  onSubmit,
}) {
  return (
    <Modal
      isOpen={Boolean(machine)}
      onClose={onClose}
      title="Link Printer"
      className="w-full max-w-lg"
      disableClose={linking}
    >
      {machine && (
        <form onSubmit={onSubmit} className="p-6 space-y-5">
          <div>
            <h2 className="text-lg font-semibold text-white">Link Printer</h2>
            <p className="text-sm text-gray-400 mt-1">
              Link {machine.name} to one existing FilaOps printer.
            </p>
          </div>

          {printers.length === 0 ? (
            <div className="bg-gray-800/60 border border-gray-700 rounded-md p-4">
              <p className="text-sm text-gray-300">
                Create a FilaOps printer before linking Bambuddy machines.
              </p>
              <Link
                to="/admin/printers"
                className="inline-flex mt-3 text-sm text-blue-400 hover:text-blue-300"
              >
                Create printer first
              </Link>
            </div>
          ) : (
            <label className="block">
              <span className="text-sm font-medium text-gray-300">FilaOps printer</span>
              <select
                value={selectedPrinterId}
                onChange={(event) => onPrinterChange(event.target.value)}
                className="mt-1 w-full bg-gray-950 border border-gray-700 rounded-md px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
              >
                <option value="">Select a printer</option>
                {printers.map((printer) => (
                  <option key={printer.id} value={printer.id}>
                    {printer.name} {printer.code ? `(${printer.code})` : ""}
                  </option>
                ))}
              </select>
            </label>
          )}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={linking}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:text-gray-500 text-white rounded-md text-sm font-medium"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={linking || printers.length === 0 || !selectedPrinterId}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-400 text-white rounded-md text-sm font-medium"
            >
              {linking ? "Linking..." : "Link Printer"}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}
