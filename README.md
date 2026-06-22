# FilaOps

[![CI](https://github.com/Blb3DPrinting/filaops/actions/workflows/filaops-ci.yml/badge.svg)](https://github.com/Blb3DPrinting/filaops/actions/workflows/filaops-ci.yml)
[![CodeQL](https://github.com/Blb3DPrinting/filaops/actions/workflows/codeql.yml/badge.svg)](https://github.com/Blb3DPrinting/filaops/actions/workflows/codeql.yml)
[![License: BSL 1.1](https://img.shields.io/badge/License-BSL_1.1-blue.svg)](LICENSE)
[![Latest Release](https://img.shields.io/github/v/release/Blb3DPrinting/filaops)](https://github.com/Blb3D/filaops/releases/latest)

Open-source ERP for 3D print farms. Manage inventory, production, sales, purchasing, MRP, and accounting in one system built specifically for additive manufacturing.

**[Documentation](https://blb3dPrinting.github.io/filaops/)** | **[Release Notes](https://github.com/Blb3DPrinting/filaops/releases/latest)**

## Quick Start (Docker)

```bash
git clone https://github.com/Blb3D/filaops.git
cd filaops
cp backend/.env.example .env
# Generate secrets (required — production startup refuses to boot without these):
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env
echo "DB_PASSWORD=$(openssl rand -hex 24)" >> .env
docker compose up -d
# Open http://localhost — create your admin account on first visit
```

## Quick Start (Manual)

### Backend

```bash
cd backend
python -m venv venv
# Windows: .\venv\Scripts\Activate
# Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your database credentials
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Database

FilaOps requires PostgreSQL 16+. Configure `backend/.env`:

```ini
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/filaops
```

Or use individual variables:

```ini
DB_HOST=localhost
DB_PORT=5432
DB_NAME=filaops
DB_USER=postgres
DB_PASSWORD=your_password
```

## Features

48 core features across 8 modules:

### Sales & Customers

- Multi-line item quotes with per-line and customer discounts
- Sales orders with fulfillment tracking and price level auto-apply
- Invoice engine with PDF templates and payment recording
- Customer management with payment terms (COD, net-15, net-30) and credit limits
- Customer traceability profiles
- Suggest Prices tool for margin-based bulk pricing
- External order ingestion with operator notification inbox

### Inventory & Warehouse

- Multi-location inventory with transactions
- Spool management (filament tracking by weight)
- Cycle counting and inventory adjustments
- Low stock alerts with MRP-driven shortage detection
- Negative inventory approval workflow

### Manufacturing

- Production orders (draft > released > in progress > complete)
- Bill of Materials with multi-level cost rollup
- Duplicate item with inline BOM component swap (color variants)
- Variant matrix — bulk create color/material variants from template products
- Copy BOM to another product
- Routings and work centers with operation materials
- Machine overhead and scrap tracking

### Purchasing

- Purchase orders with receiving workflow
- Vendor management
- Quick reorder from low stock alerts

### MRP (Material Requirements Planning)

- Demand calculation from sales orders and production
- Supply netting against on-hand inventory
- Planned order generation for shortages
- Auto-trigger on order creation

### Accounting

- Chart of accounts and journal entries
- GL reporting and trial balance
- Period close

### Operations

- Command center dashboard
- Security audit
- Analytics
- Maintenance scheduling
- UOM conversions (12 standard units)

### System

- First-run setup wizard with admin account creation
- Multi-user with role-based access
- Password reset flow (SMTP or auto-approve)
- REST API (432 endpoints)
- Shipping and order event tracking

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | FastAPI, Python 3.11+, SQLAlchemy 2.0, Alembic |
| Frontend | React 19, Vite, Tailwind CSS |
| Database | PostgreSQL 16+ |
| Auth | httpOnly cookie-based JWT |
| Deployment | Docker Compose (nginx + uvicorn) |

## Project Structure

```text
backend/
  app/
    api/v1/endpoints/   # FastAPI route handlers
    models/             # SQLAlchemy models
    services/           # 56 focused service modules
    core/               # Config, security, UOM
  alembic/              # Database migrations
  tests/                # 95 test files, 80%+ coverage
frontend/
  src/
    components/         # Shared UI components + Storybook
    hooks/              # useApi, useCRUD
    pages/admin/        # Admin page views
```

## Testing

```bash
# Backend (95 test files, 80%+ coverage)
cd backend && pytest tests/ -v

# Frontend component tests
cd frontend && npm test
```

## Troubleshooting

### Frontend can't connect to backend

- Ensure `VITE_API_URL` matches the backend URL (default: `http://localhost:8000`)
- If accessing remotely, set `VITE_API_URL=http://<server-ip>:8000` and rebuild
- Check CORS: set `ALLOWED_ORIGINS` in `backend/.env`

### Database connection errors

- Verify PostgreSQL is running: `pg_isready -h localhost -p 5432`
- Check credentials in `backend/.env`
- Create the database if needed: `createdb filaops`

### Migration errors

- Run `alembic upgrade head` from `backend/`
- For a fresh start: drop and recreate the database, then re-run migrations

### Docker issues

- Check logs: `docker compose logs backend`
- Ensure ports 80, 8000, and 5432 are available
- The migrate container must complete before the backend starts

## Documentation

- **[Full Documentation](https://blb3dPrinting.github.io/filaops/)** — Deployment, configuration, and API reference
- [User Guide](docs/user-guide/index.md) — Module-by-module usage
- [Contributing](CONTRIBUTING.md) — Development setup and PR guidelines

## FilaOps PRO

Need B2B wholesale portals, advanced reporting, Shopify/QuickBooks integrations, or AI-powered scheduling? **FilaOps PRO** adds enterprise features on top of the same codebase — no migration, no separate install.

Coming soon at [blb3dprinting.com](https://blb3dprinting.com)

## License

[Business Source License 1.1](LICENSE) — Free for non-competing use. Converts to Apache 2.0 on December 5, 2029.
