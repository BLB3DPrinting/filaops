import { T } from "./tokens";

/**
 * Fleet-level stat tile (e.g. "3 PRINTING", "12 IDLE"). Used in the HUD
 * header strip when the dashboard has aggregate counts to display.
 */
export default function StatChip({ value, label, color }) {
  return (
    <div
      style={{
        background: T.surface,
        border: `1px solid ${T.border}`,
        borderRadius: 7,
        padding: "12px 16px",
      }}
    >
      <div
        style={{
          fontFamily: T.fontMono,
          fontWeight: 600,
          fontSize: 26,
          color: color || T.textPrimary,
          lineHeight: 1,
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontFamily: T.fontDisplay,
          fontWeight: 600,
          fontSize: 9,
          letterSpacing: "0.14em",
          color: T.textMuted,
          marginTop: 6,
          textTransform: "uppercase",
        }}
      >
        {label}
      </div>
    </div>
  );
}
