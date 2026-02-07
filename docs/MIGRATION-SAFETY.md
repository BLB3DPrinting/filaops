# Migration Safety Guide

Pre-deployment checklist and rollback procedures for FilaOps database migrations.

## Pre-Deployment Checklist

### Before Running Migrations

1. **Backup the database**
   ```bash
   pg_dump -Fc filaops > filaops_backup_$(date +%Y%m%d_%H%M%S).dump
   ```

2. **Verify the current migration state**
   ```bash
   cd backend
   alembic current
   ```

3. **Review pending migrations**
   ```bash
   alembic history --verbose
   ```

4. **Test migrations against a copy**
   ```bash
   createdb filaops_staging
   pg_dump filaops | psql filaops_staging
   DB_NAME=filaops_staging alembic upgrade head
   ```

5. **Check for destructive operations** — Review migration files for:
   - `op.drop_table()` or `op.drop_column()`
   - `op.alter_column()` with type changes
   - Any raw SQL `op.execute()` statements

### During Deployment

1. Put the application in maintenance mode (stop accepting new requests)
2. Run the migration: `alembic upgrade head`
3. Verify the migration applied: `alembic current`
4. Start the application and verify the health check: `curl http://localhost:8000/health`
5. Spot-check critical workflows (login, create order, view dashboard)

## Rollback Procedures

### Downgrading Migrations

```bash
# Roll back one migration
alembic downgrade -1

# Roll back to a specific revision
alembic downgrade <revision_id>
```

### Full Database Restore

If a migration causes data loss or corruption:

```bash
# Stop the application
docker compose stop backend

# Restore from backup
pg_restore -d filaops --clean filaops_backup_YYYYMMDD_HHMMSS.dump

# Restart
docker compose start backend
```

### Docker Compose Rollback

```bash
# Stop current version
docker compose down

# Check out the previous release tag
git checkout v3.0.1

# Rebuild and restart
docker compose up -d --build
```

## Version Verification

After deployment, verify all version references match:

| Location | Command |
|----------|---------|
| Backend VERSION file | `cat backend/VERSION` |
| Settings runtime | `curl http://localhost:8000/health \| jq .version` |
| Frontend | Check the browser console or about page |
| Alembic head | `cd backend && alembic current` |

## Backup Schedule Recommendations

| Environment | Frequency | Retention |
|-------------|-----------|-----------|
| Production | Daily (automated) | 30 days |
| Staging | Before each deployment | 7 days |
| Development | As needed | N/A |

For automated backups, use `pg_dump` in a cron job or Docker healthcheck script.
