# FilaOps Documentation

**Open-source ERP for 3D print farm operations.** Manage inventory, production orders, BOMs, MRP, sales orders, purchasing, and GL accounting in one system built for additive manufacturing.

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **Getting Started**

    ---

    Install FilaOps, create your admin account, and run your first workflow in minutes.

    [:octicons-arrow-right-24: Quick start](user-guide/getting-started.md)

-   :material-book-open-variant:{ .lg .middle } **User Guide**

    ---

    Step-by-step guides for every module — sales, inventory, manufacturing, MRP, purchasing, and more.

    [:octicons-arrow-right-24: Browse guides](user-guide/index.md)

-   :material-server:{ .lg .middle } **Deployment**

    ---

    Docker Compose production setup, backups, migrations, email, and operational procedures.

    [:octicons-arrow-right-24: Deploy](deployment/index.md)

-   :material-code-tags:{ .lg .middle } **Developer Reference**

    ---

    API endpoints, database schema, UI components, and conventions for contributors.

    [:octicons-arrow-right-24: Reference](reference/index.md)

</div>

## 37 Core Features

FilaOps ships with everything you need to run a 3D print farm:

| Module | Highlights |
|--------|-----------|
| **Sales & Quotes** | Quotations, sales orders, fulfillment tracking, order status workflows |
| **Inventory** | Multi-location stock, spool tracking, cycle counting, UOM system, low stock alerts |
| **Manufacturing** | Production orders, BOMs, routings, work centers, QC inspections |
| **MRP** | Material requirements planning, planned orders, BOM explosion, firming |
| **Purchasing** | Vendor management, purchase orders, receiving, cost tracking |
| **Printers & Fleet** | Multi-brand printer management, MQTT monitoring, maintenance scheduling |
| **Accounting** | General ledger, journal entries, trial balance, COGS, tax reporting |

See the full [Feature Catalog](FEATURE-CATALOG.md) for details.

## Quick Start

=== "Docker (recommended)"

    ```bash
    git clone https://github.com/Blb3D/filaops.git
    cd filaops
    cp backend/.env.example .env
    docker compose up -d
    ```

    Open [http://localhost](http://localhost) and create your admin account.

=== "Manual"

    ```bash
    # Backend
    cd backend
    python -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    alembic upgrade head
    uvicorn app.main:app --reload

    # Frontend (separate terminal)
    cd frontend
    npm install && npm run dev
    ```

## Community

- **GitHub**: [Blb3D/filaops](https://github.com/Blb3D/filaops) — report issues, contribute, star the project
- **License**: [BSL 1.1](https://github.com/Blb3D/filaops/blob/main/LICENSE) — free for non-production use, converts to open source after 4 years
