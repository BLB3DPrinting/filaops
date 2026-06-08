# Order-To-Cash UI Workflow Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Orders experience around the real order-to-cash business workflow so staff can confirm pricing, create/send invoices, collect or approve payment terms, release work to production, fulfill, ship, and close orders without guessing which page owns the next step.

**Architecture:** Keep Core standalone and provider-neutral. The first implementation slices should derive workflow state from existing Core orders, invoices, payments, fulfillment, and production data; later slices can add focused summary/preview endpoints where the UI currently has to infer too much.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, React 19, Vite, Vitest, pytest.

---

## Why This Exists

Recent quote-to-cash stabilization fixed many important primitives:

- Manual orders can be created without a quote.
- Order line pricing can be adjusted after creation.
- One-time service/fee lines can be added to manual orders.
- Shipping charge editing recalculates tax and grand total.
- Service/fee lines no longer block fulfillment.
- Payment ledger and customer totals are moving toward real order totals instead of quote-only totals.

The remaining pain is workflow, not only missing fields. The current Orders UI behaves like an operations command center. It exposes production and shipping actions before it clearly answers commercial questions:

- Is the order commercially reviewed?
- Is the customer, pricing, shipping, tax, and fee structure correct?
- Does an invoice exist?
- Was the invoice sent?
- Is the order prepaid, partially paid, COD, or Net terms?
- Is production allowed yet?
- What is the one next action?

This plan turns Orders into the control point for commercial release and operational fulfillment.

## Current Business Problems

### Orders

- A manual order starts as `pending`.
- `OrderDetail.jsx` can only show `Generate Invoice` when the order status is one of `confirmed`, `in_production`, `ready_to_ship`, `shipped`, `delivered`, or `completed`.
- The visible `Confirm Order` button only appears for `pending_confirmation` external orders.
- A staff-created `pending` order therefore has no obvious path to "commercially confirmed" from the order detail page.
- `Generate Production Order` is the first prominent action even when the order has no invoice or payment decision.
- `generate_production_orders` can move a `pending` order directly to `in_production`.

### Invoices

- `POST /api/v1/invoices` can create an invoice from a sales order.
- `invoice_service.create_invoice` blocks pending orders, so a newly created manual order cannot be invoiced until status moves to `confirmed`.
- `OrderDetail.jsx` creates an invoice and navigates to `/admin/invoices`, but it does not open the created invoice or keep the order page in context.
- `/admin/invoices` is a list/detail page. It has no create-from-order entry point.
- The invoice list API returns `amount_due`, while `AdminInvoices.jsx` reads `balance_due`. This can display `$0.00` balances while summary A/R is nonzero.

### Payments

- Order payments are recorded through `/api/v1/payments` and stored in the payment ledger by `sales_order_id`.
- Invoice payments are recorded through `PATCH /api/v1/invoices/{invoice_id}` and also create a payment ledger record for the order.
- If a payment is recorded on the order before an invoice is created, invoice creation does not currently initialize `amount_paid` from the existing order payment ledger.
- The UI does not clearly distinguish "paid against order" from "paid against invoice".

### Production And Fulfillment

- Production order creation is operationally correct for many orders, but it is not gated by a commercial release concept.
- Service/fee lines are now fulfillment-ready and do not need production.
- Product lines may require production, stock pick, or no work order depending on item setup and stock.
- Material-only or service-only orders need a non-production path to invoice/payment/complete.

## Current Code Map

### Frontend

- `frontend/src/pages/admin/AdminOrders.jsx`
  - Lists orders.
  - Opens `SalesOrderWizard`.
  - Has a list-card modal with generic status buttons.
  - Fetches orders with fulfillment summaries.

- `frontend/src/pages/admin/OrderDetail.jsx`
  - Main order command center.
  - Fetches order, production orders, payment summary, payment list, fulfillment status, material requirements, and capacity requirements.
  - Shows top actions: refresh, packing slip, ship, confirm/reject external order, cancel, close short.
  - Shows Quick Actions: generate production order, check material availability, view production, generate invoice.
  - Shows line items, customer, shipping, material/capacity requirements, production status, payments, activity, shipping timeline.

- `frontend/src/components/SalesOrderWizard.jsx`
  - Creates manual orders with customer, product/material/service lines, shipping charge, notes, and backend tax calculation.
  - Does not ask what commercial workflow should happen next after create.

- `frontend/src/pages/admin/AdminInvoices.jsx`
  - Lists invoices and shows invoice detail modal.
  - Sends draft invoices.
  - Records invoice payments.
  - Downloads invoice PDF.

- `frontend/src/components/orders/PaymentsSection.jsx`
  - Shows order payment summary and ledger payments.
  - Records payments and refunds against the order.

- `frontend/src/components/orders/ShippingAddressSection.jsx`
  - Edits address and shipping charge.
  - Shows recalculated order total.

### Backend

- `backend/app/core/status_config.py`
  - Sales order transitions allow `pending -> confirmed`, but the detail UI does not expose a normal confirm action for `pending`.

