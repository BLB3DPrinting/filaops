import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import QuoteFormModal from "../QuoteFormModal";
import { ToastProvider } from "../../Toast";

vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));

const quote = {
  id: 42,
  quote_number: "Q-2026-000042",
  status: "pending",
  customer_id: null,
  customer_name: "Example Customer",
  customer_email: "customer@example.com",
  customer_notes: "",
  admin_notes: "",
  tax_rate: null,
  shipping_cost: "0.00",
  lines: [
    {
      id: 101,
      product_id: 201,
      product_name: "Bracket",
      quantity: 2,
      unit_price: "15.00",
      total: "30.00",
      material_type: "PETG",
      color: "Black",
      notes: "Original note",
    },
  ],
};

const renderModal = (props = {}) => render(
  <ToastProvider>
    <QuoteFormModal
      quote={quote}
      onSave={vi.fn()}
      onClose={vi.fn()}
      {...props}
    />
  </ToastProvider>,
);

describe("QuoteFormModal editing", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((url) => {
      const value = String(url);
      if (value.includes("/api/v1/items")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      if (value.includes("/api/v1/admin/customers")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      if (value.includes("/api/v1/settings/company")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ tax_enabled: false }),
        });
      }
      if (value.includes("/api/v1/tax-rates")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("submits edited line quantity and price for an existing manual quote", async () => {
    const onSave = vi.fn();
    renderModal({ onSave });

    fireEvent.click(screen.getByRole("button", { name: "Edit Items" }));

    const spinButtons = screen.getAllByRole("spinbutton");
    fireEvent.change(spinButtons[0], { target: { value: "3" } });
    fireEvent.change(spinButtons[1], { target: { value: "20.00" } });

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: "Update Quote" }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
        lines: [
          expect.objectContaining({
            product_id: 201,
            product_name: "Bracket",
            quantity: 3,
            unit_price: 20,
          }),
        ],
      }));
    });
  });
});
