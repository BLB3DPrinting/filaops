import { useEffect, useMemo, useState } from "react";
import { useApi } from "../../../hooks/useApi";
import { useToast } from "../../../components/Toast";
import Modal from "../../../components/Modal";
import { BATCH_API, partsOnPlate } from "./printBatchHelpers";

// ---------------------------------------------------------------------------
// Confirm a print batch's counts (FilaOps PRO, print batches S9).
//
// The plate is off the printer: the operator says, per part, how many came
// out good and how many are scrap (prefilled with the plan). PRO's
// POST /api/v1/pro/print-batches/{id}/complete then completes every member
// order in one transaction: scrap lands on stock top-ups first, the run's
// minutes are shared so the orders add up to the run, zero-good orders close
// as scrapped and short ones are accepted short unless kept open.
// "Preview" sends the same request with dry_run and changes nothing.
// FilaFarm (S10) opens this same modal when the printer finishes.
// ---------------------------------------------------------------------------

const OUTCOME_LABELS = {
  complete: "Order complete",
  accept_short: "Accepted short",
  stays_short: "Stays short",
  close_scrapped: "Closed as scrapped",
  continues: "Goes on to its next step",
};

/** Minutes since the plate started, as a suggestion for the run time. */
function minutesSince(start) {
  if (!start) return "";
  const ms = Date.now() - new Date(start).getTime();
  return ms > 0 ? String(Math.round(ms / 60000)) : "";
}

export default function ConfirmBatchCountsModal({ batch, isOpen, onClose, onCompleted }) {
  const api = useApi();
  const toast = useToast();
  const parts = useMemo(() => partsOnPlate(batch?.members), [batch]);
  // Mounted when opened, so the counts start from the plan (every piece good).
  const [counts, setCounts] = useState(() =>
    Object.fromEntries(parts.map((p) => [p.product_id, { good: p.planned, scrapped: 0 }])),
  );
  const [runMinutes, setRunMinutes] = useState(() =>
    batch?.actual_run_minutes != null ? String(batch.actual_run_minutes) : minutesSince(batch?.actual_start),
  );
  const [reason, setReason] = useState("");
  const [reasons, setReasons] = useState([]);
  const [acceptShort, setAcceptShort] = useState(true);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    api
      .get("/api/v1/production-orders/scrap-reasons")
      .then((data) => setReasons(data?.details || []))
      .catch(() => setReasons([]));
  }, [isOpen, api]);

  const setCount = (productId, field, value) => {
    const n = Math.max(0, parseInt(value, 10) || 0);
    setCounts((prev) => ({ ...prev, [productId]: { ...prev[productId], [field]: n } }));
    setPreview(null);
  };

  const problems = parts
    .filter((p) => {
      const c = counts[p.product_id];
      return !c || c.good + c.scrapped !== p.planned;
    })
    .map((p) => `${p.name}: good + scrapped must be ${p.planned}`);
  const anyScrap = parts.some((p) => (counts[p.product_id]?.scrapped || 0) > 0);
  if (anyScrap && !reason) problems.push("choose why pieces were scrapped");
  if (runMinutes === "" || Number(runMinutes) < 0) problems.push("enter the run time in minutes");

  const request = (dryRun) => ({
    dry_run: dryRun,
    run_minutes: Number(runMinutes),
    parts: parts.map((p) => ({ product_id: p.product_id, ...counts[p.product_id] })),
    scrap_reason: anyScrap ? reason : null,
    accept_short: acceptShort,
  });

  const submit = async (dryRun) => {
    if (problems.length) return;
    setBusy(true);
    try {
      const data = await api.post(`${BATCH_API}/${batch.id}/complete`, request(dryRun), { retry: 0 });
      if (dryRun) {
        setPreview(data);
      } else {
        toast.success(`${batch.code} confirmed`);
        onCompleted?.(data);
        onClose();
      }
    } catch (err) {
      toast.error(err?.message || "Could not confirm the counts");
    } finally {
      setBusy(false);
    }
  };

  if (!batch) return null;
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`Confirm counts: ${batch.code}`} className="w-full max-w-2xl">
      <div className="p-6 space-y-4 text-sm">
        <p className="text-gray-400">
          Count every piece on the plate as good or scrap. Scrap is taken from stock top-ups before
          orders for customers.
        </p>
        <table className="w-full">
          <thead className="text-gray-400 text-left">
            <tr>
              <th className="py-1">Part</th>
              <th className="py-1 w-20">Planned</th>
              <th className="py-1 w-24">Good</th>
              <th className="py-1 w-24">Scrapped</th>
            </tr>
          </thead>
          <tbody>
            {parts.map((p) => (
              <tr key={p.product_id} className="border-t border-gray-800">
                <td className="py-1 text-white">{p.name}</td>
                <td className="py-1 text-gray-300">{p.planned}</td>
                {["good", "scrapped"].map((field) => (
                  <td key={field} className="py-1">
                    <input
                      type="number"
                      min="0"
                      aria-label={`${p.name} ${field}`}
                      value={counts[p.product_id]?.[field] ?? 0}
                      onChange={(e) => setCount(p.product_id, field, e.target.value)}
                      className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white"
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="grid grid-cols-2 gap-4">
          <label className="block text-gray-300">
            Run time (minutes)
            <input
              type="number"
              min="0"
              value={runMinutes}
              onChange={(e) => { setRunMinutes(e.target.value); setPreview(null); }}
              className="mt-1 w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white"
            />
          </label>
          <label className="block text-gray-300">
            Scrap reason
            <select
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              disabled={!anyScrap}
              className="mt-1 w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white disabled:opacity-50"
            >
              <option value="">{anyScrap ? "Choose a reason" : "Nothing scrapped"}</option>
              {reasons.map((r) => (
                <option key={r.code} value={r.code}>{r.name || r.code}</option>
              ))}
            </select>
          </label>
        </div>
        <label className="flex items-center gap-2 text-gray-300">
          <input type="checkbox" checked={acceptShort} onChange={(e) => setAcceptShort(e.target.checked)} />
          Accept short orders now, so their good pieces go on hand
        </label>
        {problems.length > 0 && (
          <ul className="text-amber-400 list-disc pl-5">
            {problems.map((p) => <li key={p}>{p}</li>)}
          </ul>
        )}
        {preview && (
          <div className="bg-gray-800/60 rounded p-3">
            <div className="text-gray-300 mb-1">If you confirm ({preview.run_minutes} min shared):</div>
            <ul className="space-y-1">
              {preview.members.map((row) => (
                <li key={row.member_id} className="text-gray-300">
                  Order {row.order_id} ({row.role}): {row.good} good, {row.scrapped} scrapped,{" "}
                  {row.minutes} min — {OUTCOME_LABELS[row.order_outcome] || row.order_outcome}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-gray-300 hover:text-white">
            Cancel
          </button>
          <button
            type="button"
            disabled={busy || problems.length > 0}
            onClick={() => submit(true)}
            className="px-4 py-2 rounded bg-gray-700 text-white disabled:opacity-50"
          >
            Preview
          </button>
          <button
            type="button"
            disabled={busy || problems.length > 0}
            onClick={() => submit(false)}
            className="px-4 py-2 rounded bg-blue-600 text-white disabled:opacity-50"
          >
            Confirm counts
          </button>
        </div>
      </div>
    </Modal>
  );
}
