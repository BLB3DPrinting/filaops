import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ThemeProvider, useTheme } from "../ThemeContext";
import { THEME_KEY, GLASS_KEY } from "../../lib/theme";

const html = () => document.documentElement;

beforeEach(() => {
  localStorage.clear();
  html().removeAttribute("data-theme");
  html().removeAttribute("data-glass");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const wrapper = ({ children }) => <ThemeProvider>{children}</ThemeProvider>;

describe("ThemeProvider", () => {
  it("starts on light with nothing stored", () => {
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.theme).toBe("light");
    expect(result.current.glass).toBe("on");
  });

  it("honours a stored dim preference before mount", () => {
    localStorage.setItem(THEME_KEY, "dim");
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.theme).toBe("dim");
  });

  it("honours an applied data-theme attribute before mount", () => {
    html().setAttribute("data-theme", "dim");
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.theme).toBe("dim");
  });

  it("toggleTheme writes the attribute and storage and updates state", () => {
    const { result } = renderHook(() => useTheme(), { wrapper });

    act(() => {
      result.current.toggleTheme();
    });

    expect(result.current.theme).toBe("dim");
    expect(html().getAttribute("data-theme")).toBe("dim");
    expect(localStorage.getItem(THEME_KEY)).toBe("dim");

    act(() => {
      result.current.toggleTheme();
    });

    expect(result.current.theme).toBe("light");
    expect(html().getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem(THEME_KEY)).toBe("light");
  });

  it("setTheme applies a named theme and ignores unknown values", () => {
    const { result } = renderHook(() => useTheme(), { wrapper });

    act(() => {
      result.current.setTheme("dim");
    });
    expect(result.current.theme).toBe("dim");

    act(() => {
      result.current.setTheme("dark");
    });
    expect(result.current.theme).toBe("dim");
    expect(html().getAttribute("data-theme")).toBe("dim");
  });

  it("follows a change made outside React through the store event", () => {
    const { result } = renderHook(() => useTheme(), { wrapper });

    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: THEME_KEY, newValue: "dim" }));
    });

    expect(result.current.theme).toBe("dim");
    expect(html().getAttribute("data-theme")).toBe("dim");
  });

  it("stops listening after unmount", () => {
    const removeSpy = vi.spyOn(window, "removeEventListener");
    const { unmount } = renderHook(() => useTheme(), { wrapper });

    unmount();

    const removed = removeSpy.mock.calls.map((call) => call[0]);
    expect(removed).toContain("filaops:theme");
    expect(removed).toContain("storage");
  });

  it("setGlass writes the attribute and storage and updates state", () => {
    const { result } = renderHook(() => useTheme(), { wrapper });

    act(() => {
      result.current.setGlass("off");
    });

    expect(result.current.glass).toBe("off");
    expect(html().getAttribute("data-glass")).toBe("off");
    expect(localStorage.getItem(GLASS_KEY)).toBe("off");

    act(() => {
      result.current.setGlass("on");
    });

    expect(result.current.glass).toBe("on");
    expect(html().hasAttribute("data-glass")).toBe(false);
  });

  it("keeps a stable value object between renders with no change", () => {
    const { result, rerender } = renderHook(() => useTheme(), { wrapper });
    const first = result.current;
    rerender();
    expect(result.current).toBe(first);
  });
});

describe("useTheme without a provider", () => {
  it("returns light defaults and no-op setters", () => {
    const { result } = renderHook(() => useTheme());

    expect(result.current.theme).toBe("light");
    expect(result.current.glass).toBe("on");

    act(() => {
      result.current.setTheme("dim");
      result.current.toggleTheme();
      result.current.setGlass("off");
    });

    expect(result.current.theme).toBe("light");
    expect(html().hasAttribute("data-theme")).toBe(false);
    expect(html().hasAttribute("data-glass")).toBe(false);
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
  });
});
