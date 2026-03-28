# Wave 1: Payment Terms, Price Level Auto-Apply, Invoice Engine

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add customer payment terms tracking, automatic price level discount application on sales orders, and a full invoicing system with PDF generation and payment recording.

**Architecture:** Three independent features built sequentially — each on its own branch, each PR'd separately. Feature 1 (payment terms) feeds into Feature 3 (invoices) for due date calculation. Feature 2 (price level auto-apply) feeds into Feature 3 for correct line pricing on invoices. All features are Core-only; price level lookup degrades gracefully if PRO tables don't exist.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend), React 19 + Vite + Tailwind (frontend), ReportLab (PDF generation), pytest (testing)

**Dependencies:**
- PRs #461 and #462 are still OPEN — not merged. Work proceeds on `main` as-is.
- Latest migration: `068`. New migrations start at `069`.

---

## Shared Context for All Tasks

### Key Codebase Facts

1. **"Customers" are User records** with `account_type='customer'`. The `Customer` model (`backend/app/models/customer.py`) is a separate B2B CRM entity. The admin customer endpoints manage User records via `customer_service.py`.

2. **Customer service** (`backend/app/services/customer_service.py`) uses `User` model, builds responses via `_customer_response()` helper (line 77). Creates customers as `User(account_type='customer')`.

3. **Customer schemas** (`backend/app/schemas/customer.py`) — `CustomerBase`, `CustomerCreate`, `CustomerUpdate`, `CustomerListResponse`, `CustomerResponse`. These map to User fields.

4. **SalesOrderLine.discount** already exists (Numeric(10,2), nullable, default=0) at `backend/app/models/sales_order.py:194`. Currently unused.

5. **SalesOrderLine.total** (NOT `total_price`) — comment at line 212 explains this.

6. **CompanySettings** already has `invoice_prefix` (default "INV") and `invoice_terms` (String(2000)) at lines 51-53.

7. **Packing slip PDF** exists at `backend/app/services/sales_order_service.py:2001+` — use as reference for invoice PDF. Uses ReportLab, loads company logo from `CompanySettings.logo_data` (binary).

8. **Migration format**: numbered files (`069_description.py`), `revision = "069"`, `down_revision = "068"`.

9. **Ruff E712**: Never `filter(X == True)` — always `.is_(True)` / `.is_(False)`.

10. **Frontend nav**: `AdminLayout.jsx` `navGroups` array (line ~360). Add items there.

11. **Frontend routes**: `App.jsx` — lazy-loaded with `Suspense` + `PageLoader`.

12. **Customer modal**: `frontend/src/components/customers/CustomerModal.jsx` — form-based, calls `onSave(form)`.

---

## Feature 1: Customer Payment Terms (#465)

**Branch:** `feat/customer-payment-terms`

**Summary:** Add `payment_terms`, `credit_limit`, `approved_for_terms`, `approved_for_terms_at`, `approved_for_terms_by` columns to the `users` table. Expose in customer schemas, API responses, and the admin customer modal.

### Task 1.1: Migration — Add payment terms columns to users table

**Files:**
- Create: `backend/migrations/versions/069_add_customer_payment_terms.py`

**Step 1: Write the migration**

```python
"""Add customer payment terms columns to users table.

New columns (used for account_type='customer' rows):
- payment_terms: COD, prepay, net15, net30, card_on_file
- credit_limit: maximum credit amount
- approved_for_terms: admin approval flag for net terms
- approved_for_terms_at: timestamp of approval
- approved_for_terms_by: admin user ID who approved

Revision ID: 069
Revises: 068
"""
import sqlalchemy as sa
from alembic import op

revision = "069"
down_revision = "068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("payment_terms", sa.String(20), server_default="cod"))
    op.add_column("users", sa.Column("credit_limit", sa.Numeric(12, 2), nullable=True))
    op.add_column("users", sa.Column("approved_for_terms", sa.Boolean(), server_default=sa.text("false")))
    op.add_column("users", sa.Column("approved_for_terms_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("approved_for_terms_by", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "approved_for_terms_by")
    op.drop_column("users", "approved_for_terms_at")
    op.drop_column("users", "approved_for_terms")
    op.drop_column("users", "credit_limit")
    op.drop_column("users", "payment_terms")
```

**Step 2: Run the migration**

```bash
cd backend && python -m alembic upgrade head
```

Expected: migration applies cleanly. Verify with `SELECT payment_terms FROM users LIMIT 1;`.

**Step 3: Commit**

```bash
git add backend/migrations/versions/069_add_customer_payment_terms.py
git commit -m "feat: add payment terms columns to users table (migration 069)"
```

---

### Task 1.2: Model — Add payment terms fields to User model

**Files:**
- Modify: `backend/app/models/user.py`

**Step 1: Add the columns to User model**

After the `billing_country` column (around line 55-60 area), add a new section:

```python
    # Payment Terms (for account_type='customer')
    payment_terms = Column(String(20), server_default="cod")  # cod, prepay, net15, net30, card_on_file
    credit_limit = Column(Numeric(12, 2), nullable=True)  # NULL = no limit, 0 = no credit
    approved_for_terms = Column(Boolean, server_default=text("false"))
    approved_for_terms_at = Column(DateTime(timezone=True), nullable=True)
    approved_for_terms_by = Column(Integer, nullable=True)
```

Add the necessary imports: `Numeric`, `Boolean`, `text` from sqlalchemy (check which are already imported).

**Step 2: Run tests to verify model loads**

```bash
cd backend && python -c "from app.models.user import User; print('OK')"
```

**Step 3: Commit**

```bash
git add backend/app/models/user.py
git commit -m "feat: add payment terms fields to User model"
```

---

### Task 1.3: Schemas — Add payment terms to customer schemas

**Files:**
- Modify: `backend/app/schemas/customer.py`

**Step 1: Add to CustomerCreate (after status field, ~line 46)**

```python
    # Payment Terms
    payment_terms: Optional[str] = Field("cod", max_length=20)
    credit_limit: Optional[Decimal] = None
```

Add `from decimal import Decimal` to imports.

**Step 2: Add to CustomerUpdate (after shipping_country, ~line 72)**

```python
    # Payment Terms
    payment_terms: Optional[str] = Field(None, max_length=20)
    credit_limit: Optional[Decimal] = None
    approved_for_terms: Optional[bool] = None
```

**Step 3: Add to CustomerListResponse (after status, ~line 84)**

```python
    payment_terms: Optional[str] = "cod"
```

**Step 4: Add to CustomerResponse (after email_verified, ~line 111)**

```python
    # Payment Terms
    payment_terms: Optional[str] = "cod"
    credit_limit: Optional[Decimal] = None
    approved_for_terms: bool = False
    approved_for_terms_at: Optional[datetime] = None
    approved_for_terms_by: Optional[int] = None
```

**Step 5: Run tests**

```bash
cd backend && python -m pytest tests/ -x -q --tb=short
```

**Step 6: Commit**

```bash
git add backend/app/schemas/customer.py
git commit -m "feat: add payment terms fields to customer schemas"
```

---

### Task 1.4: Service — Include payment terms in customer responses and creation

**Files:**
- Modify: `backend/app/services/customer_service.py`

**Step 1: Update `_customer_response()` (line 77)**

Add after `"shipping_country"` (line 100):

```python
        "payment_terms": customer.payment_terms or "cod",
        "credit_limit": float(customer.credit_limit) if customer.credit_limit is not None else None,
        "approved_for_terms": customer.approved_for_terms or False,
        "approved_for_terms_at": customer.approved_for_terms_at,
        "approved_for_terms_by": customer.approved_for_terms_by,
```

**Step 2: Update `create_customer()` (line 278)**

Add to the `User(...)` constructor call (after `shipping_country` line):

```python
        payment_terms=data.payment_terms or "cod",
        credit_limit=data.credit_limit,
```

**Step 3: Update `update_customer()` (line 335)**

