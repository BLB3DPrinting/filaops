/**
 * SerialNumberSettingsSection — the shop-wide serial-number prefix.
 *
 * Serials look like {prefix}YYYYMMDD-NNNN, e.g. SN-20261013-0001. The prefix
 * is the `serial_number_prefix` Company Settings field: readable by staff,
 * changeable by admins only (the server enforces that).
 *
 * Self-contained (own fetch/save + type="button" controls), mirroring
 * QualitySettingsSection, so it composes cleanly inside the AdminSettings form
 * without the main "Save Settings" button ever sending the prefix.
 */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../Toast";
import {
  DEFAULT_SERIAL_PREFIX,
  MAX_SERIAL_PREFIX_LENGTH,
  normalizeSerialPrefix,
} from "./serialPrefix";

function todayStamp() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`;
}

// FastAPI 422 bodies carry a list of errors; 400/403 carry a string.
function errorMessage(status, body) {
  if (status === 403) return "Only admins can change the serial number prefix";
  const detail = body?.detail;
  if (Array.isArray(detail) && detail.length) {
    return String(detail[0].msg || "Invalid prefix").replace(/^Value error, /, "");
  }
  if (typeof detail === "string") return detail;
  return "Failed to save the serial number prefix";
}

export default function SerialNumberSettingsSection() {
  const toast = useToast();
  const [saved, setSaved] = useState(DEFAULT_SERIAL_PREFIX);
  const [input, setInput] = useState(DEFAULT_SERIAL_PREFIX);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/settings/company`, {
          credentials: "include",
        });
        if (res.ok) {
          const data = await res.json();
          const prefix = data.serial_number_prefix || DEFAULT_SERIAL_PREFIX;
          setSaved(prefix);
          setInput(prefix);
        }
      } catch (error) {
        console.error("Failed to load serial number prefix:", error);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const check = normalizeSerialPrefix(input);
  const preview = check.value ?? saved;
  const unchanged = check.value === saved;

  const handleSave = async () => {
    if (check.error || unchanged) return;
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/settings/company`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ serial_number_prefix: check.value }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(errorMessage(res.status, body));
      const prefix = body.serial_number_prefix || check.value;
      setSaved(prefix);
      setInput(prefix);
      toast.success("Serial number prefix saved");
    } catch (error) {
      toast.error(error.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-6 text-gray-400">
        Loading serial number settings…
      </div>
    );
  }

  return (
    <div className="bg-gray-800 rounded-lg p-6">
      <h2 className="text-xl font-semibold text-white mb-1">Serial Numbers</h2>
      <p className="text-sm text-gray-400 mb-4">
        Prefix for the serial numbers given to finished units of serial-tracked
        products. Changing it affects new serials only; existing serials keep
        their numbers.
      </p>
      <label
        htmlFor="serial_number_prefix"
        className="block text-sm font-medium text-gray-300 mb-1"
      >
        Serial Number Prefix
      </label>
      <input
        id="serial_number_prefix"
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          // This section sits inside the AdminSettings form: Enter here must
          // save the prefix, not submit the company form (which ignores it).
          if (e.key === "Enter") {
            e.preventDefault();
            if (!saving) handleSave();
          }
        }}
        maxLength={MAX_SERIAL_PREFIX_LENGTH + 4}
        aria-invalid={Boolean(check.error)}
        aria-describedby="serial_number_prefix_help"
        className="w-full md:w-48 bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
        placeholder={DEFAULT_SERIAL_PREFIX}
      />
      <p id="serial_number_prefix_help" className="text-sm mt-1">
        {check.error ? (
          <span className="text-red-400">{check.error}</span>
        ) : (
          <span className="text-gray-500">
            Letters, digits and dashes; a trailing dash is added for you.
            Serials will look like{" "}
            <span className="font-mono text-gray-300">
              {preview}
              {todayStamp()}-0001
            </span>
          </span>
        )}
      </p>
      <div className="flex justify-end pt-4">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving || Boolean(check.error) || unchanged}
          className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg transition-colors"
        >
          {saving ? "Saving…" : "Save Serial Prefix"}
        </button>
      </div>
    </div>
  );
}
