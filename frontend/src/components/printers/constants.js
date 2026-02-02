// Printer status badge classes (static for Tailwind purge safety)
export const statusColors = {
  offline: "bg-gray-500/20 text-gray-400",
  idle: "bg-green-500/20 text-green-400",
  printing: "bg-blue-500/20 text-blue-400",
  paused: "bg-yellow-500/20 text-yellow-400",
  error: "bg-red-500/20 text-red-400",
  maintenance: "bg-orange-500/20 text-orange-400",
};

export const brandLabels = {
  bambulab: "BambuLab",
  klipper: "Klipper/Moonraker",
  octoprint: "OctoPrint",
  prusa: "Prusa",
  creality: "Creality",
  generic: "Generic/Manual",
};

export const MAINTENANCE_TYPE_CLASS = {
  repair: "bg-red-500/20 text-red-400",
  routine: "bg-green-500/20 text-green-400",
  calibration: "bg-blue-500/20 text-blue-400",
};
