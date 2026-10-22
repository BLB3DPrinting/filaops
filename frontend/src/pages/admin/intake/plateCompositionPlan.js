/**
 * Pure helpers for the plate-composition intake panel: turning PRO's preview
 * of a multi-plate vendor file into editable part rows, the CompositionPlan
 * the commit call sends, and the messages an operator sees.
 *
 * PRO contract: POST /api/v1/pro/intake/compositions with just the file answers
 * with a preview; with `plan` (a CompositionPlan as JSON) as well, it saves
 * everything in one transaction. Group keys (`hash:...` / `name:...`) tie the
 * preview's parts to the plan's parts.
 */

export const COMPOSITIONS_URL = "/api/v1/pro/intake/compositions";

/** Q7: parts are components unless also sold loose. */
export const ITEM_TYPES = [
  { value: "component", label: "Component" },
  { value: "finished_good", label: "Finished good (also sold loose)" },
];

const lower = (value) => (value || "").toLowerCase();
const positive = (value) => Number(value) > 0;

/** "3h 15m", "1h", "3m", "<1m"; "" when there is no number. */
export function formatMinutes(minutes) {
  if (minutes == null || Number.isNaN(Number(minutes))) return "";
  const total = Math.round(Number(minutes));
  if (total < 1) return Number(minutes) > 0 ? "<1m" : "0m";
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h && m) return `${h}h ${m}m`;
  return h ? `${h}h` : `${m}m`;
}

/** "25 g", "1.2 g"; "" when there is no number. */
export function formatGrams(grams) {
  if (grams == null || Number.isNaN(Number(grams))) return "";
  return `${Number(Number(grams).toFixed(1))} g`;
}

/** What to call a kind of object: all the names it goes by. */
export const partLabel = (part) =>
  part.names?.length ? part.names.join(" / ") : part.name || part.key;

/**
 * What a part row starts as. A part we already have for the same mesh is
 * pre-selected (PRO lists them oldest first); otherwise it is created, as a
 * component, with the name and SKU PRO suggests.
 */
function defaultRow(part) {
  const proposal = part.existing_parts?.[0] ?? null;
  return {
    key: part.key,
    part,
    action: proposal ? "link" : "create",
    linked: proposal,
    name: part.suggested_name || "",
    sku: part.suggested_sku || "",
    itemType: "component",
    perParent: "1",
  };
}

/** One row per kind of object in the file, with the operator's `edits` (by key) on top. */
export function buildRows(preview, edits) {
  return (preview?.parts ?? []).map((part) => ({
    ...defaultRow(part),
    ...edits[part.key],
  }));
}

/** The filament slots (0-based, ascending) the parts being created print with. */
export function neededSlots(rows) {
  const slots = new Set();
  for (const row of rows) {
    if (row.action !== "create") continue;
    for (const slot of Object.keys(row.part.slot_grams ?? {})) slots.add(Number(slot));
  }
  return [...slots].sort((a, b) => a - b);
}

/** Slot -> { material, colorHex }, from the plates' totals. */
export function slotMeta(preview) {
  const meta = {};
  for (const plate of preview?.plates ?? []) {
    for (const slot of plate.slots ?? []) {
      if (!(slot.slot in meta)) {
        meta[slot.slot] = { material: slot.material ?? null, colorHex: slot.color_hex ?? null };
      }
    }
  }
  return meta;
}

/** The one catalog spool with a slot's material and colour; null if none or several. */
export function suggestSpool(slot, materials) {
  if (!slot?.material || !slot.colorHex) return null;
  const hits = materials.filter(
    (item) =>
      lower(item.material_code) === lower(slot.material) &&
      lower(item.color_hex) === lower(slot.colorHex),
  );
  return hits.length === 1 ? hits[0] : null;
}

const slotName = (slot, meta) => {
  const m = meta[slot];
  const what = [m?.material, m?.colorHex].filter(Boolean).join(" ");
  return `slot ${slot + 1}${what ? ` (${what})` : ""}`;
};

