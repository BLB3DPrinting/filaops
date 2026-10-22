/**
 * One card per sliced plate of a vendor file: the plate's time and grams, the
 * filament slots it uses, and each kind of object on it as "name × count" with
 * one copy's grams and minutes where the file gives them.
 *
 * Renders PRO's preview (POST /api/v1/pro/intake/compositions without a plan);
 * the grouping (same mesh = same kind of object) is PRO's.
 */
import { formatGrams, formatMinutes, partLabel } from "./plateCompositionPlan";

// Where a copy's numbers came from. G-code object markers are exact and need
// no note; the other two are a share of the plate.
const SOURCE_NOTES = {
  volume: "estimated from volume",
  even: "estimated, split evenly",
};

function pieceNumbers(group) {
  const grams = group.piece_grams > 0 ? formatGrams(group.piece_grams) : "";
  const minutes = group.piece_minutes > 0 ? formatMinutes(group.piece_minutes) : "";
  if (grams && minutes) return `${grams} · ${minutes} each`;
  if (grams) return `${grams} each`;
  return minutes ? `${minutes} each` : "";
}

function PlateCard({ plate }) {
  const title = `Plate ${plate.plate_index}`;
  const facts = [
    formatMinutes(plate.plate_time_minutes),
    formatGrams(plate.total_grams),
    plate.object_count != null &&
      `${plate.object_count} object${plate.object_count === 1 ? "" : "s"}`,
  ].filter(Boolean);
  return (
    <section
      aria-label={title}
      className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 space-y-3"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-white font-medium">
          {title}
          {plate.name && plate.name !== title && (
            <span className="text-gray-400 font-normal"> — {plate.name}</span>
          )}
        </h3>
        <span className="text-sm text-gray-400">{facts.join(" · ")}</span>
      </div>

      {(plate.slots?.length > 0 || plate.outside_grams > 0) && (
        <div className="flex flex-wrap items-center gap-3 text-xs text-gray-400">
          {(plate.slots || []).map((slot) => (
            <span key={slot.slot} className="inline-flex items-center gap-1.5">
              <span
                className="inline-block w-3 h-3 rounded border border-gray-600"
                style={{ backgroundColor: slot.color_hex || "#888" }}
              />
              {[slot.material || "Slot " + (slot.slot + 1), formatGrams(slot.grams)].join(" · ")}
            </span>
          ))}
          {plate.outside_grams > 0 && (
            <span>{formatGrams(plate.outside_grams)} purge and prime</span>
          )}
        </div>
      )}

      <ul className="space-y-1">
        {plate.groups.map((group) => (
          <li
            key={group.key}
            className="flex flex-wrap items-baseline gap-x-3 bg-gray-800 rounded px-3 py-1.5 text-sm"
          >
            <span className="text-white">{`${partLabel(group)} × ${group.count}`}</span>
            <span className="text-gray-400">{pieceNumbers(group)}</span>
            {SOURCE_NOTES[group.source] && (
              <span className="text-yellow-400/80 text-xs">{SOURCE_NOTES[group.source]}</span>
            )}
          </li>
        ))}
      </ul>

      {(plate.warnings || []).map((warning) => (
        <p key={warning} className="text-yellow-400 text-xs">
          {warning}
        </p>
      ))}
    </section>
  );
}

/**
 * @param {object} props
 * @param {Array<object>} props.plates - the preview's `plates[]`.
 * @returns {JSX.Element}
 */
export default function PlateManifestCards({ plates }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
      {plates.map((plate) => (
        <PlateCard key={plate.plate_index} plate={plate} />
      ))}
    </div>
  );
}
