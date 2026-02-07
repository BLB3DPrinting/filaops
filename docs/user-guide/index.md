# FilaOps User Guide

Welcome to the FilaOps User Guide. This documentation covers all modules of the FilaOps open-source ERP system for 3D print farm operations.

## Quick Start

New to FilaOps? Start here:

1. **[Getting Started](getting-started.md)** - Installation, setup, and your first sales order

## Module Guides

| Guide | Description |
|-------|-------------|
| **[Getting Started](getting-started.md)** | Installation, database setup, first-time wizard, creating your first sales order |
| **[Sales & Quotes](sales-and-quotes.md)** | Quote creation and approval, sales order lifecycle, customers, pricing, fulfillment |
| **[Inventory Management](inventory-management.md)** | Items, stock levels, transactions, spool tracking, UOM system, cycle counting |
| **[Manufacturing](manufacturing.md)** | Production orders, BOMs, routings, work centers, QC, scrap and rework |
| **[Purchasing](purchasing.md)** | Vendors, purchase orders, receiving inventory, documents, cost tracking |
| **[MRP](mrp.md)** | Material Requirements Planning, planned orders, firming, releasing, BOM explosion |
| **[Printers & Fleet](printers-and-fleet.md)** | Multi-brand printer management, network discovery, MQTT monitoring, maintenance |
| **[Accounting](accounting-module.md)** | General Ledger, journal entries, trial balance, COGS, tax reporting, fiscal periods |
| **[Settings & Admin](settings-and-admin.md)** | Company settings, users, locations, materials, work centers, AI configuration |

## Typical Workflow

```
1. Set Up (once)
   Getting Started → Settings & Admin

2. Daily Operations
   Sales & Quotes → Manufacturing → Inventory → Purchasing

3. Planning
   MRP → Purchasing → Manufacturing

4. Monitoring
   Printers & Fleet → Manufacturing Dashboard

5. Financial
   Accounting → Tax Reporting → Month-End Close
```

## How Modules Connect

```
Sales & Quotes
  └→ Manufacturing (production orders from sales orders)
       ├→ Inventory (material consumption and finished goods)
       ├→ Printers & Fleet (printer assignment and monitoring)
       └→ MRP (material shortage detection)
            └→ Purchasing (purchase orders from MRP)
                 └→ Inventory (receiving updates stock)

Accounting ← (automatic GL entries from all modules)
Settings ← (configuration used by all modules)
```

## Getting Help

- **API Reference:** See `docs/API-REFERENCE.md`
- **Issues:** [GitHub Issues](https://github.com/Blb3D/filaops/issues)
- **Contributing:** See `CONTRIBUTING.md` in the repository root

---

*FilaOps v3.0.0 | February 2026*
