import { useMemo } from "react";
import { createApiClient } from "../lib/apiClient";
import { API_URL } from "../config/api";

/**
 * React hook wrapping apiClient with memoized singleton.
 *
 * Returns { get, post, put, patch, del } — all return parsed JSON.
 * Auth handled via httpOnly cookies (credentials: 'include').
 * Retries, error events, and JSON parsing are built in.
 */
let _sharedClient = null;

function getClient() {
  if (!_sharedClient) {
    _sharedClient = createApiClient({
      baseUrl: API_URL,
      onUnauthorized: () => {
        // Session is genuinely dead (silent refresh already failed): clear
        // the stale auth flag so AdminLayout's localStorage guard agrees,
        // then go to login. Without the removeItem, a restarted backend
        // left users on a half-rendered admin shell full of 401 errors.
        localStorage.removeItem("adminUser");
        if (!window.location.pathname.includes("/login")) {
          window.location.href = "/admin/login";
        }
      },
    });
  }
  return _sharedClient;
}

export function useApi() {
  return useMemo(() => {
    const client = getClient();
    return {
      get: client.get,
      post: client.post,
      put: client.put,
      patch: client.patch,
      del: client.delete,
    };
  }, []);
}
