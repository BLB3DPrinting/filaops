import { useEffect, useState } from "react";
import { useApi } from "../../../hooks/useApi";
import { useToast } from "../../../components/Toast";
import Modal from "../../../components/Modal";
import { BATCH_API, formatMinutes } from "./printBatchHelpers";

// ---------------------------------------------------------------------------
// Pick a saved plate composition (FilaOps PRO, print batches S9).
//
// A saved composition (a vendor plate, a customer's quote plate, or a plate
// an operator uploaded before) is printed as it is: its file is never
// re-sliced, so it books only on its own printer model and nozzle. Choosing
// one shows how PRO would fill it from open orders (most urgent first; an
// order bigger than the plate is split) and the stock top-ups that make up
// the rest. "Make batch" creates it. A one-part plate can instead run once
// per plate-load of an order ("Run for an order"): the order is split into
// one order per run and each run is its own batch.
// ---------------------------------------------------------------------------

function itemsSummary(version) {
  return (version?.items || []).map((i) => `${i.quantity}× ${i.name || i.sku || `part ${i.product_id}`}`).join(", ");
}

export default function CompositionPicker({ isOpen, onClose, printerModel, onCreated }) {
  const api = useApi();
  const toast = useToast();
  const [compositions, setCompositions] = useState([]);
  const [chosen, setChosen] = useState(null);
  const [plan, setPlan] = useState(null);
  const [orders, setOrders] = useState([]);
  const [runOp, setRunOp] = useState("");
  const [runs, setRuns] = useState("");
  const [busy, setBusy] = useState(false);

  // Mounted when opened (the composer renders it only then), so state starts fresh.
  useEffect(() => {
    if (!isOpen) return;
    const query = printerModel ? `?printer_model=${encodeURIComponent(printerModel)}` : "";
    api
      .get(`/api/v1/pro/compositions${query}`)
      .then((data) => setCompositions(data?.compositions || []))
      .catch((err) => toast.error(err?.message || "Could not load compositions"));
  }, [isOpen, printerModel, api, toast]);

  const choose = async (composition) => {
    setChosen(composition);
    setPlan(null);
    setRunOp("");
    setRuns("");
    const version = composition.current_version;
    try {
      setPlan(await api.post(`${BATCH_API}/from-composition`, { composition_version_id: version.id, preview: true }));
      if (version.items.length === 1) {
        const data = await api.get(`${BATCH_API}/candidates`);
        setOrders((data?.candidates || []).filter((c) => c.product.id === version.items[0].product_id));
      } else {
        setOrders([]);
      }
    } catch (err) {
      toast.error(err?.message || "Could not plan this composition");
    }
  };

  const makeBatch = async () => {
    setBusy(true);
    try {
      const batch = await api.post(
        `${BATCH_API}/from-composition`,
        { composition_version_id: chosen.current_version.id, preview: false },
        { retry: 0 },
      );
      toast.success(`${batch.code} composed from ${chosen.code}`);
      onCreated?.(batch);
      onClose();
    } catch (err) {
      toast.error(err?.message || "Could not make the batch");
    } finally {
      setBusy(false);
    }
  };

  const runForOrder = async () => {
    setBusy(true);
    try {
      const body = {
        plates: [{ composition_version_id: chosen.current_version.id, operation_id: Number(runOp) }],
        ...(runs ? { runs: Number(runs) } : {}),
      };
      const result = await api.post(`${BATCH_API}/repeat`, body, { retry: 0 });
      toast.success(`${result.batches.length} batches made (${result.runs} runs)`);
      onCreated?.(result.batches[0]);
      onClose();
    } catch (err) {
      toast.error(err?.message || "Could not run this plate for the order");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Use a saved composition" className="w-full max-w-3xl">
      <div className="p-6 space-y-4 text-sm">
        {compositions.length === 0 && (
          <p className="text-gray-400">No saved compositions{printerModel ? ` for the ${printerModel}` : ""} yet.</p>
        )}
        <ul className="max-h-64 overflow-y-auto divide-y divide-gray-800">
          {compositions.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => choose(c)}
                className={`w-full text-left px-3 py-2 hover:bg-gray-800 ${chosen?.id === c.id ? "bg-gray-800" : ""}`}
              >
                <span className="text-white font-medium">{c.code}</span>{" "}
                <span className="text-gray-400">v{c.current_version?.version} · {c.printer_model || "model?"}</span>
                {c.verbatim && <span className="ml-2 text-xs text-amber-300">sent as it is</span>}
                <div className="text-gray-400">
                  {itemsSummary(c.current_version)} · {formatMinutes(c.current_version?.plate_time_minutes)}
                </div>
              </button>
            </li>
          ))}
        </ul>
        {plan && (
          <div className="bg-gray-800/60 rounded p-3 space-y-2">
            <div className="text-gray-300">
              {plan.code} v{plan.version}: books only on a {plan.printer_model}
              {plan.nozzle ? ` with a ${plan.nozzle} mm nozzle` : ""}.
            </div>
            {plan.parts.map((part) => (
              <div key={part.product_id} className="text-gray-300">
                Part {part.product_id}: the plate holds {part.plate_holds}.{" "}
                {part.takes.map((t) => `${t.order_code} × ${t.quantity}${t.splits_order ? " (split)" : ""}`).join(", ") ||
                  "No open orders."}
                {part.topup > 0 && <span className="text-amber-300"> Top-up for stock: {part.topup}.</span>}
              </div>
            ))}
            <button
              type="button"
              disabled={busy}
              onClick={makeBatch}
              className="px-4 py-2 rounded bg-blue-600 text-white disabled:opacity-50"
            >
              Make batch
            </button>
          </div>
        )}
        {plan && orders.length > 0 && (
          <div className="bg-gray-800/60 rounded p-3 space-y-2">
            <div className="text-gray-300">Run this plate for an order (one batch per plate-load):</div>
            <div className="flex gap-2 items-center">
              <select
                value={runOp}
                onChange={(e) => setRunOp(e.target.value)}
                aria-label="Order to run"
                className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-white"
              >
                <option value="">Choose an order</option>
                {orders.map((o) => (
                  <option key={o.operation_id} value={o.operation_id}>
                    {o.order_code} — {o.quantity} to make
                  </option>
                ))}
              </select>
              <input
                type="number"
                min="1"
                placeholder="all runs"
                aria-label="Runs"
                value={runs}
                onChange={(e) => setRuns(e.target.value)}
                className="w-24 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-white"
              />
              <button
                type="button"
                disabled={busy || !runOp}
                onClick={runForOrder}
                className="px-3 py-1 rounded bg-gray-700 text-white disabled:opacity-50"
              >
                Run for order
              </button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
