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

function renderList(orders, onScrap, extraHandlers = {}) {
  return render(
    <ProductionQueueList
      orders={orders}
      onOrderClick={() => {}}
      loading={false}
      filters={baseFilters}
      onFiltersChange={() => {}}
      onCreateOrder={() => {}}
      onScrap={onScrap}
      {...extraHandlers}
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

describe("ProductionQueueList — Split/Complete/QC affordances (#858)", () => {
  // These modals were mounted on AdminProduction but nothing ever opened
  // them; the row affordances are the openers.

  it.each(["draft", "scheduled", "released"])(
    "renders a Split button for a %s order with quantity > 1 and calls onSplit",
    async (status) => {
      const onSplit = vi.fn();
      const order = makeOrder({ status, quantity_ordered: 10 });
      renderList([order], vi.fn(), { onSplit });

      const btn = await screen.findByRole("button", { name: /split/i });
      fireEvent.click(btn);
      expect(onSplit).toHaveBeenCalledWith(order);
    },
  );

  it("does NOT render Split for a single-unit order", async () => {
    renderList(
      [makeOrder({ status: "draft", quantity_ordered: 1 })],
      vi.fn(),
      { onSplit: vi.fn() },
    );
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /split/i })).toBeNull();
  });

  it("renders a Complete button for an in_progress order and calls onComplete", async () => {
    const onComplete = vi.fn();
    const order = makeOrder({ status: "in_progress" });
    renderList([order], vi.fn(), { onComplete });

    const btn = await screen.findByRole("button", { name: /^complete$/i });
    fireEvent.click(btn);
    expect(onComplete).toHaveBeenCalledWith(order);
  });

  it("renders a QC button for a qc_hold order and calls onQC", async () => {
    const onQC = vi.fn();
    const order = makeOrder({ status: "qc_hold" });
    renderList([order], vi.fn(), { onQC });

    const btn = await screen.findByRole("button", { name: /^qc$/i });
    fireEvent.click(btn);
    expect(onQC).toHaveBeenCalledWith(order);
  });

  it("renders a QC button when the backend guard is_ready_for_qc is true", async () => {
    const onQC = vi.fn();
    const order = makeOrder({ status: "complete", is_ready_for_qc: true });
    renderList([order], vi.fn(), { onQC });

    expect(
      await screen.findByRole("button", { name: /^qc$/i }),
    ).toBeInTheDocument();
  });

  it("does NOT render QC for a completed order without the guard", async () => {
    renderList(
      [makeOrder({ status: "complete", is_ready_for_qc: false })],
      vi.fn(),
      { onQC: vi.fn() },
    );
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /^qc$/i })).toBeNull();
  });
});
