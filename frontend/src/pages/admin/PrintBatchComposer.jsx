import { useCallback, useEffect, useMemo, useState } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";
import CompositionPicker from "./print-batches/CompositionPicker";
import ConfirmBatchCountsModal from "./print-batches/ConfirmBatchCountsModal";
import { BATCH_API, STATUS_STYLES, formatMinutes, printerModelKey } from "./print-batches/printBatchHelpers";

// ---------------------------------------------------------------------------
// Print batch composer (FilaOps PRO, print batches S9).
//
// A batch is one plate on one printer carrying the PRINT steps of several
// production orders. The planner ticks open print steps (taking part of an
// order splits it), adds stock top-ups or "fill" to complete the plate, and
// watches the plate's share of capacity. The operator arranges the pick list
// in Bambu Studio and uploads the sliced plate, which must print exactly the
// batch's pieces. Booking puts every member on one printer as one block;
// confirming counts completes every member order. Everything is PRO's
// /api/v1/pro/print-batches; Core only shows it. Batching needs Core 4.4.0,
// and the page says so when PRO reports it can't run here.
// ---------------------------------------------------------------------------

const EDITABLE = ["draft", "composed"];
const CONFIRMABLE = ["running", "printed", "failed"];

function StatusChip({ status }) {
  return <span className={`px-2 py-0.5 rounded text-xs ${STATUS_STYLES[status] || ""}`}>{status}</span>;
}