- `backend/app/api/v1/endpoints/sales_orders.py`
  - `GET /api/v1/sales-orders/status-transitions`
  - `POST /api/v1/sales-orders/`
  - `GET /api/v1/sales-orders/{order_id}`
  - `PATCH /api/v1/sales-orders/{order_id}/status`
  - `PATCH /api/v1/sales-orders/{order_id}/address`
  - `PATCH /api/v1/sales-orders/{order_id}/lines`
  - `POST /api/v1/sales-orders/{order_id}/confirm`
  - `POST /api/v1/sales-orders/{order_id}/reject`
  - `POST /api/v1/sales-orders/{order_id}/generate-production-orders`
  - `POST /api/v1/sales-orders/{order_id}/ship`
  - `GET /api/v1/sales-orders/{order_id}/fulfillment-status`

- `backend/app/services/sales_order_service.py`
  - `create_sales_order` creates manual orders in `pending` status.
  - `confirm_external_order` only accepts `pending_confirmation`.
  - `update_sales_order_status` supports normal status transitions.
  - `generate_production_orders` can move `pending` to `in_production`.

- `backend/app/api/v1/endpoints/invoices.py`
  - `POST /api/v1/invoices`
  - `GET /api/v1/invoices`
  - `GET /api/v1/invoices/summary`
  - `GET /api/v1/invoices/{invoice_id}`
  - `PATCH /api/v1/invoices/{invoice_id}`
  - `POST /api/v1/invoices/{invoice_id}/send`
  - `GET /api/v1/invoices/{invoice_id}/pdf`

- `backend/app/services/invoice_service.py`
  - `create_invoice` allows `confirmed`, `in_production`, `ready_to_ship`, `shipped`, `delivered`, `completed`.
  - Prevents duplicate invoices per sales order.
  - Snapshots order lines, tax, shipping, customer, and terms.
  - Does not import existing order payments into invoice `amount_paid`.

- `backend/app/api/v1/endpoints/payments.py`
  - `POST /api/v1/payments` records order payment ledger entries.
  - `GET /api/v1/payments/order/{order_id}/summary` returns order payment summary.
  - `GET /api/v1/payments?order_id={order_id}` lists payments for an order.

## Target Workflow Model

The Orders page should present one business flow with two layers:

1. **Commercial layer:** customer, line items, fees, shipping, tax, total, invoice, terms, payments.
2. **Operational layer:** production, material availability, fulfillment, shipping, closeout.

Commercial release should happen before production release except for explicit override cases.

### Stage 1: Intake

Examples:

- Manual walk-in order.
- Phone order for stock part.
- Quote converted to sales order.
- Portal order awaiting review.
- Service-only engineering/design job.

Staff should be able to:

- Create the order.
- Add product, material, and service/fee lines.
- Add shipping charge.
- Save customer and notes.
- Land on the new order detail page with a clear next action.

### Stage 2: Commercial Review

Staff verifies:

- Customer identity and contact info.
- Billing/shipping address.
- Product/material/service lines.
- Per-line prices and quantities.
- Shipping charge.
- Tax calculation.
- Grand total.
- Payment terms.

Primary action:

- `Confirm Order` for `pending` orders.
- `Review External Order` for `pending_confirmation`.
- `Edit Pricing` while status allows edits.

### Stage 3: Billing

Staff chooses one of these billing paths:

- **Prepaid/COD:** Create invoice or receipt, record payment, then release.
- **Deposit:** Create/send invoice, record deposit, then release if deposit requirement is met.
- **Net terms:** Create/send invoice, mark terms accepted, then release with outstanding balance.
- **No-charge/internal:** Mark billing waived with a reason, then release.

Primary actions:

- `Create Invoice`
- `Open Invoice`
- `Send Invoice`
- `Record Payment`
- `Release to Production`

### Stage 4: Production Release

The order can move to production when:

- Commercial review is complete.
- Billing rule is satisfied.
- Product lines that require production exist.
- No unresolved commercial hold blocks release.

Primary actions:

- `Generate Production Orders`
- `Check Materials`
- `View Production`

Service/fee lines do not create production orders.

### Stage 5: Fulfillment And Shipping

Staff can:

- See fulfillment progress.
- Pick stock/material lines.
- Handle close-short.
- Print packing slip.
- Ship order when production and stock conditions are satisfied.

Primary actions:

- `Ship Order`
- `Close Short`
- `Mark Delivered`

### Stage 6: Closeout

Staff can:

- Confirm payment status.
- Confirm invoice status.
- Confirm delivery/completion.
- View accounting impact.

Primary actions:

- `Complete Order`
- `Record Final Payment`
- `Issue Refund`

## Target Order Detail Layout

### Header

The header should show:

- Order number.
- Customer.
- Order status.
- Payment status.
- Invoice status.
- Commercial release badge.
- Fulfillment badge.

The top-right action area should only show global utilities:

- Refresh.
- Print packing slip.
- Cancel order when allowed.

The primary workflow action should move into the workflow panel.

### Workflow Panel

Create a first-class panel at the top of `OrderDetail.jsx`.

Required visual stages:

1. Intake
2. Commercial Review
3. Billing
4. Production Release
5. Fulfillment
6. Closed

Each stage should render one of:

