import { describe, expect, it, vi } from "vitest";
import { isStaleBuildError, reloadForNewBuild } from "../staleBuild";

function memoryStorage(initial = {}) {
  const data = { ...initial };
  return {
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => {
      data[k] = String(v);
    },
  };
}

describe("isStaleBuildError", () => {
  it.each([
    "Failed to fetch dynamically imported module: http://localhost:18400/assets/CommandCenter-CAG0geRE.js",
    "error loading dynamically imported module: https://x/assets/a.js",
    "Importing a module script failed.",
    "Unable to preload CSS for /assets/index-abc.css",
  ])("recognises %s", (message) => {
    expect(isStaleBuildError(new TypeError(message))).toBe(true);
  });

  it("ignores other errors", () => {
    expect(isStaleBuildError(new Error("Cannot read properties of undefined"))).toBe(false);
    expect(isStaleBuildError(null)).toBe(false);
  });
});

describe("reloadForNewBuild", () => {
  it("reloads once and records the time", () => {
    const storage = memoryStorage();
    const reload = vi.fn();
    expect(reloadForNewBuild({ storage, now: 100_000, reload })).toBe(true);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(storage.getItem("filaops:stale-build-reload")).toBe("100000");
  });

  it("does not reload again within 30 seconds", () => {
    const storage = memoryStorage({ "filaops:stale-build-reload": "100000" });
    const reload = vi.fn();
    expect(reloadForNewBuild({ storage, now: 120_000, reload })).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });

  it("reloads again after the window", () => {
    const storage = memoryStorage({ "filaops:stale-build-reload": "100000" });
    const reload = vi.fn();
    expect(reloadForNewBuild({ storage, now: 131_000, reload })).toBe(true);
  });

  it("does not reload when storage is blocked", () => {
    const storage = {
      getItem: () => {
        throw new Error("SecurityError");
      },
    };
    const reload = vi.fn();
    expect(reloadForNewBuild({ storage, now: 1, reload })).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });
});
