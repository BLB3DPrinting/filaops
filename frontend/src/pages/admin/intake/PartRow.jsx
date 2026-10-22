/**
 * One row of the parts table: a kind of object in the vendor file and what it
 * becomes — a new part (named, with a SKU and an item type), or a part we
 * already have. Linking two kinds of object to the same existing part is how
 * they are merged.
 *
 * Controlled: the panel owns the row (see buildRows) and gets `onChange`
 * patches. A part we already have for the same mesh arrives pre-selected.
 */
import { useState } from "react";
import ProductSearchPicker from "./ProductSearchPicker";
import { formatGrams, formatMinutes, ITEM_TYPES, partLabel } from "./plateCompositionPlan";

const inputClass =
  "w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500";
const labelClass = "block text-xs text-gray-400 mb-1";

/** The part this kind of object is linked to, and a way to choose another. */
function LinkedPart({ row, id, onChange }) {
  const [changing, setChanging] = useState(false);
  const proposals = row.part.existing_parts ?? [];
  const pick = (product) => {
    onChange({ linked: product });
    setChanging(false);
  };
  return (
    <div className="space-y-2">
      {row.linked && (
        <div className="flex items-center justify-between gap-3 bg-gray-800 rounded px-3 py-2">
          <span className="text-sm text-gray-200">
            <span className="font-mono text-blue-300">{row.linked.sku}</span>
            {row.linked.name ? ` — ${row.linked.name}` : ""}
          </span>
          <button
            type="button"
            onClick={() => setChanging((open) => !open)}
            className="text-sm text-gray-400 hover:text-gray-200"
          >
            {changing ? "Keep this part" : "Change"}
          </button>
        </div>
      )}
      {proposals.length > 1 && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-gray-400">
          Same mesh as:
          {proposals.map((p) => (
            <button
              key={p.product_id}
              type="button"
              onClick={() => pick(p)}
              aria-pressed={row.linked?.product_id === p.product_id}
              className="border border-gray-700 rounded px-2 py-0.5 hover:bg-gray-800 aria-pressed:border-blue-500"
            >
              {p.sku}
            </button>
          ))}
        </div>
      )}
      {(!row.linked || changing) && (
        <ProductSearchPicker
          inputId={id}
          onPick={(p) => pick({ product_id: p.id, sku: p.sku, name: p.name })}
        />
      )}
    </div>
  );
}

/**
 * @param {object} props
 * @param {object} props.row - from buildRows: { key, part, action, linked, name, sku, itemType, perParent }.
 * @param {number} props.index - the row's position, for unique element ids.
 * @param {boolean} props.showPerParent - an assembly parent is being created.
 * @param {(patch: object) => void} props.onChange - merge a patch into the row.
 * @returns {JSX.Element}
 */
export default function PartRow({ row, index, showPerParent, onChange }) {
  const { part } = row;
  const id = (field) => `part-${index}-${field}`;
  const numbers = [
    part.piece_grams > 0 && formatGrams(part.piece_grams),
    part.piece_minutes > 0 && formatMinutes(part.piece_minutes),
  ].filter(Boolean);
  return (
    <div
      role="group"
      aria-label={`Part: ${partLabel(part)}`}
      className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 space-y-3"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="text-white font-medium">{partLabel(part)}</span>
        <span className="text-sm text-gray-400">
          {part.plates.map((p) => `Plate ${p.plate_index} × ${p.count}`).join(" · ")}
        </span>
        {numbers.length > 0 && (
          <span className="text-xs text-gray-500">one copy: {numbers.join(" · ")}</span>
        )}
        {part.mesh_hash && (
          <span className="text-xs text-gray-600 font-mono">mesh {part.mesh_hash.slice(0, 8)}</span>
        )}
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-gray-200">
        {[
          ["create", "Create a new part"],
          ["link", "Link to an existing part"],
        ].map(([action, label]) => (
          <label key={action} className="inline-flex items-center gap-2">
            <input
              type="radio"
              name={id("action")}
              checked={row.action === action}
              onChange={() => onChange({ action })}
            />
            {label}
          </label>
        ))}
      </div>

      {row.action === "create" ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label htmlFor={id("name")} className={labelClass}>Name</label>
            <input
              id={id("name")}
              value={row.name}
              onChange={(e) => onChange({ name: e.target.value })}
              className={inputClass}
            />
          </div>
          <div>
            <label htmlFor={id("sku")} className={labelClass}>SKU</label>
            <input
              id={id("sku")}
              value={row.sku}
              onChange={(e) => onChange({ sku: e.target.value })}
              className={`${inputClass} font-mono`}
            />
          </div>
          <div>
            <label htmlFor={id("type")} className={labelClass}>Item type</label>
            <select
              id={id("type")}
              value={row.itemType}
              onChange={(e) => onChange({ itemType: e.target.value })}
              className={inputClass}
            >
              {ITEM_TYPES.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      ) : (
        <LinkedPart row={row} id={id("find")} onChange={onChange} />
      )}

      {showPerParent && (
        <div className="max-w-[10rem]">
          <label htmlFor={id("per-parent")} className={labelClass}>Per parent</label>
          <input
            id={id("per-parent")}
            type="number"
            min="0"
            step="any"
            value={row.perParent}
            onChange={(e) => onChange({ perParent: e.target.value })}
            className={inputClass}
          />
          <p className="text-xs text-gray-500 mt-1">0 leaves it out (a spare).</p>
        </div>
      )}
    </div>
  );
}
