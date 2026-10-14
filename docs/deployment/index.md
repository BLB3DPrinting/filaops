# Deployment & Operations

Guides for deploying, configuring, and maintaining a FilaOps instance in production.

| Guide | Description |
|-------|-------------|
| **[Docker Compose](../DEPLOYMENT.md)** | Full production deployment with Docker Compose — architecture, environment variables, troubleshooting |
| **[Upgrading FilaOps](../UPGRADE.md)** | Upgrade to the current release from any earlier version, and what changed |
| **[Email Setup](../EMAIL_CONFIGURATION.md)** | Configure SMTP for password resets and notifications |
| **[Backup & Recovery](../BACKUP-AND-RECOVERY.md)** | Database backups, file uploads, Docker volume strategies, disaster recovery |
| **[Migration Safety](../MIGRATION-SAFETY.md)** | Pre-deployment checklist and rollback procedures for database migrations |
| **[Rollback](../ROLLBACK.md)** | How to roll back to a previous version |
| **[Versioning](../VERSIONING.md)** | Version numbering scheme and release process |

## Architecture Overview

```mermaid
graph TD
    Internet["🌐 Internet"] -->|"Port 80"| Frontend
    Frontend["<b>frontend</b><br/>nginx:alpine<br/>React SPA"] -->|"/api proxy"| Backend
    Internet -->|"Port 8000"| Backend
    Backend["<b>backend</b><br/>python:3.11-slim<br/>FastAPI + Uvicorn"] --> DB
    Migrate["<b>migrate</b><br/>alembic upgrade head"] --> DB
    DB["<b>db</b><br/>postgres:16<br/>Port 5432"] --> Volume["📁 filaops_pgdata<br/>(named volume)"]

    style Frontend fill:#1565C0,color:#fff,stroke:#0D47A1
    style Backend fill:#1565C0,color:#fff,stroke:#0D47A1
    style DB fill:#F57C00,color:#fff,stroke:#E65100
    style Migrate fill:#455A64,color:#fff,stroke:#37474F
    style Volume fill:#263238,color:#fff,stroke:#37474F
    style Internet fill:#0D47A1,color:#fff,stroke:#0D47A1
```
