/**
 * AmsSlots — every AMS slot on a printer, grouped by AMS unit.
 *
 * Reads PRO FilaFarm telemetry merged onto the printer: `ams_slots`
 * ({slot, unit, tray, material, brand, color, remaining_pct, active}) and
 * `ams_units` ({id, type, env_sensors, humidity_pct, temp_c}).
 *
 * remaining_pct is null when Bambu doesn't know it (spools without an RFID
 * tag), so it shows "?" rather than 0%. Humidity and temperature show only for
 * AMS units that have the sensors; an AMS lite has none.
 */

function unitOf(slot) {
  if (Number.isInteger(slot.unit)) return slot.unit;
  return Math.floor((Number(slot.slot || 1) - 1) / 4); // older PRO: 4 slots per unit
}

function envText(unit) {
  if (!unit?.env_sensors) return null;
  const parts = [];
  if (unit.humidity_pct != null) parts.push(`${unit.humidity_pct}% RH`);
  if (unit.temp_c != null) parts.push(`${Math.round(unit.temp_c)}°C`);
  return parts.length ? parts.join(" · ") : null;
}

export default function AmsSlots({ slots, units }) {
  if (!Array.isArray(slots) || slots.length === 0) return null;
  const unitInfo = new Map((Array.isArray(units) ? units : []).map((u) => [u.id, u]));
  const groups = new Map();
  for (const slot of slots) {
    const id = unitOf(slot);
    if (!groups.has(id)) groups.set(id, []);
    groups.get(id).push(slot);
  }

  return (
    <div className="mt-3 space-y-3" data-testid="ams-slots">
      {[...groups.entries()].map(([unitId, unitSlots]) => {
        const env = envText(unitInfo.get(unitId));
        return (
          <div key={unitId} className="rounded-2xl border border-slate-800 bg-slate-950/80 p-3">
            <div className="mb-2 flex items-center justify-between text-[11px] uppercase tracking-[0.16em] text-slate-500">
              <span>AMS {unitId + 1}</span>
              {env && <span data-testid={`ams-env-${unitId}`}>{env}</span>}
            </div>
            <div className="grid grid-cols-4 gap-2">
              {unitSlots.map((slot) => {
                const known = slot.remaining_pct != null;
                return (
                  <div
                    key={slot.slot}
                    data-testid={`ams-slot-${slot.slot}`}
                    className={`rounded-xl border p-2 text-xs ${
                      slot.active ? "border-emerald-400/60 bg-emerald-500/10" : "border-slate-800"
                    }`}
                    title={slot.brand || slot.material || "Empty"}
                  >
                    <div className="flex items-center gap-1.5">
                      <span
                        aria-hidden="true"
                        className="inline-block h-3 w-3 shrink-0 rounded-full border border-white/20"
                        style={{ backgroundColor: slot.color || "transparent" }}
                      />
                      <span className="truncate font-medium text-slate-100">
                        {slot.material || "Empty"}
                      </span>
                    </div>
                    <div className="mt-1 flex justify-between text-slate-400">
                      <span>{slot.active ? "Active" : `Slot ${slot.slot}`}</span>
                      {slot.material && (
                        <span title={known ? undefined : "Unknown: the spool has no RFID tag"}>
                          {known ? `${slot.remaining_pct}%` : "?"}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