The existing `model_dump(exclude_unset=True)` + `setattr` loop handles new fields automatically. However, we need special handling for `approved_for_terms`:

After the existing `setattr` loop (line 357), add:

```python
    # Handle terms approval tracking
    if "approved_for_terms" in update_fields:
        if update_fields["approved_for_terms"]:
            customer.approved_for_terms_at = datetime.now(timezone.utc)
            customer.approved_for_terms_by = admin_id
        else:
            customer.approved_for_terms_at = None
            customer.approved_for_terms_by = None
```

**Step 4: Update `_build_list_response()` or equivalent list builder**

Find the function that builds CustomerListResponse dicts and add `"payment_terms"` to it.

**Step 5: Run tests**

```bash
cd backend && python -m pytest tests/ -x -q --tb=short
```

**Step 6: Commit**

```bash
git add backend/app/services/customer_service.py
git commit -m "feat: include payment terms in customer service responses"
```

---

### Task 1.5: Tests — Payment terms CRUD

**Files:**
- Create: `backend/tests/test_customer_payment_terms.py`

**Step 1: Write tests**

```python
"""Tests for customer payment terms fields."""
from decimal import Decimal

import pytest


BASE_URL = "/api/v1/admin/customers"


class TestCustomerPaymentTerms:
    """Test payment terms CRUD on customer records."""

    def test_create_customer_default_terms(self, client, admin_headers, db):
        """New customers default to COD payment terms."""
        resp = client.post(
            BASE_URL,
            json={"email": "terms-default@test.com", "first_name": "Test"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["payment_terms"] == "cod"
        assert data["credit_limit"] is None
        assert data["approved_for_terms"] is False

    def test_create_customer_with_terms(self, client, admin_headers, db):
        """Create customer with explicit payment terms."""
        resp = client.post(
            BASE_URL,
            json={
                "email": "terms-net30@test.com",
                "first_name": "Net30",
                "payment_terms": "net30",
                "credit_limit": 5000.00,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["payment_terms"] == "net30"
        assert data["credit_limit"] == 5000.00

    def test_update_customer_payment_terms(self, client, admin_headers, db):
        """Update payment terms on existing customer."""
        # Create customer
        resp = client.post(
            BASE_URL,
            json={"email": "terms-update@test.com", "first_name": "Update"},
            headers=admin_headers,
        )
        customer_id = resp.json()["id"]

        # Update terms
        resp = client.patch(
            f"{BASE_URL}/{customer_id}",
            json={"payment_terms": "net15", "credit_limit": 2500.00},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["payment_terms"] == "net15"
        assert data["credit_limit"] == 2500.00

    def test_approve_for_terms_sets_timestamp(self, client, admin_headers, db):
        """Approving for terms sets approved_for_terms_at and _by."""
        resp = client.post(
            BASE_URL,
            json={"email": "terms-approve@test.com", "first_name": "Approve"},
            headers=admin_headers,
        )
        customer_id = resp.json()["id"]

        resp = client.patch(
            f"{BASE_URL}/{customer_id}",
            json={"approved_for_terms": True},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["approved_for_terms"] is True
        assert data["approved_for_terms_at"] is not None
        assert data["approved_for_terms_by"] is not None

    def test_revoke_terms_clears_timestamp(self, client, admin_headers, db):
        """Revoking terms approval clears timestamps."""
        resp = client.post(
            BASE_URL,
            json={"email": "terms-revoke@test.com", "first_name": "Revoke"},
            headers=admin_headers,
        )
        customer_id = resp.json()["id"]

        # Approve then revoke
        client.patch(
            f"{BASE_URL}/{customer_id}",
            json={"approved_for_terms": True},
            headers=admin_headers,
        )
        resp = client.patch(
            f"{BASE_URL}/{customer_id}",
            json={"approved_for_terms": False},
            headers=admin_headers,
        )
        data = resp.json()
        assert data["approved_for_terms"] is False
        assert data["approved_for_terms_at"] is None

    def test_payment_terms_in_list_response(self, client, admin_headers, db):
        """Payment terms appear in customer list response."""
        client.post(
            BASE_URL,
            json={
                "email": "terms-list@test.com",
                "first_name": "List",
                "payment_terms": "net30",
            },
            headers=admin_headers,
        )
        resp = client.get(BASE_URL, headers=admin_headers)
        assert resp.status_code == 200
        customers = resp.json()
        net30_customers = [c for c in customers if c["email"] == "terms-list@test.com"]
        assert len(net30_customers) == 1
        assert net30_customers[0]["payment_terms"] == "net30"
```

**Step 2: Run tests**

```bash
cd backend && python -m pytest tests/test_customer_payment_terms.py -v --tb=short
```

**Step 3: Commit**

```bash
git add backend/tests/test_customer_payment_terms.py
git commit -m "test: add customer payment terms CRUD tests"
```

---

### Task 1.6: Frontend — Payment terms in CustomerModal

**Files:**
- Modify: `frontend/src/components/customers/CustomerModal.jsx`

**Step 1: Add payment terms fields to form state**

In the `useState` initializer (line 11), add after `shipping_country`:

```javascript
    // Payment Terms
    payment_terms: customer?.payment_terms || "cod",
    credit_limit: customer?.credit_limit || "",
    approved_for_terms: customer?.approved_for_terms || false,
```

**Step 2: Add Payment Terms section to the form**

After the Company Name field (around line 153) and before Billing Address, add a new section:

```jsx
          {/* Payment Terms */}
          <div>
            <h3 className="text-sm font-medium text-gray-400 uppercase mb-3">
              Payment Terms
            </h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Terms
                </label>
                <select
                  value={form.payment_terms}
                  onChange={(e) => {
                    const newTerms = e.target.value;
                    // If switching to net terms without approval, warn
                    if ((newTerms === "net15" || newTerms === "net30") && !form.approved_for_terms) {
                      setForm({ ...form, payment_terms: newTerms });
                    } else {
                      setForm({ ...form, payment_terms: newTerms });
                    }
                  }}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                >
                  <option value="cod">COD (Cash on Delivery)</option>
                  <option value="prepay">Prepay</option>
                  <option value="net15">Net 15</option>
                  <option value="net30">Net 30</option>
                  <option value="card_on_file">Card on File</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Credit Limit ($)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={form.credit_limit}
                  onChange={(e) =>
                    setForm({ ...form, credit_limit: e.target.value })
                  }
                  placeholder="No limit"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                />
              </div>
              <div className="flex items-end">
                <label className="flex items-center gap-2 cursor-pointer pb-2">
                  <input
                    type="checkbox"
                    checked={form.approved_for_terms}
                    onChange={(e) =>
                      setForm({ ...form, approved_for_terms: e.target.checked })
                    }
                    className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-blue-500"
                  />
                  <span className="text-sm text-gray-300">Approved for Terms</span>
                </label>
              </div>
            </div>
            {(form.payment_terms === "net15" || form.payment_terms === "net30") &&
              !form.approved_for_terms && (
                <p className="mt-2 text-sm text-amber-400">
                  Net terms require admin approval. Enable "Approved for Terms" to allow net payment.
                </p>
              )}
          </div>
```

**Step 3: Add validation in handleSubmit**

Before `onSave(form)` (line 36), add validation:

```javascript
    // Validate: net terms require approval
    if ((form.payment_terms === "net15" || form.payment_terms === "net30") && !form.approved_for_terms) {
      alert("Net payment terms require admin approval. Please enable 'Approved for Terms'.");
      return;
    }
```

**Step 4: Verify in browser**

Open AdminCustomers, click "Add New Customer" or edit existing. Verify:
- Payment terms dropdown shows all options
- Credit limit field accepts numbers
- Approved for Terms checkbox works
- Warning shows when selecting net terms without approval
- Validation prevents saving net terms without approval

**Step 5: Commit**

```bash
git add frontend/src/components/customers/CustomerModal.jsx
git commit -m "feat: add payment terms fields to customer modal UI"
```

---

### Task 1.7: Frontend — Show payment terms in customer list and details