- Complete
- Current
- Blocked
- Available
- Skipped

The panel should show exactly one recommended next action unless the order is terminal.

Recommended next-action examples:

- Pending manual order with no invoice: `Confirm Order`
- Confirmed order with no invoice: `Create Invoice`
- Draft invoice exists: `Send Invoice`
- Sent invoice with COD/prepay and no payment: `Record Payment`
- Net terms invoice sent: `Release to Production`
- Paid order with product lines and no WOs: `Generate Production Orders`
- Service-only paid order: `Complete Order`
- Production complete: `Ship Order`

### Commercial Summary Panel

This should be above material requirements and production.

Required fields:

- Subtotal.
- Service/fee total.
- Shipping.
- Tax.
- Grand total.
- Amount paid.
- Balance due.
- Invoice number/status if present.
- Payment terms.

Required actions:

- Edit pricing while allowed.
- Edit shipping charge while allowed.
- Create/open/send invoice.
- Record payment/refund.

### Operational Summary Panel

This should contain:

- Fulfillment status.
- Production order status.
- Material availability.
- Shipping readiness.

Production actions should live here, not as the first primary action on every order.

## Business Rules For First Implementation

These rules intentionally use existing Core concepts.

### Confirm Order

- Use `PATCH /api/v1/sales-orders/{order_id}/status` with `{ "status": "confirmed" }` for normal `pending` orders.
- Keep `POST /api/v1/sales-orders/{order_id}/confirm` for `pending_confirmation` external orders.
- After confirm, refresh order, payment summary, invoice lookup, fulfillment, material requirements, and production orders.

### Invoice Creation

- Create invoice only after order is confirmed or already beyond confirmed.
- If invoice already exists, show `Open Invoice` instead of `Create Invoice`.
- After invoice creation, stay on order detail and show invoice status instead of navigating blindly to `/admin/invoices`.

### Payment Visibility

- Order detail remains the place to record customer payment during order handling.
- Invoice detail remains a secondary place to record payment when working A/R.
- Both paths must write the same payment ledger.
- If an invoice exists, the order payment section should show whether the payment is reflected on the invoice.

### Production Release

- Hide or disable `Generate Production Orders` until commercial release is satisfied.
- Allow an admin override only with a required reason.
- The override must create an order event.

### Stock, Service, And Material-Only Orders

- Orders with no producible product lines should skip Production Release.
- Stock/material-only orders should move from Billing to Fulfillment.
- Service-only orders should move from Billing to Closed after invoice/payment completion.

## Implementation Tasks

### Task 1: Frontend Workflow Derivation

**Files:**

- Create: `frontend/src/lib/orderWorkflow.js`
- Test: `frontend/src/lib/__tests__/orderWorkflow.test.js`

- [ ] **Step 1: Write workflow derivation tests**

Create `frontend/src/lib/__tests__/orderWorkflow.test.js` with focused scenarios:

```js
import { describe, expect, it } from "vitest";
import {
  deriveOrderWorkflow,
  getRecommendedOrderAction,
} from "../orderWorkflow";

describe("deriveOrderWorkflow", () => {
  it("starts pending manual orders in commercial review", () => {
    const result = deriveOrderWorkflow({
      order: { status: "pending", payment_status: "pending", lines: [{ line_type: "product", product_id: 1 }] },
      invoice: null,
      paymentSummary: { total_paid: 0, balance_due: 117.7 },
      productionOrders: [],
      fulfillmentStatus: null,
    });

    expect(result.currentStage).toBe("commercial_review");
    expect(getRecommendedOrderAction(result).id).toBe("confirm_order");
  });

  it("recommends invoice creation for confirmed orders without an invoice", () => {
    const result = deriveOrderWorkflow({
      order: { status: "confirmed", payment_status: "pending", lines: [{ line_type: "product", product_id: 1 }] },
      invoice: null,
      paymentSummary: { total_paid: 0, balance_due: 117.7 },
      productionOrders: [],
      fulfillmentStatus: null,
    });

    expect(result.currentStage).toBe("billing");
    expect(getRecommendedOrderAction(result).id).toBe("create_invoice");
  });

  it("skips production for service-only paid orders", () => {
    const result = deriveOrderWorkflow({
      order: { status: "confirmed", payment_status: "paid", lines: [{ line_type: "service", product_id: null }] },
      invoice: { status: "paid" },
      paymentSummary: { total_paid: 50, balance_due: 0 },
      productionOrders: [],
      fulfillmentStatus: null,
    });

    expect(result.stages.production_release.state).toBe("skipped");
    expect(getRecommendedOrderAction(result).id).toBe("complete_order");
  });
});
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
cd frontend
npx vitest run src/lib/__tests__/orderWorkflow.test.js
```

Expected: fails because `frontend/src/lib/orderWorkflow.js` does not exist.

- [ ] **Step 3: Implement the workflow helper**

Create `frontend/src/lib/orderWorkflow.js` with pure functions:

