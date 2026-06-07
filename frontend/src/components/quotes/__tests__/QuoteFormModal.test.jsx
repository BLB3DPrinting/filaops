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

let companySettingsResponse;

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
    companySettingsResponse = { tax_enabled: false };
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
          json: () => Promise.resolve(companySettingsResponse),
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

  it("submits one-time fee lines without a product id", async () => {
    const onSave = vi.fn();
    renderModal({ quote: null, onSave });

    fireEvent.click(screen.getByRole("tab", { name: "Fees" }));
    fireEvent.change(screen.getByPlaceholderText("Engineering fee"), {
      target: { value: "Engineering fee" },
    });
    fireEvent.change(screen.getByPlaceholderText("75.00"), {
      target: { value: "75.00" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: "Create Quote" }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
        lines: [
          expect.objectContaining({
            product_id: null,
            product_name: "Engineering fee",
            quantity: 1,
            unit_price: 75,
          }),
        ],
      }));
    });
  });

  it("includes taxable shipping in the quote tax preview", async () => {
    companySettingsResponse = {
      tax_enabled: true,
      tax_rate_percent: 7,
      tax_name: "Sales Tax",
      company_state: "IN",
    };
    renderModal({
      quote: {
        ...quote,
        tax_rate: "0.07",
        shipping_cost: "10.00",
        lines: [
          {
            ...quote.lines[0],
            quantity: 2,
            unit_price: "50.00",
            total: "100.00",
          },
        ],
      },
    });

    await waitFor(() => {
      expect(screen.getByText("$7.70")).toBeTruthy();
      expect(screen.getByText("$117.70")).toBeTruthy();
    });
  });
});
