import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import ProductionQueueList from "../ProductionQueueList";

// ProductionQueueList fetches work centers (once) and per-order operations
// (per order) on mount. Stub both with empty payloads so the rows render
// without network. The Scrap-button wiring under test does not depend on
// operations data.
beforeEach(() => {
  global.fetch = vi.fn().mockImplementation(async (url) => {
    const urlStr = typeof url === "string" ? url : url.toString();
    let data = {};
    if (urlStr.includes("/work-centers")) data = { items: [] };
    else if (urlStr.includes("/operations")) data = { operations: [] };
    return {
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      json: async () => data,
      text: async () => JSON.stringify(data),
    };
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

const baseFilters = { status: "all", search: "", workCenter: "all" };

function makeOrder(overrides) {
  return {
    id: 1,
    code: "PO-001",
    product_name: "Widget A",
    quantity_ordered: 10,
    quantity_completed: 10,
    quantity_scrapped: 0,
    status: "complete",
    ...overrides,
  };
}

function renderList(orders, onScrap) {
  return render(
    <ProductionQueueList
      orders={orders}
      onOrderClick={() => {}}
      loading={false}
      filters={baseFilters}
      onFiltersChange={() => {}}
      onCreateOrder={() => {}}
      onScrap={onScrap}
    />,
  );
}

describe("ProductionQueueList — Scrap affordance (#781)", () => {
  it("renders a Scrap button for a completed order and calls onScrap with it when clicked", async () => {
    const onScrap = vi.fn();
    const order = makeOrder({ status: "complete" });
    renderList([order], onScrap);

    const scrapBtn = await screen.findByRole("button", { name: /scrap/i });
    expect(scrapBtn).toBeInTheDocument();

    fireEvent.click(scrapBtn);
    expect(onScrap).toHaveBeenCalledTimes(1);
    expect(onScrap).toHaveBeenCalledWith(order);
  });

  // `complete` is exercised by the click test above; cover the remaining
  // scrappable statuses so the canScrap gate can't silently narrow.
  it.each(["in_progress", "qc_hold", "short"])(
    "renders a Scrap button for a %s order",
    async (status) => {
      const onScrap = vi.fn();
      renderList([makeOrder({ id: 2, code: "PO-002", status })], onScrap);

      expect(
        await screen.findByRole("button", { name: /scrap/i }),
      ).toBeInTheDocument();
    },
  );

  it("does NOT render a Scrap button for a draft order (nothing produced yet)", async () => {
    const onScrap = vi.fn();
    renderList([makeOrder({ id: 3, code: "PO-003", status: "draft" })], onScrap);

    // Let the mount effects settle so we are asserting on the final render.
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /scrap/i })).toBeNull();
  });
});