```js
const STAGE_ORDER = [
  "intake",
  "commercial_review",
  "billing",
  "production_release",
  "fulfillment",
  "closed",
];

function hasProductLines(order) {
  return (order?.lines || []).some((line) => Boolean(line.product_id));
}

function hasOnlyServiceLines(order) {
  const lines = order?.lines || [];
  return lines.length > 0 && lines.every((line) => line.line_type === "service" || !line.product_id);
}

function isInvoiceSentOrPaid(invoice) {
  return ["sent", "partially_paid", "paid"].includes(invoice?.status);
}

function isPaid(order, paymentSummary) {
  return order?.payment_status === "paid" || Number(paymentSummary?.balance_due || 0) <= 0;
}

export function deriveOrderWorkflow({
  order,
  invoice,
  paymentSummary,
  productionOrders = [],
  fulfillmentStatus,
}) {
  const stages = {
    intake: { state: "complete" },
    commercial_review: { state: order?.status === "pending" || order?.status === "pending_confirmation" ? "current" : "complete" },
    billing: { state: "available" },
    production_release: { state: "available" },
    fulfillment: { state: "available" },
    closed: { state: "available" },
  };

  const terminal = ["completed", "cancelled", "delivered"].includes(order?.status);
  const productLines = hasProductLines(order);
  const serviceOnly = hasOnlyServiceLines(order);
  const invoiceReady = Boolean(invoice);
  const billingSatisfied = isPaid(order, paymentSummary) || isInvoiceSentOrPaid(invoice);
  const hasProduction = productionOrders.length > 0;

  if (order?.status === "pending" || order?.status === "pending_confirmation") {
    stages.billing.state = "blocked";
    stages.production_release.state = productLines ? "blocked" : "skipped";
    stages.fulfillment.state = "blocked";
    return { stages, currentStage: "commercial_review", terminal, productLines, serviceOnly, invoiceReady, billingSatisfied, hasProduction };
  }

  if (!invoiceReady) {
    stages.commercial_review.state = "complete";
    stages.billing.state = "current";
    stages.production_release.state = productLines ? "blocked" : "skipped";
    stages.fulfillment.state = "blocked";
    return { stages, currentStage: "billing", terminal, productLines, serviceOnly, invoiceReady, billingSatisfied, hasProduction };
  }

  if (!billingSatisfied) {
    stages.commercial_review.state = "complete";
    stages.billing.state = "current";
    stages.production_release.state = productLines ? "blocked" : "skipped";
    stages.fulfillment.state = "blocked";
    return { stages, currentStage: "billing", terminal, productLines, serviceOnly, invoiceReady, billingSatisfied, hasProduction };
  }

  stages.commercial_review.state = "complete";
  stages.billing.state = "complete";

  if (serviceOnly || !productLines) {
    stages.production_release.state = "skipped";
    stages.fulfillment.state = "skipped";
    stages.closed.state = terminal ? "complete" : "current";
    return { stages, currentStage: "closed", terminal, productLines, serviceOnly, invoiceReady, billingSatisfied, hasProduction };
  }

  if (!hasProduction) {
    stages.production_release.state = "current";
    stages.fulfillment.state = "blocked";
    return { stages, currentStage: "production_release", terminal, productLines, serviceOnly, invoiceReady, billingSatisfied, hasProduction };
  }

  const fulfillmentState = fulfillmentStatus?.summary?.state || fulfillmentStatus?.state;
  stages.production_release.state = "complete";
  stages.fulfillment.state = ["ready_to_ship", "partial", "blocked"].includes(fulfillmentState) || order?.status !== "completed" ? "current" : "complete";
  stages.closed.state = terminal ? "complete" : "available";

  return { stages, currentStage: "fulfillment", terminal, productLines, serviceOnly, invoiceReady, billingSatisfied, hasProduction };
}

export function getRecommendedOrderAction(workflow) {
  if (workflow.terminal) return { id: "none", label: "No Action" };
  if (workflow.currentStage === "commercial_review") return { id: "confirm_order", label: "Confirm Order" };
  if (workflow.currentStage === "billing" && !workflow.invoiceReady) return { id: "create_invoice", label: "Create Invoice" };
  if (workflow.currentStage === "billing" && !workflow.billingSatisfied) return { id: "record_payment", label: "Record Payment" };
  if (workflow.currentStage === "production_release") return { id: "generate_production_orders", label: "Generate Production Orders" };
  if (workflow.currentStage === "fulfillment") return { id: "ship_order", label: "Ship Order" };
  if (workflow.currentStage === "closed") return { id: "complete_order", label: "Complete Order" };
  return { id: "none", label: "No Action" };
}

export { STAGE_ORDER };
```

- [ ] **Step 4: Run the workflow helper test**

Run:

```powershell
cd frontend
npx vitest run src/lib/__tests__/orderWorkflow.test.js
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/lib/orderWorkflow.js frontend/src/lib/__tests__/orderWorkflow.test.js
git commit -m "test: define order workflow derivation"
```

### Task 2: Backend Invoice Lookup For An Order

**Files:**

- Modify: `backend/app/api/v1/endpoints/invoices.py`
- Test: `backend/tests/test_invoice_service.py` or `backend/tests/api/v1/test_invoices.py`

- [ ] **Step 1: Add endpoint coverage**

