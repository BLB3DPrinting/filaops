# Sales & Quotes Guide

This guide covers the complete sales workflow in FilaOps, from quote creation to order fulfillment.

## Overview

FilaOps supports two primary sales workflows:

1. **Quote-Based Sales** - For custom 3D printing jobs
   - Customer requests quote → Admin reviews → Quote approved → Customer accepts → Convert to sales order

2. **Direct Sales Orders** - For standard products
   - Create sales order directly without quote (manual entry or marketplace integration)

Both workflows converge at the **Sales Order**, which drives production planning and fulfillment.

## Sales Workflow Diagram

```
┌─────────────────┐
│  Quote Request  │ (Optional)
└────────┬────────┘
         │
         ▼
    ┌────────┐
    │ Quote  │ → pending → approved → accepted
    └────┬───┘              ↓          ↓
         │              rejected   expired
         │
         ▼ (Convert)
┌──────────────────┐
│  Sales Order     │ → draft → confirmed → in_production
└────────┬─────────┘                           ↓
         │                              ready_to_ship
         │                                     ↓
         └────────────────────────────────→ shipped
                                                ↓
                                           delivered
                                                ↓
                                           completed
```

---

## Part 1: Quotes

### What is a Quote?

A **Quote** is a price estimate for a 3D printing job. It includes:

- Product/part details
- Material and color selection
- Quantity
- Unit price and total price
- Print time and material usage estimates
- Expiration date (default: 30 days)
- Optional: Rush level, shipping, tax

### Quote Statuses

| Status | Meaning | Next Actions |
|--------|---------|--------------|
| **pending** | Waiting for admin review | Approve, Reject, Edit |
| **approved** | Admin approved pricing | Customer can accept or decline |
| **accepted** | Customer accepted quote | Convert to sales order |
| **rejected** | Admin declined the request | No further action |
| **expired** | Past expiration date | Create new quote if still needed |
| **converted** | Converted to sales order | View sales order |
| **cancelled** | Cancelled by admin or customer | No further action |

### Creating a Manual Quote

**Navigation:** Sales → Quotes → **+ New Quote**

**Step 1: Customer & Product Information**

Fill in the quote form:

```
Product Name: "Custom Phone Stand"
Customer Name: "John Doe"
Customer Email: john@example.com
Quantity: 10

Material Type: PLA_BASIC
Color: BLK (Black)
Finish: standard (options: standard, smooth, painted)

Customer Notes: "Need logo embossed on base"
```

**Step 2: Pricing**

Enter pricing details:

```
Unit Price: $12.50
Material (grams): 45
Print Time (hours): 2.5

Apply Tax: ✓ (uses company tax rate from Settings)
Shipping Cost: $8.00 (optional)
```

**Calculated Automatically:**
- Subtotal = Unit Price × Quantity = $125.00
- Tax Amount = $10.31 (if 8.25% tax enabled)
- Total Price = $143.31

**Step 3: Quote Settings**

```
Valid Days: 30 (quote expires in 30 days)
Rush Level: standard (options: standard, rush, super_rush, urgent)
Admin Notes: (internal notes, not visible to customer)
```

**Step 4: Submit**

Click **Create Quote** → Quote number generated (e.g., `Q-2026-000001`)

**✅ Result:** Quote is created with status "pending"

### Reviewing and Approving Quotes

**View Quote:** Click on any quote in the list to open the detail view

**Approve a Quote:**

1. Review all details (product, pricing, material requirements)
2. Add admin notes if needed
3. Click **Approve Quote**
4. Status changes to "approved"
5. Customer can now accept the quote

**Reject a Quote:**

1. Click **Reject Quote**
2. Enter rejection reason (e.g., "Material not available", "Design infeasible")
3. Status changes to "rejected"
4. Customer is notified (if email integration configured)

### Editing Quotes

You can edit quotes in "pending" or "approved" status:

1. Open quote detail
2. Click **Edit**
3. Modify pricing, quantity, or details
4. Click **Save Changes**

**Note:** Once a quote is "converted" to a sales order, it cannot be edited.

### Converting Quote to Sales Order

When a customer accepts a quote (or admin manually converts):

**Navigation:** Sales → Quotes → Open quote → **Convert to Order**

