export const DEFAULT_BAMBUDDY_URL = "http://127.0.0.1:8080";

export function formatDate(value) {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function getSyncMessage(result) {
  if (typeof result?.synced === "number") {
    return `Synced ${result.synced} Bambuddy records`;
  }
  return "Bambuddy sync complete";
}
