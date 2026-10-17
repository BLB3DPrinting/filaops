/**
 * AttachToExistingProduct — Intake Studio's "existing product" mode.
 *
 * Re-slices a product that already exists: the operator picks the product,
 * sees the slice file it has now, confirms, and the new slice file is
 * attached through the same PRO endpoints the create flow uses. POST /sku is
 * never called, so the product's name, SKU, BOM, routing and price are left
 * alone. Optionally (on by default) the plate preview replaces the product
 * image.
 */
import { useEffect, useRef, useState } from "react";
import { useApi } from "../../../hooks/useApi";
import { useToast } from "../../../components/Toast";
import ConfirmDialog from "../../../components/ConfirmDialog";
import { API_URL } from "../../../config/api";
import {
  attachSliceFile,
  fetchCurrentSliceFile,
  resolveSliceSource,
} from "./sliceFileAttach";
import {
  discardUploadedProductImage,
  hasStorableThumbnail,
  setProductImage,
  uploadThumbnailAsProductImage,
} from "./productImage";

const SEARCH_DEBOUNCE_MS = 250;
const SEARCH_LIMIT = 20;

const formatDate = (date) =>
  date
    ? date.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;

function describeCurrent(current) {
  if (!current) return null;
  switch (current.status) {
    case "present": {
      const name = current.filename || "A slice file";
      const when = formatDate(current.modifiedAt);
      return when ? `${name}, saved ${when}` : name;
    }
    case "missing":
      return "A slice file is on record, but its file is missing from the server";
    case "none":
      return "No slice file on record";
    default:
      return `Couldn't check (${current.detail})`;
  }
}