function CapacityBar({ capacity }) {
  if (!capacity || capacity.share == null) {
    return <p className="text-gray-400 text-sm">{capacity?.message || "Capacity unknown"}</p>;
  }
  const pct = Math.round(capacity.share * 100);
  const notes = [];
  if (capacity.unknown_parts?.length) notes.push(`no capacity on record for ${capacity.unknown_parts.length} part(s)`);
  if (capacity.pack && !capacity.pack.fits) notes.push("the parts' boxes may not lay out on the bed");
  if (capacity.fits_with?.quantity != null) {
    notes.push(`fits with ${capacity.fits_with.quantity} of part ${capacity.fits_with.product_id}`);
  }
  return (
    <div className="space-y-1">
      <div className="h-2 bg-gray-800 rounded">
        <div
          className={`h-2 rounded ${capacity.fits ? "bg-green-500" : "bg-red-500"}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <p className="text-xs text-gray-400">
        {pct}% of a {capacity.printer_model} plate{notes.length ? ` · ${notes.join(" · ")}` : ""}
      </p>
    </div>
  );
}

export default function PrintBatchComposer() {
  const api = useApi();
  const toast = useToast();
  const { isPro, loading: flagsLoading } = useFeatureFlags();
  const [support, setSupport] = useState(null);
  const [batches, setBatches] = useState([]);
  const [batch, setBatch] = useState(null);
  const [models, setModels] = useState([]);
  const [model, setModel] = useState("");
  const [candidates, setCandidates] = useState([]);
  const [picked, setPicked] = useState({});
  const [fill, setFill] = useState(new Set());
  const [allowOver, setAllowOver] = useState(false);
  const [printers, setPrinters] = useState([]);
  const [booking, setBooking] = useState({ printer_id: "", start: "" });
  const [upload, setUpload] = useState({ file: null, preview: null, mapping: {} });
  const [busy, setBusy] = useState(false);
  const [showPicker, setShowPicker] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [variance, setVariance] = useState(null);

  const run = useCallback(
    async (work, done) => {
      setBusy(true);
      try {
        const result = await work();
        if (done) toast.success(done);
        return result;
      } catch (err) {
        toast.error(err?.message || "The print batch action failed");
        return null;
      } finally {
        setBusy(false);
      }
    },
    [toast],
  );

  const loadBatches = useCallback(async () => {
    const data = await api.get(BATCH_API);
    setBatches(data?.batches || []);
    setSupport(data?.support || null);
  }, [api]);

  const loadCandidates = useCallback(async () => {
    const query = model ? `?printer_model=${encodeURIComponent(model)}` : "";
    const data = await api.get(`${BATCH_API}/candidates${query}`);
    setCandidates(data?.candidates || []);
  }, [api, model]);

  const openBatch = useCallback(
    async (id) => {
      const card = await api.get(`${BATCH_API}/${id}`);
      setBatch(card);
      setUpload({ file: null, preview: null, mapping: {} });
      setVariance(card.status === "complete" ? await api.get(`${BATCH_API}/${id}/variance`) : null);
      if (card.printer_model) setModel(card.printer_model);
      if (card.has_plate) {
        const data = await api.get(`${BATCH_API}/${id}/printers`);
        setPrinters(data?.printers || []);
      } else {
        setPrinters([]);
      }
    },
    [api],
  );

  useEffect(() => {
    if (!isPro) return;
    api
      .get(BATCH_API)
      .then((data) => {
        setBatches(data?.batches || []);
        setSupport(data?.support || null);
      })
      .catch(() => setBatches([]));
    api
      .get("/api/v1/printers/?page_size=200")
      .then((data) => setModels([...new Set((data?.items || []).map((p) => printerModelKey(p.model)).filter(Boolean))]))
      .catch(() => setModels([]));
  }, [isPro, api]);

  useEffect(() => {
    if (!isPro) return;
    const query = model ? `?printer_model=${encodeURIComponent(model)}` : "";
    api
      .get(`${BATCH_API}/candidates${query}`)
      .then((data) => setCandidates(data?.candidates || []))
      .catch(() => setCandidates([]));
  }, [isPro, api, model]);

  const refresh = async (card) => {
    await Promise.all([loadBatches(), loadCandidates()]);
    if (card?.id) await openBatch(card.id);
  };

  const lines = useMemo(
    () =>
      Object.entries(picked).map(([operationId, quantity]) => ({
        operation_id: Number(operationId),
        ...(quantity ? { quantity: Number(quantity) } : {}),
      })),
    [picked],
  );

  const addToPlate = async () => {
    const body = { lines, fill: [...fill], allow_over: allowOver };
    const editing = batch && EDITABLE.includes(batch.status) && batch.compose_mode !== "composition";
    const card = await run(
      () =>
        editing
          ? api.post(`${BATCH_API}/${batch.id}/members`, body, { retry: 0 })
          : api.post(BATCH_API, { ...body, printer_model: model || null }, { retry: 0 }),
      editing ? "Added to the plate" : "Batch created",
    );
    if (!card) return;
    (card.warnings || []).forEach((w) => toast.warning?.(w));
    setPicked({});
    setFill(new Set());
    await refresh(card);
  };

  const action = async (path, body, done) => {
    const card = await run(() => api.post(`${BATCH_API}/${batch.id}/${path}`, body, { retry: 0 }), done);
    if (card) await refresh(card);
  };

  const detach = async (memberId) => {
    const card = await run(() => api.del(`${BATCH_API}/${batch.id}/members/${memberId}`, { retry: 0 }), "Taken off");
    if (card) await refresh(card);
  };

  const sendPlate = async (commit) => {
    const form = new FormData();
    form.append("file", upload.file);
    const mapping = Object.fromEntries(Object.entries(upload.mapping).filter(([, v]) => v));
    if (Object.keys(mapping).length) form.append("mapping", JSON.stringify(mapping));
    if (commit) form.append("commit", "true");
    const result = await run(
      () => api.post(`${BATCH_API}/${batch.id}/plate`, undefined, { body: form, retry: 0 }),
      commit ? "Plate saved" : null,
    );
    if (!result) return;
    if (commit) await refresh(result);
    else setUpload((u) => ({ ...u, preview: result }));
  };

  const book = () =>
    action(
      "book",
      {
        printer_id: Number(booking.printer_id),
        ...(booking.start ? { start: new Date(booking.start).toISOString() } : {}),
      },
      "Booked as one block",
    );

  if (flagsLoading) return null;
  if (!isPro) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-white">Print Batches</h1>
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-6 text-gray-300">
          Print batches are a PRO feature: compose one plate from several orders, book it on one printer as one
          block, and confirm what came off it in one step.
        </div>
      </div>
    );
  }

  const editable = batch && EDITABLE.includes(batch.status);
  const memberParts = new Set((batch?.members || []).map((m) => m.product_id));
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Print Batches</h1>
          <p className="text-gray-400 mt-1">One plate, several orders, one booking</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => setShowPicker(true)} className="px-3 py-2 rounded bg-gray-700 text-white">
            Use a saved composition
          </button>
          <button type="button" onClick={() => setBatch(null)} className="px-3 py-2 rounded bg-gray-800 text-gray-200">
            New plate
          </button>
        </div>
      </div>

      {support && !support.available && (
        <div className="bg-amber-500/10 border border-amber-500/40 rounded p-4 text-amber-200">{support.message}</div>
      )}

      <div className="flex flex-wrap gap-2">
        {batches.map((b) => (
          <button
            key={b.id}
            type="button"
            onClick={() => run(() => openBatch(b.id))}
            className={`px-3 py-1 rounded border text-sm ${batch?.id === b.id ? "border-blue-500" : "border-gray-700"} text-gray-200`}
          >
            {b.code} <StatusChip status={b.status} /> <span className="text-gray-400">{b.pieces} pcs</span>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <section className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white">Open print steps</h2>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              aria-label="Printer model"
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-sm"
            >
              <option value="">Printer model…</option>
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div className="max-h-[28rem] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="text-gray-400 text-left">
                <tr>
                  <th />
                  <th>Part</th>
                  <th>Order</th>
                  <th>Due</th>
                  <th>Pieces</th>
                  <th>On hand</th>
                  <th>Plate</th>
                  <th>Fill</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((c) => (
                  <tr key={c.operation_id} className="border-t border-gray-800 text-gray-200">
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Pick ${c.order_code}`}
                        checked={c.operation_id in picked}
                        onChange={(e) =>
                          setPicked((p) => {
                            const next = { ...p };
                            if (e.target.checked) next[c.operation_id] = "";
                            else delete next[c.operation_id];
                            return next;
                          })
                        }
                      />
                    </td>
                    <td>{c.product.name}{c.is_topup && <span className="ml-1 text-xs text-gray-400">stock</span>}</td>
                    <td>{c.order_code}</td>
                    <td>{c.due_date || "—"}</td>
                    <td>
                      {c.operation_id in picked ? (
                        <input
                          type="number"
                          min="1"
                          max={c.quantity}
                          placeholder={String(c.quantity)}
                          aria-label={`Pieces of ${c.order_code}`}
                          value={picked[c.operation_id]}
                          onChange={(e) => setPicked((p) => ({ ...p, [c.operation_id]: e.target.value }))}
                          className="w-16 bg-gray-800 border border-gray-700 rounded px-1"
                        />
                      ) : (
                        c.quantity
                      )}
                    </td>
                    <td>{c.on_hand}</td>
                    <td>{c.plate_share != null ? `${Math.round(c.plate_share * 100)}%` : "—"}</td>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Fill the plate with ${c.product.name}`}
                        checked={fill.has(c.product.id)}
                        onChange={(e) =>
                          setFill((f) => {
                            const next = new Set(f);
                            if (e.target.checked) next.add(c.product.id);
                            else next.delete(c.product.id);
                            return next;
                          })
                        }
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {candidates.length === 0 && <p className="text-gray-400 text-sm py-4">No open print steps.</p>}
          </div>
          <div className="flex items-center justify-between">
            <label className="text-xs text-gray-400 flex items-center gap-1">
              <input type="checkbox" checked={allowOver} onChange={(e) => setAllowOver(e.target.checked)} />
              Over a full plate is fine, the slice will tell
            </label>
            <button
              type="button"
              disabled={busy || (lines.length === 0 && fill.size === 0) || (support && !support.available)}
              onClick={addToPlate}
              className="px-4 py-2 rounded bg-blue-600 text-white disabled:opacity-50"
            >
              {editable && batch.compose_mode !== "composition" ? `Add to ${batch.code}` : "Create batch"}
            </button>
          </div>
        </section>

        <section className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-4">
          {!batch && <p className="text-gray-400">Pick print steps and create a batch, or open one above.</p>}
          {batch && (
            <>
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-white">
                  {batch.code} <StatusChip status={batch.status} />
                </h2>
                <span className="text-sm text-gray-400">
                  {batch.printer_model || "no model"} · {batch.compose_mode.replace("_", " ")}
                  {batch.has_plate && ` · ${formatMinutes(batch.booking_minutes)} booked`}
                </span>
              </div>
              {batch.problems.length > 0 && (
                <ul className="text-red-300 text-sm list-disc pl-5">
                  {batch.problems.map((p) => <li key={p}>{p}</li>)}
                </ul>
              )}
              {batch.capacity && <CapacityBar capacity={batch.capacity} />}
              <table className="w-full text-sm">
                <tbody>
                  {batch.members.map((m) => (
                    <tr key={m.id} className="border-t border-gray-800 text-gray-200">
                      <td>{m.name}</td>
                      <td>{m.order_code}</td>
                      <td>{m.role === "topup" ? "stock" : "order"}</td>
                      <td>× {m.quantity}</td>
                      <td>{m.quantity_good != null ? `${m.quantity_good} good / ${m.quantity_scrapped} scrap` : ""}</td>
                      <td className="text-right">
                        {(editable || batch.status === "broken") && batch.compose_mode !== "composition" && (
                          <button type="button" onClick={() => detach(m.id)} className="text-red-300 hover:text-red-200">
                            Remove
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {["draft", "composed", "scheduled"].includes(batch.status) && batch.compose_mode !== "composition" && (
                <div className="space-y-2 border-t border-gray-800 pt-3">
                  <h3 className="text-white font-medium">Plate</h3>
                  <p className="text-xs text-gray-400">
                    Arrange these parts on one plate in Bambu Studio for the {batch.printer_model || "chosen"} printer
                    with label objects on, slice, and upload the .gcode.3mf.
                  </p>
                  <input
                    type="file"
                    accept=".3mf"
                    aria-label="Sliced plate"
                    onChange={(e) => setUpload({ file: e.target.files?.[0] || null, preview: null, mapping: {} })}
                    className="text-sm text-gray-300"
                  />
                  {upload.preview && (
                    <div className="text-sm text-gray-300 space-y-1">
                      {upload.preview.groups.map((g) => (
                        <div key={g.key} className="flex items-center gap-2">
                          <span>{g.name || g.key} × {g.count}</span>
                          <select
                            aria-label={`Part for ${g.name || g.key}`}
                            value={upload.mapping[g.key] ?? g.product_id ?? ""}
                            onChange={(e) =>
                              setUpload((u) => ({ ...u, mapping: { ...u.mapping, [g.key]: Number(e.target.value) || null } }))
                            }
                            className="bg-gray-800 border border-gray-700 rounded px-1"
                          >
                            <option value="">Which part?</option>
                            {[...memberParts].map((pid) => (
                              <option key={pid} value={pid}>
                                {batch.members.find((m) => m.product_id === pid)?.name || pid}
                              </option>
                            ))}
                          </select>
                        </div>
                      ))}
                      {upload.preview.problems.map((p) => <p key={p} className="text-amber-300">{p}</p>)}
                    </div>
                  )}
                  <div className="flex gap-2">
                    <button type="button" disabled={!upload.file || busy} onClick={() => sendPlate(false)}
                      className="px-3 py-1 rounded bg-gray-700 text-white disabled:opacity-50">Check plate</button>
                    <button type="button" disabled={!upload.preview || busy} onClick={() => sendPlate(true)}
                      className="px-3 py-1 rounded bg-blue-600 text-white disabled:opacity-50">Use this plate</button>
                  </div>
                </div>
              )}

              {["composed", "scheduled", "broken"].includes(batch.status) && batch.has_plate && (
                <div className="space-y-2 border-t border-gray-800 pt-3">
                  <h3 className="text-white font-medium">Booking</h3>
                  <div className="flex flex-wrap gap-2 items-center">
                    <select
                      aria-label="Printer"
                      value={booking.printer_id}
                      onChange={(e) => setBooking((b) => ({ ...b, printer_id: e.target.value }))}
                      className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-sm"
                    >
                      <option value="">Printer…</option>
                      {printers.map((p) => (
                        <option key={p.id} value={p.id} disabled={!p.eligible} title={p.problems.join("; ")}>
                          {p.name} ({p.model || "?"}{p.nozzle ? ` ${p.nozzle} mm` : ""}){p.eligible ? "" : " — can't print this plate"}
                        </option>
                      ))}
                    </select>
                    <input
                      type="datetime-local"
                      aria-label="Start"
                      value={booking.start}
                      onChange={(e) => setBooking((b) => ({ ...b, start: e.target.value }))}
                      className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-sm"
                    />
                    <button type="button" disabled={!booking.printer_id || busy} onClick={book}
                      className="px-3 py-1 rounded bg-blue-600 text-white disabled:opacity-50">
                      {batch.status === "composed" ? "Book" : "Re-book"}
                    </button>
                    {batch.status !== "composed" && (
                      <button type="button" disabled={busy} onClick={() => action("unschedule", {}, "Unscheduled")}
                        className="px-3 py-1 rounded bg-gray-700 text-white">Unschedule</button>
                    )}
                  </div>
                  {batch.scheduled_start && (
                    <p className="text-xs text-gray-400">
                      Booked {new Date(batch.scheduled_start).toLocaleString()} to {new Date(batch.scheduled_end).toLocaleString()}
                    </p>
                  )}
                </div>
              )}

              <div className="flex flex-wrap gap-2 border-t border-gray-800 pt-3">
                {batch.status === "scheduled" && (
                  <button type="button" disabled={busy} onClick={() => action("start", {}, "Started")}
                    className="px-3 py-1 rounded bg-amber-600 text-white">Mark started</button>
                )}
                {CONFIRMABLE.includes(batch.status) && (
                  <button type="button" onClick={() => setShowConfirm(true)}
                    className="px-3 py-1 rounded bg-green-600 text-white">Confirm counts</button>
                )}
                {[...EDITABLE, "scheduled", "broken"].includes(batch.status) && (
                  <button type="button" disabled={busy} onClick={() => action("cancel", {}, "Batch cancelled")}
                    className="px-3 py-1 rounded bg-gray-800 text-red-300">Cancel batch</button>
                )}
              </div>

              {variance && (
                <div className="text-sm text-gray-300 border-t border-gray-800 pt-3 space-y-1">
                  <h3 className="text-white font-medium">Variance</h3>
                  <p>
                    Run {formatMinutes(variance.actual_run_minutes)} against {formatMinutes(variance.booked_minutes)} booked;
                    plate {formatMinutes(variance.plate_minutes)} against {formatMinutes(variance.member_planned_minutes)} of
                    its parts' standard minutes.
                  </p>
                  {variance.slice_vs_planned_grams != null && (
                    <p>Slice grams are {variance.slice_vs_planned_grams} g over the parts' planned grams (purge, prime tower).</p>
                  )}
                </div>
              )}
            </>
          )}
        </section>
      </div>

      {showPicker && (
        <CompositionPicker
          isOpen
          onClose={() => setShowPicker(false)}
          printerModel={model}
          onCreated={(card) => refresh(card)}
        />
      )}
      {showConfirm && batch && (
        <ConfirmBatchCountsModal
          batch={batch}
          isOpen
          onClose={() => setShowConfirm(false)}
          onCompleted={() => refresh(batch)}
        />
      )}
    </div>
  );
}
