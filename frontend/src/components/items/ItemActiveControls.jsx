/**
 * ItemActiveControls - Deactivate / Reactivate controls for the item edit form.
 *
 * Deactivate calls the soft-delete endpoint (DELETE /api/v1/items/:id), which
 * refuses items with stock on hand or active BOMs; the server's reason is
 * shown inline. Reactivate PATCHes `active: true`. The response body is never
 * parsed on success (DELETE may return JSON or nothing); errors are read
 * defensively for the same reason.
 */
import { useState } from "react";
import { API_URL } from "../../config/api";
import ConfirmDialog from "../ConfirmDialog";

async function errorMessage(res, fallback) {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
  } catch {
    // empty or non-JSON body
  }
  return fallback;
}

export default function ItemActiveControls({ item, onChanged }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (!item?.id) return null;
  const isInactive = item.active === false;

  const run = async (request, failure, nextActive) => {
    setBusy(true);
    setError(null);
    try {
      const res = await request();
      if (!res.ok) throw new Error(await errorMessage(res, failure));
      setConfirming(false);
      onChanged?.({ ...item, active: nextActive });
    } catch (err) {
      setConfirming(false);
      setError(err.message || failure);
    } finally {
      setBusy(false);
    }
  };

  const deactivate = () =>
    run(
      () =>
        fetch(`${API_URL}/api/v1/items/${item.id}`, {
          method: "DELETE",
          credentials: "include",
        }),
      "Failed to deactivate item",
      false
    );

  const reactivate = () =>
    run(
      () =>
        fetch(`${API_URL}/api/v1/items/${item.id}`, {
          method: "PATCH",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ active: true }),
        }),
      "Failed to reactivate item",
      true
    );

  return (
    <div className="mb-4 space-y-2">
      {isInactive && (
        <div
          role="status"
          className="flex items-center justify-between gap-3 rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-300"
        >
          <span>
            <strong>Inactive.</strong> This item is hidden from the default
            Items list.
          </span>
          <button
            type="button"
            onClick={reactivate}
            disabled={busy}
            className="rounded-lg bg-green-600 px-3 py-1.5 font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            {busy ? "Reactivating..." : "Reactivate"}
          </button>
        </div>
      )}
      {!isInactive && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => setConfirming(true)}
            disabled={busy}
            className="rounded-lg border border-red-500/40 px-3 py-1.5 text-sm text-red-400 hover:bg-red-500/10 disabled:opacity-50"
          >
            Deactivate
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-400">
          {error}
        </p>
      )}
      <ConfirmDialog
        isOpen={confirming}
        title="Deactivate Item"
        message={`Deactivate ${item.sku || "this item"}? It will be hidden from the default Items list. You can reactivate it later.`}
        confirmLabel="Deactivate"
        confirmVariant="danger"
        isLoading={busy}
        onConfirm={deactivate}
        onCancel={() => setConfirming(false)}
      />
    </div>
  );
}
