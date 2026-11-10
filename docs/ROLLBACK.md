# FilaOps Rollback Procedures

## Quick Reference

| Scenario | Command |
|----------|---------|
| Rollback last migration | `alembic downgrade -1` |
| Rollback to specific revision | `alembic downgrade <revision>` |
| Docker rollback | `docker-compose down && git checkout <tag> && docker-compose up --build` |

## 1. Application-Only Rollback (No Migration Changes)

If the deployment failed but no database migrations were involved:

```bash
# Docker deployment
docker-compose down
git checkout v3.1.1  # Previous known-good tag
docker-compose up --build -d

# Manual deployment
git checkout v3.1.1
cd backend && pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 2. Migration Rollback

> Migration 105 (release 4.4.0) repairs data and has no downgrade: `alembic downgrade` past it leaves the
> repaired values in place. To go back from 4.4.0, restore your backup (section 3).

If a migration failed or caused issues:

```bash
# Check current revision
alembic current

# View migration history
alembic history

# Rollback one migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade abc123def456

# Verify rollback
alembic current
```

**IMPORTANT:** Always backup the database before running migrations:
```bash
pg_dump -h localhost -U filaops filaops > backup_$(date +%Y%m%d_%H%M%S).sql
```

## 3. Emergency Database Restore

If data corruption occurred, or you are going back to a version from before a
migration that has no downgrade. PostgreSQL has to stay running for the
restore, so stop only the backend:

```bash
# Stop the backend so nothing writes during the restore. Leave the database running.
docker compose stop backend

# Drop and recreate the database (use your own DB_USER and DB_NAME if you changed them)
docker exec filaops-db psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS filaops;"
docker exec filaops-db psql -U postgres -d postgres -c "CREATE DATABASE filaops;"

# Restore from the backup file
docker cp ./filaops_before_upgrade.sql filaops-db:/tmp/restore.sql
docker exec filaops-db psql -U postgres -d filaops -f /tmp/restore.sql
docker exec filaops-db rm /tmp/restore.sql

# Going back a version: check out the previous tag before restarting
git checkout <previous tag>

# Rebuild and restart
docker compose up -d --build
```

These are the steps in section 6.1 of
[Backup and Recovery](BACKUP-AND-RECOVERY.md), which also covers custom-format
dumps. Manual install: stop the backend, then run the same `psql` commands
against your own PostgreSQL server, connecting as the database user FilaOps
uses so that it owns the restored tables.

## 4. Docker Compose Full Rollback

```bash
# Stop current deployment
docker-compose down

# Remove volumes if data is corrupted (DESTRUCTIVE). This deletes the
# database AND, on 4.3.0+, the filaops_config volume: restore both from
# backup afterwards (see BACKUP-AND-RECOVERY.md), or stored secrets such as
# the AI API key have to be entered again.
docker-compose down -v

# Checkout previous version
git checkout v3.1.1

# Rebuild and start
docker-compose up --build -d

# Verify health
curl http://localhost:8000/health
```

## 5. Handling Coupled Migration + Server Start

The current Dockerfile runs `alembic upgrade head && uvicorn`. If migration fails:

1. Check logs: `docker-compose logs backend`
2. Enter container: `docker-compose run backend bash`
3. Manually rollback: `alembic downgrade -1`
4. Exit and restart: `docker-compose up -d`

## Pre-Deployment Checklist

- [ ] Database backup taken
- [ ] Previous version tag noted
- [ ] Rollback tested in staging
- [ ] Team notified of deployment window
