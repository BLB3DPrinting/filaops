/**
 * PlateCompositionIntakePanel — Intake Studio's "parts and plate layouts" mode
 * (PRO) for a sliced multi-plate file, such as a vendor's pre-arranged plates.
 *
 * Every kind of object in the file becomes a part (new, or one we already
 * have), and every plate is saved as a plate layout (a composition) with its
 * sliced file. Optionally a routing-only assembly parent is created too.
 *
 * Two calls to the same PRO endpoint, POST /api/v1/pro/intake/compositions:
 * the file alone answers with a preview and writes nothing; the file again with
 * a `plan` saves everything in one transaction. AdminIntakeStudio only decides
 * when this panel shows and hands it the dropped file.
 */
import { useEffect, useMemo, useState } from "react";
import { useApi } from "../../../hooks/useApi";
import { useToast } from "../../../components/Toast";
import PartRow from "./PartRow";
import PlateCompositionResult from "./PlateCompositionResult";
import PlateManifestCards from "./PlateManifestCards";
import {
  buildPlan,
  buildRows,
  COMPOSITIONS_URL,
  describeIntakeError,
  neededSlots,
  planProblems,
  slotMeta,
  suggestSpool,
} from "./plateCompositionPlan";

const CONTEXT_URL = "/api/v1/pro/intake/context";
const MATERIALS_URL = "/api/v1/materials/for-bom";

const inputClass =
  "w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500";
const labelClass = "block text-xs text-gray-400 mb-1";
const sectionClass = "bg-gray-800/50 border border-gray-700 rounded-lg p-4 space-y-3";

function ErrorBanner({ title, error }) {
  return (
    <div role="alert" className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm">
      <p className="text-red-400 font-medium">
        {title}
        {error.status ? ` (HTTP ${error.status})` : ""}
      </p>
      <p className="text-gray-300 mt-1">{error.message}</p>
    </div>
  );
}

const fileForm = (file, plan) => {
  const body = new FormData();
  body.append("file", file);
  if (plan) body.append("plan", JSON.stringify(plan));
  return body;
};

/**
 * @param {object} props
 * @param {File|null} props.file - the dropped sliced multi-plate .gcode.3mf.
 * @param {() => void} props.onStartOver - back to the drop zone.
 * @returns {JSX.Element}
 */
