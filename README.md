# FilaOps

Open-source ERP for 3D print farm operations. Manage inventory, production orders, BOMs, MRP, sales orders, purchasing, and GL accounting in one system built for additive manufacturing.

## Prerequisites

- **Python** 3.11+
- **Node.js** 18+ (with npm)
- **PostgreSQL** 16+
- **Docker** (optional, for containerized deployment)

## Quick Start (Docker)

The fastest way to get FilaOps running:

```bash
# Clone the repository
git clone https://github.com/Blb3D/filaops.git
cd filaops

# Start all services (DB, backend, frontend)
docker compose up -d

# Open http://localhost in your browser
# Create your admin account on first visit
```

To customize settings, copy `.env.example` to `.env` and edit before starting.

## Quick Start (Manual)

### Backend

```bash
cd backend
python -m venv venv
# Windows
.\venv\Scripts\Activate
# Linux/Mac
source venv/bin/activate

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

FilaOps requires PostgreSQL 16+. Create a database and configure `backend/.env`:

```ini
DB_HOST=localhost
DB_PORT=5432
DB_NAME=filaops
DB_USER=postgres
DB_PASSWORD=your_password
```

Or use a full connection string:

```ini
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/filaops
```

## Features

37 core features across 8 modules:

- **Sales** - Quotes, sales orders, fulfillment tracking, blocking issues
- **Inventory** - Multi-location tracking, transactions, cycle counting, spool management
- **Manufacturing** - Production orders, BOMs, routings, work centers, scrap tracking
- **Purchasing** - Purchase orders, receiving, vendor management
- **MRP** - Demand calculation, supply netting, planned order generation
- **Accounting** - Chart of accounts, journal entries, GL reporting, period close
- **Traceability** - Lot tracking, serial numbers, material consumption history
- **Printing** - MQTT printer monitoring, print job tracking, resource scheduling

See [Feature Catalog](docs/FEATURE-CATALOG.md) for the complete list.

## Project Structure

```text
backend/
  app/
    api/v1/endpoints/   # FastAPI route handlers
    models/             # SQLAlchemy models
    services/           # Business logic
    core/               # Config, security, UOM
  alembic/              # Database migrations
  tests/                # pytest unit + integration tests
frontend/
  src/
    components/         # React components
    pages/              # Page-level views
    services/           # API client
```

## Testing

```bash
cd backend
pytest tests/ -v
```

## Troubleshooting

**Frontend can't connect to backend**
- Ensure `VITE_API_URL` matches the backend URL (default: `http://localhost:8000`)
- If accessing remotely, set `VITE_API_URL=http://<server-ip>:8000` and rebuild the frontend
- Check that CORS is configured: set `ALLOWED_ORIGINS` in `backend/.env`

**Database connection errors**
- Verify PostgreSQL is running: `pg_isready -h localhost -p 5432`
- Check credentials in `backend/.env` match your PostgreSQL setup
- Ensure the database exists: `createdb filaops`

**Migration errors**
- Run `alembic upgrade head` from the `backend/` directory
- If migrations fail, check `alembic/versions/` for the latest revision
- For a fresh start: drop and recreate the database, then re-run migrations

**Docker issues**
- If containers fail to start, check logs: `docker compose logs backend`
- Ensure ports 80, 8000, and 5432 are not already in use
- On first run, the migrate container must complete before the backend starts

## Documentation

- [User Guide](docs/user-guide/index.md) — Module-by-module usage guide
- [Feature Catalog](docs/FEATURE-CATALOG.md) — Complete feature list
- [Schema Reference](docs/SCHEMA-REFERENCE.md) — Database model documentation
- [Migration Safety](docs/MIGRATION-SAFETY.md) — Pre-deployment checklist and rollback procedures
- [Contributing](CONTRIBUTING.md) — Development setup and PR guidelines

## License

[Business Source License 1.1](LICENSE) - Free for non-competing use. Converts to Apache 2.0 on December 5, 2029.
