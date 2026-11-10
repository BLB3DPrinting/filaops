# FilaOps Backup and Recovery

> Comprehensive guide for backing up and restoring a FilaOps ERP deployment.
> Covers the PostgreSQL database, file uploads, and Docker volume strategies.

## Overview

A complete FilaOps backup requires **three components**:

| Component | Location | Contains |
|-----------|----------|----------|
| **PostgreSQL database** | Docker volume `filaops_pgdata` | All ERP data (orders, inventory, BOMs, users, etc.) |
| **Uploads directory** | `./uploads` on host (mounted at `/app/uploads`) | PO documents, product images, attachments |
| **Instance config** | Docker volume `filaops_config` (mounted at `/var/lib/filaops/config`) | `install_uuid`, the root of the key that encrypts stored secrets such as the AI API key |

Back them up together to ensure a consistent restore. A database backup without uploads will leave file references pointing to missing files, and a database restored without its `install_uuid` cannot decrypt stored secrets (they have to be entered again). Treat the config backup like a password: anyone holding it and a database dump can decrypt those secrets.

---

## 1. Manual Database Backup with pg_dump

### Option A: Plain SQL Dump

Produces a human-readable `.sql` file. Good for smaller databases and simple restores.

```bash
# From the Docker host — dump via the running db container
docker exec filaops-db pg_dump \
  -U postgres \
  -d filaops \
  --no-owner \
  --no-privileges \
  > filaops_$(date +%Y%m%d_%H%M%S).sql
```

On Windows (PowerShell), write the dump inside the database container and
copy it out. Do not redirect or pipe `pg_dump` output there (`>` or
`| Out-File`): Windows PowerShell 5.1 re-encodes it, and the file then either
cannot be restored or has non-English characters corrupted.

```powershell
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
docker exec filaops-db pg_dump -U postgres -d filaops --no-owner --no-privileges -f /tmp/filaops_backup.sql
if ($LASTEXITCODE -eq 0) { docker cp filaops-db:/tmp/filaops_backup.sql "filaops_$timestamp.sql" }
if ($LASTEXITCODE -eq 0) { Get-Content "filaops_$timestamp.sql" -Tail 5 }
```

Each step runs only if the one before it worked. It ends by printing the last
lines of the new file, which must include `PostgreSQL database dump complete`.
If nothing is printed, a step failed: read the error above it. When the lines
are right, remove the copy left inside the container:

```powershell
docker exec filaops-db rm /tmp/filaops_backup.sql
```

### Option B: Custom Format Dump (Recommended)

Produces a compressed binary archive. Supports parallel restore and selective table restore.

```bash
docker exec filaops-db pg_dump \
  -U postgres \
  -d filaops \
  --format=custom \
  --compress=6 \
  --no-owner \
  --no-privileges \
  --file=/tmp/filaops_backup.dump

# Copy from container to host
docker cp filaops-db:/tmp/filaops_backup.dump \
  ./backups/filaops_$(date +%Y%m%d_%H%M%S).dump
```

### Verifying a Dump File

```bash
# List the contents of a custom-format dump (does not restore anything)
pg_restore --list ./backups/filaops_20260207_120000.dump | head -30
```

This shows that the dump opens and what it holds. It does not prove the data
is all there: a dump cut short after its list of contents still passes.

---

## 2. Automated Backups

### Linux: cron

Create a backup script at `/opt/filaops/backup.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/opt/filaops/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_DUMP="$BACKUP_DIR/db_$TIMESTAMP.dump"
UPLOADS_TAR="$BACKUP_DIR/uploads_$TIMESTAMP.tar.gz"

mkdir -p "$BACKUP_DIR"

# Database backup (custom format)
docker exec filaops-db pg_dump \
  -U postgres -d filaops \
  --format=custom --compress=6 \
  --no-owner --no-privileges \
  --file=/tmp/filaops_backup.dump

docker cp filaops-db:/tmp/filaops_backup.dump "$DB_DUMP"
docker exec filaops-db rm /tmp/filaops_backup.dump

# Uploads backup
tar -czf "$UPLOADS_TAR" -C /opt/filaops uploads/

echo "[$(date)] Backup complete: $DB_DUMP, $UPLOADS_TAR"
```

