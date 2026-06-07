import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ReviewStep from "../ReviewStep";

const lineItems = [
  {
    _key: "product-1",
    line_type: "product",
    product: { name: "Bracket", sku: "BRACKET-001" },
    quantity: 2,
    unit_price: 50,
  },
];

const renderReview = ({
  shippingState = "IN",
  companyState = "IN",
} = {}) => render(
  <ReviewStep
    selectedCustomer={null}
    orderData={{
      shipping_address_line1: "",
      shipping_city: "",
      shipping_state: shippingState,
      shipping_zip: "",
      shipping_cost: "10.00",
      customer_notes: "",
    }}
    lineItems={lineItems}
    orderTotal={100}
    taxSettings={{
      tax_enabled: true,
      tax_rate: 0.07,
      tax_name: "Sales Tax",
      company_state: companyState,
    }}
  />,
);

describe("ReviewStep order totals", () => {
  it("includes shipping in the displayed grand total and taxable base when shipping is taxable", () => {
    renderReview();

    expect(screen.getByText("Shipping")).toBeTruthy();
    expect(screen.getByText("$10.00")).toBeTruthy();
    expect(screen.getByText("$7.70")).toBeTruthy();
    expect(screen.getByText("$117.70")).toBeTruthy();
  });

  it("keeps shipping out of the tax preview when destination state is not shipping-taxable", () => {
    renderReview({ shippingState: "OH", companyState: "IN" });

    expect(screen.getByText("$10.00")).toBeTruthy();
    expect(screen.getByText("$7.00")).toBeTruthy();
    expect(screen.getByText("$117.00")).toBeTruthy();
  });
});