**Requirements:**
- ✅ Quote status must be "approved" or "accepted"
- ✅ Quote must not be expired
- ✅ Quote cannot already be converted

**Conversion Process:**

1. Click **Convert to Sales Order**
2. System generates sales order number (e.g., `SO-2026-0001`)
3. All quote details copied to sales order:
   - Product name, quantity, material, color
   - Pricing (locked at conversion time)
   - Customer information
   - Shipping address (if provided)
4. Quote status changes to "converted"
5. Sales order created with status "draft"

**✅ Result:** You're redirected to the new sales order

---

## Part 2: Sales Orders

### What is a Sales Order?

A **Sales Order** is a confirmed customer order that drives production and fulfillment. It can be created:

1. **From a quote** (conversion)
2. **Manually** (direct entry via wizard)
3. **From marketplace integration** (Squarespace, WooCommerce - if configured)

### Sales Order Statuses

| Status | Meaning | Next Actions |
|--------|---------|--------------|
| **draft** | Being created/edited | Confirm order |
| **pending_payment** | Awaiting payment | Record payment |
| **payment_failed** | Payment declined | Retry payment or cancel |
| **confirmed** | Payment received, ready for planning | Create production order |
| **in_production** | Manufacturing in progress | Monitor production |
| **ready_to_ship** | All items completed & QC passed | Ship order |
| **partially_shipped** | Some items shipped (multi-line) | Ship remaining items |
| **shipped** | All items shipped | Update tracking, await delivery |
| **delivered** | Carrier confirmed delivery | Complete order |
| **completed** | Order fully closed | Archive |
| **on_hold** | Paused (payment issue, customer request) | Resolve and resume |
| **cancelled** | Order terminated | No further action |

### Creating a Sales Order (Manual)

**Navigation:** Sales → Sales Orders → **+ New Sales Order**

**Step 1: Customer Selection**

```
Select Customer: (dropdown or "+ Create New Customer")
  - If new customer, enter:
    Name: "Acme Corporation"
    Email: orders@acmecorp.com
    Phone: (555) 123-4567

Order Date: (defaults to today)
Due Date: (optional - requested delivery date)
```

**Step 2: Add Line Items**

Sales orders support multiple products (line items):

```
Click "+ Add Line"

Product: Select from dropdown (e.g., "Example Standard Product")
  - Or search by SKU or name

Quantity: 5
Unit Price: $15.00 (auto-filled from product, or enter custom)
Material: PLA_BASIC (for manufactured items)
Color: BLK
Finish: standard

Notes: (optional line-item notes)
```

**Calculated per line:**
- Line Total = Unit Price × Quantity

**Add more lines as needed** (repeat Step 2)

**Step 3: Order Details**

```
Rush Level: standard (affects production scheduling)
Payment Method: credit_card (options: credit_card, paypal, manual, cash, check)

Shipping Address:
  Line 1: 123 Main St
  Line 2: Suite 200
  City: Springfield
  State: IL
  ZIP: 62701
  Country: USA

Shipping Cost: $12.00
Apply Tax: ✓ (calculates tax on subtotal)
```

**Step 4: Review Totals**

```
Subtotal: $75.00 (sum of all line items)
Tax (8.25%): $6.19
Shipping: $12.00
───────────────────
Grand Total: $93.19
```

**Step 5: Submit**

Click **Create Sales Order** → Order number generated (e.g., `SO-2026-0042`)

**✅ Result:** Sales order is created with status "draft"

### Sales Order Lifecycle Management

#### Confirming Orders

**From "draft" → "confirmed":**

1. Open sales order
2. Review all details
3. Click **Confirm Order**
4. Status changes to "confirmed"
5. Order is now ready for production planning

#### Recording Payment

**From "pending_payment" → "confirmed":**

1. Open sales order
2. Click **Record Payment**
3. Enter payment details:
   - Payment Method: credit_card
   - Transaction ID: ch_1234567890 (optional)
   - Paid At: (date/time)
4. Payment status changes to "paid"
5. Order status changes to "confirmed"

#### Creating Production Orders

Once a sales order is **confirmed**, you can create production orders:

**Navigation:** Sales → Sales Orders → Open order → **Create Production Order**

**For Quote-Based Orders:**
- One production order per sales order
- Automatically uses material/color from quote

