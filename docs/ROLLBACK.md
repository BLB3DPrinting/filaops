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

**IMPORTANT:** Always back up the database before running migrations, the way
[step 1 of Upgrading FilaOps](UPGRADE.md#1-back-up) does.

## 3. Emergency Database Restore

If data corruption occurred, or you are going back to a version from before a
migration that has no downgrade. PostgreSQL has to stay running for the
restore, so only the backend is stopped. The backup is restored into a new
database first, and the live database is replaced only after that worked, so
a bad backup file cannot leave you with nothing.

These steps are for a Docker install. Run them one at a time and read what
each prints before going on. Use PowerShell, Command Prompt, or a Linux or
macOS shell. Git Bash on Windows rewrites the `/tmp/...` paths, so the
commands fail there.

If you changed `DB_USER` or `DB_NAME`: put your user after `-U`, and your
database name in place of `filaops` in the two `ALTER DATABASE` commands of
step 4. Leave everything else as written. `-d postgres` is PostgreSQL's own
maintenance database, `filaops-db` is the container, and `filaops_restore` and
`filaops_after_upgrade` are temporary names.

**1. Stop the backend,** so nothing writes during the restore. Leave the
database running.

```bash
docker compose stop backend
```

**2. Copy your backup into the database container.** Use your own file name
if it differs. If this fails, stop here: nothing has changed.

```bash
docker cp ./filaops_before_upgrade.sql filaops-db:/tmp/restore.sql
```

**3. Restore it into a new, empty database.** `psql` stops at the first error.

```bash
docker exec filaops-db psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS filaops_restore;"
docker exec filaops-db psql -U postgres -d postgres -c "CREATE DATABASE filaops_restore;"
docker exec filaops-db psql -U postgres -d filaops_restore -v ON_ERROR_STOP=1 -q -f /tmp/restore.sql
```

If the last command printed a line with `ERROR`, stop here. The live database
is untouched, and the backup file is not usable as it is. `docker compose
start backend` brings the system back as it was while you sort the file out.

**4. Put the restored database in place.** Only when step 3 finished without
an error. The database being replaced is kept as `filaops_after_upgrade`.

```bash
docker exec filaops-db psql -U postgres -d postgres -c "ALTER DATABASE filaops RENAME TO filaops_after_upgrade;"
docker exec filaops-db psql -U postgres -d postgres -c "ALTER DATABASE filaops_restore RENAME TO filaops;"
docker exec filaops-db rm /tmp/restore.sql
```

Each of the first two must print `ALTER DATABASE`. If either prints `ERROR`,
stop, and do not go on to steps 5 and 6. If it says `filaops_after_upgrade`
already exists, a copy is left over from an earlier rollback: remove it with
the command at the end of this section, then run step 4 again.

**5. Going back a version: check out the version you were on.** For example:

```bash
git checkout v4.3.2
```

If Git refuses, sort that out before step 6. Rebuilding while still on the
newer version would upgrade the restored database again.

**6. Rebuild and restart.**

```bash
docker compose up -d --build
```

When you have checked that everything is back, remove the kept copy:

```bash
docker exec filaops-db psql -U postgres -d postgres -c "DROP DATABASE filaops_after_upgrade;"
```

**Never start an older version against a database that a newer version has
upgraded.** Its migrate step stops with a "DATABASE MIGRATION MISMATCH"
message that suggests removing the database volume. Do not do that: it deletes
all your data. Restore the backup with the steps above instead.

**Manual install.** The database steps are the same, run with your own `psql`
in place of `docker exec filaops-db psql`, with no `docker cp`, and with the
path to your backup file after `-f`. Connect as the database user FilaOps
uses, so that it owns the restored tables; that user needs the right to create
databases. Close anything else that is connected to the database first (a
second backend, pgAdmin): a database cannot be renamed while something is
connected to it. Then check out the version you were on and install and
restart it the way you did before, as in the manual steps of
[Upgrading FilaOps](UPGRADE.md#upgrade).

Section 6 of [Backup and Recovery](BACKUP-AND-RECOVERY.md) covers
custom-format dumps.

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
