/**
 * Industrial HUD design tokens for the AdminPrinters fleet view.
 *
 * This aesthetic is a PRO-unlocked visual mode — Core ships with a plain
 * table view of printers, and when `isPro && hasFeature("filafarm")` is
 * true the HUD toggle becomes available. Typography (Rajdhani + JetBrains
 * Mono) is preloaded from `index.html` so this file never touches
 * `document.head` at runtime.
 */

export const T = {
  bg: "#0C0E0D",
  surface: "#131614",
  raised: "#1A1D1B",
  border: "#232724",
  borderHover: "#343B35",
  amber: "#F59E0B",
  amberDim: "#92610A",
  amberGlow: "rgba(245,158,11,0.12)",
  emerald: "#10B981",
  red: "#EF4444",
  yellow: "#EAB308",
  textPrimary: "#E8EAE6",
  textSecondary: "#8A9188",
  textMuted: "#454B43",
  fontDisplay: "'Rajdhani', sans-serif",
  fontMono: "'JetBrains Mono', monospace",
};

// Keys here must stay in sync with backend PrinterStatus enum in
// backend/app/schemas/printer.py. Missing a key makes the printer fall
// through to "unknown" visuals. The MQTT monitor at
// services/mqtt/monitor.py can also emit "unknown" as a transient state
// that isn't formally in the Pydantic enum — the entry below catches
// that too so operators don't see such printers mislabeled as OFFLINE.
export const STATUS_CFG = {
  idle:        { border: "#2B3529", dot: T.amber,   glow: "rgba(245,158,11,0.35)", label: "IDLE"        },
  printing:    { border: "#1C3829", dot: T.emerald, glow: "rgba(16,185,129,0.35)", label: "PRINTING"    },
  paused:      { border: "#332E18", dot: T.yellow,  glow: "rgba(234,179,8,0.35)",  label: "PAUSED"      },
  error:       { border: "#371A1A", dot: T.red,     glow: "rgba(239,68,68,0.35)",  label: "ERROR"       },
  maintenance: { border: "#3A311C", dot: T.yellow,  glow: "rgba(234,179,8,0.25)",  label: "MAINTENANCE" },
  offline:     { border: T.border,  dot: "#3A3F3B", glow: "transparent",           label: "OFFLINE"     },
  unknown:     { border: T.border,  dot: T.textMuted, glow: "transparent",         label: "UNKNOWN"     },
};

export const JOB_STATUS_COLORS = {
  queued:    T.amber,
  assigned:  T.yellow,
  printing:  T.emerald,
  completed: "#4ADE80",
  failed:    T.red,
  cancelled: T.textMuted,
};

/**
 * Keyframes the HUD relies on. Injected once by AdminPrinters via a `<style>`
 * tag when HUD mode is active, so animations unmount with the view instead of
 * leaking into `document.head`.
 */
export const HUD_KEYFRAMES = `
  @keyframes pulse-dot {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%      { opacity: 0.45; transform: scale(0.65); }
  }
`;
