/**
 * ProductSearchPicker — find an existing printable product by SKU or name.
 *
 * The same search AttachToExistingProduct runs (GET /api/v1/products?search=,
 * debounced, newest answer wins, raw materials left out because nothing is
 * printed from them), as a piece other intake panels can place in a row.
 *
 * @param {object} props
 * @param {string} props.inputId - id for the search box (its label points at it).
 * @param {(product: {id: number, sku: string, name: string}) => void} props.onPick
 * @returns {JSX.Element}
 */
import { useEffect, useRef, useState } from "react";
import { useApi } from "../../../hooks/useApi";

const SEARCH_DEBOUNCE_MS = 250;
const SEARCH_LIMIT = 20;

export default function ProductSearchPicker({ inputId, onPick }) {
  const api = useApi();
  const [query, setQuery] = useState("");
  // The latest finished search, tagged with the term it answered.
  const [search, setSearch] = useState({ term: "", items: [], error: null });
  const requestIdRef = useRef(0);
  const term = query.trim();

  useEffect(() => {
    // A newer term invalidates any answer still in flight.
    const requestId = ++requestIdRef.current;
    if (!term) return undefined;
    const timer = setTimeout(async () => {
      try {
        const data = await api.get(
          `/api/v1/products?search=${encodeURIComponent(term)}&limit=${SEARCH_LIMIT}`
        );
        if (requestId !== requestIdRef.current) return;
        const items = Array.isArray(data?.items) ? data.items : [];
        setSearch({ term, items: items.filter((p) => !p.is_raw_material), error: null });
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        setSearch({ term, items: [], error: err?.message || "Product search failed" });
      }
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [api, term]);

  // Until the current term's search lands, keep showing the previous list.
  const searching = Boolean(term) && search.term !== term;
  const error = search.term === term ? search.error : null;
  const results = term ? search.items : [];

  return (
    <div>
      <label htmlFor={inputId} className="block text-sm font-medium text-gray-400 mb-1">
        Find part (SKU or name)
      </label>
      <input
        id={inputId}
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="e.g. FG-011 or Goose body"
        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
      />
      {term && (
        <div className="mt-2" aria-live="polite">
          {searching && <p className="text-sm text-gray-500">Searching…</p>}
          {!searching && error && <p className="text-sm text-red-400">{error}</p>}
          {!searching && !error && results.length === 0 && (
            <p className="text-sm text-gray-500">No matching products</p>
          )}
        </div>
      )}
      {results.length > 0 && (
        <ul
          aria-label="Matching products"
          className="mt-1 max-h-48 overflow-y-auto border border-gray-800 rounded-lg divide-y divide-gray-800"
        >
          {results.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => onPick(p)}
                className="w-full text-left px-3 py-2 hover:bg-gray-800 flex items-baseline gap-3"
              >
                <span className="font-mono text-sm text-blue-300">{p.sku}</span>
                <span className="text-gray-300 truncate">{p.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