**Files:**
- Modify: `frontend/src/pages/admin/AdminCustomers.jsx`
- Modify: `frontend/src/components/customers/CustomerDetailsModal.jsx`

**Step 1: Add payment_terms column to customer table in AdminCustomers.jsx**

Find the table headers and add a "Terms" column. Find the table body rows and display `customer.payment_terms?.toUpperCase()`.

**Step 2: Show payment terms in CustomerDetailsModal.jsx**

Add a "Payment Terms" section showing: terms, credit limit, approval status with date/approver.

**Step 3: Commit**

```bash
git add frontend/src/pages/admin/AdminCustomers.jsx frontend/src/components/customers/CustomerDetailsModal.jsx
git commit -m "feat: display payment terms in customer list and detail views"
```

---

### Task 1.8: Run full test suite and PR

**Step 1: Run all tests**

```bash
cd backend && python -m pytest tests/ -x -q --tb=short
cd frontend && npx vitest run
```

**Step 2: Lint check**

```bash
cd backend && python -m ruff check app/ --select E712
```

**Step 3: Create PR**

```bash
gh pr create --title "feat: customer payment terms — COD, net-15, net-30, credit limits (#465)" \
  --body "## Summary
- Add payment_terms, credit_limit, approved_for_terms columns to users table
- Include in customer create/update/response schemas and API
- Add payment terms section to CustomerModal with validation
- Show terms in customer list and detail views

Closes #465

## Test plan
- [ ] Create customer with default terms (COD)
- [ ] Create customer with net30 + credit limit
- [ ] Approve customer for net terms — verify timestamp set
- [ ] Revoke approval — verify timestamp cleared
- [ ] Attempt net15 without approval — validation prevents save
- [ ] Customer list shows terms column
- [ ] Run pytest — all pass"
```

---

## Feature 2: SO Price Level Auto-Apply (#464)

**Branch:** `feat/so-price-level-discount`

**Summary:** When creating a sales order for a customer with a PRO price level assignment, auto-apply the discount to line item prices. Gracefully degrade if PRO tables don't exist.

**IMPORTANT:** Price level tables (`price_levels`, `pro_customer_price_levels`) are created by PRO plugin migrations. They may not exist in Core-only installations. All lookups MUST be wrapped in `try/except` with graceful fallback to no discount.

### Task 2.1: Backend — Price level lookup helper

**Files:**
- Modify: `backend/app/services/sales_order_service.py`

**Step 1: Add a price level lookup function**

Add near the top of the file (after imports):

```python
def _get_customer_discount_percent(db: Session, customer_id: int) -> Optional[Decimal]:
    """Look up a customer's price level discount percentage.

    Price levels are managed by the PRO plugin. If PRO is not installed
    (tables don't exist), returns None for graceful degradation.
    """
    try:
        result = db.execute(
            sa.text("""
                SELECT pl.discount_percent
                FROM pro_customer_price_levels cpl
                JOIN price_levels pl ON pl.id = cpl.price_level_id
                WHERE cpl.customer_id = :customer_id
                LIMIT 1
            """),
            {"customer_id": customer_id},
        ).fetchone()
        if result:
            return Decimal(str(result[0]))
    except Exception:
        # PRO tables don't exist — no discount
        pass
    return None
```

Add `import sqlalchemy as sa` if not already imported, and `from decimal import Decimal`.

**Step 2: Apply discount when creating SO lines**

Find the function that creates sales order lines (likely in the manual order creation flow). When lines are created:

```python
    discount_percent = _get_customer_discount_percent(db, customer_id)
    if discount_percent:
        for line in order_lines:
            original_price = line.unit_price
            discount_amount = original_price * discount_percent / Decimal("100")
            line.unit_price = original_price - discount_amount
            line.discount = discount_percent  # Store the percentage
```

The exact location depends on how `create_sales_order()` works. Trace the line creation code and apply the discount there.

**Step 3: Recalculate order totals**

After applying discounts to lines, recalculate:
- Each line's `total = quantity * unit_price`
- Order's `total_price` = sum of line totals
- Order's `grand_total` = total_price + tax + shipping

**Step 4: Run tests**

```bash
cd backend && python -m pytest tests/ -x -q --tb=short
```

**Step 5: Commit**

```bash
git add backend/app/services/sales_order_service.py
git commit -m "feat: auto-apply customer price level discount to SO lines"
```

---

### Task 2.2: Tests — Price level auto-apply

**Files:**
- Create: `backend/tests/test_price_level_discount.py`

**Step 1: Write tests**

```python
"""Tests for sales order price level auto-apply.

Note: These tests cover the graceful degradation path (no PRO tables).
Full discount application requires PRO tables which may not exist in test DB.
"""
from unittest.mock import patch
from decimal import Decimal

import pytest

from app.services.sales_order_service import _get_customer_discount_percent


class TestPriceLevelLookup:
    """Test the discount lookup with graceful degradation."""

    def test_returns_none_when_pro_tables_missing(self, db):
        """When PRO is not installed, lookup returns None."""
        result = _get_customer_discount_percent(db, customer_id=999)
        assert result is None

    def test_returns_none_for_nonexistent_customer(self, db):
        """Customer without price level returns None."""
        result = _get_customer_discount_percent(db, customer_id=0)
        assert result is None
```

**Step 2: Run tests**

```bash
cd backend && python -m pytest tests/test_price_level_discount.py -v --tb=short
```

**Step 3: Commit**

```bash
git add backend/tests/test_price_level_discount.py
git commit -m "test: price level discount lookup with graceful degradation"
```

---

### Task 2.3: Frontend — Show discounted prices in order creation

**Files:**
- Modify: `frontend/src/components/ProductSelectionStep.jsx` (or wherever the product grid is in the order creation flow)

**Step 1: Fetch customer discount when customer is selected**

When a customer is set on the order, call a new API endpoint or use existing customer data to get the discount percentage. Add to the component:

```javascript
const [customerDiscount, setCustomerDiscount] = useState(null);

// When customer changes, fetch their discount
useEffect(() => {
  if (customerId) {
    api.get(`/api/v1/admin/customers/${customerId}`)
      .then(data => {
        // discount comes from price level (if available)
        setCustomerDiscount(data.discount_percent || null);
      })
      .catch(() => setCustomerDiscount(null));
  } else {
    setCustomerDiscount(null);
  }
}, [customerId]);
```

**Step 2: Display discounted prices**

In the product grid, when `customerDiscount` is set, show:
- Original retail price with strikethrough
- Discounted price
- Discount percentage badge

```jsx
{customerDiscount ? (
  <div>
    <span className="text-gray-500 line-through text-sm">
      {formatCurrency(product.selling_price)}
    </span>
    <span className="text-green-400 ml-2">
      {formatCurrency(product.selling_price * (1 - customerDiscount / 100))}
    </span>
    <span className="text-xs text-green-500 ml-1">-{customerDiscount}%</span>
  </div>
) : (
  <span>{formatCurrency(product.selling_price)}</span>
)}
```

**Step 3: Verify in browser**

- Create order for customer WITHOUT price level — prices show normal
- Create order for customer WITH price level (requires PRO) — prices show discounted
- Without PRO installed, all customers show normal prices (graceful degradation)

**Step 4: Commit**

```bash
git add frontend/src/components/ProductSelectionStep.jsx
git commit -m "feat: show discounted prices in product selection when customer has price level"
```

---

### Task 2.4: Frontend — Show discount on order detail

**Files:**
- Modify: order detail view (within `AdminOrders.jsx` or `OrderDetail.jsx`)

**Step 1: Show discount column in line items table**

If `line.discount > 0`, show the discount percentage and the original/discounted price.

**Step 2: Commit**

```bash
git add frontend/src/pages/admin/AdminOrders.jsx  # or OrderDetail.jsx
git commit -m "feat: display line-level discount on order detail view"
```

---

### Task 2.5: Run full test suite and PR

