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
  const cfg = STATUS_CFG[printer.status] || STATUS_CFG.offline;
  const isPrinting = printer.status === "printing";
  const isActive = isPrinting || printer.status === "paused";
  const showControls = Boolean(onCommand) && isActive;

  return (
    <div
      style={{
        background: T.surface,
        border: `1px solid ${cfg.border}`,
        borderLeft: `3px solid ${cfg.dot}`,
        borderRadius: 8,
        padding: "14px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 10,
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
              fontSize: 16,
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
              fontSize: 10,
              color: T.textMuted,
              marginTop: 2,
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
                fontSize: 10,
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
              {Number(printer.progress ?? 0).toFixed(0)}%
            </span>
          </div>
          <div style={{ height: 4, background: T.border, borderRadius: 2, overflow: "hidden" }}>
            <div
              style={{
                height: "100%",
                width: `${printer.progress ?? 0}%`,
                background: `linear-gradient(90deg, ${T.emerald}, #34D399)`,
                borderRadius: 2,
                transition: "width 1s ease",
              }}
            />
          </div>
        </div>
      )}

      {/* AMS slots — only when the printer reports multi-material state */}
      {printer.ams_slots?.length > 0 && (
        <div>
          <div
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
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {printer.ams_slots.map((slot, i) => (
              <div
                key={i}
                title={`Slot ${slot.slot ?? i + 1}: ${slot.material || "empty"}`}
                style={{
                  width: 16,
                  height: 16,
                  borderRadius: 3,
                  background: slot.color || T.raised,
                  border: `1px solid ${T.borderHover}`,
                }}
              />
            ))}
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
          {printer.status === "paused" && (
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