**For Line-Item Orders:**
- Create production order for each line
- Select which lines to include

See [Manufacturing Guide](manufacturing.md) for production order details.

#### Shipping Orders

**From "ready_to_ship" → "shipped":**

1. Open sales order
2. Click **Mark as Shipped**
3. Enter tracking information (optional):
   - Carrier: USPS / FedEx / UPS / DHL
   - Tracking Number: 1Z999AA10123456784
   - Shipped Date: (defaults to today)
4. Status changes to "shipped"

**Partial Shipments:**
- For multi-line orders, mark individual lines as shipped
- Order status becomes "partially_shipped"
- When all lines shipped, status becomes "shipped"

#### Completing Orders

**From "delivered" → "completed":**

1. Verify delivery confirmation (manual or carrier webhook)
2. Click **Complete Order**
3. Order is archived and closed

**Or mark as completed directly:**
- Click **Complete Order** from any status
- Use for orders that don't require delivery tracking

### Viewing Sales Orders

**List View:** Sales → Sales Orders

**Filter by:**
- Status (all, draft, confirmed, in_production, etc.)
- Date range
- Customer
- Search (order number, customer name, product)

**Columns:**
- Order Number (e.g., SO-2026-0042)
- Customer Name
- Order Date
- Due Date
- Total Amount
- Payment Status
- Status

**Click any order to view details**

### Sales Order Detail View

**Sections:**

1. **Order Header**
   - Order number, customer, dates
   - Status badges (order status, payment status, fulfillment status)
   - Quick actions (Confirm, Ship, Cancel, etc.)

2. **Line Items**
   - Product, quantity, material, color, finish
   - Unit price, line total
   - Production order status (if created)

3. **Pricing Summary**
   - Subtotal
   - Tax
   - Shipping
   - Grand total

4. **Customer Information**
   - Name, email, phone
   - Billing address (if different from shipping)

5. **Shipping Address**
   - Full address
   - Tracking info (if shipped)

6. **Timeline / Order Events**
   - History of status changes
   - Created, confirmed, shipped, delivered dates
   - Who performed actions

7. **Notes**
   - Customer notes (from quote or order)
   - Internal notes (admin only)

### Editing Sales Orders

**Edit in "draft" status:**
- Can change all fields (customer, lines, pricing, shipping)

**Edit in "confirmed" status:**
- Can modify quantities, add lines, change shipping
- **Cannot** change customer or remove paid items

**Cannot edit:**
- Orders in "in_production" or later (create adjustment/credit instead)

### Cancelling Sales Orders

**Cancel any order:**

1. Open sales order
2. Click **Cancel Order**
3. Confirm cancellation
4. Enter cancellation reason (optional)
5. Status changes to "cancelled"

**Effect:**
- Linked production orders are marked as cancelled
- Inventory allocations released
- Customer refund processed (if already paid)

**Note:** You can only cancel before "shipped" status. For shipped orders, create a return/refund instead.

---

## Part 3: Customers

### Creating Customers

**Navigation:** Sales → Customers → **+ New Customer**

**Required Fields:**
```
Name: "Acme Corporation"
Email: orders@acmecorp.com
```

**Optional Fields:**
```
Phone: (555) 123-4567
Company: Acme Corp
Tax ID: 12-3456789 (for B2B orders)

Billing Address:
  Line 1: 123 Main St
  Line 2: Suite 200
  City: Springfield
  State: IL
  ZIP: 62701
  Country: USA

Shipping Address: (same as billing or different)
  ✓ Same as billing address

Notes: "Net 30 payment terms"
```

**Customer Code:** Auto-generated (e.g., `CUST-00001`)

### Customer Detail View

**View customer:**
- All quotes (pending, approved, converted)
- All sales orders
- Total revenue
- Order history

### Customer Settings

