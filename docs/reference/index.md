# Developer Reference

Technical reference for developers contributing to or integrating with FilaOps.

| Reference | Description |
|-----------|-------------|
| **[API Reference](../API-REFERENCE.md)** | Complete endpoint documentation — 418 endpoints across 48 routers |
| **[API Conventions](../API-CONVENTIONS.md)** | REST patterns, response envelopes, pagination, error formats |
| **[Database Schema](../SCHEMA-REFERENCE.md)** | 52 SQLAlchemy models with columns, constraints, and relationships |
| **[UI Components](../UI-COMPONENTS.md)** | 65+ React components across 31 pages |
| **[Feature Catalog](../FEATURE-CATALOG.md)** | 37 core features with implementation status |
| **[Migrations Log](../MIGRATIONS-LOG.md)** | Chronological history of all 35 database migrations |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16 |
| **Frontend** | React 19, Vite, Tailwind CSS, React Router |
| **Infrastructure** | Docker, nginx, GitHub Actions CI/CD |
| **Testing** | pytest (backend), Vitest (frontend), Playwright (E2E) |