Add to crontab (`crontab -e`):

```cron
# Daily at 02:00 AM
0 2 * * * /opt/filaops/backup.sh >> /var/log/filaops-backup.log 2>&1
```

### Windows: Scheduled Task (PowerShell)

Create `C:\filaops\backup.ps1`:

```powershell
$BackupDir = "C:\filaops\backups"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

# Database backup
docker exec filaops-db pg_dump -U postgres -d filaops `
  --format=custom --compress=6 --no-owner --no-privileges `
  --file=/tmp/filaops_backup.dump

docker cp filaops-db:/tmp/filaops_backup.dump "$BackupDir\db_$Timestamp.dump"
docker exec filaops-db rm /tmp/filaops_backup.dump

# Uploads backup
Compress-Archive -Path "C:\filaops\uploads\*" -DestinationPath "$BackupDir\uploads_$Timestamp.zip"

Write-Host "Backup complete: $Timestamp"
```

Register a scheduled task:

```powershell
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\filaops\backup.ps1"
$Trigger = New-ScheduledTaskTrigger -Daily -At 2:00AM
Register-ScheduledTask -TaskName "FilaOps Backup" -Action $Action -Trigger $Trigger `
  -Description "Daily FilaOps database and uploads backup"
```

---

## 3. Backup Retention Policy

Recommended rotation schedule:

| Tier | Keep | Frequency | Example |
|------|------|-----------|---------|
| Daily | 7 days | Every night | `db_20260201` through `db_20260207` |
| Weekly | 4 weeks | Sunday backup | `db_20260202`, `db_20260209`, ... |
| Monthly | 12 months | 1st of month | `db_20260201`, `db_20260301`, ... |

### Automated Cleanup (Linux)

Add to the end of `backup.sh`:

```bash
# Remove daily backups older than 7 days
find "$BACKUP_DIR" -name "db_*.dump" -mtime +7 -delete
find "$BACKUP_DIR" -name "uploads_*.tar.gz" -mtime +7 -delete

# Weekly and monthly backups should be copied to a separate directory
# or off-site storage before daily cleanup runs.
```

### Automated Cleanup (PowerShell)

Add to the end of `backup.ps1`:

```powershell
# Remove backups older than 7 days
Get-ChildItem "$BackupDir\db_*.dump" |
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
  Remove-Item -Force

Get-ChildItem "$BackupDir\uploads_*.zip" |
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } |
  Remove-Item -Force
```

---

## 4. Backing Up the Uploads Directory

The uploads directory (`./uploads` on host, `/app/uploads` in container) stores PO documents, product images, and other file attachments.

### Using rsync (Linux, incremental)

```bash
# Mirror uploads to a backup location (fast for subsequent runs)
rsync -av --delete ./uploads/ /mnt/backup/filaops-uploads/
```

### Using tar (full archive)

```bash
tar -czf uploads_$(date +%Y%m%d_%H%M%S).tar.gz -C . uploads/
```

### Using Compress-Archive (Windows)

```powershell
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
Compress-Archive -Path ".\uploads\*" -DestinationPath ".\backups\uploads_$Timestamp.zip"
```

---

## 5. Docker Volume Backup

If you prefer to back up the raw PostgreSQL data directory from the Docker volume rather than using `pg_dump`, you can export the entire volume. This captures everything including WAL files and configuration.

```bash
# Stop the database to ensure consistency
docker compose stop db

# Export the volume as a tar archive
docker run --rm \
  -v filaops_pgdata:/data \
  -v $(pwd)/backups:/backup \
  alpine tar -czf /backup/pgdata_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .

