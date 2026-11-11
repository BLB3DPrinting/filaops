/**
 * useItemEditSource - the item the edit form should start from.
 *
 * The Items page opens the form with a row of GET /api/v1/items. That row is a
 * summary: it has no weight or dimensions, and it reports a material's reorder
 * point in grams while the form saves it back to the stored column. Building the
 * form from the row alone made every save send those fields wrong (the weight and
 * dimensions as null).
 *
 * So each time the form opens for an edit this loads GET /api/v1/items/{id} and
 * takes the fields the row cannot supply from it. Everything else stays on the
 * row's values, because the detail response does not return image_url and always
 * reports stocking_policy as "on_demand".
 *
 * Returns { item, status, retry }. status is "loading", "ready" or "error"; the
 * caller must not offer a save until it is "ready". With no row (creating a new
 * item) it is "ready" at once and nothing is fetched.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { API_URL } from "../config/api";

const DETAIL_FIELDS = ["weight_oz", "length_in", "width_in", "height_in", "reorder_point"];

const LOADING = { id: null, status: "loading", detail: null };

/** Pick the fields the list row cannot supply out of a GET /api/v1/items/{id} response. */
const fieldsFromDetail = (detail) =>
  Object.fromEntries(DETAIL_FIELDS.filter((field) => field in detail).map((field) => [field, detail[field]]));

/**
 * Load the full item behind a list row each time the edit form opens.
 *
 * @param {boolean} isOpen Whether the form is open; the item is fetched on each open.
 * @param {object|null} listRow The Items list row being edited, or null when creating.
 * @returns {{item: object|null, status: "loading"|"ready"|"error", retry: () => void}}
 *   `item` is the row with the detail's weight, dimensions and reorder point merged in
 *   once `status` is "ready"; `retry` fetches again after an "error".
 */
export default function useItemEditSource(isOpen, listRow) {
  const itemId = listRow?.id ?? null;
  const [state, setState] = useState(LOADING);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!isOpen || itemId === null) return undefined;

    const controller = new AbortController();
    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/items/${itemId}`, {
          credentials: "include",
          signal: controller.signal,
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const detail = await res.json();
        if (!detail || typeof detail !== "object") throw new Error("Unexpected response");
        if (!controller.signal.aborted) setState({ id: itemId, status: "ready", detail });
      } catch {
        if (!controller.signal.aborted) setState({ id: itemId, status: "error", detail: null });
      }
    })();
    // Closing, switching item or retrying drops the result, so the next open
    // always starts from "loading" and a fresh request.
    return () => {
      controller.abort();
      setState(LOADING);
    };
  }, [isOpen, itemId, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  // A result belongs to one item; never show another item's detail.
  const current = state.id === itemId ? state : LOADING;
  const item = useMemo(
    () => (listRow && current.detail ? { ...listRow, ...fieldsFromDetail(current.detail) } : listRow ?? null),
    [listRow, current]
  );

  return { item, status: itemId === null ? "ready" : current.status, retry };
}
