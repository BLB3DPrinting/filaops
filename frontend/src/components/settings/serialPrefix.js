/**
 * Serial-number prefix rules, mirroring the backend's
 * app/services/serial_prefix.normalize_serial_prefix so the settings form
 * flags a bad prefix before it is sent. The server stays the authority.
 */
export const DEFAULT_SERIAL_PREFIX = "SN-";
export const MAX_SERIAL_PREFIX_LENGTH = 12;

/**
 * Returns { value } with the canonical prefix (trimmed, trailing dash added),
 * or { error } with a message for the admin.
 */
export function normalizeSerialPrefix(raw) {
  const prefix = (raw ?? "").trim();
  if (!prefix) return { error: "Enter a prefix, for example SN-" };
  if (!/^[A-Za-z0-9][A-Za-z0-9-]*$/.test(prefix)) {
    return {
      error: "Use letters, digits and dashes only, starting with a letter or digit",
    };
  }
  const value = prefix.endsWith("-") ? prefix : `${prefix}-`;
  if (value.length > MAX_SERIAL_PREFIX_LENGTH) {
    return {
      error: `Keep it to ${MAX_SERIAL_PREFIX_LENGTH} characters including the dash`,
    };
  }
  return { value };
}
