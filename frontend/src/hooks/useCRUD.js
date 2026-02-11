import { useState, useCallback, useEffect, useRef } from "react";
import { useApi } from "./useApi";

/**
 * Generic CRUD hook for admin pages.
 *
 * @param {string} endpoint - API path, e.g. '/api/v1/admin/customers'
 * @param {object} [options]
 * @param {boolean} [options.immediate=true] - Fetch on mount
 * @param {string|null} [options.extractKey='items'] - Key to extract array from response.
 *   Use 'items' for paginated responses ({items: [...]}),
 *   null for raw array responses, or any other key.
 * @param {object} [options.defaultParams] - Default query params for fetchAll
 *
 * @returns {{ items, loading, error, fetchAll, create, update, remove, refresh }}
 */
export function useCRUD(endpoint, options = {}) {
  const { immediate = true, extractKey = "items", defaultParams } = options;
  const api = useApi();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(immediate);
  const [error, setError] = useState(null);
  const mountedRef = useRef(true);
  const didFetchRef = useRef(false);

  // Keep latest values in refs so fetchAll closure doesn't go stale
  // but also doesn't cause re-creation on every render.
  const defaultParamsRef = useRef(defaultParams);
  defaultParamsRef.current = defaultParams;
  const extractKeyRef = useRef(extractKey);
  extractKeyRef.current = extractKey;

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const fetchAll = useCallback(async (params) => {
    setLoading(true);
    setError(null);
    try {
      const merged = { ...defaultParamsRef.current, ...params };
      const qs = Object.keys(merged).length
        ? "?" + new URLSearchParams(merged).toString()
        : "";
      const data = await api.get(`${endpoint}${qs}`);
      if (!mountedRef.current) return data;

      const key = extractKeyRef.current;
      let result;
      if (Array.isArray(data)) {
        result = data;
      } else if (key && data?.[key]) {
        result = data[key];
      } else {
        result = Array.isArray(data) ? data : [];
      }
      setItems(result);
      return data; // return full response for pagination meta etc.
    } catch (err) {
      if (mountedRef.current) setError(err.message || "Failed to fetch");
      throw err;
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [api, endpoint]);

  const create = useCallback(async (body) => {
    const data = await api.post(endpoint, body);
    return data;
  }, [api, endpoint]);

  const update = useCallback(async (id, body, method = "put") => {
    const fn = method === "patch" ? api.patch : api.put;
    const data = await fn(`${endpoint}/${id}`, body);
    return data;
  }, [api, endpoint]);

  const remove = useCallback(async (id) => {
    const data = await api.del(`${endpoint}/${id}`);
    return data;
  }, [api, endpoint]);

  // Convenience: refetch with last params
  const refresh = useCallback(() => fetchAll(), [fetchAll]);

  // Initial fetch — fires once on mount, not on every fetchAll identity change.
  useEffect(() => {
    if (immediate && !didFetchRef.current) {
      didFetchRef.current = true;
      fetchAll().catch(() => {});
    }
  }, [immediate, fetchAll]);

  return { items, setItems, loading, error, fetchAll, create, update, remove, refresh };
}
