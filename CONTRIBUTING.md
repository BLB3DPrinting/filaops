# Contributing to FilaOps

Thanks for your interest in contributing to FilaOps! This guide covers everything you need to get started.

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 16+

### Backend

```bash
cd backend
python -m venv venv

# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Windows (cmd.exe)
venv\Scripts\activate.bat
# Linux/Mac
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env with your database credentials

alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

API docs are available at `http://localhost:8000/docs` when the backend is running.

## Code Style

### Python (Backend)

- Follow PEP 8
- Use type hints for function signatures
- Service functions: standalone functions with `db: Session` as first parameter
- Keep business logic in `app/services/`, not in endpoint files

### JavaScript (Frontend)

- React functional components with hooks
- Tailwind CSS for styling
- ESLint config in `frontend/eslint.config.js`

## Testing

### Running Tests

```bash
cd backend
pytest tests/ -v              # Full suite
pytest tests/ -x -q --tb=short  # Quick run, stop on first failure
pytest tests/services/         # Service tests only
pytest tests/endpoints/        # Endpoint tests only
```

### Writing Tests

- Place service tests in `backend/tests/services/`
- Place endpoint tests in `backend/tests/endpoints/`
- Use the `db` fixture for database sessions (auto-rolls back)
- Use `make_product`, `make_sales_order`, and other fixtures from `conftest.py`

## Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes and add tests
4. Run the test suite to confirm nothing breaks
5. Commit with a clear message following [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` new feature
   - `fix:` bug fix
   - `refactor:` code restructuring
   - `test:` adding or updating tests
   - `docs:` documentation only
6. Push to your fork and open a Pull Request

### PR Guidelines

- Keep PRs focused — one logical change per PR
- Include a description of what changed and why
- Link to any related issues
- Ensure CI passes (backend tests + frontend build)

## Reporting Issues

Use [GitHub Issues](https://github.com/Blb3D/filaops/issues) with:

- Clear title describing the problem
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python/Node version, FilaOps version)

## Architecture Overview

```
backend/
  app/
    api/v1/endpoints/   # FastAPI route handlers (thin layer)
    services/           # Business logic (standalone functions)
    models/             # SQLAlchemy ORM models
    schemas/            # Pydantic request/response schemas
    core/               # Config, security, UOM
  migrations/           # Alembic database migrations
  tests/                # pytest test suite

frontend/
  src/
    components/         # Reusable React components
    pages/              # Page-level views
    modules/            # Feature modules (forms, etc.)
    lib/                # Utilities and hooks
```

Key pattern: endpoint files should be thin — call service functions for business logic, return responses.
