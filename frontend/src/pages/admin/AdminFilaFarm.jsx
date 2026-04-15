/**
 * AdminFilaFarm — Industrial Control Panel
 *
 * Aesthetic: Factory floor HUD. Dense, unambiguous, readable at a glance.
 * Typography: Rajdhani (labels/headers) + JetBrains Mono (all numeric data)
 * Color: Near-black #0C0E0D with amber #F59E0B accent, status border accents.
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";

// ─── Font injection ────────────────────────────────────────────────────────

const FONT_HREF =
  "https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap";

function useFonts() {
  useEffect(() => {
    if (document.querySelector(`link[href="${FONT_HREF}"]`)) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = FONT_HREF;
    document.head.appendChild(link);
  }, []);
}

// ─── Design tokens ─────────────────────────────────────────────────────────

const T = {
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

const STATUS_CFG = {
  idle:     { border: "#2B3529", dot: T.amber,   glow: "rgba(245,158,11,0.35)",  label: "IDLE"     },
  printing: { border: "#1C3829", dot: T.emerald, glow: "rgba(16,185,129,0.35)",  label: "PRINTING" },
  paused:   { border: "#332E18", dot: T.yellow,  glow: "rgba(234,179,8,0.35)",   label: "PAUSED"   },
  error:    { border: "#371A1A", dot: T.red,     glow: "rgba(239,68,68,0.35)",   label: "ERROR"    },
  offline:  { border: T.border,  dot: "#3A3F3B", glow: "transparent",            label: "OFFLINE"  },
};

const JOB_STATUS_COLORS = {
  queued:    T.amber,
  assigned:  T.yellow,
  printing:  T.emerald,
  completed: "#4ADE80",
  failed:    T.red,
  cancelled: T.textMuted,
};

// ─── Brand data ────────────────────────────────────────────────────────────

const BRANDS = [
  { value: "bambulab",  label: "Bambu Lab",          models: ["A1", "A1 Mini", "P1S", "P1P", "X1C", "X1E"] },
  { value: "klipper",   label: "Klipper / Moonraker", models: ["Voron 2.4", "Voron Trident", "Creality K1", "Creality K1 Max", "Custom"] },
  { value: "octoprint", label: "OctoPrint",           models: ["Ender 3", "Ender 5", "CR-10", "Custom"] },
  { value: "prusa",     label: "Prusa (PrusaLink)",   models: ["MK4", "MK3.9", "XL", "MINI+"] },
  { value: "generic",   label: "Other / Generic",     models: ["Custom"] },
];

const EMPTY_FORM = {
  brand: "bambulab",
  name: "",
  model: "",
  ip_address: "",
  serial_number: "",
  location: "",
  connection_config: {},
};

// ─── Helpers ───────────────────────────────────────────────────────────────

function fmtTime(seconds) {
  if (seconds == null) return "--";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

// ─── SVG temperature arc gauge ─────────────────────────────────────────────
//
// Uses stroke-dasharray / stroke-dashoffset on a rotated circle.
// The SVG is rotated -90deg so the arc starts at 12 o'clock.
// Max nozzle = 300°C, max bed = 120°C (FDM practical ceilings).

function TempGauge({ value, max, color, label }) {
  const R = 22;
  const CIRC = 2 * Math.PI * R;
  const pct = Math.min(1, Math.max(0, (value || 0) / max));
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
      >
        {/* Track ring */}
        <circle cx={SIZE / 2} cy={SIZE / 2} r={R} fill="none" stroke={T.border} strokeWidth={4} />
        {/* Value arc */}
        <circle
          cx={SIZE / 2} cy={SIZE / 2} r={R}
          fill="none"
          stroke={hasValue ? color : T.textMuted}
          strokeWidth={4}
          strokeLinecap="round"
          strokeDasharray={CIRC}
          strokeDashoffset={hasValue ? offset : CIRC}
          style={{ transition: "stroke-dashoffset 0.8s ease" }}
        />
        {/* Counter-rotate the text group so it reads normally */}
        <g transform={`rotate(90, ${SIZE / 2}, ${SIZE / 2})`}>
          <text
            x={SIZE / 2} y={SIZE / 2 - 3}
            textAnchor="middle" dominantBaseline="middle"
            fill={hasValue ? color : T.textMuted}
            fontSize="10" fontFamily={T.fontMono} fontWeight="600"
          >
            {hasValue ? Math.round(value) : "--"}
          </text>
          <text
            x={SIZE / 2} y={SIZE / 2 + 9}
            textAnchor="middle" dominantBaseline="middle"
            fill={T.textMuted}
            fontSize="7" fontFamily={T.fontDisplay} fontWeight="500"
          >
            °C
          </text>
        </g>
      </svg>
      <span style={{
        fontSize: 9, fontFamily: T.fontDisplay, fontWeight: 600,
        letterSpacing: "0.1em", color: T.textMuted, textTransform: "uppercase",
      }}>
        {label}
      </span>
    </div>
  );
}

