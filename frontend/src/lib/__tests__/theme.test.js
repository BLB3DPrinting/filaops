import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  THEMES,
  THEME_KEY,
  GLASS_KEY,
  THEME_EVENT,
  INITIAL_THEME_STRATEGY,
  resolveInitialTheme,
  prefersDarkScheme,
  readStoredTheme,
  readStoredGlass,
  applyTheme,
  applyGlass,
  setTheme,
  setGlass,
  getTheme,
  getGlass,
  subscribeTheme,
} from "../theme";

const html = () => document.documentElement;

// Saved so the accessor-throws case can restore the real localStorage.
const localStorageDescriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");

beforeEach(() => {
  localStorage.clear();
  html().removeAttribute("data-theme");
  html().removeAttribute("data-glass");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  if (localStorageDescriptor) {
    Object.defineProperty(globalThis, "localStorage", localStorageDescriptor);
  }
});

describe("constants", () => {
  it("exposes the attribute/storage contract", () => {
    expect(THEMES).toEqual(["light", "dim"]);
    expect(THEME_KEY).toBe("filaops_theme");
    expect(GLASS_KEY).toBe("filaops_glass");
    expect(INITIAL_THEME_STRATEGY).toBe("light");
  });
});

describe("resolveInitialTheme", () => {
  it("defaults to light with nothing stored", () => {
    expect(resolveInitialTheme({})).toBe("light");
    expect(resolveInitialTheme()).toBe("light");
  });

  it("lets a stored preference win", () => {
    expect(resolveInitialTheme({ stored: "dim" })).toBe("dim");
    expect(resolveInitialTheme({ stored: "light" })).toBe("light");
    expect(resolveInitialTheme({ stored: "dim", prefersDark: false, strategy: "system" })).toBe("dim");
  });

  it("treats unknown stored values as unset", () => {
    expect(resolveInitialTheme({ stored: "dark" })).toBe("light");
    expect(resolveInitialTheme({ stored: "garbage" })).toBe("light");
    expect(resolveInitialTheme({ stored: null })).toBe("light");
    expect(resolveInitialTheme({ stored: "" })).toBe("light");
  });

  it("ignores prefersDark under the default (light) strategy", () => {
    expect(resolveInitialTheme({ stored: null, prefersDark: true })).toBe("light");
  });

  it("follows prefersDark under the system strategy", () => {
    expect(resolveInitialTheme({ stored: null, prefersDark: true, strategy: "system" })).toBe("dim");
    expect(resolveInitialTheme({ stored: null, prefersDark: false, strategy: "system" })).toBe("light");
  });
});

describe("prefersDarkScheme", () => {
  it("reads matchMedia when available", () => {
    const matchMedia = vi.fn(() => ({ matches: true }));
    vi.stubGlobal("matchMedia", matchMedia);
    expect(prefersDarkScheme()).toBe(true);
    expect(matchMedia).toHaveBeenCalledWith("(prefers-color-scheme: dark)");
  });

  it("returns false without matchMedia", () => {
    vi.stubGlobal("matchMedia", undefined);
    expect(prefersDarkScheme()).toBe(false);
  });

  it("returns false when matchMedia throws", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => {
        throw new Error("boom");
      })
    );
    expect(prefersDarkScheme()).toBe(false);
  });

  it("is never consulted by getTheme under the default strategy", () => {
    const matchMedia = vi.fn(() => ({ matches: true }));
    vi.stubGlobal("matchMedia", matchMedia);
    expect(getTheme()).toBe("light");
    expect(matchMedia).not.toHaveBeenCalled();
  });
});

describe("storage that throws", () => {
  it("case A: getItem throws → unset, light, attribute still applied", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });

    expect(readStoredTheme()).toBeNull();
    expect(readStoredGlass()).toBeNull();
    expect(getTheme()).toBe("light");
    expect(setTheme("dim")).toBe("dim");
    expect(html().getAttribute("data-theme")).toBe("dim");
  });

  it("case B: the localStorage accessor throws → unset, light, attribute still applied", () => {
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      get() {
        throw new DOMException("denied", "SecurityError");
      },
    });

    expect(readStoredTheme()).toBeNull();
    expect(readStoredGlass()).toBeNull();
    expect(getTheme()).toBe("light");
    expect(setTheme("dim")).toBe("dim");
    expect(html().getAttribute("data-theme")).toBe("dim");
    expect(setGlass("off")).toBe("off");
    expect(html().getAttribute("data-glass")).toBe("off");
  });
});

describe("readStoredTheme / readStoredGlass", () => {
  it("returns the raw stored strings", () => {
    expect(readStoredTheme()).toBeNull();
    localStorage.setItem(THEME_KEY, "dim");
    localStorage.setItem(GLASS_KEY, "off");
    expect(readStoredTheme()).toBe("dim");
    expect(readStoredGlass()).toBe("off");
  });
});

