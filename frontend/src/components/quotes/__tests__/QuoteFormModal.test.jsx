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

describe("QuoteFormModal descriptions and discounts", () => {
  let previewResponse;

  beforeEach(() => {
    previewResponse = null;
    vi.stubGlobal("fetch", vi.fn((url) => {
      const value = String(url);
      if (value.includes("/api/v1/quotes/preview-totals")) {
        return Promise.resolve(previewResponse
          ? { ok: true, json: () => Promise.resolve(previewResponse) }
          : { ok: false, json: () => Promise.resolve({}) });
      }
      if (value.includes("/api/v1/items")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{
            id: 7,
            name: "Custom Trophy",
            sku: "TROPHY",
            selling_price: "42.56",
            description: "Custom trophy\nGold Top (PLA Silk Gold)",
          }]),
        });
      }
      if (value.includes("/api/v1/settings/company")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ tax_enabled: true, tax_rate_percent: 7, tax_name: "Sales Tax" }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const addTrophy = async () => {
    fireEvent.click(await screen.findByText("Custom Trophy"));
    fireEvent.change(screen.getAllByRole("spinbutton")[0], { target: { value: "2" } });
  };

  it("prefills the line description from the item and sends it", async () => {
    const onSave = vi.fn();
    renderModal({ quote: null, onSave });
    await addTrophy();

    const description = screen.getByLabelText("Description for Custom Trophy");
    expect(description.value).toBe("Custom trophy\nGold Top (PLA Silk Gold)");
    fireEvent.change(description, { target: { value: "Custom trophy\nBlack Base" } });

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: "Create Quote" }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
        lines: [expect.objectContaining({ description: "Custom trophy\nBlack Base", discount_type: null })],
        discount_type: null,
      }));
    });
  });

  it("shows the golden totals for a 10% quote discount and sends it", async () => {
    const onSave = vi.fn();
    renderModal({ quote: null, onSave });
    await addTrophy();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    fireEvent.change(screen.getByLabelText("Quote discount"), { target: { value: "percent" } });
    fireEvent.change(screen.getByLabelText("Quote discount percent"), { target: { value: "10" } });

    await waitFor(() => {
      expect(screen.getByText("$85.12")).toBeTruthy();
      expect(screen.getByText("-$8.51")).toBeTruthy();
      expect(screen.getByText("$76.61")).toBeTruthy();
      expect(screen.getByText("$5.36")).toBeTruthy();
      expect(screen.getByText("$81.97")).toBeTruthy();
    });
    expect(screen.getByText("10% discount:")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Create Quote" }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
        discount_type: "percent",
        discount_value: 10,
        discount_label: null,
      }));
    });
  });

  it("uses the server preview when it is available", async () => {
    previewResponse = {
      lines: [{ unit_price: "42.56", gross: "85.12", discount_amount: "0.00", total: "85.12" }],
      items_gross: "85.12",
      line_discounts: "0.00",
      items_total: "85.12",
      discount_amount: "0.00",
      subtotal: "85.12",
      tax_rate: "0.0600",
      tax_amount: "5.11",
      shipping_cost: "0.00",
      total: "90.23",
    };
    renderModal({ quote: null });
    await addTrophy();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("$90.23")).toBeTruthy();
    expect(screen.getByText("Sales Tax (6.00%):")).toBeTruthy();
  });

  it("blocks saving an incomplete line discount", async () => {
    const onSave = vi.fn();
    renderModal({ quote: null, onSave });
    await addTrophy();
    fireEvent.change(screen.getByLabelText("Line discount"), { target: { value: "amount" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(screen.getByRole("button", { name: "Create Quote" }));

    expect(await screen.findByText(/Custom Trophy: Enter a discount value/)).toBeTruthy();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("keeps saved descriptions and discounts when editing", async () => {
    const onSave = vi.fn();
    renderModal({
      onSave,
      quote: {
        ...quote,
        discount_type: "amount",
        discount_value: "5.00",
        discount_label: "Spring sale",
        lines: [{
          ...quote.lines[0],
          description: "Saved description",
          discount_type: "percent",
          discount_value: "10.00",
          discount_label: null,
        }],
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Update Quote" }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
        discount_type: "amount",
        discount_value: 5,
        discount_label: "Spring sale",
        lines: [expect.objectContaining({
          description: "Saved description",
          discount_type: "percent",
          discount_value: 10,
        })],
      }));
    });
  });
});