// ─── Printer card ──────────────────────────────────────────────────────────

function PrinterCard({ printer, onCommand, onEdit, onRemove }) {
  const cfg = STATUS_CFG[printer.status] || STATUS_CFG.offline;
  const isPrinting = printer.status === "printing";
  const isActive = isPrinting || printer.status === "paused";

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
          <div style={{
            fontFamily: T.fontDisplay, fontWeight: 700, fontSize: 16,
            letterSpacing: "0.04em", color: T.textPrimary,
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>
            {printer.name}
          </div>
          <div style={{ fontFamily: T.fontMono, fontSize: 10, color: T.textMuted, marginTop: 2, letterSpacing: "0.06em" }}>
            {printer.model}
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: 8, flexShrink: 0 }}>
          {/* Status indicator */}
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{
              width: 7, height: 7, borderRadius: "50%", flexShrink: 0,
              background: cfg.dot,
              boxShadow: isPrinting ? `0 0 6px 2px ${cfg.glow}` : "none",
              animation: isPrinting ? "pulse-dot 1.4s ease-in-out infinite" : "none",
              display: "inline-block",
            }} />
            <span style={{
              fontFamily: T.fontDisplay, fontWeight: 600, fontSize: 10,
              letterSpacing: "0.12em", color: cfg.dot,
            }}>
              {cfg.label}
            </span>
          </div>
          <IconBtn onClick={() => onEdit(printer)} title="Edit" hoverColor={T.textSecondary}>✎</IconBtn>
          <IconBtn onClick={() => onRemove(printer)} title="Remove" hoverColor={T.red}>✕</IconBtn>
        </div>
      </div>

      {/* Temperature gauges */}
      <div style={{ display: "flex", justifyContent: "space-around", paddingTop: 4 }}>
        <TempGauge value={printer.nozzle_temp ?? 0} max={300} color={T.amber}  label="NOZZLE" />
        <TempGauge value={printer.bed_temp   ?? 0} max={120} color={T.emerald} label="BED"    />
      </div>

      {/* Progress */}
      {isPrinting && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
            <span style={{ fontFamily: T.fontMono, fontSize: 9, color: T.textMuted, letterSpacing: "0.05em" }}>
              {printer.current_job || "PRINTING"}
            </span>
            <span style={{ fontFamily: T.fontMono, fontSize: 10, fontWeight: 600, color: T.emerald }}>
              {(printer.progress ?? 0).toFixed(0)}%
            </span>
          </div>
          <div style={{ height: 4, background: T.border, borderRadius: 2, overflow: "hidden" }}>
            <div style={{
              height: "100%",
              width: `${printer.progress ?? 0}%`,
              background: `linear-gradient(90deg, ${T.emerald}, #34D399)`,
              borderRadius: 2,
              transition: "width 1s ease",
            }} />
          </div>
        </div>
      )}

      {/* AMS slots */}
      {printer.ams_slots?.length > 0 && (
        <div>
          <div style={{
            fontFamily: T.fontDisplay, fontWeight: 600, fontSize: 9,
            letterSpacing: "0.14em", color: T.textMuted, marginBottom: 5,
          }}>
            AMS SLOTS
          </div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {printer.ams_slots.map((slot, i) => (
              <div
                key={i}
                title={`Slot ${slot.slot ?? i + 1}: ${slot.material || "empty"}`}
                style={{
                  width: 16, height: 16, borderRadius: 3,
                  background: slot.color || T.raised,
                  border: `1px solid ${T.borderHover}`,
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* Controls */}
      {isActive && (
        <div style={{
          display: "flex", gap: 6,
          paddingTop: 8, borderTop: `1px solid ${T.border}`,
        }}>
          {isPrinting && (
            <CtrlBtn onClick={() => onCommand(printer.id, "pause")} color={T.yellow}>PAUSE</CtrlBtn>
          )}
          {printer.status === "paused" && (
            <CtrlBtn onClick={() => onCommand(printer.id, "resume")} color={T.emerald}>RESUME</CtrlBtn>
          )}
          <CtrlBtn onClick={() => onCommand(printer.id, "cancel")} color={T.red}>CANCEL</CtrlBtn>
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
      style={{
        background: "none", border: "none", cursor: "pointer",
        color: T.textMuted, padding: "2px 3px", lineHeight: 1, fontSize: 13,
        transition: "color 0.15s",
      }}
      onMouseEnter={(e) => e.currentTarget.style.color = hoverColor}
      onMouseLeave={(e) => e.currentTarget.style.color = T.textMuted}
    >
      {children}
    </button>
  );
}

function CtrlBtn({ onClick, color, children }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: "transparent",
        border: `1px solid ${color}33`,
        color,
        fontFamily: T.fontDisplay, fontWeight: 700, fontSize: 10,
        letterSpacing: "0.12em", padding: "4px 10px", borderRadius: 4,
        cursor: "pointer", transition: "background 0.15s, border-color 0.15s",
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

// ─── Shared form primitives ────────────────────────────────────────────────

function FieldLabel({ children, required, hint }) {
  return (
    <label style={{
      display: "block",
      fontFamily: T.fontDisplay, fontWeight: 600, fontSize: 11,
      letterSpacing: "0.1em", color: T.textSecondary,
      marginBottom: 6, textTransform: "uppercase",
    }}>
      {children}
      {required && <span style={{ color: T.red, marginLeft: 3 }}>*</span>}
      {hint && (
        <span style={{
          color: T.textMuted, marginLeft: 6,
          textTransform: "none", fontSize: 10, letterSpacing: 0,
        }}>
          {hint}
        </span>
      )}
    </label>
  );
}

const baseInputStyle = {
  width: "100%", boxSizing: "border-box",
  background: T.raised, border: `1px solid ${T.border}`,
  borderRadius: 5, padding: "9px 12px",
  fontSize: 13, fontFamily: T.fontMono, color: T.textPrimary,
  outline: "none", transition: "border-color 0.15s",
};

function TextInput({ value, onChange, placeholder, type = "text", maxLength }) {
  return (
    <input
      type={type}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      maxLength={maxLength}
      style={baseInputStyle}
      onFocus={(e) => (e.currentTarget.style.borderColor = T.amber)}
      onBlur={(e) => (e.currentTarget.style.borderColor = T.border)}
    />
  );
}

function SelectInput({ value, onChange, children }) {
  return (
    <select
      value={value}
      onChange={onChange}
      style={{ ...baseInputStyle, cursor: "pointer" }}
      onFocus={(e) => (e.currentTarget.style.borderColor = T.amber)}
      onBlur={(e) => (e.currentTarget.style.borderColor = T.border)}
    >
      {children}
    </select>
  );
}

// ─── Brand-specific connection fields ──────────────────────────────────────

function BambuFields({ form, setField }) {
  return (
    <>
      <div>
        <FieldLabel required hint="from printer LCD or Bambu app">Serial Number</FieldLabel>
        <TextInput
          value={form.serial_number}
          onChange={(e) => setField("serial_number", e.target.value)}
          placeholder="01P00A123456789"
        />
      </div>
      <div>
        <FieldLabel required hint="8-char code from LCD">Access Code</FieldLabel>
        <TextInput
          value={form.connection_config?.access_code || ""}
          onChange={(e) =>
            setField("connection_config", { ...form.connection_config, access_code: e.target.value })
          }
          placeholder="12345678"
          maxLength={8}
        />
      </div>
    </>
  );
}

function KlipperFields({ form, setField }) {
  return (
    <>
      <div>
        <FieldLabel hint="default 7125">Moonraker Port</FieldLabel>
        <TextInput
          type="number"
          value={form.connection_config?.port ?? 7125}
          onChange={(e) =>
            setField("connection_config", { ...form.connection_config, port: parseInt(e.target.value) || 7125 })
          }
        />
      </div>
      <div>
        <FieldLabel hint="optional">API Key</FieldLabel>
        <TextInput
          value={form.connection_config?.api_key || ""}
          onChange={(e) =>
            setField("connection_config", { ...form.connection_config, api_key: e.target.value })
          }
          placeholder="Moonraker API key"
        />
      </div>
    </>
  );
}

function OctoPrintFields({ form, setField }) {
  return (
    <>
      <div>
        <FieldLabel hint="default 5000">OctoPrint Port</FieldLabel>
        <TextInput
          type="number"
          value={form.connection_config?.port ?? 5000}
          onChange={(e) =>
            setField("connection_config", { ...form.connection_config, port: parseInt(e.target.value) || 5000 })
          }
        />
      </div>
      <div>
        <FieldLabel required>API Key</FieldLabel>
        <TextInput
          value={form.connection_config?.api_key || ""}
          onChange={(e) =>
            setField("connection_config", { ...form.connection_config, api_key: e.target.value })
          }
          placeholder="OctoPrint API key"
        />
      </div>
    </>
  );
}

function PrusaFields({ form, setField }) {
  return (
    <>
      <div>
        <FieldLabel hint="default 8080">PrusaLink Port</FieldLabel>
        <TextInput
          type="number"
          value={form.connection_config?.port ?? 8080}
          onChange={(e) =>
            setField("connection_config", { ...form.connection_config, port: parseInt(e.target.value) || 8080 })
          }
        />
      </div>
      <div>
        <FieldLabel>Username</FieldLabel>
        <TextInput
          value={form.connection_config?.username || "maker"}
          onChange={(e) =>
            setField("connection_config", { ...form.connection_config, username: e.target.value })
          }
        />
      </div>
      <div>
        <FieldLabel required>Password</FieldLabel>
        <TextInput
          type="password"
          value={form.connection_config?.password || ""}
          onChange={(e) =>
            setField("connection_config", { ...form.connection_config, password: e.target.value })
          }
        />
      </div>
    </>
  );
}

// ─── Add / Edit modal ──────────────────────────────────────────────────────

function PrinterModal({ printer, onClose, onSave }) {
  const api = useApi();
  const toast = useToast();
  const isEdit = !!printer;

  const [form, setFormState] = useState(
    printer
      ? {
          brand: printer.brand || "bambulab",
          name: printer.name || "",
          model: printer.model || "",
          ip_address: printer.ip_address || "",
          serial_number: printer.serial_number || "",
          location: printer.location || "",
          connection_config: printer.connection_config || {},
        }
      : { ...EMPTY_FORM }
  );
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);

  const setField = (key, val) => setFormState((p) => ({ ...p, [key]: val }));

  const handleBrandChange = (brand) => {
    setFormState((p) => ({ ...p, brand, model: "", connection_config: {} }));
    setTestResult(null);
  };

  const handleTest = async () => {
    if (!printer?.id) { toast.error("Save the printer first, then test."); return; }
    setTesting(true); setTestResult(null);
    try {
      setTestResult(await api.post(`/api/v1/pro/filafarm/printers/${printer.id}/test-connection`));
    } catch (err) {
      setTestResult({ reachable: false, message: err.message });
    } finally { setTesting(false); }
  };

  const validate = () => {
    if (!form.name.trim()) return "Printer name is required";
    if (!form.model.trim() || form.model === "__custom") return "Select or enter a model";
    if (!form.ip_address.trim()) return "IP address is required";
    if (form.brand === "bambulab") {
      if (!form.serial_number.trim()) return "Serial number required for Bambu Lab";
      if (!form.connection_config?.access_code?.trim()) return "Access code required for Bambu Lab";
    }
    if (form.brand === "octoprint" && !form.connection_config?.api_key?.trim()) return "API key required for OctoPrint";
    if (form.brand === "prusa" && !form.connection_config?.password?.trim()) return "Password required for PrusaLink";
    return null;
  };

  const handleSave = async () => {
    const err = validate();
    if (err) { toast.error(err); return; }
    setSaving(true);
    try {
      const payload = {
        brand: form.brand,
        name: form.name.trim(),
        model: form.model.trim(),
        ip_address: form.ip_address.trim(),
        serial_number: form.serial_number.trim() || null,
        location: form.location.trim() || null,
        connection_config: form.connection_config || {},
      };
      if (isEdit) {
        await api.put(`/api/v1/pro/filafarm/printers/${printer.id}`, payload);
        toast.success(`${form.name} updated`);
      } else {
        await api.post("/api/v1/pro/filafarm/printers", payload);
        toast.success(`${form.name} added — fleet connecting`);
      }
      onSave(); onClose();
    } catch (err) {
      toast.error(err.message);
    } finally { setSaving(false); }
  };

  const brandMeta = BRANDS.find((b) => b.value === form.brand);
  const isCustomModel = form.model === "__custom";

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 50, padding: 16,
    }}>
      <div style={{
        background: T.surface,
        border: `1px solid ${T.border}`,
        borderTop: `2px solid ${T.amber}`,
        borderRadius: 10,
        width: "100%", maxWidth: 500, maxHeight: "90vh", overflowY: "auto",
      }}>
        {/* Header */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "16px 20px", borderBottom: `1px solid ${T.border}`,
        }}>
          <div>
            <div style={{ fontFamily: T.fontDisplay, fontWeight: 700, fontSize: 18, letterSpacing: "0.06em", color: T.textPrimary }}>
              {isEdit ? "EDIT PRINTER" : "ADD PRINTER"}
            </div>
            {!isEdit && (
              <div style={{ fontFamily: T.fontMono, fontSize: 9, color: T.textMuted, marginTop: 3, letterSpacing: "0.08em" }}>
                SELECT BRAND → CONFIGURE → SAVE
              </div>
            )}
          </div>
          <IconBtn onClick={onClose} hoverColor={T.textPrimary} title="Close">×</IconBtn>
        </div>

        <div style={{ padding: "20px", display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Brand grid — add mode only */}
          {!isEdit && (
            <div>
              <FieldLabel>Brand</FieldLabel>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                {BRANDS.map((b) => {
                  const active = form.brand === b.value;
                  return (
                    <button
                      key={b.value}
                      onClick={() => handleBrandChange(b.value)}
                      style={{
                        background: active ? T.amberGlow : T.raised,
                        border: `1px solid ${active ? T.amber : T.border}`,
                        borderRadius: 5, padding: "8px 12px",
                        fontFamily: T.fontDisplay, fontWeight: 600, fontSize: 13,
                        color: active ? T.amber : T.textSecondary,
                        cursor: "pointer", textAlign: "left", letterSpacing: "0.03em",
                        transition: "all 0.15s",
                      }}
                    >
                      {b.label}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Common fields */}
          <div>
            <FieldLabel required>Printer Name</FieldLabel>
            <TextInput value={form.name} onChange={(e) => setField("name", e.target.value)} placeholder="BLB-A1-01" />
          </div>

          <div>
            <FieldLabel required>Model</FieldLabel>
            {brandMeta?.models.length > 1 ? (
              <SelectInput value={isCustomModel ? "__custom" : form.model} onChange={(e) => setField("model", e.target.value)}>
                <option value="">Select model…</option>
                {brandMeta.models.map((m) => <option key={m} value={m}>{m}</option>)}
                <option value="__custom">Custom…</option>
              </SelectInput>
            ) : (
              <TextInput value={form.model} onChange={(e) => setField("model", e.target.value)} placeholder="Printer model" />
            )}
            {isCustomModel && (
              <div style={{ marginTop: 6 }}>
                <TextInput value="" onChange={(e) => setField("model", e.target.value)} placeholder="Enter model name" />
              </div>
            )}
          </div>

          <div>
            <FieldLabel required>IP Address</FieldLabel>
            <TextInput value={form.ip_address} onChange={(e) => setField("ip_address", e.target.value)} placeholder="192.168.1.42" />
          </div>

          {/* Brand-specific */}
          {form.brand === "bambulab"  && <BambuFields  form={form} setField={setField} />}
          {form.brand === "klipper"   && <KlipperFields form={form} setField={setField} />}
          {form.brand === "octoprint" && <OctoPrintFields form={form} setField={setField} />}
          {form.brand === "prusa"     && <PrusaFields   form={form} setField={setField} />}

          <div>
            <FieldLabel hint="optional">Location</FieldLabel>
            <TextInput value={form.location} onChange={(e) => setField("location", e.target.value)} placeholder="Farm Room A" />
          </div>

          {/* Test connection result */}
          {testResult && (
            <div style={{
              background: testResult.reachable ? "rgba(16,185,129,0.08)" : "rgba(239,68,68,0.08)",
              border: `1px solid ${testResult.reachable ? T.emerald : T.red}44`,
              borderRadius: 5, padding: "10px 12px",
              fontFamily: T.fontMono, fontSize: 12,
              color: testResult.reachable ? T.emerald : T.red,
            }}>
              {testResult.reachable ? "✓ " : "✗ "}{testResult.message}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          display: "flex", alignItems: "center",
          padding: "14px 20px", borderTop: `1px solid ${T.border}`, gap: 10,
        }}>
          {isEdit && (
            <button
              onClick={handleTest}
              disabled={testing}
              style={{
                background: T.raised, border: `1px solid ${T.border}`,
                color: T.textSecondary, fontFamily: T.fontDisplay, fontWeight: 600,
                fontSize: 12, letterSpacing: "0.08em", padding: "7px 14px",
                borderRadius: 5, cursor: testing ? "default" : "pointer",
                opacity: testing ? 0.5 : 1,
              }}
            >
              {testing ? "TESTING…" : "TEST CONNECTION"}
            </button>
          )}
          <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
            <button
              onClick={onClose}
              style={{
                background: "transparent", border: "none",
                color: T.textMuted, fontFamily: T.fontDisplay, fontWeight: 600,
                fontSize: 13, letterSpacing: "0.06em", padding: "7px 14px", cursor: "pointer",
              }}
            >
              CANCEL
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                background: saving ? T.amberDim : T.amber,
                border: "none", color: "#000",
                fontFamily: T.fontDisplay, fontWeight: 700,
                fontSize: 13, letterSpacing: "0.08em",
                padding: "7px 18px", borderRadius: 5,
                cursor: saving ? "default" : "pointer",
                opacity: saving ? 0.8 : 1, transition: "background 0.15s",
              }}
            >
              {saving ? "SAVING…" : isEdit ? "SAVE CHANGES" : "ADD PRINTER"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Remove confirm ────────────────────────────────────────────────────────

function RemoveConfirm({ printer, onConfirm, onCancel }) {
  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 50, padding: 16,
    }}>
      <div style={{
        background: T.surface,
        border: `1px solid ${T.border}`,
        borderTop: `2px solid ${T.red}`,
        borderRadius: 10, width: "100%", maxWidth: 380, padding: "24px",
      }}>
        <div style={{ fontFamily: T.fontDisplay, fontWeight: 700, fontSize: 16, letterSpacing: "0.06em", color: T.textPrimary, marginBottom: 10 }}>
          REMOVE PRINTER
        </div>
        <p style={{ fontFamily: T.fontMono, fontSize: 12, color: T.textSecondary, lineHeight: 1.6, marginBottom: 20 }}>
          Remove <span style={{ color: T.textPrimary }}>{printer.name}</span>?{" "}
          Print job history is preserved. Re-add at any time.
        </p>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button
            onClick={onCancel}
            style={{
              background: "transparent", border: "none",
              color: T.textMuted, fontFamily: T.fontDisplay, fontWeight: 600,
              fontSize: 13, letterSpacing: "0.06em", padding: "7px 14px", cursor: "pointer",
            }}
          >
            CANCEL
          </button>
          <button
            onClick={onConfirm}
            style={{
              background: "transparent",
              border: `1px solid ${T.red}`,
              color: T.red, fontFamily: T.fontDisplay, fontWeight: 700,
              fontSize: 13, letterSpacing: "0.08em",
              padding: "7px 18px", borderRadius: 5, cursor: "pointer",
              transition: "background 0.15s",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(239,68,68,0.12)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
          >
            REMOVE
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Stat chip ─────────────────────────────────────────────────────────────

function StatChip({ value, label, color }) {
  return (
    <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 7, padding: "12px 16px" }}>
      <div style={{ fontFamily: T.fontMono, fontWeight: 600, fontSize: 26, color: color || T.textPrimary, lineHeight: 1 }}>
        {value}
      </div>
      <div style={{ fontFamily: T.fontDisplay, fontWeight: 600, fontSize: 9, letterSpacing: "0.14em", color: T.textMuted, marginTop: 6, textTransform: "uppercase" }}>
        {label}
      </div>
    </div>
  );
}

// ─── Job row ───────────────────────────────────────────────────────────────

function JobRow({ job }) {
  const color = JOB_STATUS_COLORS[job.status] || T.textMuted;
  const cell = { padding: "10px 12px" };
  return (
    <tr style={{ borderBottom: `1px solid ${T.border}` }}>
      <td style={{ ...cell, fontFamily: T.fontMono, fontSize: 12, color: T.textPrimary }}>{job.name}</td>
      <td style={cell}>
        <span style={{ fontFamily: T.fontDisplay, fontWeight: 700, fontSize: 10, letterSpacing: "0.12em", color }}>
          {job.status.toUpperCase()}
        </span>
      </td>
      <td style={{ ...cell, fontFamily: T.fontMono, fontSize: 11, color: T.textSecondary }}>{job.printer_id || "—"}</td>
      <td style={{ ...cell, fontFamily: T.fontMono, fontSize: 11, color: T.textSecondary }}>{(job.progress ?? 0).toFixed(0)}%</td>
      <td style={{ ...cell, fontFamily: T.fontMono, fontSize: 11, color: T.textSecondary }}>{fmtTime(job.estimated_time)}</td>
      <td style={{ ...cell, fontFamily: T.fontMono, fontSize: 11, color: T.textMuted }}>{job.priority}</td>
    </tr>
  );
}

// ─── Global keyframes ──────────────────────────────────────────────────────

const GLOBAL_STYLES = `
  @keyframes pulse-dot {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%       { opacity: 0.45; transform: scale(0.65); }
  }
`;

// ─── Main page ─────────────────────────────────────────────────────────────

export default function AdminFilaFarm() {
  useFonts();

  const api = useApi();
  const toast = useToast();
  const { isPro, hasFeature, loading: flagsLoading } = useFeatureFlags();
  const hasFilaFarmAccess = isPro && hasFeature("filafarm");

  const [printers, setPrinters] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("printers");

  const [showAddModal, setShowAddModal] = useState(false);
  const [editingPrinter, setEditingPrinter] = useState(null);
  const [removingPrinter, setRemovingPrinter] = useState(null);

  const refreshRef = useRef(null);
  const cmdTimeoutRef = useRef(null);

  const fetchData = useCallback(async () => {
    try {
      const [pRes, jRes, sRes] = await Promise.allSettled([
        api.get("/api/v1/pro/filafarm/printers"),
        api.get("/api/v1/pro/filafarm/jobs"),
        api.get("/api/v1/pro/filafarm/stats/today"),
      ]);
      setPrinters(pRes.status === "fulfilled" ? pRes.value?.printers || [] : []);
      setJobs(jRes.status === "fulfilled" ? jRes.value?.jobs || [] : []);
      setStats(sRes.status === "fulfilled" ? sRes.value : null);
      setError(
        pRes.status === "rejected" || jRes.status === "rejected" || sRes.status === "rejected"
          ? "Some data could not be loaded."
          : null
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    if (!hasFilaFarmAccess) return;
    fetchData();
    refreshRef.current = setInterval(fetchData, 15000);
    return () => clearInterval(refreshRef.current);
  }, [fetchData, hasFilaFarmAccess]);

  useEffect(() => () => cmdTimeoutRef.current && clearTimeout(cmdTimeoutRef.current), []);

  const handleCommand = async (printerId, command) => {
    try {
      await api.post(`/api/v1/pro/filafarm/printers/${printerId}/command`, { command });
      toast.success(`${command} sent`);
      if (cmdTimeoutRef.current) clearTimeout(cmdTimeoutRef.current);
      cmdTimeoutRef.current = setTimeout(fetchData, 1000);
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleRemoveConfirm = async () => {
    if (!removingPrinter) return;
    try {
      await api.del(`/api/v1/pro/filafarm/printers/${removingPrinter.id}`);
      toast.success(`${removingPrinter.name} removed`);
      setRemovingPrinter(null);
      fetchData();
    } catch (err) {
      toast.error(err.message);
    }
  };

  if (flagsLoading) {
    return (
      <div style={{ padding: 24, display: "flex", justifyContent: "center" }}>
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-amber-500" />
      </div>
    );
  }

  if (!hasFilaFarmAccess) {
    return (
      <div style={{ padding: 24, display: "flex", justifyContent: "center" }}>
        <div style={{
          background: T.surface, border: `1px solid ${T.border}`, borderRadius: 10,
          padding: "40px 32px", maxWidth: 400, textAlign: "center",
        }}>
          <div style={{ fontFamily: T.fontDisplay, fontWeight: 700, fontSize: 20, letterSpacing: "0.08em", color: T.textPrimary, marginBottom: 10 }}>
            PRO FEATURE
          </div>
          <p style={{ fontFamily: T.fontMono, fontSize: 11, color: T.textMuted, lineHeight: 1.7 }}>
            FilaFarm requires a PRO license with the filafarm feature enabled.
          </p>
        </div>
      </div>
    );
  }

  const printingCount = printers.filter((p) => p.status === "printing").length;
  const idleCount     = printers.filter((p) => p.status === "idle").length;
  const offlineCount  = printers.filter((p) => p.status === "offline").length;
  const errorCount    = printers.filter((p) => p.status === "error").length;

  return (
    <div style={{ padding: 24, background: T.bg, minHeight: "100%" }}>
      <style>{GLOBAL_STYLES}</style>

      {/* Modals */}
      {(showAddModal || editingPrinter) && (
        <PrinterModal
          printer={editingPrinter}
          onClose={() => { setShowAddModal(false); setEditingPrinter(null); }}
          onSave={fetchData}
        />
      )}
      {removingPrinter && (
        <RemoveConfirm
          printer={removingPrinter}
          onConfirm={handleRemoveConfirm}
          onCancel={() => setRemovingPrinter(null)}
        />
      )}

      {/* Page header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
            <h1 style={{
              fontFamily: T.fontDisplay, fontWeight: 700, fontSize: 30,
              letterSpacing: "0.1em", color: T.textPrimary, margin: 0,
            }}>
              FILAFARM
            </h1>
            <span style={{ fontFamily: T.fontMono, fontSize: 10, color: T.amber, letterSpacing: "0.14em" }}>
              PRODUCTION CONTROL
            </span>
          </div>
          <div style={{ fontFamily: T.fontMono, fontSize: 10, color: T.textMuted, letterSpacing: "0.08em", marginTop: 4 }}>
            {printers.length} PRINTER{printers.length !== 1 ? "S" : ""} · {printingCount} ACTIVE
          </div>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={fetchData}
            style={{
              background: T.raised, border: `1px solid ${T.border}`,
              color: T.textSecondary, fontFamily: T.fontDisplay, fontWeight: 600,
              fontSize: 12, letterSpacing: "0.08em", padding: "8px 14px",
              borderRadius: 5, cursor: "pointer", transition: "border-color 0.15s",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.borderColor = T.borderHover)}
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = T.border)}
          >
            ↻ REFRESH
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            style={{
              background: T.amber, border: "none", color: "#000",
              fontFamily: T.fontDisplay, fontWeight: 700,
              fontSize: 12, letterSpacing: "0.1em", padding: "8px 18px",
              borderRadius: 5, cursor: "pointer", transition: "opacity 0.15s",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.opacity = "0.85")}
            onMouseLeave={(e) => (e.currentTarget.style.opacity = "1")}
          >
            + ADD PRINTER
          </button>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 20 }}>
          <StatChip value={stats.jobs_completed ?? 0} label="Jobs Completed Today" />
          <StatChip value={stats.jobs_printing ?? 0}  label="Currently Printing"   color={T.emerald} />
          <StatChip value={stats.jobs_queued ?? 0}    label="In Queue"             color={T.amber} />
          <StatChip value={fmtTime(stats.total_print_time ?? 0)} label="Total Print Time" />
        </div>
      )}

      {/* Tab bar */}
      <div style={{
        display: "flex", gap: 2,
        background: T.surface, border: `1px solid ${T.border}`,
        borderRadius: 6, padding: 3, width: "fit-content", marginBottom: 20,
      }}>
        {[
          { id: "printers", label: `PRINTERS (${printers.length})` },
          { id: "jobs",     label: `JOBS (${jobs.length})` },
        ].map(({ id, label }) => {
          const active = activeTab === id;
          return (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              style={{
                background: active ? T.amber : "transparent",
                border: "none",
                color: active ? "#000" : T.textMuted,
                fontFamily: T.fontDisplay, fontWeight: 700,
                fontSize: 11, letterSpacing: "0.12em",
                padding: "6px 16px", borderRadius: 4,
                cursor: "pointer", transition: "all 0.15s",
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* Error */}
      {error && (
        <div style={{
          background: "rgba(239,68,68,0.08)", border: `1px solid ${T.red}44`,
          borderRadius: 6, padding: "12px 16px",
          fontFamily: T.fontMono, fontSize: 12, color: T.red, marginBottom: 16,
        }}>
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div style={{ display: "flex", justifyContent: "center", padding: "48px 0" }}>
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-amber-500" />
        </div>
      )}

      {/* Printers tab */}
      {!loading && activeTab === "printers" && (
        <div>
          {printers.length === 0 ? (
            <div style={{
              background: T.surface, border: `1px dashed ${T.border}`,
              borderRadius: 10, padding: "60px 24px", textAlign: "center",
            }}>
              <div style={{
                fontFamily: T.fontDisplay, fontWeight: 700, fontSize: 52,
                color: T.border, lineHeight: 1, marginBottom: 16,
              }}>
                [ ]
              </div>
              <div style={{ fontFamily: T.fontDisplay, fontWeight: 700, fontSize: 15, letterSpacing: "0.12em", color: T.textMuted, marginBottom: 8 }}>
                NO PRINTERS REGISTERED
              </div>
              <div style={{ fontFamily: T.fontMono, fontSize: 11, color: T.textMuted, marginBottom: 24, lineHeight: 1.7 }}>
                Add your first printer to initialize the fleet.
              </div>
              <button
                onClick={() => setShowAddModal(true)}
                style={{
                  background: T.amber, border: "none", color: "#000",
                  fontFamily: T.fontDisplay, fontWeight: 700,
                  fontSize: 12, letterSpacing: "0.1em", padding: "10px 24px",
                  borderRadius: 5, cursor: "pointer",
                }}
              >
                + ADD PRINTER
              </button>
            </div>
          ) : (
            <>
              {/* Fleet status strip */}
              <div style={{ display: "flex", gap: 20, marginBottom: 14 }}>
                {[
                  { count: printingCount, label: "PRINTING", color: T.emerald },
                  { count: idleCount,     label: "IDLE",     color: T.amber },
                  { count: offlineCount,  label: "OFFLINE",  color: T.textMuted },
                  ...(errorCount > 0 ? [{ count: errorCount, label: "ERROR", color: T.red }] : []),
                ].map(({ count, label, color }) => (
                  <div key={label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontFamily: T.fontMono, fontWeight: 600, fontSize: 15, color }}>{count}</span>
                    <span style={{ fontFamily: T.fontDisplay, fontWeight: 600, fontSize: 10, letterSpacing: "0.12em", color: T.textMuted }}>{label}</span>
                  </div>
                ))}
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
                {printers.map((p) => (
                  <PrinterCard
                    key={p.id}
                    printer={p}
                    onCommand={handleCommand}
                    onEdit={setEditingPrinter}
                    onRemove={setRemovingPrinter}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Jobs tab */}
      {!loading && activeTab === "jobs" && (
        <div>
          {jobs.length === 0 ? (
            <div style={{
              background: T.surface, border: `1px solid ${T.border}`,
              borderRadius: 8, padding: "32px 24px", textAlign: "center",
            }}>
              <div style={{ fontFamily: T.fontDisplay, fontWeight: 700, fontSize: 12, letterSpacing: "0.12em", color: T.textMuted }}>
                NO PRINT JOBS
              </div>
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                    {["Job", "Status", "Printer", "Progress", "Est. Time", "Priority"].map((h) => (
                      <th key={h} style={{
                        padding: "8px 12px", textAlign: "left",
                        fontFamily: T.fontDisplay, fontWeight: 700, fontSize: 9,
                        letterSpacing: "0.14em", color: T.textMuted, textTransform: "uppercase",
                      }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => <JobRow key={job.id} job={job} />)}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
