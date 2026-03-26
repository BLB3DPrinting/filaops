# Portal Order Ingestion & Operator Notifications — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add external order ingestion (source tracking, pending_confirmation status, confirm/reject flow) and an operator notification inbox to Core, laying the foundation for Portal GTM Track 2.

**Architecture:** Extends existing SalesOrder with a new `pending_confirmation` status before `draft` in the lifecycle. Adds a new `notifications` table with UUID-based thread grouping for operator messaging. When an external order is confirmed, an auto-notification is created. No PRO references — this is pure Core functionality.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, React 19, Vite, Tailwind CSS

**Issues:** #456 (External Order Ingestion), #457 (Operator Notification Inbox)
**Branch:** `feat/portal-order-ingestion`

---

## Key Discovery: Existing Columns

The SalesOrder model **already has** these columns:
- `source VARCHAR(50) DEFAULT 'portal'` — values: portal, squarespace, woocommerce, manual
- `source_order_id VARCHAR(255)` — external order ID (spec calls it `external_reference`)
- `confirmed_at DateTime` — already exists

**What needs to be added:**
- `submitted_at` column on sales_orders
- `PENDING_CONFIRMATION` status in SalesOrderStatus enum + transition rules
- Confirm/reject endpoints
- Source filter on list endpoint
- Entire notifications system (model, service, API, frontend)

The spec's `external_reference` maps to existing `source_order_id`. The spec's source values (`admin`, `portal`, `api`) extend the existing source column — we add `admin` and `api` as valid values alongside existing ones.

---

### Task 1: Migration 072 — submitted_at + notifications table

**Files:**
- Create: `backend/migrations/versions/072_portal_ingestion_notifications.py`

**Step 1: Write the migration**

```python
"""Add submitted_at to sales_orders and create notifications table

Revision ID: 072
Revises: 071
"""
from alembic import op
import sqlalchemy as sa

revision = "072"
down_revision = "071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add submitted_at to sales_orders
    op.add_column("sales_orders", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))

    # Create notifications table
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thread_id", sa.String(36), nullable=False),  # UUID stored as string
        sa.Column("thread_subject", sa.String(200), nullable=True),
        sa.Column("sales_order_id", sa.Integer(), sa.ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=True),
        sa.Column("sender_type", sa.String(20), nullable=False, server_default="system"),
        sa.Column("sender_name", sa.String(200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(20), nullable=True, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_notifications_thread", "notifications", ["thread_id", "created_at"])
    op.create_index("idx_notifications_unread", "notifications", ["read_at"], postgresql_where=sa.text("read_at IS NULL"))
    op.create_index("idx_notifications_sales_order", "notifications", ["sales_order_id"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_column("sales_orders", "submitted_at")
```

**Step 2: Run migration**
```bash
cd backend && alembic upgrade head
```

**Step 3: Commit**
```bash
git add backend/migrations/versions/072_portal_ingestion_notifications.py
git commit -m "feat: migration 072 — submitted_at + notifications table (#456, #457)"
```

---

### Task 2: Add PENDING_CONFIRMATION status

**Files:**
- Modify: `backend/app/core/status_config.py:105-160`

**Changes:**
1. Add `PENDING_CONFIRMATION = "pending_confirmation"` to `SalesOrderStatus` enum
2. Add transition: `pending_confirmation → {confirmed, cancelled}`
3. Update `DRAFT` transitions to include `pending_confirmation` as a valid target (for when external systems create orders as draft then submit)

```python
class SalesOrderStatus(str, Enum):
    PENDING_CONFIRMATION = "pending_confirmation"  # New: awaiting admin review
    DRAFT = "draft"
    PENDING = "pending"
    # ... rest unchanged

SALES_ORDER_TRANSITIONS = {
    SalesOrderStatus.PENDING_CONFIRMATION: {
        SalesOrderStatus.CONFIRMED,
        SalesOrderStatus.CANCELLED,
    },
    # ... rest unchanged
}
```

**Step: Commit**
```bash
git add backend/app/core/status_config.py
git commit -m "feat: add pending_confirmation status for external orders (#456)"
```

---

### Task 3: Update SalesOrder model + schemas

**Files:**
- Modify: `backend/app/models/sales_order.py:125` — add `submitted_at`
- Modify: `backend/app/schemas/sales_order.py` — add fields to create/response schemas

**Model change (after confirmed_at line 125):**
```python
submitted_at = Column(DateTime, nullable=True)
```

**Schema changes:**
- `SalesOrderCreate`: source field description updated to include 'api'
- `SalesOrderListResponse`: add `source: Optional[str] = None`, `source_order_id: Optional[str] = None`
- `SalesOrderResponse`: add `submitted_at: Optional[datetime] = None`
- `SalesOrderStatsResponse`: add `pending_confirmation_orders: int`

**Step: Commit**
```bash
git add backend/app/models/sales_order.py backend/app/schemas/sales_order.py
git commit -m "feat: add submitted_at to model, source to list response (#456)"
```

---

### Task 4: Add confirm/reject endpoints

**Files:**
- Modify: `backend/app/api/v1/endpoints/sales_orders.py`
- Modify: `backend/app/services/sales_order_service.py`

**Service functions:**
```python
def confirm_external_order(db: Session, order_id: int, confirmed_by_user_id: int) -> SalesOrder:
    """Confirm a pending_confirmation order — sets status to confirmed, records confirmed_at."""

def reject_external_order(db: Session, order_id: int, reason: str, rejected_by_user_id: int) -> SalesOrder:
    """Reject a pending_confirmation order — sets status to cancelled with reason."""
```

**API endpoints:**
```python
POST /api/v1/sales-orders/{order_id}/confirm   → pending_confirmation → confirmed
POST /api/v1/sales-orders/{order_id}/reject    → pending_confirmation → cancelled
```