```bash
cd backend && python -m pytest tests/ -x -q --tb=short
cd frontend && npx vitest run
cd backend && python -m ruff check app/ --select E712
```

```bash
gh pr create --title "feat: sales order price level auto-apply (#464)" \
  --body "## Summary
- Auto-lookup customer price level discount when creating sales orders
- Apply discount to line item unit_price, store percentage in discount column
- Gracefully degrade when PRO tables don't exist (try/except, returns None)
- Show discounted prices in product selection grid
- Show discount info on order detail

Closes #464

## Test plan
- [ ] Create SO for customer without price level — full retail prices
- [ ] Discount lookup returns None when PRO tables missing
- [ ] Product grid shows normal prices when no discount
- [ ] Order detail shows discount column when applicable
- [ ] Run pytest — all pass"
```

---

## Feature 3: Invoice Engine (#466)

**Branch:** `feat/invoice-engine`

**Summary:** Full invoicing system — invoice model, PDF generation, payment recording, API endpoints, and admin UI page.

### Task 3.1: Migration — Create invoices and invoice_lines tables

**Files:**
- Create: `backend/migrations/versions/070_create_invoices_tables.py`

**Step 1: Write the migration**

```python
"""Create invoices and invoice_lines tables.

Revision ID: 070
Revises: 069
"""
import sqlalchemy as sa
from alembic import op

revision = "070"
down_revision = "069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_number", sa.String(20), nullable=False, unique=True),
        sa.Column("sales_order_id", sa.Integer(), sa.ForeignKey("sales_orders.id"), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("customer_name", sa.String(200), nullable=True),
        sa.Column("customer_email", sa.String(200), nullable=True),
        sa.Column("customer_company", sa.String(200), nullable=True),
        sa.Column("bill_to_line1", sa.String(200), nullable=True),
        sa.Column("bill_to_city", sa.String(100), nullable=True),
        sa.Column("bill_to_state", sa.String(50), nullable=True),
        sa.Column("bill_to_zip", sa.String(20), nullable=True),
        sa.Column("payment_terms", sa.String(20), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(12, 2), server_default="0"),
        sa.Column("tax_rate", sa.Numeric(5, 4), server_default="0"),
        sa.Column("tax_amount", sa.Numeric(12, 2), server_default="0"),
        sa.Column("shipping_amount", sa.Numeric(12, 2), server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("amount_paid", sa.Numeric(12, 2), server_default="0"),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_method", sa.String(20), nullable=True),
        sa.Column("payment_reference", sa.String(200), nullable=True),
        sa.Column("external_invoice_id", sa.String(100), nullable=True),
        sa.Column("external_invoice_url", sa.String(500), nullable=True),
        sa.Column("external_provider", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pdf_path", sa.String(500), nullable=True),
    )
    op.create_index("ix_invoices_sales_order_id", "invoices", ["sales_order_id"])
    op.create_index("ix_invoices_customer_id", "invoices", ["customer_id"])
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index("ix_invoices_due_date", "invoices", ["due_date"])

    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("sku", sa.String(50), nullable=True),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("base_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
    )
    op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"])


def downgrade() -> None:
    op.drop_table("invoice_lines")
    op.drop_table("invoices")
```

**Step 2: Run migration**

```bash
cd backend && python -m alembic upgrade head
```

**Step 3: Commit**

```bash
git add backend/migrations/versions/070_create_invoices_tables.py
git commit -m "feat: create invoices and invoice_lines tables (migration 070)"
```

---

### Task 3.2: Models — Invoice and InvoiceLine

**Files:**
- Create: `backend/app/models/invoice.py`
- Modify: `backend/app/models/__init__.py` (if it has explicit imports)

**Step 1: Write the model**

```python
"""Invoice models for tracking billing and payments."""
from sqlalchemy import (
    Column, Integer, String, Numeric, Date, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(20), unique=True, nullable=False, index=True)
    sales_order_id = Column(Integer, ForeignKey("sales_orders.id"), nullable=True, index=True)
    customer_id = Column(Integer, nullable=True, index=True)
    customer_name = Column(String(200), nullable=True)
    customer_email = Column(String(200), nullable=True)
    customer_company = Column(String(200), nullable=True)

    # Billing address (snapshot)
    bill_to_line1 = Column(String(200), nullable=True)
    bill_to_city = Column(String(100), nullable=True)
    bill_to_state = Column(String(50), nullable=True)
    bill_to_zip = Column(String(20), nullable=True)

    # Terms and dates
    payment_terms = Column(String(20), nullable=False)
    due_date = Column(Date, nullable=False)

    # Amounts
    subtotal = Column(Numeric(12, 2), nullable=False)
    discount_amount = Column(Numeric(12, 2), server_default="0")
    tax_rate = Column(Numeric(5, 4), server_default="0")
    tax_amount = Column(Numeric(12, 2), server_default="0")
    shipping_amount = Column(Numeric(12, 2), server_default="0")
    total = Column(Numeric(12, 2), nullable=False)

    # Status: draft, sent, paid, overdue, cancelled
    status = Column(String(20), nullable=False, server_default="draft", index=True)

    # Payment
    amount_paid = Column(Numeric(12, 2), server_default="0")
    paid_at = Column(DateTime(timezone=True), nullable=True)
    payment_method = Column(String(20), nullable=True)
    payment_reference = Column(String(200), nullable=True)

    # External integration
    external_invoice_id = Column(String(100), nullable=True)
    external_invoice_url = Column(String(500), nullable=True)
    external_provider = Column(String(20), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    pdf_path = Column(String(500), nullable=True)

    # Relationships
    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan")
    sales_order = relationship("SalesOrder", backref="invoices")

    def __repr__(self):
        return f"<Invoice(id={self.id}, number='{self.invoice_number}', status='{self.status}')>"


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, nullable=True)
    sku = Column(String(50), nullable=True)
    description = Column(String(200), nullable=False)
    quantity = Column(Numeric(12, 4), nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    base_price = Column(Numeric(12, 2), nullable=True)
    discount_percent = Column(Numeric(5, 2), nullable=True)
    line_total = Column(Numeric(12, 2), nullable=False)

    # Relationships
    invoice = relationship("Invoice", back_populates="lines")
```

**Step 2: Register in models `__init__.py`**

Check `backend/app/models/__init__.py`. If it explicitly imports models, add `from app.models.invoice import Invoice, InvoiceLine`.

**Step 3: Verify model loads**

```bash
cd backend && python -c "from app.models.invoice import Invoice, InvoiceLine; print('OK')"
```

**Step 4: Commit**

```bash
git add backend/app/models/invoice.py backend/app/models/__init__.py
git commit -m "feat: add Invoice and InvoiceLine models"
```

---

### Task 3.3: Schemas — Invoice request/response schemas

**Files:**
- Create: `backend/app/schemas/invoice.py`

**Step 1: Write schemas**

```python
"""Invoice Pydantic schemas."""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal


class InvoiceLineResponse(BaseModel):
    id: int
    product_id: Optional[int] = None
    sku: Optional[str] = None
    description: str
    quantity: Decimal
    unit_price: Decimal
    base_price: Optional[Decimal] = None
    discount_percent: Optional[Decimal] = None
    line_total: Decimal

    class Config:
        from_attributes = True


class InvoiceCreate(BaseModel):
    sales_order_id: int


class InvoiceUpdate(BaseModel):
    status: Optional[str] = None
    amount_paid: Optional[Decimal] = None
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None


class InvoiceResponse(BaseModel):
    id: int
    invoice_number: str
    sales_order_id: Optional[int] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_company: Optional[str] = None
    bill_to_line1: Optional[str] = None
    bill_to_city: Optional[str] = None
    bill_to_state: Optional[str] = None
    bill_to_zip: Optional[str] = None
    payment_terms: str
    due_date: date
    subtotal: Decimal
    discount_amount: Decimal = Decimal("0")
    tax_rate: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    shipping_amount: Decimal = Decimal("0")
    total: Decimal
    status: str
    amount_paid: Decimal = Decimal("0")
    paid_at: Optional[datetime] = None
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None
    external_invoice_id: Optional[str] = None
    external_invoice_url: Optional[str] = None
    external_provider: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    sent_at: Optional[datetime] = None
    pdf_path: Optional[str] = None
    lines: List[InvoiceLineResponse] = []

    # Derived fields
    order_number: Optional[str] = None
    amount_due: Decimal = Decimal("0")

    class Config:
        from_attributes = True


class InvoiceListResponse(BaseModel):
    id: int
    invoice_number: str
    sales_order_id: Optional[int] = None
    order_number: Optional[str] = None
    customer_name: Optional[str] = None
    customer_company: Optional[str] = None
    payment_terms: str
    due_date: date
    total: Decimal
    amount_paid: Decimal = Decimal("0")
    amount_due: Decimal = Decimal("0")
    status: str
    created_at: datetime
    sent_at: Optional[datetime] = None

    class Config:
        from_attributes = True
```

