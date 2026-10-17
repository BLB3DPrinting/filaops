/**
 * Plate preview → product image.
 *
 * The parse result carries the plate thumbnail as base64. These helpers turn
 * it into a file, store it through Core's product-image upload endpoint (the
 * same storage the item form uses) and point a product at it. The DB keeps a
 * normal /static/uploads/products/... URL, never a data: URL.
 */
import { API_URL } from "../../../config/api";

const EXTENSION_BY_MIME = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/webp": "webp",
  "image/gif": "gif",
};

const PRODUCT_IMAGE_URL_PREFIX = "/static/uploads/products/";

/** True when the parse result has a thumbnail we can store. */
export function hasStorableThumbnail(parseResult) {
  return Boolean(
    parseResult?.thumbnail_base64 &&
      EXTENSION_BY_MIME[parseResult.thumbnail_mime || "image/png"]
  );
}

/**
 * Decode the parse result's thumbnail into a File, or null when there is
 * none (or it isn't valid base64 / a supported image type).
 */
export function thumbnailToFile(parseResult, baseName = "plate-preview") {
  if (!hasStorableThumbnail(parseResult)) return null;
  const mime = parseResult.thumbnail_mime || "image/png";
  let binary;
  try {
    binary = atob(parseResult.thumbnail_base64);
  } catch {
    return null;
  }
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const safeBase = (baseName || "plate-preview").replace(/[^A-Za-z0-9._-]+/g, "-");
  return new File([bytes], `${safeBase}.${EXTENSION_BY_MIME[mime]}`, {
    type: mime,
  });
}

async function readDetail(res) {
  try {
    const body = await res.json();
    return typeof body?.detail === "string" ? body.detail : null;
  } catch {
    return null;
  }
}

/**
 * Upload the parse result's thumbnail as a product image.
 * @returns {Promise<{ok: true, url: string} | {ok: false, error: string}>}
 */
export async function uploadThumbnailAsProductImage(parseResult, baseName) {
  const file = thumbnailToFile(parseResult, baseName);
  if (!file) return { ok: false, error: "No plate preview to save" };
  const fd = new FormData();
  fd.append("file", file);
  let res;
  try {
    res = await fetch(`${API_URL}/api/v1/admin/uploads/product-image`, {
      method: "POST",
      credentials: "include",
      body: fd,
    });
  } catch (err) {
    return { ok: false, error: err?.message || "Network error" };
  }
  if (!res.ok) {
    return {
      ok: false,
      error: (await readDetail(res)) || `Image upload failed (HTTP ${res.status})`,
    };
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    // fall through to the missing-url error
  }
  if (typeof data?.url !== "string" || !data.url) {
    return { ok: false, error: "Image upload returned no URL" };
  }
  return { ok: true, url: data.url };
}

/**
 * Best-effort removal of an image this flow uploaded but didn't use
 * (e.g. product creation failed afterwards). Ignores failures.
 */
export async function discardUploadedProductImage(url) {
  if (!url || !url.startsWith(PRODUCT_IMAGE_URL_PREFIX)) return;
  const filename = url.slice(PRODUCT_IMAGE_URL_PREFIX.length);
  try {
    await fetch(
      `${API_URL}/api/v1/admin/uploads/product-image/${encodeURIComponent(filename)}`,
      { method: "DELETE", credentials: "include" }
    );
  } catch {
    // leaving an unused file behind is harmless
  }
}

/**
 * Point an existing product at an image. Sends only image_url, so nothing
 * else on the product changes. `status` is set when the server answered with
 * an error (absent on a network error, where the update may have landed).
 * @returns {Promise<{ok: true} | {ok: false, error: string, status?: number}>}
 */
export async function setProductImage(productId, imageUrl) {
  let res;
  try {
    res = await fetch(`${API_URL}/api/v1/products/${productId}`, {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_url: imageUrl }),
    });
  } catch (err) {
    return { ok: false, error: err?.message || "Network error" };
  }
  if (!res.ok) {
    return {
      ok: false,
      error: (await readDetail(res)) || `Image update failed (HTTP ${res.status})`,
      status: res.status,
    };
  }
  return { ok: true };
}
