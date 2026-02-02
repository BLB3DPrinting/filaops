/**
 * Settings constants — shared across settings components.
 *
 * Extracted from AdminSettings.jsx (ARCHITECT-002)
 */

// Format phone number as (XXX) XXX-XXXX
export const formatPhoneNumber = (value) => {
  const digits = value.replace(/\D/g, "").slice(0, 10);
  if (digits.length === 0) return "";
  if (digits.length <= 3) return `(${digits}`;
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
};

// Common timezones (grouped by region)
export const timezoneOptions = [
  // Americas
  { value: "America/New_York", label: "US - Eastern Time (ET)" },
  { value: "America/Chicago", label: "US - Central Time (CT)" },
  { value: "America/Denver", label: "US - Mountain Time (MT)" },
  { value: "America/Phoenix", label: "US - Arizona (no DST)" },
  { value: "America/Los_Angeles", label: "US - Pacific Time (PT)" },
  { value: "America/Anchorage", label: "US - Alaska Time (AKT)" },
  { value: "Pacific/Honolulu", label: "US - Hawaii Time (HT)" },
  { value: "America/Toronto", label: "Canada - Eastern" },
  { value: "America/Vancouver", label: "Canada - Pacific" },
  { value: "America/Mexico_City", label: "Mexico - Central" },
  { value: "America/Sao_Paulo", label: "Brazil - Sao Paulo" },
  // Europe
  { value: "Europe/London", label: "UK - London (GMT/BST)" },
  { value: "Europe/Paris", label: "Europe - Central (CET)" },
  { value: "Europe/Berlin", label: "Germany - Berlin" },
  { value: "Europe/Amsterdam", label: "Netherlands - Amsterdam" },
  // Asia
  { value: "Asia/Dubai", label: "UAE - Dubai (GST)" },
  { value: "Asia/Kolkata", label: "India - IST" },
  { value: "Asia/Singapore", label: "Singapore (SGT)" },
  { value: "Asia/Hong_Kong", label: "Hong Kong (HKT)" },
  { value: "Asia/Tokyo", label: "Japan - Tokyo (JST)" },
  { value: "Asia/Shanghai", label: "China - Shanghai (CST)" },
  { value: "Asia/Seoul", label: "South Korea - Seoul (KST)" },
  // Australia & Pacific
  { value: "Australia/Perth", label: "Australia - Perth (AWST)" },
  { value: "Australia/Adelaide", label: "Australia - Adelaide (ACST)" },
  { value: "Australia/Sydney", label: "Australia - Sydney (AEST)" },
  { value: "Australia/Brisbane", label: "Australia - Brisbane (no DST)" },
  { value: "Australia/Melbourne", label: "Australia - Melbourne (AEST)" },
  { value: "Pacific/Auckland", label: "New Zealand (NZST)" },
  // UTC
  { value: "UTC", label: "UTC (Coordinated Universal Time)" },
];
