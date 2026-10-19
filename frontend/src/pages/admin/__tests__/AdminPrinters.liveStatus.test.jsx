/**
 * AdminPrinters table view shows live printer status when PRO's FilaFarm is
 * available. Core's stored printers.status is only a last-known value, so on
 * production (2026-10-19) every printer read "offline" in the table while it
 * was printing; only the HUD view fetched PRO's live overlay.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mocks } = vi.hoisted(() => ({
  mocks: { get: vi.fn(), isPro: true, features: ["filafarm"] },
}));

vi.mock("../../../hooks/useApi", () => {
  const api = { get: mocks.get, post: vi.fn(), patch: vi.fn(), del: vi.fn() };
  return { useApi: () => api };
});

vi.mock("../../../hooks/useFeatureFlags", () => ({
  useFeatureFlags: () => ({
    tier: mocks.isPro ? "professional" : "community",
    features: mocks.features,
    hasFeature: (feature) => mocks.isPro && mocks.features.includes(feature),
    isPro: mocks.isPro,
    isEnterprise: false,
    loading: false,
  }),
}));

vi.mock("../../../components/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}));

import AdminPrinters from "../AdminPrinters";

const corePrinter = {
  id: 1,
  name: "Leonardo",
  code: "PRT-001",
  brand: "bambulab",
  model: "P1S",
  status: "offline", // stale stored value
  active: true,
};

function routeGets() {
  mocks.get.mockImplementation((path) => {
    if (path.startsWith("/api/v1/printers?")) return Promise.resolve({ items: [corePrinter] });
    if (path === "/api/v1/pro/filafarm/printers") {
      return Promise.resolve({
        printers: [{ id: "1", status: "printing", state: "preparing", state_label: "Preparing" }],
      });
    }
    if (path === "/api/v1/printers/active-work") return Promise.resolve({ printers: {} });
    if (path === "/api/v1/printers/brands/info") return Promise.resolve({ brands: [] });
    return Promise.resolve({ items: [] });
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminPrinters />
    </MemoryRouter>
  );
}

beforeEach(() => {
  mocks.get.mockReset();
  mocks.isPro = true;
  mocks.features = ["filafarm"];
  routeGets();
});

describe("AdminPrinters table view status", () => {
  it("shows PRO's live state in the table view", async () => {
    renderPage();

    expect(await screen.findByText("Preparing")).toBeInTheDocument();
    expect(screen.getByTestId("printer-status-1")).toHaveTextContent("Preparing");
    expect(screen.getByTestId("printer-status-1")).toHaveAttribute("aria-live", "polite");
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/pro/filafarm/printers");
  });

  it("shows Core's status and skips the PRO call without FilaFarm", async () => {
    mocks.isPro = false;

    renderPage();

    expect(await screen.findByTestId("printer-status-1")).toHaveTextContent("offline");
    expect(mocks.get).not.toHaveBeenCalledWith("/api/v1/pro/filafarm/printers");
  });
});
