import { describe, it, expect } from "vitest";
import { API_URL, getApiConnectionHelp, getApiUrl } from "../api";

// What docker-entrypoint.sh writes into config.js when VITE_API_URL is not set
// on the frontend container.
const DOCKER_CONFIG = { API_URL: "", API_SAME_ORIGIN: true };

const page = (url) => {
  const { protocol, hostname, port } = new URL(url);
  return { protocol, hostname, port };
};

const resolve = ({ runtimeConfig, buildTimeUrl = "", url }) =>
  getApiUrl({ runtimeConfig, buildTimeUrl, location: page(url) });

describe("getApiUrl", () => {
  describe("served by the frontend container (nginx proxies /api)", () => {
    it("uses the page's own origin on localhost, whatever the port", () => {
      expect(
        resolve({ runtimeConfig: DOCKER_CONFIG, url: "http://localhost:18400/admin/login" })
      ).toBe("");
      expect(
        resolve({ runtimeConfig: DOCKER_CONFIG, url: "http://localhost/admin/login" })
      ).toBe("");
    });

    it("uses the page's own origin on 127.0.0.1", () => {
      expect(
        resolve({ runtimeConfig: DOCKER_CONFIG, url: "http://127.0.0.1:18400/" })
      ).toBe("");
    });

    it("uses the page's own origin on another host", () => {
      expect(
        resolve({ runtimeConfig: DOCKER_CONFIG, url: "http://192.168.1.50:8080/" })
      ).toBe("");
      expect(
        resolve({ runtimeConfig: DOCKER_CONFIG, url: "https://erp.example.com/" })
      ).toBe("");
    });
  });

  describe("vite dev server (no config.js)", () => {
    it("reaches the backend on http://localhost:8000", () => {
      expect(
        resolve({ runtimeConfig: undefined, url: "http://localhost:5173/" })
      ).toBe("http://localhost:8000");
      expect(
        resolve({ runtimeConfig: undefined, url: "http://127.0.0.1:5173/" })
      ).toBe("http://localhost:8000");
    });
  });

  describe("an explicit address", () => {
    it("set on the container at runtime wins over the page's own origin", () => {
      expect(
        resolve({
          runtimeConfig: { API_URL: "http://192.168.1.50:8000", API_SAME_ORIGIN: true },
          url: "http://localhost:18400/",
        })
      ).toBe("http://192.168.1.50:8000");
    });

    it("set at build time wins over the page's own origin", () => {
      expect(
        resolve({
          runtimeConfig: DOCKER_CONFIG,
          buildTimeUrl: "http://192.168.1.50:8000",
          url: "http://localhost:18400/",
        })
      ).toBe("http://192.168.1.50:8000");
    });

    it("set at build time is used by the dev server", () => {
      expect(
        resolve({
          runtimeConfig: undefined,
          buildTimeUrl: "http://localhost:8001",
          url: "http://localhost:5173/",
        })
      ).toBe("http://localhost:8001");
    });

    it("set at runtime wins over one set at build time", () => {
      expect(
        resolve({
          runtimeConfig: { API_URL: "http://runtime:8000", API_SAME_ORIGIN: true },
          buildTimeUrl: "http://build:8000",
          url: "http://localhost/",
        })
      ).toBe("http://runtime:8000");
    });
  });

  describe("no marker and no address (static build behind another web server)", () => {
    it("uses the page's own origin over https or on a host other than localhost", () => {
      expect(resolve({ runtimeConfig: undefined, url: "https://localhost/" })).toBe("");
      expect(resolve({ runtimeConfig: undefined, url: "http://filaops.local/" })).toBe("");
    });

    // A config.js written before the marker existed (for example one a browser
    // still holds from an older version) must behave as it always did.
    it("treats a config.js without the marker like no config.js", () => {
      expect(
        resolve({ runtimeConfig: { API_URL: "" }, url: "http://localhost/" })
      ).toBe("http://localhost:8000");
    });

    it("only accepts the marker as the boolean true", () => {
      expect(
        resolve({
          runtimeConfig: { API_URL: "", API_SAME_ORIGIN: "false" },
          url: "http://localhost/",
        })
      ).toBe("http://localhost:8000");
    });
  });

  it("is what API_URL is resolved from when called with no arguments", () => {
    // jsdom: http://localhost:3000, no config.js, no VITE_API_URL.
    expect(getApiUrl()).toBe(API_URL);
  });
});

describe("getApiConnectionHelp", () => {
  const help = ({ apiUrl, runtimeConfig, url }) => {
    const { origin, hostname } = new URL(url);
    return getApiConnectionHelp({ apiUrl, runtimeConfig, location: { origin, hostname } });
  };

  it("names the page's own address when the frontend container proxies /api", () => {
    const text = help({
      apiUrl: "",
      runtimeConfig: DOCKER_CONFIG,
      url: "http://localhost:18400/admin/login",
    });
    expect(text).toBe(
      "Cannot connect to API at http://localhost:18400. Please ensure the backend is running."
    );
  });

  it("does not tell a Docker install to set VITE_API_URL or rebuild", () => {
    const text = help({
      apiUrl: "",
      runtimeConfig: DOCKER_CONFIG,
      url: "http://192.168.1.50/admin/login",
    });
    expect(text).not.toMatch(/VITE_API_URL|rebuild/);
  });

  it("names the address in use when one is set or the dev default applies", () => {
    expect(
      help({
        apiUrl: "http://localhost:8000",
        runtimeConfig: undefined,
        url: "http://localhost:5173/admin/login",
      })
    ).toBe(
      "Cannot connect to API at http://localhost:8000. Please ensure the backend is running at that address."
    );
  });

  it("points at VITE_API_URL when a build without the container has no address", () => {
    const text = help({
      apiUrl: "",
      runtimeConfig: undefined,
      url: "http://192.168.1.50:5173/admin/login",
    });
    expect(text).toBe(
      "Cannot connect to API at http://192.168.1.50:5173. " +
        "If the backend is at another address, set VITE_API_URL to it " +
        "(e.g., http://192.168.1.50:8000) and restart or rebuild the frontend."
    );
  });
});
