import { T } from "./tokens";

/**
 * SVG arc temperature gauge (nozzle or bed).
 *
 * The SVG is rotated -90° so the arc sweep starts at 12 o'clock. The text
 * group is counter-rotated 90° so the reading stays readable. Stroke dash
 * offset encodes the fill percentage; 0.8s ease transitions smooth real-
 * time temp updates.
 */
export default function TempGauge({ value, max, color, label }) {
  const R = 22;
  const CIRC = 2 * Math.PI * R;
  // Guard against zero/undefined max so a mis-props'd gauge can't produce
  // NaN stroke offsets and blow up the SVG.
  const safeMax = Number(max) > 0 ? Number(max) : 1;
  const pct = Math.min(1, Math.max(0, (value || 0) / safeMax));
  const offset = CIRC * (1 - pct);
  const SIZE = 58;
  const hasValue = value > 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
      <svg
        width={SIZE}
        height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        style={{ transform: "rotate(-90deg)" }}
        role="img"
        aria-label={`${label} temperature ${hasValue ? `${Math.round(value)} degrees Celsius` : "not reading"}`}
      >
        <circle cx={SIZE / 2} cy={SIZE / 2} r={R} fill="none" stroke={T.border} strokeWidth={4} />
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={R}
          fill="none"
          stroke={hasValue ? color : T.textMuted}
          strokeWidth={4}
          strokeLinecap="round"
          strokeDasharray={CIRC}
          strokeDashoffset={hasValue ? offset : CIRC}
          style={{ transition: "stroke-dashoffset 0.8s ease" }}
        />
        <g transform={`rotate(90, ${SIZE / 2}, ${SIZE / 2})`}>
          <text
            x={SIZE / 2}
            y={SIZE / 2 - 3}
            textAnchor="middle"
            dominantBaseline="middle"
            fill={hasValue ? color : T.textMuted}
            fontSize="10"
            fontFamily={T.fontMono}
            fontWeight="600"
          >
            {hasValue ? Math.round(value) : "--"}
          </text>
          <text
            x={SIZE / 2}
            y={SIZE / 2 + 9}
            textAnchor="middle"
            dominantBaseline="middle"
            fill={T.textMuted}
            fontSize="7"
            fontFamily={T.fontDisplay}
            fontWeight="500"
          >
            °C
          </text>
        </g>
      </svg>
      <span
        style={{
          fontSize: 9,
          fontFamily: T.fontDisplay,
          fontWeight: 600,
          letterSpacing: "0.1em",
          color: T.textMuted,
          textTransform: "uppercase",
        }}
      >
        {label}
      </span>
    </div>
  );
}
