import { describe, it, expect } from "vitest";
import {
  NAV_TITLES,
  WORKBENCH_ROUTES,
  DEFAULT_DOCUMENT_TITLE,
  resolveRouteTitle,
  documentTitleFor,
  isWorkbenchRoute,
} from "../routeTitles";
import { navGroups } from "../navConfig";

describe("NAV_TITLES", () => {
  it("covers every navGroups item with its label", () => {
    const items = navGroups.flatMap((group) => group.items);
    expect(Object.keys(NAV_TITLES)).toHaveLength(items.length);
    for (const item of items) {
      expect(NAV_TITLES[item.path]).toBe(item.label);
    }
  });

  it("is frozen", () => {
    expect(Object.isFrozen(NAV_TITLES)).toBe(true);
    expect(Object.isFrozen(WORKBENCH_ROUTES)).toBe(true);
  });
});

describe("resolveRouteTitle", () => {
  it("returns the nav label for static routes", () => {
    expect(resolveRouteTitle("/admin")).toBe("Command Center");
    expect(resolveRouteTitle("/admin/orders")).toBe("Orders");
    expect(resolveRouteTitle("/admin/shipping")).toBe("Shipping");
    expect(resolveRouteTitle("/admin/quality")).toBe("Quality Dashboard");
    expect(resolveRouteTitle("/admin/manufacturing")).toBe("Work Centers & Routings");
    expect(resolveRouteTitle("/admin/inventory/cycle-count")).toBe("Cycle Count");
  });

  it("titles detail routes as parent #id", () => {
    expect(resolveRouteTitle("/admin/orders/42")).toBe("Orders #42");
    expect(resolveRouteTitle("/admin/production/7")).toBe("Production #7");
  });

  it("accepts a UUID-shaped id", () => {
    expect(resolveRouteTitle("/admin/orders/123e4567-e89b-12d3-a456-426614174000")).toBe(
      "Orders #123e4567-e89b-12d3-a456-426614174000"
    );
  });

  it("ignores a trailing slash", () => {
    expect(resolveRouteTitle("/admin/orders/")).toBe("Orders");
    expect(resolveRouteTitle("/admin/orders/42/")).toBe("Orders #42");
    expect(resolveRouteTitle("/admin/")).toBe("Command Center");
  });

  it("title-cases unknown routes", () => {
    expect(resolveRouteTitle("/admin/some-new-page")).toBe("Some New Page");
    expect(resolveRouteTitle("/admin/inventory")).toBe("Inventory");
  });

  it("title-cases the parent of an unknown detail route", () => {
    expect(resolveRouteTitle("/admin/work-orders/9")).toBe("Work Orders #9");
  });

  it("keeps static children of dynamic parents static", () => {
    expect(resolveRouteTitle("/admin/orders/import")).toBe("Import Orders");
    expect(resolveRouteTitle("/admin/materials/import")).toBe("Import Materials");
  });

  it("returns an empty title for the root", () => {
    expect(resolveRouteTitle("/")).toBe("");
    expect(resolveRouteTitle("")).toBe("");
  });
});

describe("documentTitleFor", () => {
  it("suffixes the route title with the product name", () => {
    expect(documentTitleFor("/admin")).toBe("Command Center · FilaOps");
    expect(documentTitleFor("/admin/shipping")).toBe("Shipping · FilaOps");
    expect(documentTitleFor("/admin/orders/42")).toBe("Orders #42 · FilaOps");
  });

  it("falls back to the default title when nothing resolves", () => {
    expect(documentTitleFor("/")).toBe(DEFAULT_DOCUMENT_TITLE);
  });

  it("default title matches the static index.html title", () => {
    expect(DEFAULT_DOCUMENT_TITLE).toBe("FilaOps Production Scheduling");
  });
});

describe("isWorkbenchRoute", () => {
  it.each([
    "/admin/shipping",
    "/admin/production",
    "/admin/orders/42",
    "/admin/orders/42/",
    "/admin/production/7",
    "/admin/shipping/",
  ])("is true for migrated route %s", (path) => {
    expect(isWorkbenchRoute(path)).toBe(true);
  });

  it.each([
    "/admin",
    "/admin/orders",
    "/admin/orders/import",
    "/admin/materials/import",
    "/admin/quality/plans",
    "/admin/orders/42/lines",
    "/admin/customers/42",
    "/",
  ])("is false for gated route %s", (path) => {
    expect(isWorkbenchRoute(path)).toBe(false);
  });

  it("lists exactly the four PR-3 routes", () => {
    expect(WORKBENCH_ROUTES).toEqual([
      "/admin/shipping",
      "/admin/production",
      "/admin/production/:orderId",
      "/admin/orders/:orderId",
    ]);
  });
});
