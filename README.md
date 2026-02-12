# FilaOps

[![CI](https://github.com/Blb3D/filaops/actions/workflows/filaops-ci.yml/badge.svg)](https://github.com/Blb3D/filaops/actions/workflows/filaops-ci.yml)
[![CodeQL](https://github.com/Blb3D/filaops/actions/workflows/codeql.yml/badge.svg)](https://github.com/Blb3D/filaops/actions/workflows/codeql.yml)
[![License: BSL 1.1](https://img.shields.io/badge/License-BSL_1.1-blue.svg)](LICENSE)
[![Latest Release](https://img.shields.io/github/v/release/Blb3D/filaops)](https://github.com/Blb3D/filaops/releases/latest)

Open-source ERP for 3D print farms. Manage inventory, production, sales, purchasing, MRP, and accounting in one system built specifically for additive manufacturing.

**[Documentation](https://blb3d.github.io/filaops/)** | **[Release Notes](https://github.com/Blb3D/filaops/releases/latest)**

## Quick Start (Docker)

```bash
git clone https://github.com/Blb3D/filaops.git
cd filaops
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

37 core features across 8 modules:

### Sales & Customers

- Quotes with material cost rollup
- Sales orders with fulfillment tracking
- Customer management and traceability profiles
- Payment tracking

### Inventory & Warehouse

- Multi-location inventory with transactions
- Spool management (filament tracking by weight)
- Cycle counting and inventory adjustments
- Low stock alerts with MRP-driven shortage detection
- Negative inventory approval workflow

### Manufacturing

- Production orders (draft > released > in progress > complete)
- Bill of Materials with multi-level cost rollup
- Routings and work centers
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

- Multi-user with role-based access
- REST API (382 endpoints)
- Shipping and order event tracking

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | FastAPI, Python 3.11+, SQLAlchemy 2.0, Alembic |
| Frontend | React, Vite, Tailwind CSS |
| Database | PostgreSQL 16+ |
| Auth | httpOnly cookie-based JWT |
| Deployment | Docker Compose (nginx + uvicorn) |

## Project Structure

```text
backend/
  app/
    api/v1/endpoints/   # FastAPI route handlers
    models/             # SQLAlchemy models
    services/           # 20 focused service modules
    core/               # Config, security, UOM
  alembic/              # Database migrations
  tests/                # 71 test files, 80%+ coverage
frontend/
  src/
    components/         # Shared UI components + Storybook
    hooks/              # useApi, useCRUD
    pages/admin/        # Admin page views
```

## Testing

```bash
# Backend (71 test files, 80%+ coverage)
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

- **[Full Documentation](https://blb3d.github.io/filaops/)** — Deployment, configuration, and API reference
- [User Guide](docs/user-guide/index.md) — Module-by-module usage
- [Contributing](CONTRIBUTING.md) — Development setup and PR guidelines

## FilaOps PRO

Need B2B wholesale portals, advanced reporting, Shopify/QuickBooks integrations, or AI-powered scheduling? **FilaOps PRO** adds enterprise features on top of the same codebase — no migration, no separate install.

Coming soon at [blb3dprinting.com](https://blb3dprinting.com)

## License

[Business Source License 1.1](LICENSE) — Free for non-competing use. Converts to Apache 2.0 on December 5, 2029.
