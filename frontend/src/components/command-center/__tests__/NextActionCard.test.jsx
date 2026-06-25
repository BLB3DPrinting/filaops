import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { MemoryRouter } from "react-router-dom";
import NextActionCard from "../NextActionCard";

const renderCard = (action) =>
  render(
    <MemoryRouter>
      <NextActionCard action={action} />
    </MemoryRouter>
  );

describe("NextActionCard", () => {
  it("renders label, reason, target code, and a severity badge", () => {
    renderCard({
      axis: "production",
      label: "PO blocked",
      reason: "Out of PLA",
      severity: "critical",
      target: { type: "production_order", id: 7, code: "WO-7" },
      enabled: true,
    });
    expect(screen.getByText("PO blocked")).toBeTruthy();
    expect(screen.getByText("Out of PLA")).toBeTruthy();
    expect(screen.getByText("WO-7")).toBeTruthy();
    expect(screen.getByText("Critical")).toBeTruthy(); // severity badge
  });

  it("renders the deep-link with verbLabel when enabled + href", () => {
    renderCard({
      axis: "supply",
      label: "Order filament",
      severity: "high",
      verbLabel: "View PO",
      href: "/admin/purchasing/3",
      enabled: true,
    });
    const link = screen.getByRole("link", { name: /View PO/ });
    expect(link.getAttribute("href")).toBe("/admin/purchasing/3");
  });

  it("defaults the button label to 'Open' when no verbLabel", () => {
    renderCard({ axis: "fulfillment", label: "Ship it", severity: "high", href: "/x", enabled: true });
    expect(screen.getByRole("link", { name: /Open/ })).toBeTruthy();
  });

  it("shows the disabled reason instead of a link when not actionable", () => {
    renderCard({
      axis: "payment",
      label: "Collect payment",
      severity: "medium",
      enabled: false,
      disabledReason: "Awaiting invoice",
    });
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("Awaiting invoice")).toBeTruthy();
  });

  it("renders nothing for a null/invalid action", () => {
    const { container } = renderCard(null);
    expect(container.firstChild).toBeNull();
  });
});
