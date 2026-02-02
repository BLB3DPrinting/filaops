// Work center type options
export const CENTER_TYPES = [
  { value: "machine", label: "Machine Pool", color: "blue" },
  { value: "station", label: "Work Station", color: "purple" },
  { value: "labor", label: "Labor Pool", color: "green" },
];

// Resource status options
export const RESOURCE_STATUSES = [
  { value: "available", label: "Available", color: "green" },
  { value: "busy", label: "Busy", color: "yellow" },
  { value: "maintenance", label: "Maintenance", color: "orange" },
  { value: "offline", label: "Offline", color: "red" },
];

export const getTypeColor = (type) => {
  const t = CENTER_TYPES.find((ct) => ct.value === type);
  return t?.color || "gray";
};

export const getStatusColor = (status) => {
  const s = RESOURCE_STATUSES.find((rs) => rs.value === status);
  return s?.color || "gray";
};

// Static Tailwind class maps — avoids dynamic template literals that get purged
export const TYPE_BADGE_CLASS = {
  blue: "bg-blue-900/30 text-blue-400",
  purple: "bg-purple-900/30 text-purple-400",
  green: "bg-green-900/30 text-green-400",
  gray: "bg-gray-700 text-gray-400",
};

export const STATUS_DOT_CLASS = {
  green: "bg-green-500",
  yellow: "bg-yellow-500",
  orange: "bg-orange-500",
  red: "bg-red-500",
  gray: "bg-gray-500",
};

export const STATUS_BADGE_CLASS = {
  green: "bg-green-900/30 text-green-400",
  yellow: "bg-yellow-900/30 text-yellow-400",
  orange: "bg-orange-900/30 text-orange-400",
  red: "bg-red-900/30 text-red-400",
  gray: "bg-gray-700 text-gray-400",
};
