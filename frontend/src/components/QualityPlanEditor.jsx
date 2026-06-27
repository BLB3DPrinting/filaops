import { useState, useRef, useEffect } from "react";
import Modal from "./Modal";
import { useApi } from "../hooks/useApi";
import { useToast } from "./Toast";
import { slugifyCode } from "./qualityPlanEditor.utils";

const SEVERITIES = ["minor", "major", "critical"];

let _rowSeq = 0;
const blankRow = () => ({
  key: ++_rowSeq,
  code: "",
  codeTouched: false,
  characteristic: "",
  characteristic_type: "variable",
  nominal: "",
  lower_limit: "",
  upper_limit: "",
  unit: "",
  acceptance_criteria: "",
  severity: "",
});

const rowFromChar = (c) => ({
  key: ++_rowSeq,
  code: c.code ?? "",
  codeTouched: Boolean(c.code),
  characteristic: c.characteristic ?? "",
  characteristic_type: c.characteristic_type ?? "variable",
  nominal: c.nominal ?? "",
  lower_limit: c.lower_limit ?? "",
  upper_limit: c.upper_limit ?? "",
  unit: c.unit ?? "",
  acceptance_criteria: c.acceptance_criteria ?? "",
  severity: c.severity ?? "",
});

const inputCls =
  "w-full rounded-md bg-[var(--bg-secondary)] border border-[var(--border-subtle)] px-2 py-1.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-cyan-500/50";
const labelCls = "block text-xs font-medium text-[var(--text-muted)] mb-1";

/**
 * QualityPlanEditor — create or edit a per-product (or template) quality plan
 * and its characteristic grid. PR-5b (#784).
 *
 * Props:
 *   plan    — existing plan to edit, or null/undefined to create
 *   onClose — dismiss without saving
 *   onSaved — called after a successful create/update
 */
