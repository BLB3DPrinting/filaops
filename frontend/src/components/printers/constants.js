// Printer status badge classes - sourced from shared palette
export { PRINTER_COLORS as statusColors } from "../../lib/statusColors.js";

export const brandLabels = {
  bambulab: "BambuLab",
  klipper: "Klipper/Moonraker",
  octoprint: "OctoPrint",
  prusa: "Prusa",
  creality: "Creality",
  generic: "Generic/Manual",
};

// Brands Core can monitor without a PRO license. Everything else in
// `brandLabels` requires `isPro && hasFeature("filafarm")`. Keep this
// in sync with backend `_CORE_BRAND_CODES` in endpoints/printers.py.
export const CORE_BRANDS = new Set(["bambulab", "generic"]);

export const MAINTENANCE_TYPE_CLASS = {
  repair: "bg-red-500/20 text-red-400",
  routine: "bg-green-500/20 text-green-400",
  calibration: "bg-blue-500/20 text-blue-400",
};
