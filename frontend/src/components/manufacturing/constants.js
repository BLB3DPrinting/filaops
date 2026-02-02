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
