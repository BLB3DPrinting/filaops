# FilaOps Feature Catalog

> Complete feature inventory with tier classification, hidden features, and implementation status.
> Use this for roadmap planning.
>
> **Note**: This document covers **Core (Open Source)** features only.

## Overview

| Tier | Features | Status |
| ------ | ---------- | -------- |
| **Core (Open Source)** | 41 | Released |
| **Total** | 41 | - |

---

## Feature Classification

### Tier Definition

### Core (Open Source)

## Core Features (41)

### Authentication & Access

| # | Feature | Description | Status |
| --- | ------- | ----------- | ------ |
| 1 | User Authentication | Email/password login with JWT | ✅ Complete |
| 2 | Token Refresh | Auto-refresh JWT without re-login | ✅ Complete |
| 3 | Password Reset | Admin-approved password reset flow | ✅ Complete |
| 4 | Role-Based Access | Admin vs Operator permissions | ✅ Complete |

### Sales Management

| # | Feature | Description | Status |
| --- | ------- | ----------- | ------ |
| 5 | Sales Orders | Create, edit, track customer orders | ✅ Complete |
| 6 | Order Lines | Add products with quantities, prices | ✅ Complete |
| 7 | Order Status Workflow | Draft -> Open -> In Progress -> Shipped -> Complete | ✅ Complete |
| 8 | Fulfillment Tracking | Track order through production to shipment | ✅ Complete |
| 9 | Blocking Issues | Identify what's preventing order completion | ✅ Complete |
| 10 | Quotes | Create customer quotations | ✅ Complete |
| 11 | Quote Conversion | Convert approved quote to sales order | ✅ Complete |

### Inventory Management

| # | Feature | Description | Status |
| --- | ------- | ----------- | ------ |
| 12 | Product Catalog | SKU, name, description, pricing | ✅ Complete |
| 13 | Item Categories | Hierarchical product categorization | ✅ Complete |
| 14 | Inventory Tracking | On-hand, allocated, available quantities | ✅ Complete |
| 15 | Inventory Transactions | Full audit trail of inventory movements | ✅ Complete |
| 16 | Inventory Adjustment | Manual adjustments with reason codes | ✅ Complete |
| 17 | Multiple Locations | Track inventory across warehouses | ✅ Complete |
| 18 | Low Stock Alerts | Reorder point monitoring | ✅ Complete |
| 19 | Cycle Counting | Physical inventory verification | ✅ Complete |
| 20 | Material Spools | Filament spool tracking with weight | ✅ Complete |

### Manufacturing

| # | Feature | Description | Status |
| --- | ------- | ----------- | ------ |
| 21 | Production Orders | Work orders for manufacturing | ✅ Complete |
| 22 | Operations Tracking | Track each operation in production | ✅ Complete |
| 23 | Operation Scheduling | Assign operations to work centers | ✅ Complete |
| 24 | Bill of Materials | Define product components and quantities | ✅ Complete |
| 25 | Multi-Level BOM | Sub-assembly support with explosion | ✅ Complete |
| 26 | Routings | Define manufacturing steps | ✅ Complete |
| 27 | Operation Materials | Materials per operation (Manufacturing BOM) | ✅ Complete |
| 28 | Work Centers | Define manufacturing areas | ✅ Complete |
| 29 | Scrap Tracking | Record scrap with reason codes | ✅ Complete |
| 30 | QC Pass/Fail | Quality inspection recording | ✅ Complete |

### Supply Chain

| # | Feature | Description | Status |
| --- | ------- | ----------- | ------ |
| 31 | Vendor Management | Supplier database | ✅ Complete |
| 32 | Purchase Orders | Create and track POs | ✅ Complete |
| 33 | PO Receipt | Receive items against POs | ✅ Complete |
| 34 | PO Documents | Attach invoices, receipts to POs | ✅ Complete |
| 35 | Low Stock PO Creation | Create POs from low stock report | ✅ Complete |

### Planning

| # | Feature | Description | Status |
| --- | ------- | ----------- | ------ |
| 36 | MRP | Material Requirements Planning | ✅ Complete |
| 37 | Planned Orders | Generate and manage planned orders | ✅ Complete |

### System & Setup

| # | Feature | Description | Status |
| --- | ------- | ----------- | ------ |
| 38 | First-Run Setup Wizard | Onboarding wizard with initial admin account creation | ✅ Complete |
| 39 | SMTP & Auto-Approve Reset Delivery | Password reset delivery via SMTP email or auto-approve with direct link | ✅ Complete |
| 40 | Duplicate Item | Clone items with inline BOM component swap for color variants | ✅ Complete |
| 41 | Copy BOM | Copy a BOM to a different product with target product picker | ✅ Complete |

---

## Hidden Features (Backend Only)

These features have API endpoints but no UI implementation.

### Negative Inventory Approval

**Status**: ⚠️ Backend Only

**API Endpoints**:

- `POST /inventory/transactions/{id}/approve-negative`
- `GET /inventory/negative-inventory-report`

**Database Columns** (inventory_transactions):

- `requires_approval`
- `approval_reason`
- `approved_by`
- `approved_at`

**Missing UI**:

1. Pending approval list/notification
2. Approval modal with reason field
3. Negative inventory report view

**Recommended Implementation**:

```jsx
// components/NegativeInventoryApprovalModal.jsx
// - List transactions requiring approval
// - Approve/Deny buttons
// - Reason text field
// - Audit display (who requested, when)

// pages/AdminInventoryTransactions.jsx
// - Add "Pending Approvals" tab or filter
// - Badge showing count of pending approvals
```

---

## Feature Roadmap

### Q1 2026 - Core Stability

- [x] Complete Core feature set
- [x] MRP double-counting fix
- [ ] Negative Inventory Approval UI
- [ ] Performance optimization

---

## Feature Dependencies

```text
Authentication
    └─ Sales Orders
        └─ Order Lines
        └─ Payments
        └─ Fulfillment
            └─ Production Orders
                └─ Operations
                └─ Materials Consumption
                └─ Scrap Tracking

Products
    └─ BOM
        └─ BOM Lines
    └─ Routings
        └─ Routing Operations
        └─ Operation Materials
    └─ Inventory
        └─ Transactions
        └─ Spools

Vendors
    └─ Purchase Orders
        └─ PO Lines
        └─ PO Documents
        └─ Receipt

MRP
    └─ Planned Orders
        └─ → Purchase Orders
        └─ → Production Orders
```

---

## Feature Testing Checklist

### Core Features

- [ ] User can login/logout
- [ ] User can create sales order
- [ ] User can add items to catalog
- [ ] User can create BOM for product
- [ ] User can create production order from sales order
- [ ] User can track operations
- [ ] User can receive purchase orders
- [ ] User can run MRP
- [ ] Inventory updates correctly on transactions

---

*Last updated: 2026-01-28*
*Generated for FilaOps Core (Open Source)*
