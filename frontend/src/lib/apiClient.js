/**
 * Fetch wrapper with auth, JSON parsing, retries, and typed errors.
 *
 * Auth: Uses httpOnly cookies (credentials: 'include'). No manual token handling.
 * Usage: const api = createApiClient({ baseUrl: API_URL });
 */
import { emit } from "./events";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export class ApiError extends Error {
  /** @param {number} status @param {any} payload */
  constructor(message, status, payload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

/**
 * @typedef {Object} ApiConfig
 * @property {string} baseUrl
 * @property {() => (void|Promise<void>)} [onUnauthorized]
 * @property {(err:ApiError)=>void} [onError]
 * @property {Record<string,string>} [defaultHeaders]
 */
export function createApiClient(/** @type {ApiConfig} */ cfg) {
  const base = cfg.baseUrl.replace(/\/+$/, "");

  /** @param {RequestInit & {json?: any, retry?: number}} init */
  async function doFetch(
    path,
    init = /** @type {RequestInit & {json?:any,retry?:number}} */ ({})
  ) {
    const url = path.startsWith("http")
      ? path
      : `${base}${path.startsWith("/") ? "" : "/"}${path}`;
    const headers = {
      Accept: "application/json",
      ...(init.json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(cfg.defaultHeaders || {}),
      ...(init.headers || {}),
    };
    const retry = Math.max(0, init.retry ?? 2);
    let attempt = 0;

    while (true) {
      const res = await fetch(url, {
        ...init,
        credentials: "include",
        headers,
        body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
      }).catch((e) => ({
        ok: false,
        status: 0,
        text: async () => String(e?.message || "Network error"),
      }));

      // 401: clear auth state and redirect to login
      if (res.status === 401 && cfg.onUnauthorized) {
        await cfg.onUnauthorized();
      }

      if (res.ok) {
        const ct = res.headers?.get?.("content-type") || "";
        if (ct.includes("application/json")) return res.json();
        const txt = await res.text();
        try {
          return JSON.parse(txt);
        } catch {
          return txt;
        }
      }

      const isRetryable = [0, 429, 500, 502, 503, 504].includes(res.status);
      if (isRetryable && attempt < retry) {
        const backoff = Math.min(2000 * (attempt + 1), 6000);
        await sleep(backoff);
        attempt++;
        continue;
      }

      let payload;
      try {
        payload = await res.json();
      } catch {
        payload = await res.text();
      }
      const message =
        (payload && (payload.detail || payload.message)) || `HTTP ${res.status}`;
      const err = new ApiError(message, res.status, payload);
      // why: notify app-wide error listeners
      try {
        emit("api:error", {
          url,
          method: init.method || "GET",
          status: res.status,
          message,
        });
      } catch { /* emit error silently */ }
      try {
        cfg.onError?.(err);
      } catch { /* callback error silently */ }
      throw err;
    }
  }

  return {
    get: (p, init) => doFetch(p, { ...init, method: "GET" }),
    post: (p, json, init) => doFetch(p, { ...init, method: "POST", json }),
    put: (p, json, init) => doFetch(p, { ...init, method: "PUT", json }),
    patch: (p, json, init) => doFetch(p, { ...init, method: "PATCH", json }),
    delete: (p, init) => doFetch(p, { ...init, method: "DELETE" }),
    ApiError,
  };
}

