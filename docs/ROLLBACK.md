# FilaOps Rollback Procedures

## Quick Reference

| Scenario | Command |
|----------|---------|
| Rollback last migration | `alembic downgrade -1` |
| Rollback to specific revision | `alembic downgrade <revision>` |
| Docker rollback | `docker-compose down && git checkout <tag> && docker-compose up --build` |

After an upgrade that changed the database, which 4.4.0 does, none of these is
enough alone: follow [section 3](#3-emergency-database-restore).
`alembic downgrade` does not undo migration 105, and an older version does not
start on the upgraded database.

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
database name in place of `filaops` in the `ALTER DATABASE` commands of step
4, including the one that puts the live database back. Leave everything else
as written. `-d postgres` is PostgreSQL's own
maintenance database, `filaops-db` is the container, and `filaops_restore` and
`filaops_after_upgrade` are temporary names. If a database of your own already
has one of those two names, use other temporary names throughout. If your
database is itself called `postgres`, use `-d template1` in step 4: a
database cannot be renamed from inside itself.

A database name that starts with a digit, or has capital letters, a hyphen, or
anything else beyond lower-case letters, digits and underscores, has to be
written in double quotes inside SQL, and each shell treats quotes inside quotes differently. For such a
name, do step 4 from inside `psql`, as described under it.

**1. Stop the backend,** so nothing writes during the restore. Leave the
database running.

```bash
docker compose stop backend
```

**2. Copy your backup into the database container,** and look at its last
lines there.

```bash
docker cp ./filaops_before_upgrade.sql filaops-db:/tmp/restore.sql
docker exec filaops-db tail -n 5 /tmp/restore.sql
```

Use your own file name if it differs. If the copy fails, stop here: nothing
has changed. The second command must show `PostgreSQL database dump complete`.
If it does not, the file is not a complete backup: stop here.

**3. Restore it into a new, empty database,** then check that data arrived.

```bash
docker exec filaops-db psql -U postgres -d postgres -c "CREATE DATABASE filaops_restore;"
docker exec filaops-db psql -U postgres -d filaops_restore -v ON_ERROR_STOP=1 -q -o /dev/null -f /tmp/restore.sql -c "\echo restore complete"
docker exec filaops-db psql -U postgres -d filaops_restore -c "SELECT version_num FROM alembic_version;"
```

- If the first command says `filaops_restore` already exists, it is left over
  from an earlier attempt at this step. Once you are sure that is what it is,
  remove it with
  `docker exec filaops-db psql -U postgres -d postgres -c "DROP DATABASE filaops_restore;"`
  and run the step again.
- The restore (the second command) stops at the first error. When it has
  worked through the whole file it prints one line, `restore complete`, and
  nothing else. If it prints anything else, or nothing at all, it did not
  finish.
- The last command must print a migration number: the one the backup was
  taken at (`104` for a backup from 4.3.2).

If the restore did not end with `restore complete`, or the last command
printed an error instead of a number, stop here. The live database is untouched, and the backup file is
not usable as it is. `docker compose start backend` brings the system back as
it was while you sort the file out.

**4. Put the restored database in place.** Only when step 3 passed both
checks. The database being replaced is kept as `filaops_after_upgrade`.

```bash
docker exec filaops-db psql -U postgres -d postgres -c "ALTER DATABASE filaops RENAME TO filaops_after_upgrade;"
docker exec filaops-db psql -U postgres -d postgres -c "ALTER DATABASE filaops_restore RENAME TO filaops;"
docker exec filaops-db rm /tmp/restore.sql
```

Each of the first two must print `ALTER DATABASE`. If either prints `ERROR`,
stop, and do not go on to steps 5 and 6.

- If the first says `filaops_after_upgrade` already exists, a copy is left
  over from an earlier rollback. Once you are sure you no longer need it,
  remove it with the `DROP DATABASE filaops_after_upgrade` command shown after
  step 6, then run step 4 again.
- If the first worked and the second failed, there is now no database called
  `filaops`. Put the live one back before anything else:
  `docker exec filaops-db psql -U postgres -d postgres -c "ALTER DATABASE filaops_after_upgrade RENAME TO filaops;"`

For a database name that needs double quotes, open `psql` in place of the
first two commands, type the two statements there with your name in double
quotes, and leave with `\q`. Then run the third command above.

```bash
docker exec -it filaops-db psql -U postgres -d postgres
```

```sql
ALTER DATABASE "My-Shop" RENAME TO filaops_after_upgrade;
ALTER DATABASE filaops_restore RENAME TO "My-Shop";
\q
```

If the second statement fails, put the live database back with
`ALTER DATABASE filaops_after_upgrade RENAME TO "My-Shop";` before leaving.

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

Then check that the version you went back to is running on the restored
data. This must show the migration number you saw in step 3:

```bash
docker compose exec backend alembic current
```

Log in and look at your recent records as well. When everything is back and
you no longer need the database that was replaced, remove the kept copy:

```bash
docker exec filaops-db psql -U postgres -d postgres -c "DROP DATABASE filaops_after_upgrade;"
```

**Never start an older version against a database that a newer version has
upgraded.** Its migrate step stops with a "DATABASE MIGRATION MISMATCH"
message that suggests removing the database volume. Do not do that: it deletes
all your data. Restore the backup with the steps above instead.

**Manual install.** The database steps are the same, run with your own `psql`
in place of `docker exec filaops-db psql`, and with the path to your backup
file after `-f`. Leave out the `docker cp` and `rm` lines.

- Give `psql` the host and port FilaOps itself uses (`DB_HOST` and `DB_PORT` in
  `backend/.env`, or the ones inside `DATABASE_URL` if you set that) with `-h`
  and `-p`, so that you are working on the same server as the application.
- Connect as the database user FilaOps uses, so that it owns the restored
  tables. That user needs the right to create databases.
- Before step 3, look at the last lines of a plain SQL backup file yourself.
  They must include `PostgreSQL database dump complete`.
- On Windows, leave out `-o /dev/null`. The restore then prints its normal
  output as well. It failed if any line contains `error`, or if the last line
  is not `restore complete`.
- A custom-format dump has no text marker. Restore it with one of the two
  commands below in place of the `psql ... -f` one, with your own host, port,
  user and file. Each prints `restore complete` only if `pg_restore`
  succeeded.
- Close anything else that is connected to the database first (a second
  backend, pgAdmin). A database cannot be renamed while something is connected
  to it.

A custom-format dump on a manual install, in bash or Command Prompt:

```bash
pg_restore -h HOST -p PORT -U USER -d filaops_restore --no-owner --no-privileges --exit-on-error BACKUP.dump && echo restore complete
```

In PowerShell:

```powershell
pg_restore -h HOST -p PORT -U USER -d filaops_restore --no-owner --no-privileges --exit-on-error BACKUP.dump; if ($LASTEXITCODE -eq 0) { "restore complete" }
```

Then check out the version you were on and install and restart it the way you
did before, as in the manual steps of [Upgrading FilaOps](UPGRADE.md#upgrade).

For a custom-format dump on a Docker install, section 6.1 of
[Backup and Recovery](BACKUP-AND-RECOVERY.md) gives the three changes to make
to these steps.

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
