import { useState, useEffect, useRef } from "react";
import { API_URL } from "../config/api";
import { useToast } from "./Toast";

/**
 * QCInspectionPhotos — upload / view / delete photos for one QC inspection (#784).
 *
 * Reusable (props: inspectionId). Thumbnails are fetched as blobs with
 * credentials rather than via a bare <img src>, because the download endpoint is
 * auth-gated and, in dev, cross-origin — a plain <img> would not send the cookie.
 */
export default function QCInspectionPhotos({ inspectionId }) {
  const toast = useToast();
  const [photos, setPhotos] = useState([]);
  const [thumbs, setThumbs] = useState({}); // photoId -> object URL
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(false);
  const fileRef = useRef(null);
  const thumbsRef = useRef({}); // mirror of `thumbs` for cleanup without re-renders

  const base = `${API_URL}/api/v1/production-orders/qc-inspections/${inspectionId}/photos`;

  const revokeAll = () => {
    Object.values(thumbsRef.current).forEach((u) => u && URL.revokeObjectURL(u));
    thumbsRef.current = {};
  };

  const load = async () => {
    try {
      const res = await fetch(base, { credentials: "include" });
      if (!res.ok) {
        setError(true); // a failed fetch must not masquerade as an empty gallery
        return;
      }
      setError(false);
      const list = await res.json();
      setPhotos(list);
      const entries = await Promise.all(
        list.map(async (p) => {
          try {
            const r = await fetch(`${API_URL}${p.download_url}`, { credentials: "include" });
            return r.ok ? [p.id, URL.createObjectURL(await r.blob())] : [p.id, null];
          } catch {
            return [p.id, null];
          }
        }),
      );
      revokeAll();
      const map = Object.fromEntries(entries);
      thumbsRef.current = map;
      setThumbs(map);
    } catch {
      setError(true);
    }
  };

  useEffect(() => {
    load();
    return revokeAll;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inspectionId]);

  const onPick = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    setUploading(true);
    try {
      const res = await fetch(base, { method: "POST", credentials: "include", body: fd });
      if (res.ok) {
        await load();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Upload failed");
      }
    } catch (err) {
      toast.error(err.message || "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const remove = async (id) => {
    const res = await fetch(`${base}/${id}`, { method: "DELETE", credentials: "include" });
    if (res.ok) await load();
    else toast.error("Failed to delete photo");
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <label className="text-sm text-gray-400">Photos</label>
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="text-sm text-blue-400 hover:text-blue-300 disabled:opacity-50"
        >
          {uploading ? "Uploading…" : "+ Upload photo"}
        </button>
        <input ref={fileRef} type="file" accept="image/*" onChange={onPick} className="hidden" />
      </div>

      {error ? (
        <p className="text-xs text-red-400">Couldn&apos;t load photos. Please try again.</p>
      ) : photos.length === 0 ? (
        <p className="text-xs text-gray-500">No photos attached.</p>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
          {photos.map((p) => (
            <div key={p.id} className="relative group">
              {thumbs[p.id] ? (
                <img
                  src={thumbs[p.id]}
                  alt={p.caption || p.file_name}
                  className="w-full h-24 object-cover rounded-lg border border-gray-700"
                />
              ) : (
                <div className="w-full h-24 rounded-lg border border-gray-700 bg-gray-800 flex items-center justify-center text-gray-500 text-xs px-1 text-center break-all">
                  {p.file_name}
                </div>
              )}
              <button
                type="button"
                onClick={() => remove(p.id)}
                title="Delete photo"
                className="absolute -top-2 -right-2 bg-red-600 hover:bg-red-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-sm opacity-0 group-hover:opacity-100 transition-opacity"
              >
                &times;
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
