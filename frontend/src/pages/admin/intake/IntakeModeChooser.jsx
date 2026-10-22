/**
 * Intake-mode choice for a multi-plate file: slice one plate (the existing
 * single-plate flow), the whole raw model as an assembly, or (PRO, a sliced
 * file) the parts and plate layouts of a vendor's pre-arranged plates.
 * Renders the choice only; AdminIntakeStudio owns `mode` and decides when it
 * shows.
 *
 * @param {object} props
 * @param {"plate"|"assembly"|"plateLayouts"} props.mode - the operator's current choice.
 * @param {(mode: "plate"|"assembly"|"plateLayouts") => void} props.onModeChange - called with the picked mode.
 * @param {number} [props.plateCount] - plate count shown in the assembly option.
 * @param {boolean} [props.isRaw] - true (default) for a raw .3mf that can be
 *   sliced here; false for a sliced .gcode.3mf, which has no assembly option.
 * @param {boolean} [props.showPlateLayouts] - show the parts-and-plate-layouts
 *   option. It needs a sliced file, so it is disabled for a raw one.
 * @returns {JSX.Element}
 */
export default function IntakeModeChooser({
  mode,
  onModeChange,
  plateCount,
  isRaw = true,
  showPlateLayouts = false,
}) {
  const optionClass = (selected) =>
    `text-left rounded-lg border px-4 py-3 transition-colors ${
      selected
        ? "border-blue-500 bg-blue-500/10"
        : "border-gray-700 bg-gray-800 hover:border-gray-600"
    }`;
  const optionCount = 1 + (isRaw ? 1 : 0) + (showPlateLayouts ? 1 : 0);

  return (
    <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
      <h2 className="text-base font-semibold text-white mb-3">
        How do you want to intake this file?
      </h2>
      <div
        className={`grid grid-cols-1 gap-2 ${
          optionCount > 2 ? "md:grid-cols-3" : "md:grid-cols-2"
        }`}
      >
        <button
          type="button"
          onClick={() => onModeChange("plate")}
          aria-pressed={mode === "plate"}
          className={optionClass(mode === "plate")}
        >
          <span className="block text-white font-medium">
            Intake one plate
          </span>
          <span className="block text-gray-500 text-sm mt-1">
            Pick a single plate below — it&apos;s sliced and becomes
            one SKU.
          </span>
        </button>
        {isRaw && (
          <button
            type="button"
            onClick={() => onModeChange("assembly")}
            aria-pressed={mode === "assembly"}
            className={optionClass(mode === "assembly")}
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
        )}
        {showPlateLayouts && (
          <button
            type="button"
            onClick={() => onModeChange("plateLayouts")}
            aria-pressed={mode === "plateLayouts"}
            disabled={isRaw}
            className={`${optionClass(mode === "plateLayouts")} ${
              isRaw ? "opacity-50 cursor-not-allowed" : ""
            }`}
          >
            <span className="block text-white font-medium">
              Intake as parts and plate layouts
            </span>
            <span className="block text-gray-500 text-sm mt-1">
              {isRaw
                ? "Needs a sliced .gcode.3mf — slice the plates in Bambu Studio and export the sliced file."
                : "Each kind of object becomes a part, and each plate is saved as a plate layout."}
            </span>
          </button>
        )}
      </div>
    </div>
  );
}