Add an API test that creates an order, creates an invoice, and verifies the UI can fetch the invoice by `sales_order_id`:

```python
def test_list_invoices_filters_by_sales_order_id(client, admin_user, auth_headers, db, make_sales_order):
    order = make_sales_order(status="confirmed")
    response = client.post(
        "/api/v1/invoices",
        json={"sales_order_id": order.id},
        headers=auth_headers,
    )
    assert response.status_code == 200

    response = client.get(
        f"/api/v1/invoices?sales_order_id={order.id}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["sales_order_id"] == order.id
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
$env:DATABASE_URL=$null
$env:DB_NAME="filaops_test"
$env:DEBUG="false"
python -m pytest backend/tests/api/v1/test_invoices.py::test_list_invoices_filters_by_sales_order_id -q
```

Expected: fails because `sales_order_id` query filtering is not implemented.

- [ ] **Step 3: Add the query parameter**

Update `backend/app/api/v1/endpoints/invoices.py`:

```python
@router.get("", response_model=list[InvoiceListResponse])
def list_invoices(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sales_order_id: Optional[int] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    invoices = invoice_service.list_invoices(
        db,
        status=status,
        customer_search=search,
        sales_order_id=sales_order_id,
        limit=limit,
        offset=offset,
    )
```

Update `backend/app/services/invoice_service.py`:

```python
def list_invoices(
    db: Session,
    status: Optional[str] = None,
    customer_search: Optional[str] = None,
    sales_order_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Invoice]:
    query = db.query(Invoice).order_by(desc(Invoice.created_at))

    if sales_order_id is not None:
        query = query.filter(Invoice.sales_order_id == sales_order_id)
```

- [ ] **Step 4: Run the endpoint test**

Run the same pytest command from Step 2.

Expected: pass in a correctly configured test database.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/api/v1/endpoints/invoices.py backend/app/services/invoice_service.py backend/tests/api/v1/test_invoices.py
git commit -m "feat: filter invoices by sales order"
```

### Task 3: Invoice Balance Field Compatibility

**Files:**

- Modify: `backend/app/api/v1/endpoints/invoices.py`
- Modify: `frontend/src/pages/admin/AdminInvoices.jsx`
- Test: `frontend/src/pages/admin/__tests__/AdminInvoices.test.jsx`

- [ ] **Step 1: Add UI regression coverage**

Test that invoice list rows render `amount_due` when `balance_due` is absent:

```jsx
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AdminInvoices from "../AdminInvoices";

vi.mock("../../../hooks/useApi", () => ({
  useApi: () => ({
    get: vi.fn((path) => {
      if (path.startsWith("/api/v1/invoices?")) {
        return Promise.resolve([
          {
            id: 1,
            invoice_number: "INV-2026-001",
            order_number: "SO-2026-001",
            customer_name: "Walk-In Customer",
            total: 125,
            amount_paid: 25,
            amount_due: 100,
            status: "sent",
          },
        ]);
      }
      if (path === "/api/v1/invoices/summary") {
        return Promise.resolve({ total_ar: 100, overdue_count: 0 });
      }
      return Promise.resolve({});
    }),
  }),
}));