# Restart the database
docker compose start db
```

**Note:** This method requires stopping the database, causing downtime. For zero-downtime backups, use `pg_dump` (Section 1) instead.

---

## 6. Recovery Procedures

### 6.1 Full Database Restore from pg_dump

#### From a Plain SQL Dump

Follow section 3 of [Rollback](ROLLBACK.md#3-emergency-database-restore). It
copies the dump in, restores it into a new database, checks that the data
arrived, and replaces the live database only after that worked.

#### From a Custom Format Dump

Follow section 3 of [Rollback](ROLLBACK.md#3-emergency-database-restore), with
three changes:

- In step 2, copy the dump to `/tmp/restore.dump` and skip the `tail` command.
  A custom-format dump has no text marker to look for.
- In step 3, use the restore command below in place of the `psql ... -f` one.
  It must end by printing `restore complete`. If it prints an error, or
  nothing, stop. Put your own user after `-U` in it if you changed `DB_USER`.
- In step 4, the file to remove is `/tmp/restore.dump`.

```bash
docker exec filaops-db sh -c "pg_restore -U postgres -d filaops_restore --no-owner --no-privileges --exit-on-error /tmp/restore.dump && echo restore complete"
```

`pg_restore --list` is not a check of the dump. It reads the list of contents
at the start of the file, so a dump cut short further on still passes it.

### 6.2 Point-in-Time Recovery (PITR) Overview

For production deployments that need recovery to a specific moment in time (e.g., "restore to 10 minutes before the accidental delete"), PostgreSQL supports WAL (Write-Ahead Log) archiving.

**Requirements:**

1. Enable WAL archiving in `postgresql.conf`:
   ```
   wal_level = replica
   archive_mode = on
   archive_command = 'cp %p /var/lib/postgresql/wal_archive/%f'
   ```

2. Take a base backup periodically:
   ```bash
   pg_basebackup -U postgres -D /var/lib/postgresql/basebackup -Ft -z -P
   ```

3. To recover to a specific time, configure `recovery_target_time` in `postgresql.conf` and start PostgreSQL in recovery mode.

**Note:** PITR is an advanced topic. For most single-server FilaOps deployments, regular `pg_dump` backups (Section 1-2) provide sufficient protection. PITR is recommended when you need sub-minute recovery granularity for production workloads. See the [PostgreSQL PITR documentation](https://www.postgresql.org/docs/16/continuous-archiving.html) for full details.

### 6.3 Restoring the Uploads Directory

```bash
# From a tar archive
tar -xzf uploads_20260207_120000.tar.gz -C /opt/filaops/

# From rsync backup
rsync -av /mnt/backup/filaops-uploads/ /opt/filaops/uploads/

# Ownership: the backend container gives files in /app/uploads to its
# appuser at startup, so restored files owned by another user are fine.
```

On Windows (from zip):

```powershell
Expand-Archive -Path ".\backups\uploads_20260207_120000.zip" -DestinationPath ".\uploads" -Force
```

### 6.4 Full Disaster Recovery

Complete restore from scratch when the entire server is lost.

```bash
# 1. Install Docker and Docker Compose on the new server

# 2. Clone the repository (or copy docker-compose.yml and .env)
git clone https://github.com/BLB3DPrinting/filaops.git
cd filaops

# 3. Copy your .env file with DB credentials
cp /path/to/backup/.env .env

# 4. Start only the database
docker compose up -d db
docker compose exec db pg_isready -U postgres  # wait until ready

# 5. Restore the database
docker cp /path/to/backup/filaops_20260207_120000.dump filaops-db:/tmp/restore.dump
docker exec filaops-db pg_restore \
  -U postgres \
  -d filaops \
  --no-owner \
  --no-privileges \
  --clean \
  --if-exists \
  /tmp/restore.dump
docker exec filaops-db rm /tmp/restore.dump

# 6. Restore uploads
tar -xzf /path/to/backup/uploads_20260207_120000.tar.gz -C .

# 7. Start all services (migrate will run automatically but is a no-op if DB is current)
docker compose up -d

