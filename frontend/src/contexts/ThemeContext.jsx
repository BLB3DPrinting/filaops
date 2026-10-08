/* eslint-disable react-refresh/only-export-components */
/**
 * ThemeContext — Workbench theme (Day / Dim) and glass material for React.
 *
 * A thin bridge over lib/theme.js: the store owns the `data-theme` /
 * `data-glass` attributes, localStorage and the change event; this provider
 * mirrors the current value into React state and re-renders consumers.
 *
 * Provides:
 *   { theme, glass, setTheme, toggleTheme, setGlass }
 *
 * Without a provider the hook returns the defaults ("light", "on") and the
 * setters are no-ops, so it never throws.
 *
 * Usage:
 *   const { theme, toggleTheme } = useTheme();
 *   <button onClick={toggleTheme}>{theme === "dim" ? "Day" : "Dim"}</button>
 */
import { createContext, useContext, useState, useEffect, useMemo, useCallback } from "react";
import {
  getTheme,
  getGlass,
  setTheme as storeSetTheme,
  setGlass as storeSetGlass,
  subscribeTheme,
} from "../lib/theme";

const ThemeContext = createContext({
  theme: "light",
  glass: "on",
  setTheme() {},
  toggleTheme() {},
  setGlass() {},
});

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(getTheme);
  const [glass, setGlassState] = useState(getGlass);

  // Subscribe only: state changes arrive through the store's event, including
  // cross-tab storage changes, so the effect itself never sets state.
  useEffect(() => subscribeTheme((next) => setThemeState(next)), []);

  const setTheme = useCallback((next) => {
    setThemeState(storeSetTheme(next));
  }, []);

  const toggleTheme = useCallback(() => {
    // Read the applied attribute rather than closed-over state so rapid
    // toggles and cross-tab changes cannot flip the wrong way.
    setThemeState(storeSetTheme(getTheme() === "dim" ? "light" : "dim"));
  }, []);

  const setGlass = useCallback((mode) => {
    setGlassState(storeSetGlass(mode));
  }, []);

  const value = useMemo(
    () => ({ theme, glass, setTheme, toggleTheme, setGlass }),
    [theme, glass, setTheme, toggleTheme, setGlass]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}

export default ThemeContext;