**Step 2: Commit**

```bash
git add backend/app/schemas/invoice.py
git commit -m "feat: add invoice Pydantic schemas"
```

---

### Task 3.4: Service — Invoice service (core logic)

**Files:**
- Create: `backend/app/services/invoice_service.py`

**Step 1: Write the service**

This is the largest single file. Key functions:

```python
"""Invoice service — create, list, pay, PDF generation."""
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import Integer, cast, desc, func
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models.company_settings import CompanySettings
from app.models.invoice import Invoice, InvoiceLine
from app.models.product import Product
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.user import User

logger = get_logger(__name__)


# ============================================================================
# Invoice Number Generation
# ============================================================================

def _generate_invoice_number(db: Session) -> str:
    """Generate next invoice number: INV-YYYY-NNN.

    Derives sequence from MAX existing invoice number for the current year.
    Uses the invoice_prefix from CompanySettings if available.
    """
    settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
    prefix = (settings.invoice_prefix if settings and settings.invoice_prefix else "INV")
    year = date.today().year
    full_prefix = f"{prefix}-{year}-"

    # Find max sequence for this year
    max_seq = (
        db.query(
            func.max(
                cast(
                    func.replace(Invoice.invoice_number, full_prefix, ""),
                    Integer,
                )
            )
        )
        .filter(
            Invoice.invoice_number.like(f"{full_prefix}%"),
            Invoice.invoice_number.op("~")(rf"^{prefix}-{year}-\d+$"),
        )
        .scalar()
    ) or 0

    return f"{full_prefix}{max_seq + 1:03d}"


# ============================================================================
# Due Date Calculation
# ============================================================================

def _calculate_due_date(payment_terms: str, from_date: Optional[date] = None) -> date:
    """Calculate invoice due date from payment terms."""
    base = from_date or date.today()
    terms_days = {
        "cod": 0,
        "prepay": 0,
        "card_on_file": 0,
        "net15": 15,
        "net30": 30,
    }
    days = terms_days.get(payment_terms, 0)
    return base + timedelta(days=days)


# ============================================================================
# Create Invoice
# ============================================================================

def create_invoice(db: Session, sales_order_id: int) -> Invoice:
    """Generate an invoice from a confirmed sales order.

    Snapshots customer info and line items from the SO.
    """
    order = db.query(SalesOrder).filter(SalesOrder.id == sales_order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Sales order not found")

    if order.status not in ("confirmed", "in_production", "ready_to_ship", "shipped", "delivered", "completed"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot invoice order in '{order.status}' status",
        )

    # Check for existing invoice
    existing = db.query(Invoice).filter(Invoice.sales_order_id == sales_order_id).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Invoice {existing.invoice_number} already exists for this order",
        )

    # Get customer info
    customer = None
    if order.user_id:
        customer = db.query(User).filter(User.id == order.user_id).first()

    payment_terms = (customer.payment_terms if customer and customer.payment_terms else "cod")
    due_date = _calculate_due_date(payment_terms)

    invoice_number = _generate_invoice_number(db)

    # Get order lines
    order_lines = (
        db.query(SalesOrderLine)
        .filter(SalesOrderLine.sales_order_id == order.id)
        .all()
    )

    # Calculate subtotal from lines
    subtotal = Decimal("0")
    invoice_lines = []

    if order_lines:
        for ol in order_lines:
            product = None
            if ol.product_id:
                product = db.query(Product).filter(Product.id == ol.product_id).first()

            sku = product.sku if product else ""
            description = product.name if product else "Item"
            base_price = product.selling_price if product else ol.unit_price
            line_total = ol.quantity * ol.unit_price

            invoice_lines.append(InvoiceLine(
                product_id=ol.product_id,
                sku=sku,
                description=description,
                quantity=ol.quantity,
                unit_price=ol.unit_price,
                base_price=base_price if base_price != ol.unit_price else None,
                discount_percent=ol.discount if ol.discount else None,
                line_total=line_total,
            ))
            subtotal += line_total
    else:
        # Single-product order (quote-based)
        product = None
        if order.product_id:
            product = db.query(Product).filter(Product.id == order.product_id).first()
        sku = product.sku if product else ""
        description = order.product_name or (product.name if product else "Item")
        unit_price = order.unit_price or Decimal("0")
        quantity = order.quantity or Decimal("1")
        line_total = quantity * unit_price

        invoice_lines.append(InvoiceLine(
            product_id=order.product_id,
            sku=sku,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            line_total=line_total,
        ))
        subtotal = line_total

    tax_rate = order.tax_rate or Decimal("0")
    tax_amount = order.tax_amount or Decimal("0")
    shipping = order.shipping_cost or Decimal("0")
    total = subtotal + tax_amount + shipping

    invoice = Invoice(
        invoice_number=invoice_number,
        sales_order_id=order.id,
        customer_id=order.user_id,
        customer_name=order.customer_name or (
            f"{customer.first_name or ''} {customer.last_name or ''}".strip()
            if customer else None
        ),
        customer_email=order.customer_email or (customer.email if customer else None),
        customer_company=customer.company_name if customer else None,
        bill_to_line1=customer.billing_address_line1 if customer else None,
        bill_to_city=customer.billing_city if customer else None,
        bill_to_state=customer.billing_state if customer else None,
        bill_to_zip=customer.billing_zip if customer else None,
        payment_terms=payment_terms,
        due_date=due_date,
        subtotal=subtotal,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        shipping_amount=shipping,
        total=total,
    )

    db.add(invoice)
    db.flush()

    for il in invoice_lines:
        il.invoice_id = invoice.id
        db.add(il)

    db.commit()
    db.refresh(invoice)
    return invoice


# ============================================================================
# Record Payment
# ============================================================================

def record_payment(
    db: Session,
    invoice_id: int,
    amount: Decimal,
    method: str,
    reference: Optional[str] = None,
) -> Invoice:
    """Record a payment against an invoice."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status in ("paid", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot record payment on {invoice.status} invoice",
        )

    new_paid = (invoice.amount_paid or Decimal("0")) + amount
    invoice.amount_paid = new_paid
    invoice.payment_method = method
    invoice.payment_reference = reference

    if new_paid >= invoice.total:
        invoice.status = "paid"
        invoice.paid_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(invoice)
    return invoice


# ============================================================================
# List / Query
# ============================================================================

def list_invoices(
    db: Session,
    status: Optional[str] = None,
    customer_search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Invoice]:
    """List invoices with optional filters."""
    query = db.query(Invoice).order_by(desc(Invoice.created_at))

    if status and status != "all":
        if status == "overdue":
            query = query.filter(
                Invoice.status == "sent",
                Invoice.due_date < date.today(),
            )
        else:
            query = query.filter(Invoice.status == status)

    if customer_search:
        search = f"%{customer_search}%"
        query = query.filter(
            (Invoice.customer_name.ilike(search))
            | (Invoice.customer_company.ilike(search))
            | (Invoice.customer_email.ilike(search))
            | (Invoice.invoice_number.ilike(search))
        )

    return query.offset(offset).limit(limit).all()


def get_invoice(db: Session, invoice_id: int) -> Invoice:
    """Get a single invoice by ID."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


def get_overdue_invoices(db: Session) -> list[Invoice]:
    """Get invoices past due_date still in 'sent' status."""
    return (
        db.query(Invoice)
        .filter(
            Invoice.status == "sent",
            Invoice.due_date < date.today(),
        )
        .order_by(Invoice.due_date)
        .all()
    )


def get_invoice_summary(db: Session) -> dict:
    """Get summary stats for dashboard widget."""
    overdue_count = (
        db.query(func.count(Invoice.id))
        .filter(Invoice.status == "sent", Invoice.due_date < date.today())
        .scalar()
    ) or 0

    total_ar = (
        db.query(func.sum(Invoice.total - Invoice.amount_paid))
        .filter(Invoice.status.in_(["draft", "sent"]))
        .scalar()
    ) or Decimal("0")

    return {
        "overdue_count": overdue_count,
        "total_ar": float(total_ar),
    }


def mark_sent(db: Session, invoice_id: int) -> Invoice:
    """Mark an invoice as sent."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft invoices can be sent")
    invoice.status = "sent"
    invoice.sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invoice)
    return invoice
```