export default function QualityPlanEditor({ plan, onClose, onSaved }) {
  const api = useApi();
  const toast = useToast();
  const isEdit = Boolean(plan?.id);

  const [isTemplate, setIsTemplate] = useState(plan?.is_template ?? false);
  const [productId, setProductId] = useState(plan?.product_id ?? null);
  const [productLabel, setProductLabel] = useState("");
  const [code, setCode] = useState(plan?.code ?? "");
  const [name, setName] = useState(plan?.name ?? "");
  const [version, setVersion] = useState(plan?.version ?? 1);
  const [revision, setRevision] = useState(plan?.revision ?? "1.0");
  const [effectiveDate, setEffectiveDate] = useState(plan?.effective_date ?? "");
  const [isActive, setIsActive] = useState(plan?.is_active ?? true);
  const [notes, setNotes] = useState(plan?.notes ?? "");
  const [rows, setRows] = useState(() =>
    plan?.characteristics?.length
      ? plan.characteristics.map(rowFromChar)
      : [blankRow()]
  );

  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState(null);

  // Product typeahead state
  const [search, setSearch] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [queried, setQueried] = useState(""); // term the current results belong to

  // Resolve the initial product's human-readable label once (edit mode).
  const initialLabelLoaded = useRef(false);
  useEffect(() => {
    if (initialLabelLoaded.current) return;
    initialLabelLoaded.current = true;
    if (isTemplate || productId == null) return;
    let active = true;
    api
      .get(`/api/v1/items/${productId}`)
      .then((item) => {
        if (active) setProductLabel(`${item.sku} — ${item.name}`);
      })
      .catch(() => {
        /* fall back to "Product #id" below */
      });
    return () => {
      active = false;
    };
  }, [api, isTemplate, productId]);

  // Debounced server-side product search (scales to any catalog; no silent cap).
  // All state updates happen inside the debounce callback so nothing is set
  // synchronously in the effect body; result UI is gated on `search` in render.
  useEffect(() => {
    if (isTemplate) return;
    const q = search.trim();
    if (!q) return;
    let active = true;
    const t = setTimeout(async () => {
      if (active) setSearching(true);
      try {
        const data = await api.get(
          `/api/v1/items?search=${encodeURIComponent(q)}&active_only=true&limit=25`
        );
        if (active) setResults(data.items || []);
      } catch {
        if (active) setResults([]);
      } finally {
        if (active) {
          setQueried(q);
          setSearching(false);
        }
      }
    }, 250);
    return () => {
      active = false;
      clearTimeout(t);
    };
  }, [search, isTemplate, api]);

  const updateRow = (key, patch) =>
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const addRow = () => setRows((rs) => [...rs, blankRow()]);
  const removeRow = (key) => setRows((rs) => rs.filter((r) => r.key !== key));

  // Switching to "attribute" clears the spec-limit fields (they're meaningless
  // for pass/fail); switching back to "variable" clears acceptance criteria.
  const setRowType = (key, type) =>
    updateRow(
      key,
      type === "attribute"
        ? { characteristic_type: type, nominal: "", lower_limit: "", upper_limit: "", unit: "" }
        : { characteristic_type: type, acceptance_criteria: "" }
    );

  // Auto-fill the code from the name on blur, unless the user has set one.
  const onCharacteristicBlur = (row) => {
    if (!row.codeTouched && !row.code.trim() && row.characteristic.trim()) {
      updateRow(row.key, { code: slugifyCode(row.characteristic) });
    }
  };

  const pickProduct = (item) => {
    setProductId(item.id);
    setProductLabel(`${item.sku} — ${item.name}`);
    setSearch("");
    setResults([]);
    setQueried("");
  };

  const onToggleTemplate = (checked) => {
    setIsTemplate(checked);
    if (checked) {
      setProductId(null);
      setProductLabel("");
      setSearch("");
      setResults([]);
      setQueried("");
      setSearching(false);
    }
  };

  const buildPayload = () => {
    // Validate header fields that have non-null persisted values, so a cleared
    // or zeroed field can't silently overwrite a stored value on edit.
    const parsedVersion = Number(version);
    if (!Number.isInteger(parsedVersion) || parsedVersion < 1) {
      throw new Error("Version must be a positive integer.");
    }
    const trimmedRevision = revision.trim();
    if (!trimmedRevision) {
      throw new Error("Revision is required.");
    }

    const cleaned = [];
    for (const r of rows) {
      const ch = r.characteristic.trim();
      const isAttr = r.characteristic_type === "attribute";
      const anyData =
        ch ||
        r.code.trim() ||
        r.nominal !== "" ||
        r.lower_limit !== "" ||
        r.upper_limit !== "" ||
        r.unit.trim() ||
        r.acceptance_criteria.trim() ||
        r.severity;
      if (!anyData) continue; // skip an untouched scaffold row
      if (!ch) throw new Error("Each characteristic needs a name.");
      if (
        !isAttr &&
        r.lower_limit !== "" &&
        r.upper_limit !== "" &&
        Number(r.lower_limit) > Number(r.upper_limit)
      ) {
        throw new Error(`"${ch}": lower limit cannot exceed upper limit.`);
      }
      cleaned.push(r);
    }
    const codes = cleaned.map((r) => r.code.trim()).filter(Boolean);
    const dupe = codes.find((c, i) => codes.indexOf(c) !== i);
    if (dupe) throw new Error(`Duplicate characteristic code: ${dupe}`);

    return {
      product_id: isTemplate ? null : productId,
      code: code.trim(),
      name: name.trim(),
      version: parsedVersion,
      revision: trimmedRevision,
      is_active: isActive,
      is_template: isTemplate,
      effective_date: effectiveDate || null,
      notes: notes.trim() || null,
      characteristics: cleaned.map((r, idx) => {
        // Attribute (pass/fail) rows carry no spec limits/unit; variable rows
        // carry no acceptance criteria. Force the irrelevant fields null so the
        // backend never sees a stale value the other type left behind.
        const isAttr = r.characteristic_type === "attribute";
        return {
          code: r.code.trim() || null,
          characteristic: r.characteristic.trim(),
          characteristic_type: r.characteristic_type,
          nominal: isAttr || r.nominal === "" ? null : r.nominal,
          lower_limit: isAttr || r.lower_limit === "" ? null : r.lower_limit,
          upper_limit: isAttr || r.upper_limit === "" ? null : r.upper_limit,
          unit: isAttr ? null : r.unit.trim() || null,
          acceptance_criteria: isAttr
            ? r.acceptance_criteria.trim() || null
            : null,
          severity: r.severity || null,
          sequence: idx,
        };
      }),
    };
  };

  const handleSave = async () => {
    setFormError(null);
    if (!name.trim()) {
      setFormError("Plan name is required.");
      return;
    }
    if (!code.trim()) {
      setFormError("Plan code is required.");
      return;
    }
    if (!isTemplate && productId == null) {
      setFormError("Pick a product, or mark this plan as a template.");
      return;
    }
    let payload;
    try {
      payload = buildPayload();
    } catch (e) {
      setFormError(e.message);
      return;
    }
    setSaving(true);
    try {
      if (isEdit) {
        await api.patch(`/api/v1/quality-plans/${plan.id}`, payload);
      } else {
        await api.post(`/api/v1/quality-plans`, payload);
      }
      toast.success(isEdit ? "Quality plan updated" : "Quality plan created");
      onSaved?.();
    } catch (err) {
      setFormError(err?.message || "Failed to save the quality plan.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen
      onClose={onClose}
      disableClose={saving}
      title={isEdit ? "Edit quality plan" : "New quality plan"}
      className="w-full max-w-3xl"
    >
      <div className="flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border-subtle)]">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
            {isEdit ? "Edit quality plan" : "New quality plan"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            aria-label="Close"
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)] disabled:opacity-50"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 overflow-y-auto space-y-5">
          {formError && (
            <div
              role="alert"
              className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm"
            >
              {formError}
            </div>
          )}

          {/* Scope */}
          <div className="space-y-2">
            <label className="inline-flex items-center gap-2 text-sm text-[var(--text-primary)]">
              <input
                type="checkbox"
                checked={isTemplate}
                onChange={(e) => onToggleTemplate(e.target.checked)}
                className="rounded border-[var(--border-subtle)]"
              />
              Reusable template (not tied to a product)
            </label>

            {!isTemplate && (
              <div>
                <label className={labelCls} htmlFor="qp-product-search">
                  Product
                </label>
                {productId != null && (
                  <div className="mb-2 text-sm text-[var(--text-secondary)]">
                    Selected:{" "}
                    <span className="text-[var(--text-primary)] font-medium">
                      {productLabel || `Product #${productId}`}
                    </span>
                  </div>
                )}
                <input
                  id="qp-product-search"
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search products by SKU or name…"
                  className={inputCls}
                />
                {search.trim() && searching && (
                  <div
                    role="status"
                    className="mt-1 text-xs text-[var(--text-muted)]"
                  >
                    Searching…
                  </div>
                )}
                {/* Gate results on `queried === search` so a previous term's
                    results aren't shown (and clickable) while a newer search is
                    in flight — a stale click would pick the wrong product. */}
                {search.trim() && queried === search.trim() && results.length > 0 && (
                  // A list of buttons (not a multi-row <select>): arrowing a
                  // sized select fires onChange per keypress and would commit +
                  // unmount on the first option, trapping keyboard users.
                  <ul
                    aria-label="Matching products"
                    className="mt-1 max-h-48 overflow-y-auto rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] divide-y divide-[var(--border-subtle)]"
                  >
                    {results.map((item) => (
                      <li key={item.id}>
                        <button
                          type="button"
                          onClick={() => pickProduct(item)}
                          className="w-full text-left px-2 py-1.5 text-sm text-[var(--text-primary)] hover:bg-[var(--bg-card)] focus:bg-[var(--bg-card)] focus:outline-none"
                        >
                          {item.sku} — {item.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {search.trim() &&
                  !searching &&
                  queried === search.trim() &&
                  results.length === 0 && (
                    <div
                      role="status"
                      className="mt-1 text-xs text-[var(--text-muted)]"
                    >
                      No matching products.
                    </div>
                  )}
              </div>
            )}
          </div>

          {/* Plan header fields */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className={labelCls} htmlFor="qp-code">
                Plan code *
              </label>
              <input
                id="qp-code"
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="e.g. QP-WIDGET-A"
                maxLength={50}
                className={inputCls}
              />
            </div>
            <div>
              <label className={labelCls} htmlFor="qp-name">
                Plan name *
              </label>
              <input
                id="qp-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Incoming inspection plan"
                maxLength={200}
                className={inputCls}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelCls} htmlFor="qp-version">
                  Version
                </label>
                <input
                  id="qp-version"
                  type="number"
                  min={1}
                  step={1}
                  value={version}
                  onChange={(e) => setVersion(e.target.value)}
                  className={inputCls}
                />
              </div>
              <div>
                <label className={labelCls} htmlFor="qp-revision">
                  Revision *
                </label>
                <input
                  id="qp-revision"
                  type="text"
                  value={revision}
                  onChange={(e) => setRevision(e.target.value)}
                  maxLength={20}
                  className={inputCls}
                />
              </div>
            </div>
            <div>
              <label className={labelCls} htmlFor="qp-effective">
                Effective date
              </label>
              <input
                id="qp-effective"
                type="date"
                value={effectiveDate || ""}
                onChange={(e) => setEffectiveDate(e.target.value)}
                className={inputCls}
              />
            </div>
          </div>

          <div>
            <label className={labelCls} htmlFor="qp-notes">
              Notes
            </label>
            <textarea
              id="qp-notes"
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className={inputCls}
            />
          </div>

          <label className="inline-flex items-center gap-2 text-sm text-[var(--text-primary)]">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="rounded border-[var(--border-subtle)]"
            />
            Active
          </label>

          {/* Characteristic grid */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-[var(--text-primary)] uppercase tracking-wider">
                Characteristics
              </h3>
              <button
                type="button"
                onClick={addRow}
                className="text-xs px-2 py-1 rounded-md border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
              >
                + Add characteristic
              </button>
            </div>
            <div className="overflow-x-auto border border-[var(--border-subtle)] rounded-lg">
              <table className="w-full text-sm min-w-[820px]">
                <thead>
                  <tr className="border-b border-[var(--border-subtle)] text-left">
                    <th className="px-2 py-2 text-[var(--text-muted)] font-medium">
                      Code
                    </th>
                    <th className="px-2 py-2 text-[var(--text-muted)] font-medium">
                      Characteristic *
                    </th>
                    <th className="px-2 py-2 text-[var(--text-muted)] font-medium">
                      Type
                    </th>
                    <th className="px-2 py-2 text-[var(--text-muted)] font-medium">
                      Nominal
                    </th>
                    <th className="px-2 py-2 text-[var(--text-muted)] font-medium">
                      LSL
                    </th>
                    <th className="px-2 py-2 text-[var(--text-muted)] font-medium">
                      USL
                    </th>
                    <th className="px-2 py-2 text-[var(--text-muted)] font-medium">
                      Unit
                    </th>
                    <th className="px-2 py-2 text-[var(--text-muted)] font-medium">
                      Severity
                    </th>
                    <th className="px-2 py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-subtle)]">
                  {rows.map((r) => (
                    <tr key={r.key}>
                      <td className="px-2 py-1.5">
                        <input
                          type="text"
                          value={r.code}
                          onChange={(e) =>
                            updateRow(r.key, {
                              code: e.target.value,
                              codeTouched: true,
                            })
                          }
                          placeholder="auto"
                          maxLength={50}
                          aria-label="Characteristic code"
                          className={`${inputCls} min-w-[7rem]`}
                        />
                      </td>
                      <td className="px-2 py-1.5">
                        <input
                          type="text"
                          value={r.characteristic}
                          onChange={(e) =>
                            updateRow(r.key, { characteristic: e.target.value })
                          }
                          onBlur={() => onCharacteristicBlur(r)}
                          maxLength={100}
                          aria-label="Characteristic name"
                          className={`${inputCls} min-w-[10rem]`}
                        />
                      </td>
                      <td className="px-2 py-1.5">
                        <select
                          value={r.characteristic_type}
                          onChange={(e) => setRowType(r.key, e.target.value)}
                          aria-label="Characteristic type"
                          className={`${inputCls} min-w-[7rem]`}
                        >
                          <option value="variable">Variable</option>
                          <option value="attribute">Attribute</option>
                        </select>
                      </td>
                      {r.characteristic_type === "attribute" ? (
                        <td className="px-2 py-1.5" colSpan={4}>
                          <input
                            type="text"
                            value={r.acceptance_criteria}
                            onChange={(e) =>
                              updateRow(r.key, {
                                acceptance_criteria: e.target.value,
                              })
                            }
                            placeholder="Pass/fail acceptance criteria (e.g. no visible defects)"
                            aria-label="Acceptance criteria"
                            className={`${inputCls} min-w-[12rem]`}
                          />
                        </td>
                      ) : (
                        <>
                          <td className="px-2 py-1.5">
                            <input
                              type="number"
                              step="any"
                              value={r.nominal}
                              onChange={(e) =>
                                updateRow(r.key, { nominal: e.target.value })
                              }
                              aria-label="Nominal"
                              className={`${inputCls} min-w-[5rem]`}
                            />
                          </td>
                          <td className="px-2 py-1.5">
                            <input
                              type="number"
                              step="any"
                              value={r.lower_limit}
                              onChange={(e) =>
                                updateRow(r.key, { lower_limit: e.target.value })
                              }
                              aria-label="Lower spec limit"
                              className={`${inputCls} min-w-[5rem]`}
                            />
                          </td>
                          <td className="px-2 py-1.5">
                            <input
                              type="number"
                              step="any"
                              value={r.upper_limit}
                              onChange={(e) =>
                                updateRow(r.key, { upper_limit: e.target.value })
                              }
                              aria-label="Upper spec limit"
                              className={`${inputCls} min-w-[5rem]`}
                            />
                          </td>
                          <td className="px-2 py-1.5">
                            <input
                              type="text"
                              value={r.unit}
                              onChange={(e) =>
                                updateRow(r.key, { unit: e.target.value })
                              }
                              maxLength={20}
                              aria-label="Unit"
                              className={`${inputCls} min-w-[4rem]`}
                            />
                          </td>
                        </>
                      )}
                      <td className="px-2 py-1.5">
                        <select
                          value={r.severity}
                          onChange={(e) =>
                            updateRow(r.key, { severity: e.target.value })
                          }
                          aria-label="Severity"
                          className={`${inputCls} min-w-[6rem]`}
                        >
                          <option value="">—</option>
                          {SEVERITIES.map((s) => (
                            <option key={s} value={s}>
                              {s}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        <button
                          type="button"
                          onClick={() => removeRow(r.key)}
                          aria-label="Remove characteristic"
                          className="text-[var(--text-muted)] hover:text-red-400 px-1"
                        >
                          ✕
                        </button>
                      </td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr>
                      <td
                        colSpan={9}
                        className="px-2 py-4 text-center text-[var(--text-muted)]"
                      >
                        No characteristics. Add one to inspect against this plan.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              Code is derived from the name and stays stable if you rename the
              characteristic — it&apos;s the key SPC trends are grouped by.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-[var(--border-subtle)]">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 rounded-md text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)] disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 rounded-md text-sm font-medium bg-cyan-600 text-white hover:bg-cyan-500 disabled:opacity-50"
          >
            {saving ? "Saving…" : isEdit ? "Save changes" : "Create plan"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
