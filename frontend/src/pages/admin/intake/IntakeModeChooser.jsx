/**
 * Intake-mode choice for a raw multi-plate .3mf: slice one plate (the
 * existing single-plate flow) or the whole model as an assembly. Renders
 * the choice only; AdminIntakeStudio owns `mode` and decides when it shows.
 *
 * @param {object} props
 * @param {"plate"|"assembly"} props.mode - the operator's current choice.
 * @param {(mode: "plate"|"assembly") => void} props.onModeChange - called with the picked mode.
 * @param {number} [props.plateCount] - plate count shown in the assembly option.
 * @returns {JSX.Element}
 */
export default function IntakeModeChooser({ mode, onModeChange, plateCount }) {
  return (
    <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
      <h2 className="text-base font-semibold text-white mb-3">
        How do you want to intake this file?
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => onModeChange("plate")}
          aria-pressed={mode === "plate"}
          className={`text-left rounded-lg border px-4 py-3 transition-colors ${
            mode === "plate"
              ? "border-blue-500 bg-blue-500/10"
              : "border-gray-700 bg-gray-800 hover:border-gray-600"
          }`}
        >
          <span className="block text-white font-medium">
            Intake one plate
          </span>
          <span className="block text-gray-500 text-sm mt-1">
            Pick a single plate below — it&apos;s sliced and becomes
            one SKU.
          </span>
        </button>
        <button
          type="button"
          onClick={() => onModeChange("assembly")}
          aria-pressed={mode === "assembly"}
          className={`text-left rounded-lg border px-4 py-3 transition-colors ${
            mode === "assembly"
              ? "border-blue-500 bg-blue-500/10"
              : "border-gray-700 bg-gray-800 hover:border-gray-600"
          }`}
        >
          <span className="block text-white font-medium">
            Intake whole model as an assembly (
            {plateCount} plates)
          </span>
          <span className="block text-gray-500 text-sm mt-1">
            Slice every plate, create one component per plate plus
            an assembly BOM — all in one flow.
          </span>
        </button>
      </div>
    </div>
  );
}
