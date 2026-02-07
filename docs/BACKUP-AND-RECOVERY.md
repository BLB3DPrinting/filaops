# FilaOps Backup and Recovery

> Comprehensive guide for backing up and restoring a FilaOps ERP deployment.
> Covers the PostgreSQL database, file uploads, and Docker volume strategies.

## Overview

A complete FilaOps backup requires **two components**:

| Component | Location | Contains |
|-----------|----------|----------|
| **PostgreSQL database** | Docker volume `filaops_pgdata` | All ERP data (orders, inventory, BOMs, users, etc.) |
| **Uploads directory** | `./uploads` on host (mounted at `/app/uploads`) | PO documents, product images, attachments |

Both must be backed up together to ensure a consistent restore. A database backup without uploads will leave file references pointing to missing files.

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

On Windows (PowerShell):

```powershell
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
docker exec filaops-db pg_dump -U postgres -d filaops --no-owner --no-privileges `
  | Out-File -Encoding utf8 "filaops_$timestamp.sql"
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

```bash
# Stop the backend to prevent writes during restore
docker compose stop backend

# Drop and recreate the database
docker exec filaops-db psql -U postgres -c "DROP DATABASE IF EXISTS filaops;"
docker exec filaops-db psql -U postgres -c "CREATE DATABASE filaops;"

# Restore from SQL file
docker cp ./backups/filaops_20260207_120000.sql filaops-db:/tmp/restore.sql
docker exec filaops-db psql -U postgres -d filaops -f /tmp/restore.sql
docker exec filaops-db rm /tmp/restore.sql

# Restart all services
docker compose up -d
```

#### From a Custom Format Dump

```bash
docker compose stop backend

docker exec filaops-db psql -U postgres -c "DROP DATABASE IF EXISTS filaops;"
docker exec filaops-db psql -U postgres -c "CREATE DATABASE filaops;"

docker cp ./backups/filaops_20260207_120000.dump filaops-db:/tmp/restore.dump
docker exec filaops-db pg_restore \
  -U postgres \
  -d filaops \
  --no-owner \
  --no-privileges \
  --clean \
  --if-exists \
  /tmp/restore.dump
docker exec filaops-db rm /tmp/restore.dump

docker compose up -d
```

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

# Ensure correct ownership (if running as non-root in container)
chown -R 1000:1000 /opt/filaops/uploads/
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
git clone https://github.com/Blb3D/filaops.git
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

---

## 7. Testing Backups

Backups are only valuable if they can be restored. Test your backups regularly.

### Quick Integrity Check

```bash
# Verify a custom-format dump is not corrupted
pg_restore --list ./backups/filaops_20260207_120000.dump > /dev/null && echo "OK" || echo "CORRUPT"
```

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

If the counts match your expectations, the backup is valid.

---

## 8. Quick Reference

### Backup Commands

| Task | Command |
|------|---------|
| DB dump (SQL) | `docker exec filaops-db pg_dump -U postgres -d filaops > backup.sql` |
| DB dump (custom) | `docker exec filaops-db pg_dump -U postgres -d filaops -Fc --compress=6 -f /tmp/b.dump` |
| Copy dump to host | `docker cp filaops-db:/tmp/b.dump ./backups/` |
| Uploads tar | `tar -czf uploads_backup.tar.gz -C . uploads/` |
| Docker volume export | `docker run --rm -v filaops_pgdata:/data -v $(pwd):/bk alpine tar -czf /bk/pgdata.tar.gz -C /data .` |

### Restore Commands

| Task | Command |
|------|---------|
| Restore SQL dump | `docker exec -i filaops-db psql -U postgres -d filaops < backup.sql` |
| Restore custom dump | `docker exec filaops-db pg_restore -U postgres -d filaops --clean --if-exists /tmp/b.dump` |
| Restore uploads | `tar -xzf uploads_backup.tar.gz -C .` |
| Full restart | `docker compose down && docker compose up -d` |

### Checklist

- [ ] Database dump runs daily without errors
- [ ] Uploads directory is included in backups
- [ ] Backups are stored off-site (cloud storage, remote server)
- [ ] Retention policy removes old backups automatically
- [ ] Restore test performed at least once per quarter
- [ ] `.env` file backed up separately (contains DB credentials)

---

*Last updated: 2026-02-07*
*Applies to FilaOps Core (Open Source)*