# 8. Verify
curl http://localhost:8000/health
```

If `pg_restore` in step 5 prints an error, stop there. The dump is incomplete,
and starting the services would run them on a partly restored database.

---

## 7. Testing Backups

Backups are only valuable if they can be restored. Test your backups regularly.

### Quick Integrity Check

```bash
# Check that a custom-format dump opens and its list of contents is readable
pg_restore --list ./backups/filaops_20260207_120000.dump > /dev/null && echo "OK" || echo "CORRUPT"
```

"OK" here is not proof that the dump is complete: a dump cut short after its
list of contents still passes. Only a restore proves that, as in the test
below.

### Full Restore Test (Isolated)

Spin up a temporary PostgreSQL container, restore into it, and run a basic query:

```bash
# Start a throwaway Postgres container
docker run -d --name filaops-restore-test \
  -e POSTGRES_PASSWORD=testpass \
  -e POSTGRES_DB=filaops_test \
  postgres:16

# Wait for it to be ready
sleep 5

# Restore the backup
docker cp ./backups/filaops_20260207_120000.dump filaops-restore-test:/tmp/restore.dump
docker exec filaops-restore-test pg_restore \
  -U postgres \
  -d filaops_test \
  --no-owner \
  --no-privileges \
  --exit-on-error \
  /tmp/restore.dump

# Verify core tables exist and have data
docker exec filaops-restore-test psql -U postgres -d filaops_test -c "
  SELECT
    (SELECT count(*) FROM products) AS products,
    (SELECT count(*) FROM users) AS users,
    (SELECT count(*) FROM sales_orders) AS sales_orders,
    (SELECT count(*) FROM production_orders) AS production_orders;
"

# Clean up
docker rm -f filaops-restore-test
```

If `pg_restore` printed no error and the counts match your expectations, the
backup is valid. An error from `pg_restore` means the dump is incomplete,
whatever the counts say.

---

## 8. Quick Reference

These one-liners are for a bash-style shell (Linux, macOS, WSL). In Windows
PowerShell, `>` and `<` do not behave the same way: use the forms in sections
1 and 6.1.

### Backup Commands

| Task | Command |
|------|---------|
| DB dump (SQL) | `docker exec filaops-db pg_dump -U postgres -d filaops > backup.sql` |
| DB dump (custom) | `docker exec filaops-db pg_dump -U postgres -d filaops -Fc --compress=6 -f /tmp/b.dump` |
| Copy dump to host | `docker cp filaops-db:/tmp/b.dump ./backups/` |
| Uploads tar | `tar -czf uploads_backup.tar.gz -C . uploads/` |
| Docker volume export | `docker run --rm -v filaops_pgdata:/data -v $(pwd):/bk alpine tar -czf /bk/pgdata.tar.gz -C /data .` |
| Config volume export | `docker run --rm -v filaops_config:/data -v $(pwd):/bk alpine tar -czf /bk/config.tar.gz -C /data .` |

### Restore Commands

| Task | Command |
|------|---------|
| Restore SQL dump | See section 6.1: restore into a new database, then swap it in |
| Restore custom dump | See section 6.1: restore into a new database, then swap it in |
| Restore uploads | `tar -xzf uploads_backup.tar.gz -C .` |
| Restore config volume (backend stopped) | `docker run --rm -v filaops_config:/data -v $(pwd):/bk alpine tar -xzf /bk/config.tar.gz -C /data` |
| Full restart | `docker compose down && docker compose up -d` |

### Checklist

- [ ] Database dump runs daily without errors
- [ ] Uploads directory is included in backups
- [ ] `filaops_config` volume is included in backups and stored as securely as the database
- [ ] Backups are stored off-site (cloud storage, remote server)
- [ ] Retention policy removes old backups automatically
- [ ] Restore test performed at least once per quarter
- [ ] `.env` file backed up separately (contains DB credentials)

---

*Last updated: 2026-02-07*
*Applies to FilaOps Core (Open Source)*
