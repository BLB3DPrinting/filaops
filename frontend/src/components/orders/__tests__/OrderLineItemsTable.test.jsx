/**
 * OrderLineItemsTable shows the descriptions and discounts carried from a quote.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import OrderLineItemsTable from "../OrderLineItemsTable";

vi.mock("../../../hooks/useApi", () => ({ useApi: () => ({ patch: vi.fn(), del: vi.fn() }) }));
vi.mock("../../Toast", () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }));

const baseOrder = {
  status: "shipped",
  tax_amount: "5.36",
  shipping_cost: "0.00",
  total_price: "76.61",
  grand_total: "81.97",
  lines: [{
    id: 1,
    product_name: "Custom Trophy",
    product_sku: "TROPHY",
    quantity: 2,
    unit_price: "42.56",
    total: "85.12",
    long_description: "Black Base (PLA Matte Charcoal)\nGold Plate with words",
  }],
};

const renderTable = (order) => render(<OrderLineItemsTable order={order} orderId={1} onOrderUpdated={vi.fn()} />);

describe("OrderLineItemsTable discounts", () => {
  it("shows the line description and the quote discount above the subtotal", () => {
    renderTable({
      ...baseOrder,
      discount_type: "percent",
      discount_value: "10.00",
      discount_label: "10% discount",
      discount_amount: "8.51",
    });
    expect(screen.getByText(/Gold Plate with words/)).toBeInTheDocument();
    expect(screen.getByText("Items total")).toBeInTheDocument();
    expect(screen.getByText("10% discount")).toBeInTheDocument();
    expect(screen.getByText("-$8.51")).toBeInTheDocument();
    expect(screen.getByText("$76.61")).toBeInTheDocument();
    expect(screen.getByText("$81.97")).toBeInTheDocument();
  });

  it("shows a line discount and the line amount before it", () => {
    renderTable({
      ...baseOrder,
      total_price: "76.61",
      lines: [{
        ...baseOrder.lines[0],
        total: "76.61",
        discount_type: "amount",
        discount_value: "8.51",
        discount_label: "Loyalty",
        discount_amount: "8.51",
      }],
    });
    expect(screen.getByText("Loyalty: -$8.51")).toBeInTheDocument();
    expect(screen.getAllByText("$85.12").length).toBe(2); // line amount + items total
    expect(screen.getByText("Line discounts")).toBeInTheDocument();
  });

  it("adds no rows for an order without discounts", () => {
    renderTable({ ...baseOrder, total_price: "85.12", grand_total: "91.08" });
    expect(screen.queryByText("Items total")).not.toBeInTheDocument();
    expect(screen.getAllByText("$85.12").length).toBe(2); // line + subtotal
  });
});