/**
 * What stops this form from being saved, in words; empty when it is ready.
 * @param {object} form
 * @param {string} form.name - the plan (model) name.
 * @param {string} form.workCenterId - the print work centre.
 * @param {Array<object>} form.rows - from buildRows.
 * @param {Object<number, number|string>} form.spoolIds - slot -> spool product id.
 * @param {Object<number, {material: string|null, colorHex: string|null}>} form.meta - from slotMeta.
 * @param {object|null} form.parent - null, or { name, sku, workCenterId, runMinutes, setupMinutes }.
 * @returns {string[]}
 */
export function planProblems({ name, workCenterId, rows, spoolIds, meta, parent }) {
  const problems = [];
  if (!name.trim()) problems.push("Give the model a name.");
  if (!workCenterId) problems.push("Choose the print work centre.");
  for (const row of rows) {
    const label = partLabel(row.part);
    if (row.action === "link" && !row.linked) {
      problems.push(`${label}: choose the existing part, or create a new one.`);
    }
    if (row.action === "create" && !row.name.trim()) {
      problems.push(`${label}: give the new part a name.`);
    }
  }
  for (const slot of neededSlots(rows)) {
    if (!spoolIds[slot]) problems.push(`Choose a spool for ${slotName(slot, meta)}.`);
  }
  if (parent) {
    if (!parent.name.trim()) problems.push("Give the assembly parent a name.");
    if (!parent.workCenterId) problems.push("Choose the assembly work centre for the parent.");
    if (!rows.some((row) => positive(row.perParent))) {
      problems.push("Put at least one part in the parent (a quantity above 0).");
    }
  }
  return problems;
}

/** The CompositionPlan to send. Call only once planProblems is empty. */
export function buildPlan({ name, workCenterId, rows, spoolIds, meta, parent }) {
  const plan = {
    name: name.trim(),
    print_work_center_id: Number(workCenterId),
    slot_spools: neededSlots(rows).map((slot) => ({
      slot,
      spool_product_id: Number(spoolIds[slot]),
      filament_type: meta[slot]?.material ?? null,
      color_hex: meta[slot]?.colorHex ?? null,
    })),
    parts: rows.map((row) =>
      row.action === "link"
        ? { key: row.key, action: "link", product_id: row.linked.product_id }
        : {
            key: row.key,
            action: "create",
            name: row.name.trim(),
            ...(row.sku.trim() ? { sku: row.sku.trim() } : {}),
            item_type: row.itemType,
          },
    ),
  };
  if (parent) {
    plan.parent = {
      name: parent.name.trim(),
      ...(parent.sku.trim() ? { sku: parent.sku.trim() } : {}),
      assembly_work_center_id: Number(parent.workCenterId),
      assembly_run_time_minutes: Number(parent.runMinutes) || 0,
      assembly_setup_minutes: Number(parent.setupMinutes) || 0,
      quantities: Object.fromEntries(
        rows.filter((row) => positive(row.perParent)).map((row) => [row.key, Number(row.perParent)]),
      ),
    };
  }
  return plan;
}

const plainValidation = (msg) => String(msg || "").replace(/^Value error, /, "");

/**
 * Words for a failed call. PRO answers 4xx with `detail`: a sentence, or (for
 * a plan that doesn't parse) a list of { loc, msg }. A 404 whose detail is just
 * "Not Found" is a backend without the route, not a missing part.
 * @returns {{status: number, message: string}}
 */
export function describeIntakeError(error) {
  const status = Number(error?.status) || 0;
  const detail = error?.payload?.detail;
  if (status === 0 && error?.status !== undefined) {
    return { status, message: "Couldn't reach the server. Check the connection and try again." };
  }
  if (status === 404 && detail === "Not Found") {
    return {
      status,
      message:
        "This server's PRO backend doesn't have plate layouts yet — update PRO, then try again.",
    };
  }
  if (typeof detail === "string" && detail) return { status, message: detail };
  if (Array.isArray(detail) && detail.length) {
    const lines = detail.map((item) => {
      const where = Array.isArray(item?.loc) ? item.loc.join(".") : "";
      const what = plainValidation(item?.msg);
      return where ? `${where}: ${what}` : what;
    });
    return { status, message: lines.join("; ") };
  }
  return { status, message: error?.message || "Request failed" };
}
