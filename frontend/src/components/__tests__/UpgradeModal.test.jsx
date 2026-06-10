/**
 * Unit tests for UpgradeModal.
 *
 * Covers:
 *  - Modal is closed by default (nothing rendered)
 *  - Opens when tier:limit-reached event is emitted, shows resource/limit info
 *  - "Maybe Later" closes the modal
 *  - "View Plans" link points to PRICING_URL
 *  - Modal is importable from App.jsx (mount smoke test)
 */
import { render, screen, act, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { emit } from "../../lib/events";
import UpgradeModal from "../UpgradeModal";

// Suppress requestAnimationFrame in jsdom (Modal uses it for focus)
beforeEach(() => {
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
    cb(0);
    return 0;
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function fireLimit(payload = {}) {
  act(() => {
    emit("tier:limit-reached", {
      resource: "users",
      limit: 3,
      current: 3,
      tier: "community",
      message: "You've reached the user limit.",
      ...payload,
    });
  });
}

describe("UpgradeModal", () => {
  it("renders nothing when no event has been emitted", () => {
    const { container } = render(<UpgradeModal />);
    // Modal returns null when closed
    expect(container.firstChild).toBeNull();
  });

  it("opens when tier:limit-reached is emitted", () => {
    render(<UpgradeModal />);
    fireLimit();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // Modal renders title in both an sr-only span (aria) and a visible h2
    expect(screen.getAllByText("Upgrade to PRO").length).toBeGreaterThanOrEqual(1);
  });

  it("shows resource name and limit/current counts", () => {
    render(<UpgradeModal />);
    fireLimit({ resource: "printers", limit: 5, current: 5 });
    expect(screen.getByText(/printers/)).toBeInTheDocument();
    expect(screen.getByText(/5\/5/)).toBeInTheDocument();
  });

  it("replaces underscores in resource name with spaces", () => {
    render(<UpgradeModal />);
    fireLimit({ resource: "active_users" });
    expect(screen.getByText(/active users/)).toBeInTheDocument();
  });

  it("closes when Maybe Later is clicked", () => {
    render(<UpgradeModal />);
    fireLimit();
    fireEvent.click(screen.getByText("Maybe Later"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("View Plans link points to PRICING_URL", () => {
    render(<UpgradeModal />);
    fireLimit();
    const link = screen.getByRole("link", { name: /View Plans/i });
    expect(link).toHaveAttribute("href", "https://blb3dprinting.com/pro/pricing/");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("can be imported and rendered without crashing (mount smoke test)", () => {
    // This verifies UpgradeModal is a valid, importable React component
    expect(() => render(<UpgradeModal />)).not.toThrow();
  });
});