export default function AttachToExistingProduct({
  parseResult,
  sourceFile,
  initialQuery = "",
  onStartOver,
}) {
  const api = useApi();
  const toast = useToast();

  const [query, setQuery] = useState(initialQuery);
  // The latest finished search, tagged with the term it answered.
  const [search, setSearch] = useState({ term: "", items: [], error: null });
  const searchRequestIdRef = useRef(0);

  const [selected, setSelected] = useState(null);
  const [current, setCurrent] = useState(null);
  const [currentLoading, setCurrentLoading] = useState(false);
  const currentRequestIdRef = useRef(0);

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [attaching, setAttaching] = useState(false);
  const [attached, setAttached] = useState(null);

  const canSaveImage = hasStorableThumbnail(parseResult);
  const [useAsImage, setUseAsImage] = useState(true);
  const willSaveImage = canSaveImage && useAsImage;

  const source = resolveSliceSource(parseResult, sourceFile);

  const term = query.trim();

  // Server-side product search (SKU or name), debounced; a newer query
  // invalidates any response still in flight.
  useEffect(() => {
    const requestId = ++searchRequestIdRef.current;
    if (!term) return undefined;
    const timer = setTimeout(async () => {
      try {
        const data = await api.get(
          `/api/v1/products?search=${encodeURIComponent(term)}&limit=${SEARCH_LIMIT}`
        );
        if (requestId !== searchRequestIdRef.current) return;
        const items = Array.isArray(data?.items) ? data.items : [];
        // Slice files belong to things we print, not to raw materials.
        setSearch({
          term,
          items: items.filter((p) => !p.is_raw_material),
          error: null,
        });
      } catch (err) {
        if (requestId !== searchRequestIdRef.current) return;
        setSearch({
          term,
          items: [],
          error: err?.message || "Product search failed",
        });
      }
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [api, term]);

  // Until the current term's search lands, keep showing the previous list.
  const searching = Boolean(term) && search.term !== term;
  const searchError = search.term === term ? search.error : null;
  const visibleResults = term ? search.items : [];

  const selectProduct = async (product) => {
    setSelected(product);
    setAttached(null);
    setCurrent(null);
    setCurrentLoading(true);
    const requestId = ++currentRequestIdRef.current;
    const info = await fetchCurrentSliceFile(product.id);
    if (requestId !== currentRequestIdRef.current) return;
    setCurrent(info);
    setCurrentLoading(false);
  };

  const clearSelection = () => {
    currentRequestIdRef.current += 1;
    setSelected(null);
    setCurrent(null);
    setCurrentLoading(false);
    setAttached(null);
  };

  const hasExistingFile =
    current?.status === "present" || current?.status === "missing";

  const runAttach = async () => {
    if (!selected || !source) return;
    setAttaching(true);
    const filename = `${selected.name || selected.sku || "model"}.gcode.3mf`;
    const result = await attachSliceFile(selected.id, source, filename);
    if (!result.ok) {
      setAttaching(false);
      setConfirmOpen(false);
      toast.error(result.error);
      return;
    }
    // The slice file is what matters; an image failure is reported, not fatal.
    let imageError = null;
    if (willSaveImage) {
      const upload = await uploadThumbnailAsProductImage(parseResult, selected.sku);
      const saved = upload.ok
        ? await setProductImage(selected.id, upload.url)
        : upload;
      if (!saved.ok) {
        imageError = saved.error;
        // The server refused the update, so nothing points at the uploaded
        // file. (On a network error the update may have landed; keep it.)
        if (upload.ok && saved.status >= 400 && saved.status < 500) {
          discardUploadedProductImage(upload.url);
        }
      }
    }
    setAttaching(false);
    setConfirmOpen(false);
    setAttached({
      ...result.data,
      image: willSaveImage ? (imageError ? "failed" : "saved") : "skipped",
    });
    toast.success(`Slice file attached to ${selected.sku}`);
    if (imageError) {
      toast.warning(`Product image not updated: ${imageError}`);
    }
  };

  const imageSentence = willSaveImage
    ? selected?.image_url
      ? " The plate preview replaces the product image."
      : " The plate preview becomes the product image."
    : "";
  const confirmMessage = selected
    ? (hasExistingFile
        ? `${selected.sku} (${selected.name}) has: ${describeCurrent(current)}. ` +
          "The new file becomes the one production downloads. The old file stays " +
          "on the server as history."
        : `${selected.sku} (${selected.name}) has no slice file on record. ` +
          "The new file will be attached.") +
      imageSentence +
      " Nothing else on the product changes."
    : "";

  if (attached && selected) {
    return (
      <div className="space-y-4">
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
          <p className="text-green-400 font-medium">
            Slice file attached to {selected.sku}
          </p>
          <p className="text-gray-300 text-sm mt-1">
            Production now downloads{" "}
            <span className="font-mono">
              {attached.original_filename || "the new file"}
            </span>
            . The product&apos;s name, SKU, BOM, routing and price were not
            changed.
          </p>
          {attached.image === "saved" && (
            <p className="text-gray-300 text-sm mt-1">
              The plate preview is now the product image.
            </p>
          )}
          {attached.image === "failed" && (
            <p className="text-yellow-400 text-sm mt-1">
              The product image was not updated.
            </p>
          )}
        </div>
        <div className="flex justify-between">
          <a
            href={`${API_URL}/api/v1/pro/intake/products/${selected.id}/slice-file`}
            className="border border-gray-700 text-gray-300 hover:bg-gray-800 px-4 py-2 rounded-lg transition-colors"
          >
            Download slice file
          </a>
          <button
            type="button"
            onClick={onStartOver}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
          >
            Re-slice another product
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-400">
        Attach this slice file to a product that already exists. The
        product&apos;s name, SKU, BOM, routing and price stay as they are.
      </p>

      {!source && (
        <div className="text-yellow-400 text-sm bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
          This upload didn&apos;t produce a printable .gcode.3mf, so there is
          nothing to attach. Upload a sliced .gcode.3mf, or a .3mf/.stl the
          server can slice.
        </div>
      )}

      {!selected ? (
        <div>
          <label
            htmlFor="intake-existing-product-search"
            className="block text-sm font-medium text-gray-400 mb-1"
          >
            Find product (SKU or name)
          </label>
          <input
            id="intake-existing-product-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. FG-011 or Crystal Dragon"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
          />
          {term && (
            <div className="mt-2" aria-live="polite">
              {searching && (
                <p className="text-sm text-gray-500">Searching…</p>
              )}
              {!searching && searchError && (
                <p className="text-sm text-red-400">{searchError}</p>
              )}
              {!searching && !searchError && visibleResults.length === 0 && (
                <p className="text-sm text-gray-500">No matching products</p>
              )}
            </div>
          )}
          {visibleResults.length > 0 && (
            <ul
              aria-label="Matching products"
              className="mt-1 max-h-64 overflow-y-auto border border-gray-800 rounded-lg divide-y divide-gray-800"
            >
              {visibleResults.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    onClick={() => selectProduct(p)}
                    className="w-full text-left px-3 py-2 hover:bg-gray-800 flex items-baseline gap-3"
                  >
                    <span className="font-mono text-sm text-blue-300">
                      {p.sku}
                    </span>
                    <span className="text-gray-300 truncate">{p.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 space-y-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="font-mono text-blue-300">{selected.sku}</p>
              <p className="text-white">{selected.name}</p>
            </div>
            <button
              type="button"
              onClick={clearSelection}
              className="text-sm text-gray-400 hover:text-gray-200"
            >
              Change
            </button>
          </div>
          <div className="text-sm">
            <span className="text-gray-400">Current slice file: </span>
            <span className="text-gray-200" data-testid="current-slice-file">
              {currentLoading ? "Checking…" : describeCurrent(current)}
            </span>
          </div>
        </div>
      )}

      {canSaveImage && (
        <label className="flex items-start gap-2 text-sm text-gray-300">
          <input
            type="checkbox"
            checked={useAsImage}
            onChange={(e) => setUseAsImage(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            Use the plate preview as the product image
            {selected?.image_url && (
              <span className="block text-gray-500">
                Replaces the product&apos;s current image.
              </span>
            )}
          </span>
        </label>
      )}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => setConfirmOpen(true)}
          disabled={!selected || !source || currentLoading || attaching}
          className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg transition-colors"
        >
          {hasExistingFile ? "Replace slice file" : "Attach slice file"}
        </button>
      </div>

      <ConfirmDialog
        isOpen={confirmOpen}
        title={hasExistingFile ? "Replace slice file?" : "Attach slice file?"}
        message={confirmMessage}
        confirmLabel={hasExistingFile ? "Replace" : "Attach"}
        confirmVariant={hasExistingFile ? "warning" : "info"}
        isLoading={attaching}
        onConfirm={runAttach}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