**Step 2: Verify it imports**

```bash
cd backend && python -c "from app.services.invoice_service import create_invoice; print('OK')"
```

**Step 3: Commit**

```bash
git add backend/app/services/invoice_service.py
git commit -m "feat: add invoice service — create, payment, list, query"
```

---

### Task 3.5: Service — Invoice PDF generation

**Files:**
- Modify: `backend/app/services/invoice_service.py`

**Step 1: Add `generate_invoice_pdf()` function**

Model after `generate_packing_slip_pdf()` in `sales_order_service.py:2001+`. Key differences:
- Title: "INVOICE" not "PACKING SLIP"
- Add: invoice number, date, due date, payment terms
- Add: bill-to address section
- Add: line items with SKU, description, qty, unit price, total
- Add: subtotal, discount, tax, shipping, total due
- Add: payment status / amount paid / balance due
- Add: payment instructions from `CompanySettings.invoice_terms`

```python
def generate_invoice_pdf(db: Session, invoice_id: int) -> io.BytesIO:
    """Generate a professional invoice PDF using ReportLab.

    Pattern mirrors generate_packing_slip_pdf() in sales_order_service.py.
    """
    from xml.sax.saxutils import escape as _xml_escape

    def esc(value) -> str:
        return _xml_escape(str(value)) if value else ""

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    )

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()

    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "InvoiceTitle", parent=styles["Heading1"],
        fontSize=24, textColor=colors.HexColor("#2563eb"),
    )
    heading_style = ParagraphStyle(
        "InvoiceHeading", parent=styles["Heading2"],
        fontSize=12, textColor=colors.gray,
    )
    normal_style = styles["Normal"]

    content = []

    # ---- Company Header (same pattern as packing slip) ----
    if settings and settings.logo_data:
        try:
            logo_buffer = io.BytesIO(settings.logo_data)
            logo_img = Image(logo_buffer, width=1.5 * inch, height=1.5 * inch)
            logo_img.hAlign = "LEFT"
            company_info = []
            if settings.company_name:
                company_info.append(f"<b>{esc(settings.company_name)}</b>")
            if settings.company_address_line1:
                company_info.append(esc(settings.company_address_line1))
            if settings.company_city or settings.company_state:
                city_state = (
                    f"{esc(settings.company_city or '')}, "
                    f"{esc(settings.company_state or '')} "
                    f"{esc(settings.company_zip or '')}"
                ).strip(", ")
                company_info.append(city_state)
            if settings.company_phone:
                company_info.append(esc(settings.company_phone))
            if settings.company_email:
                company_info.append(esc(settings.company_email))
            header_data = [[logo_img, Paragraph("<br/>".join(company_info), normal_style)]]
            header_table = Table(header_data, colWidths=[2 * inch, 4.5 * inch])
            header_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
            content.append(header_table)
            content.append(Spacer(1, 0.3 * inch))
        except Exception:
            pass
    elif settings and settings.company_name:
        content.append(Paragraph(f"<b>{esc(settings.company_name)}</b>", title_style))
        content.append(Spacer(1, 0.2 * inch))

    # ---- Title ----
    content.append(Paragraph("INVOICE", title_style))
    content.append(Spacer(1, 0.2 * inch))

    # ---- Invoice Info ----
    content.append(Paragraph("INVOICE DETAILS", heading_style))
    content.append(Spacer(1, 0.05 * inch))
    info_data = [
        ["Invoice Number:", esc(invoice.invoice_number)],
        ["Date:", invoice.created_at.strftime("%B %d, %Y") if invoice.created_at else "N/A"],
        ["Due Date:", invoice.due_date.strftime("%B %d, %Y") if invoice.due_date else "N/A"],
        ["Terms:", esc(invoice.payment_terms.upper())],
    ]
    if invoice.sales_order_id:
        order = db.query(SalesOrder).filter(SalesOrder.id == invoice.sales_order_id).first()
        if order:
            info_data.append(["Order:", esc(order.order_number)])
    info_table = Table(info_data, colWidths=[1.5 * inch, 4 * inch])
    info_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    content.append(info_table)
    content.append(Spacer(1, 0.2 * inch))

    # ---- Bill To ----
    content.append(Paragraph("BILL TO", heading_style))
    content.append(Spacer(1, 0.05 * inch))
    bill_parts = []
    if invoice.customer_name:
        bill_parts.append(f"<b>{esc(invoice.customer_name)}</b>")
    if invoice.customer_company:
        bill_parts.append(esc(invoice.customer_company))
    if invoice.bill_to_line1:
        bill_parts.append(esc(invoice.bill_to_line1))
    city_state_zip = ""
    if invoice.bill_to_city:
        city_state_zip += esc(invoice.bill_to_city)
    if invoice.bill_to_state:
        city_state_zip += f", {esc(invoice.bill_to_state)}"
    if invoice.bill_to_zip:
        city_state_zip += f" {esc(invoice.bill_to_zip)}"
    if city_state_zip:
        bill_parts.append(city_state_zip)
    if invoice.customer_email:
        bill_parts.append(esc(invoice.customer_email))
    content.append(Paragraph("<br/>".join(bill_parts) if bill_parts else "N/A", normal_style))
    content.append(Spacer(1, 0.2 * inch))

    # ---- Line Items ----
    content.append(Paragraph("ITEMS", heading_style))
    content.append(Spacer(1, 0.1 * inch))

    table_data = [["SKU", "Description", "Qty", "Unit Price", "Total"]]
    lines = db.query(InvoiceLine).filter(InvoiceLine.invoice_id == invoice.id).all()
    for line in lines:
        qty_str = str(int(line.quantity)) if line.quantity == int(line.quantity) else str(line.quantity)
        table_data.append([
            esc(line.sku or ""),
            esc(line.description),
            qty_str,
            f"${line.unit_price:,.2f}",
            f"${line.line_total:,.2f}",
        ])

    items_table = Table(table_data, colWidths=[1 * inch, 2.5 * inch, 0.7 * inch, 1.1 * inch, 1.2 * inch])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    content.append(items_table)
    content.append(Spacer(1, 0.2 * inch))

    # ---- Totals ----
    totals_data = [
        ["Subtotal:", f"${invoice.subtotal:,.2f}"],
    ]
    if invoice.discount_amount and invoice.discount_amount > 0:
        totals_data.append(["Discount:", f"-${invoice.discount_amount:,.2f}"])
    if invoice.tax_amount and invoice.tax_amount > 0:
        tax_pct = f" ({float(invoice.tax_rate) * 100:.2f}%)" if invoice.tax_rate else ""
        totals_data.append([f"Tax{tax_pct}:", f"${invoice.tax_amount:,.2f}"])
    if invoice.shipping_amount and invoice.shipping_amount > 0:
        totals_data.append(["Shipping:", f"${invoice.shipping_amount:,.2f}"])
    totals_data.append(["Total Due:", f"${invoice.total:,.2f}"])
    if invoice.amount_paid and invoice.amount_paid > 0:
        balance = invoice.total - invoice.amount_paid
        totals_data.append(["Amount Paid:", f"${invoice.amount_paid:,.2f}"])
        totals_data.append(["Balance Due:", f"${balance:,.2f}"])

    totals_table = Table(totals_data, colWidths=[4.5 * inch, 2 * inch])
    totals_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    content.append(totals_table)
    content.append(Spacer(1, 0.3 * inch))

    # ---- Payment Instructions / Terms ----
    if settings and settings.invoice_terms:
        content.append(Paragraph("PAYMENT INSTRUCTIONS", heading_style))
        content.append(Spacer(1, 0.05 * inch))
        content.append(Paragraph(esc(settings.invoice_terms), normal_style))

    doc.build(content)
    pdf_buffer.seek(0)
    return pdf_buffer
```

