/**
 * What a saved plate-composition intake made: the new and linked parts, one
 * plate layout (composition) per plate, and the assembly parent if one was
 * asked for. Shown in place of the form once PRO has committed.
 *
 * Core has no page per product yet, so every part links to the Items list.
 */
import { formatGrams, formatMinutes, partLabel } from "./plateCompositionPlan";

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

/**
 * @param {object} props
 * @param {object} props.result - PRO's `mode: "committed"` answer.
 * @param {Array<object>} props.rows - the rows the plan was built from (they
 *   know which existing part a link pointed at, which the answer does not).
 * @param {() => void} props.onStartOver - back to the drop zone.
 * @returns {JSX.Element}
 */
export default function PlateCompositionResult({ result, rows, onStartOver }) {
  const parts = result.parts ?? [];
  const compositions = result.compositions ?? [];
  const created = parts.filter((p) => p.action === "create").length;
  const linked = parts.length - created;
  const rowByKey = Object.fromEntries(rows.map((row) => [row.key, row]));

  return (
    <div className="space-y-5">
      <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
        <h2 className="text-green-400 font-semibold">Parts and plate layouts saved</h2>
        <p className="text-gray-300 text-sm mt-1">
          {`Created ${plural(created, "part")} · linked ${linked} · ${plural(
            compositions.length,
            "plate layout"
          )}`}
        </p>
      </div>

      <div className="bg-gray-800/50 rounded-lg p-4 space-y-1">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-2">Parts</h3>
        {parts.map((p) => {
          const row = rowByKey[p.key];
          const sku = p.sku || row?.linked?.sku;
          return (
            <div
              key={p.key}
              className="flex items-center justify-between text-sm bg-gray-800 rounded px-3 py-1.5"
            >
              <span className="text-gray-300">{row ? partLabel(row.part) : p.key}</span>
              <span className="flex items-center gap-3">
                <a href="/admin/items" className="text-blue-300 font-mono hover:underline">
                  {sku || `#${p.product_id}`}
                </a>
                <span className="text-gray-500 text-xs">
                  {p.action === "create" ? "new part" : "existing part"}
                </span>
              </span>
            </div>
          );
        })}
      </div>

      <div className="bg-gray-800/50 rounded-lg p-4 space-y-1">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Plate layouts
        </h3>
        {compositions.map((c) => (
          <div
            key={c.composition_id}
            className="flex items-center justify-between text-sm bg-gray-800 rounded px-3 py-1.5"
          >
            <span className="text-gray-400">Plate {c.plate_index}</span>
            <span className="flex items-center gap-3">
              <span className="text-white font-mono">{c.code}</span>
              <span className="text-gray-500 text-xs">
                {[`v${c.version}`, formatMinutes(c.plate_time_minutes), formatGrams(c.total_grams)]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </span>
          </div>
        ))}
      </div>

      {result.parent && (
        <div className="bg-gray-800/50 rounded-lg p-4 space-y-1">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
            Assembly parent
          </h3>
          <a href="/admin/items" className="text-blue-300 font-mono hover:underline">
            {result.parent.sku}
          </a>
          <p className="text-gray-400 text-sm">
            {`${plural(result.parent.operation_count, "step")}, ${plural(
              result.parent.material_count,
              "material line"
            )}. No BOM — its parts are on its routing.`}
          </p>
        </div>
      )}

      <div className="flex justify-between">
        <a
          href="/admin/items"
          className="border border-gray-700 text-gray-300 hover:bg-gray-800 px-4 py-2 rounded-lg transition-colors"
        >
          View items
        </a>
        <button
          type="button"
          onClick={onStartOver}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
        >
          Intake another file
        </button>
      </div>
    </div>
  );
}
