/**
 * Turn a failed fetch Response (or a thrown fetch error) into a sentence a
 * shop owner can act on.
 *
 * The backend answers errors in three shapes:
 *   - validation (422): { error, message, details: { errors: [{ field, message }] } }
 *   - HTTPException:     { detail: "..." } (or detail as a list / object)
 *   - rate limit (429):  { error: "Rate limit exceeded: ..." }
 * A proxy in front of the backend can also answer with an HTML page (502/503),
 * so the body is not always JSON.
 */

const STATUS_MESSAGES = {
  429: "Too many attempts. Wait a minute and try again.",
  502: "FilaOps isn't responding right now. Wait a minute and try again.",
  503: "FilaOps isn't responding right now. Wait a minute and try again.",
  504: "FilaOps took too long to respond. Wait a minute and try again.",
};

// Pydantic prefixes that mean nothing to a user.
const NOISE_PREFIXES = [
  /^value error,\s*/i,
  /^value is not a valid email address:\s*/i,
  /^assertion failed,\s*/i,
];

function cleanMessage(message) {
  let text = String(message || "").trim();
  for (const prefix of NOISE_PREFIXES) text = text.replace(prefix, "");
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
}

function fieldLabel(field, labels) {
  const key = String(field || "").split(".").pop();
  if (labels[key]) return labels[key];
  const words = key.replace(/_/g, " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : "";
}

function fieldErrors(list, labels) {
  return list
    .map((item) => {
      if (!item || typeof item !== "object") return cleanMessage(item);
      const field = item.field ?? (Array.isArray(item.loc) ? item.loc.filter((p) => p !== "body").join(".") : "");
      const message = cleanMessage(item.message ?? item.msg);
      const label = fieldLabel(field, labels);
      return label && message ? `${label}: ${message}` : message;
    })
    .filter(Boolean);
}

/**
 * Pull a readable message out of an already-parsed error body.
 * Returns "" when the body carries nothing useful.
 */
export function messageFromErrorBody(body, labels = {}) {
  if (!body || typeof body !== "object") return "";

  const errors = body.details?.errors;
  if (Array.isArray(errors) && errors.length) return fieldErrors(errors, labels).join(" ");

  const { detail } = body;
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (Array.isArray(detail) && detail.length) return fieldErrors(detail, labels).join(" ");
  if (detail && typeof detail === "object" && typeof detail.message === "string") return detail.message;

  if (typeof body.message === "string" && body.message && body.message !== "Request validation failed") {
    return body.message;
  }
  if (typeof body.error === "string" && /\s/.test(body.error)) return body.error;
  return "";
}

/**
 * Read a failed Response and return the message to show.
 *
 * @param {Response} res - a fetch Response with ok === false
 * @param {string} fallback - shown when the server gives no reason, e.g. "Setup failed"
 * @param {Record<string, string>} [labels] - API field name -> form label, e.g. { email: "Email Address" }
 */
export async function errorMessageFromResponse(res, fallback, labels = {}) {
  let body = null;
  try {
    body = await res.json();
  } catch {
    body = null; // not JSON (for example an HTML page from a proxy)
  }
  const fromBody = messageFromErrorBody(body, labels);
  if (fromBody) return fromBody;
  if (STATUS_MESSAGES[res?.status]) return STATUS_MESSAGES[res.status];
  return res?.status ? `${fallback} (error ${res.status}).` : fallback;
}

/**
 * Message for an error caught around a fetch call. A network failure (the
 * server can't be reached at all) surfaces as a TypeError such as
 * "Failed to fetch", which says nothing to a user.
 */
export function messageForCaughtError(err, fallback = "Something went wrong. Try again.") {
  // Chrome: "Failed to fetch"; Firefox: "NetworkError when attempting to fetch
  // resource."; Safari: "Load failed". Other TypeErrors are bugs, not outages.
  if (err instanceof TypeError && /failed to fetch|networkerror|load failed/i.test(err.message)) {
    return "Cannot reach the FilaOps server. Check that FilaOps is running, then try again.";
  }
  return err?.message || fallback;
}