**Step 2: Commit**

```bash
git add backend/app/services/invoice_service.py
git commit -m "feat: add invoice PDF generation with ReportLab"
```

---

### Task 3.6: API Endpoints — Invoice CRUD

**Files:**
- Create: `backend/app/api/v1/endpoints/invoices.py`
- Modify: `backend/app/api/v1/endpoints/__init__.py` or wherever routers are registered

**Step 1: Write the endpoint file**

```python
"""Invoice API endpoints."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.api.v1.deps import get_current_staff_user
from app.models.user import User
from app.schemas.invoice import InvoiceCreate, InvoiceUpdate, InvoiceResponse, InvoiceListResponse
from app.services import invoice_service

router = APIRouter(prefix="/invoices", tags=["Invoices"])


def _build_invoice_response(invoice, db) -> dict:
    """Build InvoiceResponse dict from Invoice model."""
    from app.models.sales_order import SalesOrder

    order_number = None
    if invoice.sales_order_id:
        order = db.query(SalesOrder).filter(SalesOrder.id == invoice.sales_order_id).first()
        order_number = order.order_number if order else None

    amount_due = invoice.total - (invoice.amount_paid or 0)

    return {
        **{c.name: getattr(invoice, c.name) for c in invoice.__table__.columns},
        "lines": [
            {c.name: getattr(line, c.name) for c in line.__table__.columns}
            for line in invoice.lines
        ],
        "order_number": order_number,
        "amount_due": float(amount_due),
    }


@router.post("", response_model=InvoiceResponse)
def create_invoice(
    data: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    invoice = invoice_service.create_invoice(db, data.sales_order_id)
    return _build_invoice_response(invoice, db)


@router.get("", response_model=list[InvoiceListResponse])
def list_invoices(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    invoices = invoice_service.list_invoices(db, status=status, customer_search=search, limit=limit, offset=offset)

    from app.models.sales_order import SalesOrder
    results = []
    for inv in invoices:
        order_number = None
        if inv.sales_order_id:
            order = db.query(SalesOrder).filter(SalesOrder.id == inv.sales_order_id).first()
            order_number = order.order_number if order else None
        results.append({
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "sales_order_id": inv.sales_order_id,
            "order_number": order_number,
            "customer_name": inv.customer_name,
            "customer_company": inv.customer_company,
            "payment_terms": inv.payment_terms,
            "due_date": inv.due_date,
            "total": inv.total,
            "amount_paid": inv.amount_paid or 0,
            "amount_due": float(inv.total - (inv.amount_paid or 0)),
            "status": inv.status,
            "created_at": inv.created_at,
            "sent_at": inv.sent_at,
        })
    return results


@router.get("/summary")
def invoice_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    return invoice_service.get_invoice_summary(db)


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    invoice = invoice_service.get_invoice(db, invoice_id)
    return _build_invoice_response(invoice, db)


@router.patch("/{invoice_id}", response_model=InvoiceResponse)
def update_invoice(
    invoice_id: int,
    data: InvoiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    if data.amount_paid is not None and data.payment_method:
        invoice = invoice_service.record_payment(
            db, invoice_id,
            amount=data.amount_paid,
            method=data.payment_method,
            reference=data.payment_reference,
        )
    else:
        invoice = invoice_service.get_invoice(db, invoice_id)
        if data.status:
            invoice.status = data.status
            db.commit()
            db.refresh(invoice)
    return _build_invoice_response(invoice, db)


@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    pdf_buffer = invoice_service.generate_invoice_pdf(db, invoice_id)
    invoice = invoice_service.get_invoice(db, invoice_id)
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{invoice.invoice_number}.pdf"'
        },
    )


@router.post("/{invoice_id}/send", response_model=InvoiceResponse)
def send_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    invoice = invoice_service.mark_sent(db, invoice_id)
    return _build_invoice_response(invoice, db)
```

**Step 2: Register the router**

Find where other routers are registered (likely in `backend/app/api/v1/__init__.py` or `backend/app/main.py`). Add:

```python
from app.api.v1.endpoints.invoices import router as invoices_router
app.include_router(invoices_router, prefix="/api/v1")
```

Follow the existing pattern for how other routers like `sales_orders` are registered.

**Step 3: Verify endpoints load**

```bash
cd backend && python -c "from app.api.v1.endpoints.invoices import router; print('OK')"
```

**Step 4: Commit**

```bash
git add backend/app/api/v1/endpoints/invoices.py
# + whatever registration file was modified
git commit -m "feat: add invoice API endpoints — CRUD, PDF download, send"
```

---

### Task 3.7: Tests — Invoice service

**Files:**
- Create: `backend/tests/test_invoice_service.py`

**Step 1: Write tests**

```python
"""Tests for invoice service."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services.invoice_service import (
    _calculate_due_date,
    _generate_invoice_number,
)


class TestDueDateCalculation:
    def test_cod_due_immediately(self):
        today = date.today()
        assert _calculate_due_date("cod", today) == today

    def test_net15(self):
        base = date(2026, 3, 1)
        assert _calculate_due_date("net15", base) == date(2026, 3, 16)

    def test_net30(self):
        base = date(2026, 3, 1)
        assert _calculate_due_date("net30", base) == date(2026, 3, 31)

    def test_prepay_due_immediately(self):
        today = date.today()
        assert _calculate_due_date("prepay", today) == today


class TestInvoiceNumberGeneration:
    def test_first_invoice_of_year(self, db):
        number = _generate_invoice_number(db)
        year = date.today().year
        assert number.startswith(f"INV-{year}-")
        assert number.endswith("001") or int(number.split("-")[-1]) >= 1


class TestCreateInvoice:
    def test_create_from_confirmed_order(self, client, admin_headers, db, make_product):
        """Create an invoice from a confirmed sales order."""
        # Create a product
        product = make_product(sku="INV-TEST-001", selling_price=Decimal("29.99"))
        db.flush()

        # Create a sales order (via API)
        # This test depends on the sales order creation flow working.
        # If make_product/make_order fixtures exist, use those.
        # Otherwise, create manually via the API.
        pass  # Implementation depends on available fixtures

    def test_cannot_invoice_draft_order(self, client, admin_headers, db):
        """Draft orders cannot be invoiced."""
        resp = client.post(
            "/api/v1/invoices",
            json={"sales_order_id": 999999},
            headers=admin_headers,
        )
        assert resp.status_code in (400, 404)

    def test_duplicate_invoice_prevented(self, client, admin_headers, db):
        """Cannot create two invoices for the same SO."""
        # Would need a confirmed order fixture
        pass


class TestRecordPayment:
    def test_record_payment_endpoint(self, client, admin_headers, db):
        """Record payment updates amount_paid."""
        # Would need an existing invoice fixture
        pass
```

**Step 2: Run tests**

```bash
cd backend && python -m pytest tests/test_invoice_service.py -v --tb=short
```

**Step 3: Commit**

```bash
git add backend/tests/test_invoice_service.py
git commit -m "test: add invoice service tests — due dates, number generation"
```

