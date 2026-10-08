/**
 * theme — Workbench theme store (Day / Dim) and the glass-material flag.
 *
 * Plain module with no React import, so it is safe to call before first paint.
 * The inline script in index.html mirrors resolveInitialTheme() for the
 * pre-paint case with INITIAL_THEME_STRATEGY = "light"; the two must change
 * together.
 *
 * Contract (shared with .storybook/preview.js and index.css):
 *   - `data-theme` on <html>: "light" | "dim"
 *   - `data-glass` on <html>: "off" when the glass material is opted out,
 *     absent otherwise (index.css only matches [data-glass="off"])
 *   - localStorage: THEME_KEY → "light" | "dim", GLASS_KEY → "on" | "off"
 *
 * Every storage access is wrapped: a denied or missing localStorage never
 * blocks applying the attribute.
 *
 * Usage:
 *   import { getTheme, setTheme, subscribeTheme } from "../lib/theme";
 *   setTheme("dim");                              // apply + persist + notify
 *   const stop = subscribeTheme((theme) => …);    // this tab and other tabs
 *   stop();
 */

export const THEMES = Object.freeze(["light", "dim"]);
export const GLASS_MODES = Object.freeze(["on", "off"]);

export const THEME_KEY = "filaops_theme";
export const GLASS_KEY = "filaops_glass";

/** window CustomEvent name dispatched by setTheme(); detail is { theme }. */
export const THEME_EVENT = "filaops:theme";

/**
 * First-visit rule: "light" forces Day; "system" follows prefers-color-scheme.
 * A stored preference always wins over the strategy.
 */
export const INITIAL_THEME_STRATEGY = "light";

const DEFAULT_THEME = "light";
const DEFAULT_GLASS = "on";
const THEME_ATTR = "data-theme";
const GLASS_ATTR = "data-glass";

function isTheme(value) {
  return THEMES.includes(value);
}

function isGlassMode(value) {
  return GLASS_MODES.includes(value);
}

function hasDocument() {
  return typeof document !== "undefined" && Boolean(document.documentElement);
}

/**
 * Resolve the theme for a first paint.
 *
 * @param {object} [options]
 * @param {string|null} [options.stored] value read from THEME_KEY
 * @param {boolean} [options.prefersDark] prefers-color-scheme: dark (only
 *   consulted by the "system" strategy)
 * @param {"light"|"system"} [options.strategy]
 * @returns {"light"|"dim"}
 */
export function resolveInitialTheme({
  stored = null,
  prefersDark = false,
  strategy = INITIAL_THEME_STRATEGY,
} = {}) {
  if (isTheme(stored)) return stored;
  if (strategy === "system") return prefersDark ? "dim" : DEFAULT_THEME;
  return DEFAULT_THEME;
}

/**
 * Whether the OS asks for a dark scheme. Guarded so jsdom and old browsers
 * without matchMedia report false instead of throwing.
 */
export function prefersDarkScheme() {
  try {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return false;
    }
    return Boolean(window.matchMedia("(prefers-color-scheme: dark)").matches);
  } catch {
    return false;
  }
}

function readStorage(key) {
  try {
    // Both the accessor (SecurityError in sandboxed frames) and getItem can
    // throw; either way the caller treats the preference as unset.
    if (typeof window === "undefined") return null;
    const storage = window.localStorage;
    if (!storage) return null;
    return storage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key, value) {
  try {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(key, value);
  } catch {
    // Storage denied or full: the attribute is already applied, so the
    // choice still holds for this page load.
  }
}

/** Raw THEME_KEY value, or null when unset or unreadable. */
export function readStoredTheme() {
  return readStorage(THEME_KEY);
}

/** Raw GLASS_KEY value, or null when unset or unreadable. */
export function readStoredGlass() {
  return readStorage(GLASS_KEY);
}

/** The strategy-aware resolution used wherever the store falls back to storage. */
function resolveFromStored(stored) {
  return resolveInitialTheme({
    stored,
    prefersDark: INITIAL_THEME_STRATEGY === "system" ? prefersDarkScheme() : false,
  });
}

/**
 * Write `data-theme` on <html>. Unknown values fall back to the default.
 * @returns {"light"|"dim"} the theme that was applied
 */
export function applyTheme(theme) {
  const next = isTheme(theme) ? theme : DEFAULT_THEME;
  if (hasDocument()) {
    document.documentElement.setAttribute(THEME_ATTR, next);
  }
  return next;
}

/**
 * Write `data-glass` on <html>: "off" sets the attribute, "on" removes it.
 * @returns {"on"|"off"} the mode that was applied
 */
export function applyGlass(mode) {
  const next = isGlassMode(mode) ? mode : DEFAULT_GLASS;
  if (hasDocument()) {
    if (next === "off") {
      document.documentElement.setAttribute(GLASS_ATTR, "off");
    } else {
      document.documentElement.removeAttribute(GLASS_ATTR);
    }
  }
  return next;
}

/** Current theme: the applied attribute when valid, else the stored fallback. */
export function getTheme() {
  if (hasDocument()) {
    const applied = document.documentElement.getAttribute(THEME_ATTR);
    if (isTheme(applied)) return applied;
  }
  return resolveFromStored(readStoredTheme());
}

/** Current glass mode: "off" when the attribute or storage says so, else "on". */
export function getGlass() {
  if (hasDocument() && document.documentElement.getAttribute(GLASS_ATTR) === "off") {
    return "off";
  }
  return readStoredGlass() === "off" ? "off" : DEFAULT_GLASS;
}

function dispatchThemeEvent(theme) {
  if (typeof window === "undefined" || typeof window.dispatchEvent !== "function") return;
  window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: { theme } }));
}

/**
 * Apply, persist and announce a theme. Unknown values are ignored.
 * @returns {"light"|"dim"} the theme in effect afterwards
 */
export function setTheme(theme) {
  if (!isTheme(theme)) return getTheme();
  applyTheme(theme);
  writeStorage(THEME_KEY, theme);
  dispatchThemeEvent(theme);
  return theme;
}

/**
 * Apply and persist the glass mode. Unknown values are ignored.
 * @returns {"on"|"off"} the mode in effect afterwards
 */
export function setGlass(mode) {
  if (!isGlassMode(mode)) return getGlass();
  applyGlass(mode);
  writeStorage(GLASS_KEY, mode);
  return mode;
}

/**
 * Subscribe to theme changes from this tab (THEME_EVENT) and from other tabs
 * (`storage` events on THEME_KEY). A cross-tab change is applied to <html>
 * before the callback runs, so the callback always sees the DOM in sync.
 *
 * @param {(theme: "light"|"dim") => void} callback
 * @returns {() => void} unsubscribe
 */
export function subscribeTheme(callback) {
  if (typeof window === "undefined" || typeof window.addEventListener !== "function") {
    return () => {};
  }

  const onThemeEvent = () => {
    callback(getTheme());
  };

  const onStorage = (event) => {
    if (event.key !== THEME_KEY) return;
    // null (cleared elsewhere) or garbage resolves to the default.
    callback(applyTheme(resolveFromStored(event.newValue)));
  };

  window.addEventListener(THEME_EVENT, onThemeEvent);
  window.addEventListener("storage", onStorage);

  return () => {
    window.removeEventListener(THEME_EVENT, onThemeEvent);
    window.removeEventListener("storage", onStorage);
  };
}
