/**
 * Response normalizer (UX Foundation, epic #808).
 *
 * FilaOps list endpoints are inconsistent: some return a bare array, most return
 * a `{ items, pagination }` envelope (see apiTypes.js ListResponse), and a few
 * use a domain-keyed envelope (`{ work_centers: [] }`, `{ products: [] }`, ...).
 * Consumers hand-rolled `data.items || data || []` and `Array.isArray(data) ? ...`
 * unwraps that diverge per call site and CRASH on a non-list body (an error
 * payload, a 422 `{ detail: [...] }`, a stray object) with the classic
 * `x.map is not a function`.
 *
 * `normalizeList` is the single, defensive coercion: it ALWAYS returns
 * `{ items: Array, pagination: Object|null }`, never throws, and yields an empty
 * list for anything that is not a recognizable collection.
 */

// Envelope keys we accept out of the box, in priority order. `items` is the
// canonical Sprint 1-2 shape; the rest are the domain-keyed envelopes still in
// the wild. Callers can pass extra keys for a bespoke shape.
const DEFAULT_KEYS = [
  "items",
  "results",
  "data",
  "work_centers",
  "workCenters",
  "routings",
  "products",
  "operations",
  "customers",
  "transactions",
  "spools",
];

/**
 * Coerce any list-ish API payload into `{ items, pagination }`.
 *
 * @template T
 * @param {unknown} data - The parsed response body (array, envelope, or junk).
 * @param {string[]} [keys] - Extra envelope keys to check (tried before the defaults).
 * @returns {{ items: T[], pagination: (import('./apiTypes').PaginationMeta|null) }}
 */
export function normalizeList(data, keys = []) {
  if (Array.isArray(data)) {
    return { items: data, pagination: null };
  }

  if (data && typeof data === "object") {
    for (const key of [...keys, ...DEFAULT_KEYS]) {
      if (Array.isArray(data[key])) {
        return { items: data[key], pagination: data.pagination ?? null };
      }
    }
  }

  // null / undefined / "error string" / { error, message } / { detail: [...] }
  // (FastAPI 422) / any non-collection object → render empty, never crash.
  return { items: [], pagination: null };
}

export default normalizeList;
