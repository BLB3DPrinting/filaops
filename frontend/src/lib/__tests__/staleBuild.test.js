import { describe, expect, it, vi } from "vitest";
import { currentBuildId, handlePreloadError, isStaleBuildError, reloadForNewBuild } from "../staleBuild";

const KEY = "filaops:stale-build-reload";

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

describe("currentBuildId", () => {
  it("is the entry script's address", () => {
    document.head.innerHTML =
      '<script type="module" crossorigin src="/assets/index-CZ1E9Z0O.js"></script><script src="/config.js?v=2"></script>';
    expect(currentBuildId()).toBe("/assets/index-CZ1E9Z0O.js");
    document.head.innerHTML = "";
  });
});

describe("reloadForNewBuild", () => {
  it("reloads once and records the build", () => {
    const storage = memoryStorage();
    const reload = vi.fn();
    expect(reloadForNewBuild({ getStorage: () => storage, buildId: "/assets/index-A.js", reload })).toBe(true);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(storage.getItem(KEY)).toBe("/assets/index-A.js");
  });

  it("never reloads the same build twice, however long ago the first was", () => {
    const storage = memoryStorage({ [KEY]: "/assets/index-A.js" });
    const reload = vi.fn();
    expect(reloadForNewBuild({ getStorage: () => storage, buildId: "/assets/index-A.js", reload })).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });

  it("allows one reload for a later build", () => {
    const storage = memoryStorage({ [KEY]: "/assets/index-A.js" });
    const reload = vi.fn();
    expect(reloadForNewBuild({ getStorage: () => storage, buildId: "/assets/index-B.js", reload })).toBe(true);
    expect(storage.getItem(KEY)).toBe("/assets/index-B.js");
  });

  it("does not reload when reading storage throws", () => {
    const storage = {
      getItem: () => {
        throw new Error("SecurityError");
      },
    };
    const reload = vi.fn();
    expect(reloadForNewBuild({ getStorage: () => storage, buildId: "x", reload })).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });

  it("does not reload when the sessionStorage getter itself throws", () => {
    const original = Object.getOwnPropertyDescriptor(globalThis, "sessionStorage");
    Object.defineProperty(globalThis, "sessionStorage", {
      configurable: true,
      get() {
        throw new DOMException("blocked", "SecurityError");
      },
    });
    const reload = vi.fn();
    try {
      expect(() => reloadForNewBuild({ buildId: "x", reload })).not.toThrow();
      expect(reloadForNewBuild({ buildId: "x", reload })).toBe(false);
      expect(reload).not.toHaveBeenCalled();
    } finally {
      if (original) Object.defineProperty(globalThis, "sessionStorage", original);
      else delete globalThis.sessionStorage;
    }
  });
});

describe("handlePreloadError", () => {
  const stale = new TypeError("Failed to fetch dynamically imported module: /assets/Items-abc.js");

  function preloadEvent(payload) {
    return { payload, preventDefault: vi.fn() };
  }

  it("reloads for a file that is gone, and takes the error over", () => {
    const reload = vi.fn();
    const event = preloadEvent(stale);
    const started = handlePreloadError(event, { getStorage: () => memoryStorage(), buildId: "a", reload });
    expect(started).toBe(true);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(event.preventDefault).toHaveBeenCalledTimes(1);
  });

  it("leaves an error thrown by the screen's own code alone", () => {
    // Vite sends this through the same event. Reloading would hide it.
    const reload = vi.fn();
    const event = preloadEvent(new ReferenceError("formatQuantity is not defined"));
    const started = handlePreloadError(event, { getStorage: () => memoryStorage(), buildId: "a", reload });
    expect(started).toBe(false);
    expect(reload).not.toHaveBeenCalled();
    expect(event.preventDefault).not.toHaveBeenCalled();
  });

  it("leaves an event with no payload alone", () => {
    const reload = vi.fn();
    const event = preloadEvent(undefined);
    expect(handlePreloadError(event, { getStorage: () => memoryStorage(), buildId: "a", reload })).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });

  it("does not take the error over when this build was already reloaded once", () => {
    const reload = vi.fn();
    const event = preloadEvent(stale);
    const storage = memoryStorage({ [KEY]: "a" });
    expect(handlePreloadError(event, { getStorage: () => storage, buildId: "a", reload })).toBe(false);
    expect(reload).not.toHaveBeenCalled();
    expect(event.preventDefault).not.toHaveBeenCalled();
  });
});