**Per-customer settings:**
- Tax Exempt: ☐ (if customer doesn't pay sales tax)
- Payment Terms: Net 30 (if not immediate payment)
- Credit Limit: $5,000 (optional)
- Discount Rate: 10% (optional - applies to all orders)

---

## Part 4: Integration with Manufacturing

### From Sales Order to Production

**Workflow:**

1. Sales order confirmed → **Create Production Order**
2. Production order created → Manufacturing begins
3. Production order completed → Sales order status → "ready_to_ship"
4. Ship order → Status → "shipped"

**Production Order Creation:**

**For Quote-Based Orders:**
```
Product: Custom Phone Stand
Quantity: 10
Material: PLA_BASIC - BLK
Routing: Standard 3D Print Routing
  → Print (2.5 hrs @ 45g/unit)
  → Finishing (optional)
  → QC
  → Pack
```

**For Standard Products with BOMs:**
```
Product: Standard Product SKU
BOM: BOM-001 (Bill of Materials)
  → Component 1: Material product (450g)
  → Component 2: Hardware (10 units)
  → Component 3: Packaging
Routing: Routing-001
  → Operations defined in routing
```

**See:** [Manufacturing Guide](manufacturing.md) for production details

---

## Part 5: Pricing and Financial Settings

### Company Tax Settings

**Navigation:** Settings → Company Settings → **Tax Settings**

```
Enable Tax: ✓
Tax Rate: 8.25% (0.0825)
Tax Label: "Sales Tax" (or "VAT", "GST")
```

**Per-Customer Tax Exempt:**
- Customers can be marked "Tax Exempt"
- No tax charged on their orders

### Payment Methods

**Supported payment methods:**
- Credit Card (via payment gateway)
- PayPal
- Manual (cash, check, wire transfer)
- Net Terms (invoice with payment terms)

**Configuration:** Settings → Payment Settings

### Shipping Calculations

**Shipping cost can be:**
1. **Manual entry** - Enter dollar amount per order
2. **Flat rate** - Configured per order or customer
3. **Carrier integration** - EasyPost (if configured) for real-time rates

---

## Part 6: Reporting and Analytics

### Sales Dashboard

**Navigation:** Dashboard (home page)

**Widgets:**
- **Sales Chart** - Revenue over time (daily, weekly, monthly)
- **Recent Orders** - Last 10 sales orders
- **Order Status Breakdown** - Count by status
- **Revenue This Month** - Total sales

### Quote Statistics

**Navigation:** Sales → Quotes → **Stats**

**Metrics:**
- Total quotes
- Pending (awaiting review)
- Approved (awaiting customer acceptance)
- Conversion rate (accepted / approved)
- Average quote value
- Expired quotes

### Sales Order Reports

**Navigation:** Sales → Sales Orders → **Reports** (coming soon)

**Available Reports:**
- Sales by Customer
- Sales by Product
- Sales by Date Range
- Outstanding Orders (not completed)
- Revenue by Payment Method

---

## Part 7: Common Workflows

### Workflow 1: Simple Quote → Order

```
1. Customer requests quote via portal (or manual entry)
2. Admin reviews → Approve quote
3. Customer accepts quote
4. Admin converts to sales order
5. Admin confirms order
6. Create production order
7. Manufacture product
8. Ship to customer
9. Mark as delivered
10. Complete order
```

**Time estimate:** Quote to ship: 3-7 days (depending on production time)

### Workflow 2: Direct Sales Order (No Quote)

```
1. Customer calls/emails with order
2. Create sales order directly (skip quote)
3. Confirm payment
4. Create production order
5. Manufacture
6. Ship
7. Complete
```

**Time estimate:** 2-5 days

### Workflow 3: Rush Order

```
1. Customer requests rush quote
2. Admin creates quote with Rush Level: "super_rush"
3. Higher unit price charged (rush fee)
4. Convert to order → Confirm
5. Create production order with rush flag
6. Production prioritizes rush orders
7. Expedited shipping
8. Complete
```

**Time estimate:** Same day or next day

---

## Part 8: Troubleshooting

### Quote Conversion Fails

**Problem:** "Quote must be approved or accepted to convert"

**Solution:**
- Verify quote status is "approved" or "accepted"
- If "pending", approve it first
- If "expired", extend expiration date or create new quote

### Cannot Edit Sales Order

**Problem:** "Cannot modify order in production"

**Solution:**
- Orders in "in_production" or later cannot be edited
- Cancel the order and create a new one
- Or create a change order / adjustment (contact support)

### Tax Not Calculating

**Problem:** Tax amount shows $0.00

**Solution:**
- Check Settings → Company Settings → Tax Settings
- Ensure "Enable Tax" is checked
- Verify Tax Rate is set (e.g., 0.0825 for 8.25%)
- Check if customer is marked "Tax Exempt"

### Production Order Button Disabled

**Problem:** Cannot click "Create Production Order"

**Solution:**
- Order must be in "confirmed" status
- If "draft", confirm the order first
- If already has production order, view existing PO instead

### Shipping Address Missing

**Problem:** No shipping address on order

**Solution:**
- For quote-based orders, shipping address comes from quote
- Customer must provide address when accepting quote
- For manual orders, enter address in order wizard
- Can update address in order detail view (before shipping)

---

## Part 9: Best Practices

### Quote Management

✅ **Do:**
- Review quotes daily to maintain fast response times
- Use admin notes to document pricing decisions
- Set realistic expiration dates (30 days standard)
- Include material and print time estimates for transparency

❌ **Don't:**
- Approve quotes without verifying material availability
- Let quotes expire without follow-up
- Modify pricing after customer sees original quote (create new quote instead)

### Sales Order Management

✅ **Do:**
- Confirm payment before starting production
- Create production orders as soon as order is confirmed
- Update shipping tracking for customer visibility
- Add internal notes for special handling instructions

❌ **Don't:**
- Start production without confirmed order
- Ship without marking order as "shipped" (breaks inventory tracking)
- Cancel orders without customer notification

### Customer Communication

✅ **Do:**
- Document customer communication in internal notes
- Set accurate due dates and communicate delays early
- Provide tracking information when shipping
- Follow up on delivered orders

❌ **Don't:**
- Promise delivery dates without checking production capacity
- Charge shipping without customer agreement
- Apply rush fees without customer approval

---

## Part 10: Advanced Features

### Multi-Line Orders

**Line-item based orders** support multiple products:

```
Sales Order SO-2026-0050
  Line 1: Product A × 10 @ $12.00 = $120.00
  Line 2: Product B × 5 @ $20.00 = $100.00
  Line 3: Product C × 2 @ $50.00 = $100.00
  ──────────────────────────────────────────
  Subtotal: $320.00
```

**Each line can have:**
- Different product
- Different material/color
- Different production order
- Individual ship dates (partial shipments)

### Rush Levels

**Rush levels affect pricing and scheduling:**

| Rush Level | Lead Time | Price Multiplier | Priority |
|------------|-----------|------------------|----------|
| **standard** | 5-7 days | 1.0x | Normal |
| **rush** | 2-3 days | 1.5x | High |
| **super_rush** | 1 day | 2.0x | Very High |
| **urgent** | Same day | 3.0x | Critical |

**Set rush level on:**
- Quote (charges premium)
- Sales order (manual entry)
- Production order (prioritizes scheduling)

### Payment Status Tracking

**Payment status separate from order status:**

| Payment Status | Meaning |
|----------------|---------|
| **pending** | No payment received |
| **paid** | Full payment received |
| **partial** | Partial payment (deposits) |
| **refunded** | Payment refunded |
| **cancelled** | Payment cancelled |

**Workflow:**
- Order created → payment_status: "pending"
- Payment received → payment_status: "paid", order status: "confirmed"
- Refund issued → payment_status: "refunded"

---

## Next Steps

Now that you understand quotes and sales orders, explore these related guides:

| Guide | Learn About |
|-------|-------------|
| **Manufacturing** | Creating production orders from sales orders, operations, BOMs |
| **Inventory Management** | Tracking material usage, stock levels, cycle counting |
| **MRP** | Material requirements planning, automated PO generation |
| **Accounting** | Revenue recognition, COGS calculation, financial reports |

## Quick Reference

### Quote Statuses

`pending` → `approved` → `accepted` → `converted`
    ↓            ↓
`rejected`   `expired`

### Sales Order Statuses

`draft` → `confirmed` → `in_production` → `ready_to_ship` → `shipped` → `delivered` → `completed`

### Keyboard Shortcuts (in quote/order lists)

- `n` - New quote/order
- `r` - Refresh list
- `f` - Focus search
- `/` - Quick search

---

**🎉 Congratulations!** You now understand the complete sales workflow in FilaOps. Create your first quote and convert it to a sales order to see the process in action.
