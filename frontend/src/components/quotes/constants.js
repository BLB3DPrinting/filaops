// Quote status options and styling (static for Tailwind purge safety)
export const STATUS_OPTIONS = [
  { value: "pending", label: "Pending", color: "yellow" },
  { value: "approved", label: "Approved", color: "blue" },
  { value: "accepted", label: "Accepted", color: "cyan" },
  { value: "rejected", label: "Rejected", color: "red" },
  { value: "converted", label: "Converted", color: "green" },
  { value: "cancelled", label: "Cancelled", color: "gray" },
];

const STATUS_CLASS = {
  yellow: "bg-yellow-500/20 text-yellow-400",
  blue: "bg-blue-500/20 text-blue-400",
  cyan: "bg-cyan-500/20 text-cyan-400",
  red: "bg-red-500/20 text-red-400",
  green: "bg-green-500/20 text-green-400",
  gray: "bg-gray-500/20 text-gray-400",
};

export function getStatusStyle(status) {
  const found = STATUS_OPTIONS.find((s) => s.value === status);
  if (!found) return STATUS_CLASS.gray;
  return STATUS_CLASS[found.color];
}
