/**
 * Slice-file helpers for attaching an Intake Studio result to an EXISTING
 * product (re-slice), without going through POST /sku.
 *
 * The PRO attach endpoints accept any product id:
 *   POST /api/v1/pro/intake/products/{id}/slice-file                (multipart upload)
 *   POST /api/v1/pro/intake/products/{id}/slice-file-from-artifact  (worker artifact id)
 * Each call adds a new slice-file record; GET .../slice-file serves the newest
 * one, so attaching again replaces what production downloads. Older files stay
 * on the server as history.
 */
import { API_URL } from "../../../config/api";

const intakeProductUrl = (productId) =>
  `${API_URL}/api/v1/pro/intake/products/${productId}`;

/**
 * Decide which slice file a parse result produces. Mirrors the create-SKU
 * path in AdminIntakeStudio.runCreateSku:
 * - server-sliced input (raw .3mf / bare mesh): the worker's exported
 *   .gcode.3mf, referenced by gcode_3mf_artifact_id;
 * - pre-sliced .gcode.3mf upload: the uploaded file itself;
 * - anything else (e.g. server-sliced with no .gcode.3mf export): nothing.
 *
 * @returns {{kind: "artifact", artifactId: string} | {kind: "upload", file: File} | null}
 */
export function resolveSliceSource(parseResult, sourceFile) {
  const artifactId = parseResult?.gcode_3mf_artifact_id;
  if (artifactId) return { kind: "artifact", artifactId };
  const isServerSliced = Boolean(parseResult?.gcode_artifact_id);
  if (
    !isServerSliced &&
    sourceFile &&
    sourceFile.name.toLowerCase().endsWith(".gcode.3mf")
  ) {
    return { kind: "upload", file: sourceFile };
  }
  return null;
}

/** Pull the filename out of a Content-Disposition header, if present. */
export function filenameFromContentDisposition(header) {
  if (!header) return null;
  const encoded = /filename\*\s*=\s*[^']*''([^;]+)/i.exec(header);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim());
    } catch {
      // fall through to the plain filename= form
    }
  }
  const plain = /filename\s*=\s*"?([^";]+)"?/i.exec(header);
  return plain ? plain[1].trim() : null;
}

/**
 * Look up the slice file a product has now.
 *
 * PRO has no metadata endpoint, so this requests the download and stops
 * reading once the headers arrive. The filename comes from
 * Content-Disposition (readable same-origin only) and the date from
 * Last-Modified (the stored file's write time).
 *
 * @returns {Promise<
 *   {status: "present", filename: string|null, modifiedAt: Date|null} |
 *   {status: "none"} |
 *   {status: "missing", detail: string} |
 *   {status: "unknown", detail: string}
 * >}
 */
export async function fetchCurrentSliceFile(productId) {
  const controller = new AbortController();
  let res;
  try {
    res = await fetch(`${intakeProductUrl(productId)}/slice-file`, {
      method: "GET",
      credentials: "include",
      signal: controller.signal,
    });
  } catch (err) {
    return { status: "unknown", detail: err?.message || "Network error" };
  }

  if (res.ok) {
    const modified = res.headers.get("last-modified");
    const modifiedAt = modified ? new Date(modified) : null;
    const result = {
      status: "present",
      filename: filenameFromContentDisposition(
        res.headers.get("content-disposition")
      ),
      modifiedAt:
        modifiedAt && !Number.isNaN(modifiedAt.getTime()) ? modifiedAt : null,
    };
    // Don't download the file just to describe it.
    controller.abort();
    return result;
  }

  let detail = "";
  try {
    const body = await res.json();
    detail = typeof body?.detail === "string" ? body.detail : "";
  } catch {
    // non-JSON error body
  }
  if (res.status === 404) {
    // PRO returns 404 both when no file was ever attached and when a record
    // exists but its file is gone from disk (the files lost before PRO
    // stored them on the uploads volume).
    if (/content missing/i.test(detail)) {
      return { status: "missing", detail };
    }
    return { status: "none" };
  }
  return {
    status: "unknown",
    detail: detail || `HTTP ${res.status}`,
  };
}

/**
 * Attach a slice file to an existing product. Only the slice file changes;
 * name, SKU, BOM, routing and price are not sent.
 *
 * @param {number} productId
 * @param {{kind: "artifact", artifactId: string} | {kind: "upload", file: File}} source
 * @param {string} filename display/download name for artifact sources
 * @returns {Promise<{ok: true, data: object} | {ok: false, error: string}>}
 */
export async function attachSliceFile(productId, source, filename) {
  let res;
  try {
    if (source.kind === "artifact") {
      res = await fetch(`${intakeProductUrl(productId)}/slice-file-from-artifact`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          gcode_artifact_id: source.artifactId,
          filename,
        }),
      });
    } else {
      const fd = new FormData();
      fd.append("file", source.file);
      res = await fetch(`${intakeProductUrl(productId)}/slice-file`, {
        method: "POST",
        credentials: "include",
        body: fd,
      });
    }
  } catch (err) {
    return { ok: false, error: err?.message || "Network error" };
  }

  let body = null;
  try {
    body = await res.json();
  } catch {
    // empty or non-JSON body
  }
  if (!res.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : null;
    return { ok: false, error: detail || `Attach failed (HTTP ${res.status})` };
  }
  return { ok: true, data: body || {} };
}