**Step: Commit**
```bash
git add backend/app/services/sales_order_service.py backend/app/api/v1/endpoints/sales_orders.py
git commit -m "feat: confirm/reject endpoints for external orders (#456)"
```

---

### Task 5: Add source filter to list endpoint

**Files:**
- Modify: `backend/app/api/v1/endpoints/sales_orders.py` — list endpoint query params
- Modify: `backend/app/services/sales_order_service.py` — list_sales_orders function

**Changes:**
- Add `source: Optional[str] = None` query param to GET `/sales-orders/`
- Add `source` filter to `list_sales_orders()` service function
- Ensure `pending_confirmation` works in multi-status filter

---

### Task 6: Build notification model + service

**Files:**
- Create: `backend/app/models/notification.py`
- Create: `backend/app/schemas/notification.py`
- Create: `backend/app/services/notification_service.py`
- Modify: `backend/app/models/__init__.py` — register Notification

**Model:**
```python
class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    thread_id = Column(String(36), nullable=False, index=True)
    thread_subject = Column(String(200), nullable=True)
    sales_order_id = Column(Integer, ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=True)
    sender_type = Column(String(20), nullable=False, default="system")
    sender_name = Column(String(200), nullable=True)
    body = Column(Text, nullable=False)
    read_at = Column(DateTime, nullable=True)
    source = Column(String(20), default="system")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    sales_order = relationship("SalesOrder")
```

**Service functions:**
```python
def create_notification(db, *, thread_id=None, thread_subject, sales_order_id=None, sender_type="system", sender_name=None, body, source="system") -> Notification
def list_threads(db, *, skip=0, limit=50, unread_only=False) -> list[dict]
def get_thread(db, thread_id: str) -> list[Notification]
def reply_to_thread(db, thread_id: str, *, sender_name: str, body: str) -> Notification
def mark_read(db, notification_id: int) -> Notification
def get_unread_count(db) -> int
```

---

### Task 7: Build notifications API router

**Files:**
- Create: `backend/app/api/v1/endpoints/notifications.py`
- Modify: `backend/app/api/v1/api.py` — register router

**Endpoints:**
```
GET    /api/v1/notifications              — list threads (paginated)
GET    /api/v1/notifications/{thread_id}  — thread messages
POST   /api/v1/notifications/{thread_id}/reply — operator reply
POST   /api/v1/notifications/{id}/read    — mark read
GET    /api/v1/notifications/unread-count  — badge count
```

---

### Task 8: Wire confirm → auto-create notification

**Files:**
- Modify: `backend/app/services/sales_order_service.py` — confirm_external_order

**Logic:** After confirming, call `create_notification()` with:
- thread_subject: `"Order {order_number} confirmed"`
- body: `"Order {order_number} was confirmed by {admin_name}."`
- sender_type: `"admin"`
- sales_order_id: the confirmed order
- source: `"system"`

---

### Task 9: Add pending_confirmation count to dashboard summary

**Files:**
- Modify: `backend/app/api/v1/endpoints/admin/dashboard.py:297-583`

**Changes:**
- Add `pending_confirmation_orders` count query
- Add to summary response dict under `orders`
- Add `unread_notifications` count to summary

---

### Task 10: Write backend tests

**Files:**
- Create: `backend/tests/services/test_notification_service.py`
- Modify: `backend/tests/api/v1/test_sales_orders.py` — add confirm/reject/source filter tests
- Create: `backend/tests/api/v1/test_notifications.py`
- Modify: `backend/tests/conftest.py` — add `make_notification` fixture

**Test cases:**
- Confirm: pending_confirmation → confirmed, sets confirmed_at
- Confirm: non-pending_confirmation → 409
- Reject: pending_confirmation → cancelled with reason
- Source filter: list orders filtered by source
- Notification CRUD: create, list threads, get thread, reply, mark read, unread count
- Auto-notification on confirm

---

### Task 11: Frontend — Orders page source badge + pending tab

**Files:**
- Modify: `frontend/src/pages/admin/AdminOrders.jsx`
- Modify: `frontend/src/components/orders/SalesOrderCard.jsx`
- Modify: `frontend/src/components/orders/OrderFilters.jsx`

**Changes:**
- Add source badge to SalesOrderCard (small pill: "API", "Portal", etc.)
- Add "Pending Review" quick-filter tab to OrderFilters
- Wire `?status=pending_confirmation` filter

---

### Task 12: Frontend — Order detail confirm/reject + invoice wire

**Files:**
- Modify: `frontend/src/pages/admin/OrderDetail.jsx` (or wherever the detail page is)

**Changes:**
- Confirm/Reject buttons when `status === "pending_confirmation"`
- Confirm calls `POST /sales-orders/{id}/confirm`
- Reject opens modal for reason, calls `POST /sales-orders/{id}/reject`
- "Generate Invoice" button appears after confirm (uses existing invoice engine)

---

### Task 13: Frontend — AdminNotifications + sidebar + dashboard

**Files:**
- Create: `frontend/src/pages/admin/AdminNotifications.jsx`
- Modify: `frontend/src/components/AdminLayout.jsx` — add Messages to SALES nav group
- Modify: `frontend/src/App.jsx` — add route
- Modify: `frontend/src/pages/admin/AdminDashboard.jsx` — add unread messages action item

**AdminNotifications layout:**
- Left panel: thread list (subject, preview, unread dot, linked SO)
- Right panel: thread messages chronologically + reply textarea
- Uses existing dark theme patterns from AdminOrders/AdminPayments

**Sidebar:** Add `{ path: "/admin/messages", label: "Messages", icon: MessagesIcon }` to SALES group (after Customers)

**Dashboard:** Add to Action Items: `unread_notifications > 0` → link to `/admin/messages`