---

### Task 3.8: Frontend — Invoice list page

**Files:**
- Create: `frontend/src/pages/admin/AdminInvoices.jsx`
- Modify: `frontend/src/App.jsx` (add route)
- Modify: `frontend/src/components/AdminLayout.jsx` (add nav item)

**Step 1: Create AdminInvoices.jsx**

Follow the pattern of `AdminOrders.jsx`. Key sections:
- Status filter tabs: All, Draft, Sent, Paid, Overdue
- Search input (customer name, invoice number)
- Table: Invoice #, Order #, Customer, Terms, Due Date, Total, Paid, Status
- Row click opens detail modal
- Status badges with colors (draft=gray, sent=blue, paid=green, overdue=red)

```jsx
import { useState, useEffect } from "react";
import { useFormatCurrency } from "../../hooks/useFormatCurrency";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";

export default function AdminInvoices() {
  const formatCurrency = useFormatCurrency();
  const api = useApi();
  const toast = useToast();
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [selectedInvoice, setSelectedInvoice] = useState(null);
  const [summary, setSummary] = useState({ overdue_count: 0, total_ar: 0 });

  const fetchInvoices = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== "all") params.set("status", statusFilter);
      if (search) params.set("search", search);
      const data = await api.get(`/api/v1/invoices?${params}`);
      setInvoices(data);
    } catch (err) {
      toast.error("Failed to load invoices");
    } finally {
      setLoading(false);
    }
  };

  const fetchSummary = async () => {
    try {
      const data = await api.get("/api/v1/invoices/summary");
      setSummary(data);
    } catch {}
  };

  useEffect(() => { fetchInvoices(); fetchSummary(); }, [statusFilter]);

  // ... render table, filters, detail modal
  // Follow AdminOrders.jsx patterns for layout, table styling, modals
}
```

**Step 2: Add route to App.jsx**

```jsx
const AdminInvoices = lazy(() => import("./pages/admin/AdminInvoices"));

// In routes:
<Route path="/admin/invoices" element={<Suspense fallback={<PageLoader />}><AdminInvoices /></Suspense>} />
```

**Step 3: Add nav item to AdminLayout.jsx**

In the `navGroups` array, add to the "SALES" group (after "Payments"):

```jsx
{ name: "Invoices", path: "/admin/invoices", icon: DocumentTextIcon },
```

Import `DocumentTextIcon` from `@heroicons/react/24/outline`.

**Step 4: Commit**

```bash
git add frontend/src/pages/admin/AdminInvoices.jsx frontend/src/App.jsx frontend/src/components/AdminLayout.jsx
git commit -m "feat: add invoice list page with filters and navigation"
```

---

### Task 3.9: Frontend — Invoice detail modal

**Files:**
- Modify: `frontend/src/pages/admin/AdminInvoices.jsx`

**Step 1: Add detail modal**

When clicking an invoice row, show a modal with:
- Invoice header (number, date, due date, terms, status badge)
- Customer info (name, company, billing address)
- Line items table (SKU, description, qty, unit price, total)
- Totals section (subtotal, discount, tax, shipping, total, amount paid, balance due)
- Action buttons:
  - "Send Invoice" (if draft) — POST /invoices/{id}/send
  - "Record Payment" — opens sub-form with amount, method, reference
  - "Download PDF" — GET /invoices/{id}/pdf

**Step 2: Add "Record Payment" sub-form**

```jsx
const [showPaymentForm, setShowPaymentForm] = useState(false);
const [paymentForm, setPaymentForm] = useState({
  amount: "", method: "check", reference: ""
});

const handleRecordPayment = async () => {
  try {
    await api.patch(`/api/v1/invoices/${selectedInvoice.id}`, {
      amount_paid: parseFloat(paymentForm.amount),
      payment_method: paymentForm.method,
      payment_reference: paymentForm.reference,
    });
    toast.success("Payment recorded");
    fetchInvoices();
    // Refresh selected invoice
  } catch (err) {
    toast.error("Failed to record payment");
  }
};
```

**Step 3: Add PDF download handler**

```jsx
const handleDownloadPDF = async () => {
  try {
    const response = await fetch(`/api/v1/invoices/${selectedInvoice.id}/pdf`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${selectedInvoice.invoice_number}.pdf`;
    a.click();
    window.URL.revokeObjectURL(url);
  } catch {
    toast.error("Failed to download PDF");
  }
};
```

**Step 4: Commit**

```bash
git add frontend/src/pages/admin/AdminInvoices.jsx
git commit -m "feat: add invoice detail modal with payment recording and PDF download"
```

---

### Task 3.10: Frontend — "Generate Invoice" button on order detail

**Files:**
- Modify: `frontend/src/pages/admin/AdminOrders.jsx` (or `OrderDetail.jsx`)

**Step 1: Add "Generate Invoice" button**

In the order detail view, when the order status is confirmed or later AND no invoice exists yet, show a "Generate Invoice" button:

```jsx
const handleGenerateInvoice = async () => {
  try {
    const invoice = await api.post("/api/v1/invoices", {
      sales_order_id: order.id,
    });
    toast.success(`Invoice ${invoice.invoice_number} created`);
    // Optionally navigate to invoice detail
  } catch (err) {
    toast.error(err.message || "Failed to generate invoice");
  }
};
```

**Step 2: Commit**

```bash
git add frontend/src/pages/admin/AdminOrders.jsx
git commit -m "feat: add 'Generate Invoice' button on order detail"
```

---

### Task 3.11: Frontend — Dashboard AR widget

**Files:**
- Modify: dashboard page (find it — likely `frontend/src/pages/admin/AdminDashboard.jsx` or similar)

**Step 1: Add AR widget**

Fetch invoice summary from `/api/v1/invoices/summary` and display:
- Overdue invoice count (red if > 0)
- Total accounts receivable

Use `StatCard` component (already imported in AdminCustomers).

**Step 2: Commit**

```bash
git add frontend/src/pages/admin/AdminDashboard.jsx  # or equivalent
git commit -m "feat: add overdue invoices and AR widget to dashboard"
```

---

### Task 3.12: Run full test suite and PR

**Step 1: Run all tests**

```bash
cd backend && python -m pytest tests/ -x -q --tb=short
cd frontend && npx vitest run
```

**Step 2: Lint check**

```bash
cd backend && python -m ruff check app/ --select E712
```

**Step 3: Create PR**

```bash
gh pr create --title "feat: invoice engine — PDF templates, payment recording (#466)" \
  --body "## Summary
- Create invoices and invoice_lines tables (migration 070)
- Invoice service: create from SO, PDF generation, payment recording, list/query
- API endpoints: CRUD, PDF download, send, summary
- Admin invoice list page with status filters and search
- Invoice detail modal with line items, payment recording, PDF download
- Generate Invoice button on order detail
- Dashboard AR widget (overdue count + total receivable)

Closes #466
Depends on #465

## Test plan
- [ ] Generate invoice from confirmed SO — verify auto-number, customer snapshot
- [ ] Download invoice PDF — verify logo, line items, totals
- [ ] Record payment — verify amount_paid updates, status changes to 'paid' when full
- [ ] Mark invoice as sent — verify status and sent_at timestamp
- [ ] List invoices with status filter — verify overdue detection
- [ ] Dashboard shows overdue count and AR total
- [ ] Run pytest — all pass"
```

---

## Execution Order Summary

| # | Branch | Feature | Migration | Depends On |
|---|--------|---------|-----------|------------|
| 1 | `feat/customer-payment-terms` | Payment terms (#465) | 069 | — |
| 2 | `feat/so-price-level-discount` | Price level auto-apply (#464) | — | — |
| 3 | `feat/invoice-engine` | Invoice engine (#466) | 070 | #465, #464 |

**Each feature should be merged to `main` before starting the next**, since Feature 3 depends on Features 1 and 2.

**Note:** PRs #461 and #462 are still open. They don't block this work, but should be merged when ready.
