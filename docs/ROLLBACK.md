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
git checkout v3.0.0  # Previous known-good tag
docker-compose up --build -d

# Manual deployment
git checkout v3.0.0
cd backend && pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 2. Migration Rollback

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

If data corruption occurred:

```bash
# Stop all services
docker-compose down

# Restore from backup
psql -h localhost -U filaops filaops < backup_20260131_120000.sql

# Restart services
docker-compose up -d
```

## 4. Docker Compose Full Rollback

```bash
# Stop current deployment
docker-compose down

# Remove volumes if data is corrupted (DESTRUCTIVE)
docker-compose down -v

# Checkout previous version
git checkout v3.0.0

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