export default function PlateCompositionIntakePanel({ file, onStartOver }) {
  const api = useApi();
  const toast = useToast();

  // The preview of the file, and the work centres and spools to pick from.
  const [preview, setPreview] = useState({ status: "loading", data: null, error: null });
  const [previewTry, setPreviewTry] = useState(0);
  const [support, setSupport] = useState({ status: "loading", context: null, materials: [], error: null });
  const [supportTry, setSupportTry] = useState(0);

  // What the operator changed; everything else is derived from the preview.
  const [edits, setEdits] = useState({});
  const [settings, setSettings] = useState({ spools: {} });
  const [parentOn, setParentOn] = useState(false);
  const [parentEdits, setParentEdits] = useState({});
  const [saving, setSaving] = useState({ busy: false, error: null });
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (!file) return undefined;
    let current = true;
    api
      .post(COMPOSITIONS_URL, undefined, { body: fileForm(file), retry: 0 })
      .then((data) => {
        if (!current) return;
        if (data?.mode !== "preview") throw new Error("The server sent no preview of this file.");
        setPreview({ status: "ready", data, error: null });
      })
      .catch((err) => {
        if (current) setPreview({ status: "error", data: null, error: describeIntakeError(err) });
      });
    return () => {
      current = false;
    };
  }, [api, file, previewTry]);

  useEffect(() => {
    let current = true;
    Promise.all([api.get(CONTEXT_URL), api.get(MATERIALS_URL)])
      .then(([context, materials]) => {
        if (!current) return;
        setSupport({ status: "ready", context: context ?? {}, materials: materials?.items ?? [], error: null });
      })
      .catch((err) => {
        if (current) setSupport({ status: "error", context: null, materials: [], error: describeIntakeError(err) });
      });
    return () => {
      current = false;
    };
  }, [api, supportTry]);

  const data = preview.data;
  const rows = useMemo(() => buildRows(data, edits), [data, edits]);
  const meta = useMemo(() => slotMeta(data), [data]);
  const slots = neededSlots(rows);

  const workCenters = support.context?.work_centers ?? [];
  const printerWorkCenter = support.context?.printer_work_center_map?.[data?.printer?.model];
  const planName = settings.name ?? data?.model_name ?? "";
  const printWorkCenterId =
    settings.workCenterId ?? (printerWorkCenter ? String(printerWorkCenter.work_center_id) : "");
  const spoolIds = Object.fromEntries(
    slots.map((slot) => [slot, settings.spools[slot] ?? suggestSpool(meta[slot], support.materials)?.id])
  );
  const parent = parentOn
    ? { name: planName, sku: "", workCenterId: "", runMinutes: "", setupMinutes: "", ...parentEdits }
    : null;

  const form = { name: planName, workCenterId: printWorkCenterId, rows, spoolIds, meta, parent };
  const problems = planProblems(form);
  const canSave = support.status === "ready" && problems.length === 0 && !saving.busy;

  const editRow = (key, patch) => setEdits((all) => ({ ...all, [key]: { ...all[key], ...patch } }));
  const editSettings = (patch) => setSettings((all) => ({ ...all, ...patch }));
  const editParent = (patch) => setParentEdits((all) => ({ ...all, ...patch }));

  const save = async () => {
    setSaving({ busy: true, error: null });
    try {
      const answer = await api.post(COMPOSITIONS_URL, undefined, {
        body: fileForm(file, buildPlan(form)),
        retry: 0,
      });
      if (answer?.mode !== "committed") throw new Error("The server did not confirm the save.");
      setResult(answer);
      toast.success(`Saved ${answer.compositions?.length ?? 0} plate layouts`);
    } catch (err) {
      setSaving({ busy: false, error: describeIntakeError(err) });
      return;
    }
    setSaving({ busy: false, error: null });
  };

  if (!file) {
    return (
      <div className="space-y-4">
        <ErrorBanner title="The file is no longer held" error={{ message: "Choose it again to continue." }} />
        <button type="button" onClick={onStartOver} className="border border-gray-700 text-gray-300 hover:bg-gray-800 px-4 py-2 rounded-lg">
          Choose a different file
        </button>
      </div>
    );
  }

  if (preview.status === "loading") {
    return <p className="text-gray-400 py-10 text-center">Reading the plates…</p>;
  }

  if (preview.status === "error") {
    return (
      <div className="space-y-4">
        <ErrorBanner title="Couldn't read this file" error={preview.error} />
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => {
              setPreview({ status: "loading", data: null, error: null });
              setPreviewTry((n) => n + 1);
            }}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
          >
            Try again
          </button>
          <button type="button" onClick={onStartOver} className="border border-gray-700 text-gray-300 hover:bg-gray-800 px-4 py-2 rounded-lg transition-colors">
            Choose a different file
          </button>
        </div>
      </div>
    );
  }

  if (result) {
    return <PlateCompositionResult result={result} rows={rows} onStartOver={onStartOver} />;
  }

  const printer = data.printer ?? {};
  const printerText = [printer.name || printer.model, printer.nozzle && `${printer.nozzle} mm nozzle`]
    .filter(Boolean)
    .join(", ");

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-white">Parts and plate layouts</h2>
        <p className="text-sm text-gray-400 mt-1">
          {`${data.filename} · ${data.plates.length} plates${printerText ? ` · ${printerText}` : ""}`}
        </p>
        <p className="text-sm text-gray-500 mt-1">
          Each kind of object becomes a part, and each plate is saved as a plate layout with its sliced file.
        </p>
        {data.warnings?.map((warning) => (
          <p key={warning} className="text-yellow-400 text-sm mt-1">{warning}</p>
        ))}
      </div>

      <PlateManifestCards plates={data.plates} />

      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Parts</h3>
        {rows.map((row, index) => (
          <PartRow
            key={row.key}
            row={row}
            index={index}
            showPerParent={parentOn}
            onChange={(patch) => editRow(row.key, patch)}
          />
        ))}
      </div>

      <div className={sectionClass}>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Where it prints</h3>
        {support.status === "error" && (
          <div className="flex items-center justify-between gap-3 text-sm text-red-400">
            <span>{`Couldn't load work centres and spools: ${support.error.message}`}</span>
            <button
              type="button"
              onClick={() => {
                setSupport({ status: "loading", context: null, materials: [], error: null });
                setSupportTry((n) => n + 1);
              }}
              className="border border-gray-700 text-gray-300 hover:bg-gray-800 px-3 py-1 rounded-lg"
            >
              Reload
            </button>
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label htmlFor="plate-layouts-name" className={labelClass}>Model name</label>
            <input
              id="plate-layouts-name"
              value={planName}
              onChange={(e) => editSettings({ name: e.target.value })}
              className={inputClass}
            />
          </div>
          <div>
            <label htmlFor="plate-layouts-print-wc" className={labelClass}>Print work centre</label>
            <select
              id="plate-layouts-print-wc"
              value={printWorkCenterId}
              onChange={(e) => editSettings({ workCenterId: e.target.value })}
              className={inputClass}
            >
              <option value="">Choose…</option>
              {workCenters.map((wc) => (
                <option key={wc.id} value={String(wc.id)}>{wc.name || wc.code}</option>
              ))}
            </select>
          </div>
          {slots.map((slot) => {
            const what = [meta[slot]?.material, meta[slot]?.colorHex].filter(Boolean).join(" ");
            return (
              <div key={slot}>
                <label htmlFor={`plate-layouts-spool-${slot}`} className={labelClass}>
                  {`Spool for slot ${slot + 1}${what ? ` (${what})` : ""}`}
                </label>
                <select
                  id={`plate-layouts-spool-${slot}`}
                  value={String(spoolIds[slot] ?? "")}
                  onChange={(e) =>
                    editSettings({ spools: { ...settings.spools, [slot]: e.target.value } })
                  }
                  className={inputClass}
                >
                  <option value="">Choose…</option>
                  {support.materials.map((item) => (
                    <option key={item.id} value={String(item.id)}>{`${item.sku} — ${item.name}`}</option>
                  ))}
                </select>
              </div>
            );
          })}
        </div>
      </div>

      <div className={sectionClass}>
        <label className="flex items-center gap-2 text-sm text-gray-200">
          <input type="checkbox" checked={parentOn} onChange={(e) => setParentOn(e.target.checked)} />
          Also create an assembly parent that uses these parts
        </label>
        {parent && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label htmlFor="plate-layouts-parent-name" className={labelClass}>Parent name</label>
              <input id="plate-layouts-parent-name" value={parent.name} onChange={(e) => editParent({ name: e.target.value })} className={inputClass} />
            </div>
            <div>
              <label htmlFor="plate-layouts-parent-sku" className={labelClass}>Parent SKU (optional)</label>
              <input id="plate-layouts-parent-sku" value={parent.sku} onChange={(e) => editParent({ sku: e.target.value })} className={`${inputClass} font-mono`} />
            </div>
            <div>
              <label htmlFor="plate-layouts-parent-wc" className={labelClass}>Assembly work centre</label>
              <select id="plate-layouts-parent-wc" value={parent.workCenterId} onChange={(e) => editParent({ workCenterId: e.target.value })} className={inputClass}>
                <option value="">Choose…</option>
                {workCenters.map((wc) => (
                  <option key={wc.id} value={String(wc.id)}>{wc.name || wc.code}</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="plate-layouts-parent-run" className={labelClass}>Run minutes</label>
                <input id="plate-layouts-parent-run" type="number" min="0" step="any" value={parent.runMinutes} onChange={(e) => editParent({ runMinutes: e.target.value })} className={inputClass} />
              </div>
              <div>
                <label htmlFor="plate-layouts-parent-setup" className={labelClass}>Setup minutes</label>
                <input id="plate-layouts-parent-setup" type="number" min="0" step="any" value={parent.setupMinutes} onChange={(e) => editParent({ setupMinutes: e.target.value })} className={inputClass} />
              </div>
            </div>
          </div>
        )}
      </div>

      {saving.error && <ErrorBanner title="Couldn't save" error={saving.error} />}
      {support.status === "ready" && !saving.busy && problems.length > 0 && (
        <ul className="text-sm text-gray-400 space-y-0.5">
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={!canSave}
          className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-6 py-2 rounded-lg font-medium transition-colors"
        >
          Create parts and plate layouts
        </button>
        {saving.busy && <span className="text-sm text-gray-400">Saving…</span>}
        <button type="button" onClick={onStartOver} className="border border-gray-700 text-gray-400 hover:bg-gray-800 hover:text-gray-300 px-4 py-2 rounded-lg transition-colors">
          Choose a different file
        </button>
      </div>
    </div>
  );
}
