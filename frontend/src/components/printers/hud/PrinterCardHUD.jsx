import { T, STATUS_CFG } from "./tokens";
import TempGauge from "./TempGauge";

/**
 * Industrial HUD printer card.
 *
 * Tier behavior — Core (free) passes `onCommand=undefined`, which hides the
 * pause/resume/cancel control strip. Live telemetry fields (nozzle_temp,
 * bed_temp, progress, current_job, ams_slots) degrade gracefully when the
 * backend has no MQTT data for a printer — gauges show "--", progress bar
 * is hidden, AMS row is hidden.
 *
 * Props:
 *   printer      — Printer object from /api/v1/printers; status required
 *   onEdit(p)    — handler for the edit icon button
 *   onRemove(p)  — handler for the remove icon button
 *   onCommand?   — (printerId, cmd) → void. When provided, enables PRO
 *                  fleet controls (pause / resume / cancel).
 */
export default function PrinterCardHUD({ printer, onEdit, onRemove, onCommand }) {
  // Normalize the status key: backend MQTT monitor can emit "unknown" as a
  // transient state (see services/mqtt/monitor.py), which is not in the
  // Pydantic PrinterStatus enum but still reaches the UI via telemetry JSON.
  // Lowercase so case-mismatched strings still resolve to the right entry.
  const statusKey = String(printer.status ?? "").toLowerCase();
  const cfg = STATUS_CFG[statusKey] || STATUS_CFG.unknown;
  const isPrinting = statusKey === "printing";
  const isActive = isPrinting || statusKey === "paused";
  const showControls = Boolean(onCommand) && isActive;
  // Clamp progress to [0, 100] so out-of-range values from telemetry can't
  // push the CSS width bar off the card or show "115%" to operators.
  const progressPct = Math.max(0, Math.min(100, Number(printer.progress ?? 0) || 0));

  return (
    <div
      style={{
        background: T.surface,
        border: `1px solid ${cfg.border}`,
        borderLeft: `3px solid ${cfg.dot}`,
        borderRadius: 8,
        padding: "24px 28px",
        display: "flex",
        flexDirection: "column",
        gap: 18,
        transition: "box-shadow 0.2s, border-color 0.2s",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = cfg.dot;
        e.currentTarget.style.boxShadow = `0 0 16px -4px ${cfg.glow}`;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = cfg.border;
        e.currentTarget.style.borderLeftColor = cfg.dot;
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontFamily: T.fontDisplay,
              fontWeight: 700,
              fontSize: 22,
              letterSpacing: "0.04em",
              color: T.textPrimary,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {printer.name}
          </div>
          <div
            style={{
              fontFamily: T.fontMono,
              fontSize: 14,
              color: T.textMuted,
              marginTop: 4,
              letterSpacing: "0.06em",
            }}
          >
            {printer.model}
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: 8, flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                flexShrink: 0,
                background: cfg.dot,
                boxShadow: isPrinting ? `0 0 6px 2px ${cfg.glow}` : "none",
                animation: isPrinting ? "pulse-dot 1.4s ease-in-out infinite" : "none",
                display: "inline-block",
              }}
            />
            <span
              style={{
                fontFamily: T.fontDisplay,
                fontWeight: 600,
                fontSize: 14,
                letterSpacing: "0.12em",
                color: cfg.dot,
              }}
            >
              {cfg.label}
            </span>
          </div>
          {onEdit && (
            <IconBtn onClick={() => onEdit(printer)} title="Edit" hoverColor={T.textSecondary}>
              ✎
            </IconBtn>
          )}
          {onRemove && (
            <IconBtn onClick={() => onRemove(printer)} title="Remove" hoverColor={T.red}>
              ✕
            </IconBtn>
          )}
        </div>
      </div>

      {/* Temperature gauges */}
      <div style={{ display: "flex", justifyContent: "space-around", paddingTop: 4 }}>
        <TempGauge value={printer.nozzle_temp ?? 0} max={300} color={T.amber}   label="NOZZLE" />
        <TempGauge value={printer.bed_temp    ?? 0} max={120} color={T.emerald} label="BED"    />
      </div>

      {/* Progress bar — only while printing and we have data */}
      {isPrinting && printer.progress != null && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
            <span
              style={{
                fontFamily: T.fontMono,
                fontSize: 9,
                color: T.textMuted,
                letterSpacing: "0.05em",
              }}
            >
              {printer.current_job || "PRINTING"}
            </span>
            <span
              style={{
                fontFamily: T.fontMono,
                fontSize: 10,
                fontWeight: 600,
                color: T.emerald,
              }}
            >
              {progressPct.toFixed(0)}%
            </span>
          </div>
          <div
            style={{ height: 4, background: T.border, borderRadius: 2, overflow: "hidden" }}
            role="progressbar"
            aria-valuenow={progressPct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Print progress ${progressPct.toFixed(0)} percent`}
          >
            <div
              style={{
                height: "100%",
                width: `${progressPct}%`,
                background: `linear-gradient(90deg, ${T.emerald}, #34D399)`,
                borderRadius: 2,
                transition: "width 1s ease",
              }}
            />
          </div>
        </div>
      )}

      {/* AMS slots — only when the printer reports multi-material state.
          Color-only UI is inaccessible on its own, so each swatch carries
          a role="img" + aria-label describing slot number and material. */}
      {printer.ams_slots?.length > 0 && (
        <div>
          <div
            id={`ams-label-${printer.id}`}
            style={{
              fontFamily: T.fontDisplay,
              fontWeight: 600,
              fontSize: 9,
              letterSpacing: "0.14em",
              color: T.textMuted,
              marginBottom: 5,
            }}
          >
            AMS SLOTS
          </div>
          <div
            role="list"
            aria-labelledby={`ams-label-${printer.id}`}
            style={{ display: "flex", gap: 6, flexWrap: "wrap" }}
          >
            {printer.ams_slots.map((slot, i) => {
              const slotNum = slot.slot ?? i + 1;
              const slotLabel = `Slot ${slotNum}: ${slot.material || "empty"}`;
              return (
                <div
                  key={i}
                  role="listitem"
                  aria-label={slotLabel}
                  title={slotLabel}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: 2,
                  }}
                >
                  <div
                    style={{
                      width: 18,
                      height: 18,
                      borderRadius: 3,
                      background: slot.color || T.raised,
                      border: `1px solid ${T.borderHover}`,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {/* Slot number inside swatch — mix-blend-mode: difference
                        auto-inverts against any background color so the
                        digit stays legible without per-color contrast math. */}
                    <span
                      aria-hidden="true"
                      style={{
                        fontFamily: T.fontMono,
                        fontSize: 9,
                        fontWeight: 700,
                        color: "#fff",
                        mixBlendMode: "difference",
                        lineHeight: 1,
                      }}
                    >
                      {slotNum}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* PRO-gated control strip */}
      {showControls && (
        <div
          style={{
            display: "flex",
            gap: 6,
            paddingTop: 8,
            borderTop: `1px solid ${T.border}`,
          }}
        >
          {isPrinting && (
            <CtrlBtn onClick={() => onCommand(printer.id, "pause")} color={T.yellow}>
              PAUSE
            </CtrlBtn>
          )}
          {statusKey === "paused" && (
            <CtrlBtn onClick={() => onCommand(printer.id, "resume")} color={T.emerald}>
              RESUME
            </CtrlBtn>
          )}
          <CtrlBtn onClick={() => onCommand(printer.id, "cancel")} color={T.red}>
            CANCEL
          </CtrlBtn>
        </div>
      )}
    </div>
  );
}

function IconBtn({ onClick, title, hoverColor, children }) {
  return (
    <button
      onClick={onClick}
      title={title}
      aria-label={title}
      type="button"
      style={{
        background: "none",
        border: "none",
        cursor: "pointer",
        color: T.textMuted,
        padding: "2px 3px",
        lineHeight: 1,
        fontSize: 13,
        transition: "color 0.15s",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.color = hoverColor)}
      onMouseLeave={(e) => (e.currentTarget.style.color = T.textMuted)}
    >
      {children}
    </button>
  );
}

function CtrlBtn({ onClick, color, children }) {
  return (
    <button
      onClick={onClick}
      type="button"
      style={{
        background: "transparent",
        border: `1px solid ${color}33`,
        color,
        fontFamily: T.fontDisplay,
        fontWeight: 700,
        fontSize: 10,
        letterSpacing: "0.12em",
        padding: "4px 10px",
        borderRadius: 4,
        cursor: "pointer",
        transition: "background 0.15s, border-color 0.15s",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = `${color}18`;
        e.currentTarget.style.borderColor = color;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "transparent";
        e.currentTarget.style.borderColor = `${color}33`;
      }}
    >
      {children}
    </button>
  );
}