describe("applyTheme / applyGlass", () => {
  it("writes data-theme and coerces unknown values to light", () => {
    expect(applyTheme("dim")).toBe("dim");
    expect(html().getAttribute("data-theme")).toBe("dim");
    expect(applyTheme("dark")).toBe("light");
    expect(html().getAttribute("data-theme")).toBe("light");
  });

  it("sets data-glass only for off and removes it for on", () => {
    expect(applyGlass("off")).toBe("off");
    expect(html().getAttribute("data-glass")).toBe("off");
    expect(applyGlass("on")).toBe("on");
    expect(html().hasAttribute("data-glass")).toBe(false);
    applyGlass("off");
    expect(applyGlass("nonsense")).toBe("on");
    expect(html().hasAttribute("data-glass")).toBe(false);
  });
});

describe("getTheme", () => {
  it("prefers a valid applied attribute over storage", () => {
    localStorage.setItem(THEME_KEY, "light");
    html().setAttribute("data-theme", "dim");
    expect(getTheme()).toBe("dim");
  });

  it("falls back to storage when the attribute is absent or invalid", () => {
    localStorage.setItem(THEME_KEY, "dim");
    expect(getTheme()).toBe("dim");
    html().setAttribute("data-theme", "dark");
    expect(getTheme()).toBe("dim");
  });

  it("resolves light when nothing is set anywhere", () => {
    expect(getTheme()).toBe("light");
  });
});

describe("getGlass", () => {
  it("reads the attribute, then storage, then defaults on", () => {
    expect(getGlass()).toBe("on");
    localStorage.setItem(GLASS_KEY, "off");
    expect(getGlass()).toBe("off");
    localStorage.clear();
    html().setAttribute("data-glass", "off");
    expect(getGlass()).toBe("off");
  });
});

describe("setTheme", () => {
  it("writes the attribute, persists and dispatches the window event", () => {
    const listener = vi.fn();
    window.addEventListener(THEME_EVENT, listener);

    expect(setTheme("dim")).toBe("dim");

    expect(html().getAttribute("data-theme")).toBe("dim");
    expect(localStorage.getItem(THEME_KEY)).toBe("dim");
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail).toEqual({ theme: "dim" });

    window.removeEventListener(THEME_EVENT, listener);
  });

  it("ignores unknown values", () => {
    html().setAttribute("data-theme", "dim");
    expect(setTheme("dark")).toBe("dim");
    expect(html().getAttribute("data-theme")).toBe("dim");
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
  });
});

describe("setGlass", () => {
  it("writes the attribute and persists", () => {
    expect(setGlass("off")).toBe("off");
    expect(html().getAttribute("data-glass")).toBe("off");
    expect(localStorage.getItem(GLASS_KEY)).toBe("off");
    expect(setGlass("on")).toBe("on");
    expect(html().hasAttribute("data-glass")).toBe(false);
    expect(localStorage.getItem(GLASS_KEY)).toBe("on");
  });

  it("ignores unknown values", () => {
    expect(setGlass("blurry")).toBe("on");
    expect(localStorage.getItem(GLASS_KEY)).toBeNull();
  });
});

describe("subscribeTheme", () => {
  it("notifies on setTheme and stops after unsubscribe", () => {
    const callback = vi.fn();
    const unsubscribe = subscribeTheme(callback);

    setTheme("dim");
    expect(callback).toHaveBeenCalledTimes(1);
    expect(callback).toHaveBeenLastCalledWith("dim");

    unsubscribe();
    setTheme("light");
    expect(callback).toHaveBeenCalledTimes(1);
  });

  it("applies a cross-tab storage change before notifying", () => {
    const callback = vi.fn(() => html().getAttribute("data-theme"));
    const unsubscribe = subscribeTheme(callback);

    window.dispatchEvent(new StorageEvent("storage", { key: THEME_KEY, newValue: "dim" }));

    expect(html().getAttribute("data-theme")).toBe("dim");
    expect(callback).toHaveBeenCalledWith("dim");
    // The attribute was already "dim" when the callback ran.
    expect(callback.mock.results[0].value).toBe("dim");

    unsubscribe();
  });

  it("resolves garbage or cleared storage from another tab to light", () => {
    const callback = vi.fn();
    const unsubscribe = subscribeTheme(callback);
    html().setAttribute("data-theme", "dim");

    window.dispatchEvent(new StorageEvent("storage", { key: THEME_KEY, newValue: "dark" }));
    expect(html().getAttribute("data-theme")).toBe("light");
    expect(callback).toHaveBeenLastCalledWith("light");

    html().setAttribute("data-theme", "dim");
    window.dispatchEvent(new StorageEvent("storage", { key: THEME_KEY, newValue: null }));
    expect(html().getAttribute("data-theme")).toBe("light");

    unsubscribe();
  });

  it("ignores storage events for other keys", () => {
    const callback = vi.fn();
    const unsubscribe = subscribeTheme(callback);
    html().setAttribute("data-theme", "dim");

    window.dispatchEvent(new StorageEvent("storage", { key: "adminUser", newValue: "{}" }));

    expect(callback).not.toHaveBeenCalled();
    expect(html().getAttribute("data-theme")).toBe("dim");

    unsubscribe();
  });
});
