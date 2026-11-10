/**
 * ItemFormLoadState - what the item edit form shows until the item has loaded.
 *
 * There is no form here on purpose: until the full item is in, the form would
 * hold a partial copy of it, and saving that would overwrite stored values.
 * When the load fails the user can try again or close; there is nothing to save.
 */
import Modal from "../Modal";

export default function ItemFormLoadState({ isOpen, onClose, status, onRetry }) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Edit Item"
      className="w-full max-w-2xl max-h-[90vh] overflow-y-auto"
    >
      <div className="p-6">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-white">Edit Item</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-gray-400 hover:text-white"
          >
            ✕
          </button>
        </div>

        {status === "error" ? (
          <div
            role="alert"
            className="p-3 bg-red-500/10 border border-red-500/30 text-red-400 rounded-xl"
          >
            <p>Could not load this item, so it cannot be edited right now. Nothing was changed.</p>
            <div className="flex gap-3 mt-3">
              <button
                type="button"
                onClick={onRetry}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700"
              >
                Try again
              </button>
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-300 hover:bg-gray-700"
              >
                Close
              </button>
            </div>
          </div>
        ) : (
          <p role="status" className="text-gray-400">
            Loading item…
          </p>
        )}
      </div>
    </Modal>
  );
}
