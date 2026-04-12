import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect } from "vitest";
import Breadcrumbs, { buildBreadcrumbs, ROUTE_LABELS } from "../Breadcrumbs";

function renderAtPath(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Breadcrumbs />
    </MemoryRouter>
  );
}

describe("buildBreadcrumbs", () => {
  it("returns empty array for dashboard root", () => {
    expect(buildBreadcrumbs("/admin")).toEqual([]);
    expect(buildBreadcrumbs("/admin/")).toEqual([]);
  });

  it("builds crumbs for a top-level page", () => {
    const crumbs = buildBreadcrumbs("/admin/orders");
    expect(crumbs).toHaveLength(2);
    expect(crumbs[0]).toEqual({ label: "Dashboard", path: "/admin" });
    expect(crumbs[1]).toEqual({
      label: "Orders",
      path: "/admin/orders",
      isLast: true,
    });
  });

  it("builds crumbs for a nested page", () => {
    const crumbs = buildBreadcrumbs("/admin/inventory/transactions");
    expect(crumbs).toHaveLength(3);
    expect(crumbs[0].label).toBe("Dashboard");
    expect(crumbs[1].label).toBe("Inventory");
    expect(crumbs[1].path).toBe("/admin/inventory");
    expect(crumbs[2].label).toBe("Transactions");
    expect(crumbs[2].isLast).toBe(true);
  });

  it("handles dynamic ID segments", () => {
    const crumbs = buildBreadcrumbs("/admin/orders/42");
    expect(crumbs).toHaveLength(3);
    expect(crumbs[2].label).toBe("#42");
    expect(crumbs[2].isLast).toBe(true);
  });

  it("handles UUID-like dynamic segments", () => {
    const crumbs = buildBreadcrumbs(
      "/admin/orders/550e8400-e29b-41d4-a716-446655440000"
    );
    expect(crumbs[2].label).toBe(
      "#550e8400-e29b-41d4-a716-446655440000"
    );
  });

  it("title-cases unknown segments", () => {
    const crumbs = buildBreadcrumbs("/admin/some-new-feature");
    expect(crumbs[1].label).toBe("Some New Feature");
  });

  it("builds crumbs for quality/traceability", () => {
    const crumbs = buildBreadcrumbs("/admin/quality/traceability");
    expect(crumbs).toHaveLength(3);
    expect(crumbs[1].label).toBe("Quality");
    expect(crumbs[2].label).toBe("Material Traceability");
  });
});

describe("Breadcrumbs component", () => {
  it("renders nothing on dashboard", () => {
    const { container } = renderAtPath("/admin");
    expect(container.querySelector("nav")).toBeNull();
  });

  it("renders breadcrumb nav for a page", () => {
    renderAtPath("/admin/orders");
    const nav = screen.getByLabelText("Breadcrumb");
    expect(nav).toBeInTheDocument();
  });

  it("renders dashboard as a link and current page as text", () => {
    renderAtPath("/admin/quotes");
    // Dashboard is a link (home icon)
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/admin");
    // Current page not a link
    expect(screen.getByText("Quotes")).toBeInTheDocument();
    expect(screen.getByText("Quotes").closest("a")).toBeNull();
  });

  it("marks the last crumb with aria-current=page", () => {
    renderAtPath("/admin/settings");
    const current = screen.getByText("Settings");
    expect(current).toHaveAttribute("aria-current", "page");
  });

  it("renders nested breadcrumbs with intermediate links", () => {
    renderAtPath("/admin/inventory/cycle-count");
    // Dashboard link + Inventory link + Cycle Count (text)
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[1]).toHaveAttribute("href", "/admin/inventory");
    expect(screen.getByText("Cycle Count")).toBeInTheDocument();
  });

  it("renders dynamic segment as #ID", () => {
    renderAtPath("/admin/production/99");
    expect(screen.getByText("#99")).toBeInTheDocument();
  });
});

describe("ROUTE_LABELS coverage", () => {
  it("has labels for all main nav routes", () => {
    const expectedPaths = [
      "/admin/orders",
      "/admin/quotes",
      "/admin/payments",
      "/admin/invoices",
      "/admin/customers",
      "/admin/items",
      "/admin/bom",
      "/admin/purchasing",
      "/admin/manufacturing",
      "/admin/production",
      "/admin/shipping",
      "/admin/settings",
      "/admin/accounting",
      "/admin/printers",
    ];
    for (const path of expectedPaths) {
      expect(ROUTE_LABELS[path]).toBeDefined();
    }
  });
});