it("renders invoice balance from amount_due", async () => {
  render(
    <MemoryRouter>
      <AdminInvoices />
    </MemoryRouter>
  );

  await waitFor(() => expect(screen.getByText("INV-2026-001")).toBeInTheDocument());
  expect(screen.getByText("$100.00")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the failing UI test**

Run:

```powershell
cd frontend
npx vitest run src/pages/admin/__tests__/AdminInvoices.test.jsx
```

Expected: fails if the page only reads `balance_due`.

- [ ] **Step 3: Fix the UI field fallback**

Update `AdminInvoices.jsx` table and modal balance reads:

```jsx
const balanceDue = invoice.balance_due ?? invoice.amount_due ?? 0;
```

For selected invoice detail:

```jsx
const selectedBalanceDue = selectedInvoice.balance_due ?? selectedInvoice.amount_due ?? 0;
```

- [ ] **Step 4: Also return `balance_due` from the backend**

In `backend/app/api/v1/endpoints/invoices.py`, include both names during the compatibility period:

```python
"amount_due": amount_due,
"balance_due": amount_due,
```

Do this in `_build_invoice_response` and invoice list result dictionaries.

- [ ] **Step 5: Run tests**

Run:

```powershell
cd frontend
npx vitest run src/pages/admin/__tests__/AdminInvoices.test.jsx
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/api/v1/endpoints/invoices.py frontend/src/pages/admin/AdminInvoices.jsx frontend/src/pages/admin/__tests__/AdminInvoices.test.jsx
git commit -m "fix: show invoice balance due consistently"
```

### Task 4: Order Workflow Panel

**Files:**

- Create: `frontend/src/components/orders/OrderWorkflowPanel.jsx`
- Test: `frontend/src/components/orders/__tests__/OrderWorkflowPanel.test.jsx`

- [ ] **Step 1: Add component tests**

Cover the stage labels, recommended action, and disabled state messaging:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import OrderWorkflowPanel from "../OrderWorkflowPanel";

it("shows confirm as the next action for pending orders", async () => {
  const onAction = vi.fn();

  render(
    <OrderWorkflowPanel
      workflow={{
        currentStage: "commercial_review",
        stages: {
          intake: { state: "complete" },
          commercial_review: { state: "current" },
          billing: { state: "blocked" },
          production_release: { state: "blocked" },
          fulfillment: { state: "blocked" },
          closed: { state: "available" },
        },
        terminal: false,
        invoiceReady: false,
        billingSatisfied: false,
      }}
      recommendedAction={{ id: "confirm_order", label: "Confirm Order" }}
      onAction={onAction}
    />
  );

  expect(screen.getByText("Commercial Review")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Confirm Order" }));
  expect(onAction).toHaveBeenCalledWith("confirm_order");
});
```

- [ ] **Step 2: Run the failing component test**

Run:

```powershell
cd frontend
npx vitest run src/components/orders/__tests__/OrderWorkflowPanel.test.jsx
```

Expected: fails because the component does not exist.

- [ ] **Step 3: Implement the component**

Create `OrderWorkflowPanel.jsx` with:

- Stage rail.
- Stage labels.
- Recommended next-action button.
- Compact commercial release description.
- No API calls inside the component.

Implementation rule:

```jsx
const STAGE_LABELS = {
  intake: "Intake",
  commercial_review: "Commercial Review",
  billing: "Billing",
  production_release: "Production Release",
  fulfillment: "Fulfillment",
  closed: "Closed",
};
```

- [ ] **Step 4: Run component tests**

Run the same Vitest command from Step 2.

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/orders/OrderWorkflowPanel.jsx frontend/src/components/orders/__tests__/OrderWorkflowPanel.test.jsx
git commit -m "feat: add order workflow panel"
```

### Task 5: Wire Workflow Into Order Detail

**Files:**

- Modify: `frontend/src/pages/admin/OrderDetail.jsx`
- Modify: `frontend/src/components/orders/index.js`
- Test: `frontend/src/pages/admin/__tests__/OrderDetail.workflow.test.jsx`

- [ ] **Step 1: Add an order detail workflow test**

Test the path that Brandan hit:

```jsx
it("shows Confirm Order before production for a pending manual order", async () => {
  renderOrderDetail({
    order: {
      id: 2788,
      order_number: "SO-2026-053",
      status: "pending",
      payment_status: "pending",
      grand_total: 117.7,
      lines: [{ id: 1, line_type: "product", product_id: 1, product_name: "Custom Keychain" }],
    },
    invoices: [],
    paymentSummary: { total_paid: 0, balance_due: 117.7 },
    productionOrders: [],
  });

  expect(await screen.findByRole("button", { name: "Confirm Order" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Generate Production Order" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
cd frontend
npx vitest run src/pages/admin/__tests__/OrderDetail.workflow.test.jsx
```

Expected: fails because the workflow panel is not wired in.

- [ ] **Step 3: Fetch existing invoice by order**

In `OrderDetail.jsx`, add state:

```js
const [orderInvoice, setOrderInvoice] = useState(null);
```

Add fetch:

```js
const fetchOrderInvoice = async () => {
  const invoices = await api.get(`/api/v1/invoices?sales_order_id=${orderId}&limit=1`);
  setOrderInvoice((invoices || [])[0] || null);
};
```

Call it in the existing `useEffect` with `fetchOrder`, `fetchProductionOrders`, and `fetchPaymentData`.

- [ ] **Step 4: Add normal pending-order confirmation**

Add handler:

```js
const handleNormalConfirmOrder = async () => {
  await api.patch(`/api/v1/sales-orders/${orderId}/status`, { status: "confirmed" });
  toast.success(`Order ${order.order_number} confirmed`);
  await Promise.all([fetchOrder(), fetchOrderInvoice(), fetchPaymentData()]);
};
```

Keep `handleConfirmOrder` for `pending_confirmation`.

- [ ] **Step 5: Route recommended actions**

Add:

```js
const handleWorkflowAction = async (actionId) => {
  if (actionId === "confirm_order") {
    if (order.status === "pending_confirmation") return handleConfirmOrder();
    return handleNormalConfirmOrder();
  }
  if (actionId === "create_invoice") return handleGenerateInvoice();
  if (actionId === "record_payment") {
    setIsRefund(false);
    setShowPaymentModal(true);
    return;
  }
  if (actionId === "generate_production_orders") return handleCreateProductionOrder();
  if (actionId === "ship_order") {
    navigate(`/admin/shipping?orderId=${order.id}`);
  }
};
```

- [ ] **Step 6: Move production action behind workflow gate**

Render `Generate Production Order` inside the workflow/operational area only when:

```js
workflow.currentStage === "production_release"
```

Do not show it as the first Quick Action for a `pending` or unbilled order.

- [ ] **Step 7: Run tests**

Run:

```powershell
cd frontend
npx vitest run src/lib/__tests__/orderWorkflow.test.js src/components/orders/__tests__/OrderWorkflowPanel.test.jsx src/pages/admin/__tests__/OrderDetail.workflow.test.jsx
```

Expected: pass.

- [ ] **Step 8: Commit**

```powershell
git add frontend/src/pages/admin/OrderDetail.jsx frontend/src/components/orders/index.js frontend/src/pages/admin/__tests__/OrderDetail.workflow.test.jsx
git commit -m "feat: guide orders through commercial workflow"
```

### Task 6: Invoice Creation Stays In Order Context

**Files:**

- Modify: `frontend/src/pages/admin/OrderDetail.jsx`
- Test: `frontend/src/pages/admin/__tests__/OrderDetail.workflow.test.jsx`

- [ ] **Step 1: Add behavior test**

```jsx
it("shows the created invoice on the order after create invoice", async () => {
  const api = createMockApi({
    post: vi.fn(() => Promise.resolve({ id: 10, invoice_number: "INV-2026-010", status: "draft" })),
  });

  renderOrderDetail({ api, order: confirmedOrderWithoutInvoice });

  await userEvent.click(await screen.findByRole("button", { name: "Create Invoice" }));

  expect(api.post).toHaveBeenCalledWith("/api/v1/invoices", { sales_order_id: confirmedOrderWithoutInvoice.id });
  expect(await screen.findByText("INV-2026-010")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
cd frontend
npx vitest run src/pages/admin/__tests__/OrderDetail.workflow.test.jsx
```

Expected: fails if the page navigates away after invoice creation.

- [ ] **Step 3: Change invoice creation behavior**

Update `handleGenerateInvoice`:

```js
const invoice = await api.post("/api/v1/invoices", { sales_order_id: order.id });
setOrderInvoice(invoice);
toast.success(`Invoice ${invoice.invoice_number} created`);
await Promise.all([fetchOrder(), fetchOrderInvoice(), fetchPaymentData()]);
```

Remove the automatic `navigate("/admin/invoices")` call.

- [ ] **Step 4: Add invoice action buttons**

When `orderInvoice` exists, show:

- `Open Invoice` linking to `/admin/invoices?invoice=${orderInvoice.id}` or opening an invoice detail route if one exists.
- `Send Invoice` if `orderInvoice.status === "draft"`.
- `Download PDF`.

- [ ] **Step 5: Run tests**

Run the same Vitest command from Step 2.

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/pages/admin/OrderDetail.jsx frontend/src/pages/admin/__tests__/OrderDetail.workflow.test.jsx
git commit -m "fix: keep invoice creation in order context"
```

### Task 7: Payment And Invoice Reconciliation

**Files:**

- Modify: `backend/app/services/invoice_service.py`
- Modify: `backend/tests/test_invoice_service.py`
- Modify: `frontend/src/components/orders/PaymentsSection.jsx`

- [ ] **Step 1: Add backend regression test**

Create a confirmed order, record an order payment, then create an invoice:

```python
def test_create_invoice_imports_existing_order_payments(db, make_sales_order):
    order = make_sales_order(status="confirmed", grand_total=Decimal("117.70"))
    payment = Payment(
        payment_number="PAY-2026-9999",
        sales_order_id=order.id,
        amount=Decimal("25.00"),
        payment_method="cash",
        payment_type="payment",
        status="completed",
    )
    db.add(payment)
    db.commit()

    invoice = invoice_service.create_invoice(db, order.id)

    assert invoice.amount_paid == Decimal("25.00")
    assert invoice.status in ("draft", "partially_paid")
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
$env:DATABASE_URL=$null
$env:DB_NAME="filaops_test"
$env:DEBUG="false"
python -m pytest backend/tests/test_invoice_service.py::test_create_invoice_imports_existing_order_payments -q
```

Expected: fails because invoice `amount_paid` starts at zero.

- [ ] **Step 3: Import completed payment totals during invoice creation**

In `invoice_service.create_invoice`, calculate:

```python
existing_paid = (
    db.query(func.coalesce(func.sum(Payment.amount), 0))
    .filter(
        Payment.sales_order_id == order.id,
        Payment.status == "completed",
    )
    .scalar()
    or Decimal("0")
)
```

Set:

```python
amount_paid=max(existing_paid, Decimal("0")),
status="paid" if existing_paid >= total else "partially_paid" if existing_paid > 0 else "draft",
```

- [ ] **Step 4: Clarify payment section copy**

In `PaymentsSection.jsx`, when an invoice exists, show a compact label:

```jsx
Invoice payments and order payments share the same payment ledger.
```

Use this only after the invoice reconciliation behavior is implemented.

- [ ] **Step 5: Run tests**

Run the backend test from Step 2 and the relevant frontend payment section test:

```powershell
cd frontend
npx vitest run src/components/orders/__tests__/PaymentsSection.test.jsx
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/services/invoice_service.py backend/tests/test_invoice_service.py frontend/src/components/orders/PaymentsSection.jsx
git commit -m "fix: reconcile order payments when invoicing"
```

### Task 8: Production Release Gate

**Files:**

- Modify: `backend/app/services/sales_order_service.py`
- Modify: `backend/app/api/v1/endpoints/sales_orders.py`
- Test: `backend/tests/services/test_sales_order_service.py`
- Test: `frontend/src/pages/admin/__tests__/OrderDetail.workflow.test.jsx`

- [ ] **Step 1: Add backend guard test**

```python
def test_generate_production_orders_blocks_unconfirmed_unbilled_order(db, make_sales_order):
    order = make_sales_order(status="pending", payment_status="pending")

    with pytest.raises(HTTPException) as exc:
        sales_order_service.generate_production_orders(
            db,
            order_id=order.id,
            user_email="admin@example.com",
        )

    assert exc.value.status_code == 400
    assert "commercial release" in exc.value.detail.lower()
```

- [ ] **Step 2: Run the failing backend test**

Run:

```powershell
$env:DATABASE_URL=$null
$env:DB_NAME="filaops_test"
$env:DEBUG="false"
python -m pytest backend/tests/services/test_sales_order_service.py::test_generate_production_orders_blocks_unconfirmed_unbilled_order -q
```

Expected: fails because production orders are currently allowed from `pending`.

- [ ] **Step 3: Implement a simple first guard**

In `sales_order_service.generate_production_orders`, before existing production creation logic:

```python
if order.status == "pending":
    raise HTTPException(
        status_code=400,
        detail="Order requires commercial release before production orders can be generated",
    )
```

This first guard is deliberately conservative. More nuanced Net terms and override logic should be added after the UI workflow is in place.

- [ ] **Step 4: Add UI test that production is disabled before billing**

```jsx
expect(screen.queryByRole("button", { name: "Generate Production Order" })).not.toBeInTheDocument();
expect(screen.getByText(/commercial review/i)).toBeInTheDocument();
```

- [ ] **Step 5: Run backend and frontend tests**

Run:

```powershell
$env:DATABASE_URL=$null
$env:DB_NAME="filaops_test"
$env:DEBUG="false"
python -m pytest backend/tests/services/test_sales_order_service.py::test_generate_production_orders_blocks_unconfirmed_unbilled_order -q

cd frontend
npx vitest run src/pages/admin/__tests__/OrderDetail.workflow.test.jsx
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/services/sales_order_service.py backend/app/api/v1/endpoints/sales_orders.py backend/tests/services/test_sales_order_service.py frontend/src/pages/admin/__tests__/OrderDetail.workflow.test.jsx
git commit -m "fix: gate production release behind commercial review"
```

## Manual Acceptance Scenarios

### Scenario A: Walk-In Paid Now

1. Go to `/admin/orders`.
2. Create order with one stock product, one design fee, and shipping charge.
3. Land on order detail.
4. Confirm order.
5. Create invoice.
6. Record full cash payment.
7. Verify workflow recommends fulfillment or complete, not invoice/payment.
8. Verify invoice balance is zero.
9. Verify order payment status is paid.

### Scenario B: Phone Order With Net Terms

1. Create order for an existing customer with Net 30 terms.
2. Confirm order.
3. Create invoice.
4. Send invoice.
5. Verify workflow allows production release after invoice sent.
6. Record payment later from either order detail or invoice detail.
7. Verify order and invoice balances agree.

### Scenario C: Quote-To-Order Custom Print

1. Create or accept a quote.
2. Convert to order.
3. Open order detail.
4. Verify the order starts after intake and requires billing review.
5. Create/send invoice or record deposit.
6. Generate production orders only after commercial release.
7. Complete production.
8. Ship order.

### Scenario D: Service-Only Engineering Fee

1. Create order with only a service line.
2. Confirm order.
3. Create invoice.
4. Record payment.
5. Verify production stage is skipped.
6. Complete order without requiring a production order.

## PR Sequence

1. **PR A: Plan only**
   - This document.

2. **PR B: Invoice visibility and balance compatibility**
   - Add invoice lookup by order.
   - Fix `amount_due`/`balance_due` display.
   - Keep order detail in context after invoice creation.

3. **PR C: Workflow panel and normal confirm**
   - Add workflow derivation helper.
   - Add workflow panel.
   - Expose `pending -> confirmed` on order detail.
   - Move production behind the workflow.

4. **PR D: Payment/invoice reconciliation**
   - Import order ledger payments when creating invoice.
   - Clarify payment section.
   - Add API tests.

5. **PR E: Production release gate**
   - Block production order generation from unconfirmed orders.
   - Add override design if Brandan wants it after seeing PR C.

## Open Product Decisions

- Should Core store a separate `commercial_status`, or should the workflow remain derived from order/invoice/payment state for now?
- For Net terms customers, is "invoice sent" enough to release production, or should staff explicitly click `Approve Terms`?
- Should deposits be represented as payment records only, or should orders store a required deposit amount?
- Should service-only orders close as `completed`, or should they use a distinct non-shipping completion path?
- Should the packing slip button be hidden until billing/fulfillment stage, or remain globally available for warehouse prep?

## Recommended Immediate Next Step

Implement PR B first. It is the smallest functional improvement and removes the confusion of "how do I get an invoice?" by letting Order Detail know whether an invoice exists and keeping invoice creation in the order workflow.

After PR B, implement PR C so the page visibly answers: "what should I do next?"

## AI Assistance

Drafted with Codex during session `codex-order-workflow-ui-plan-20260607`.
