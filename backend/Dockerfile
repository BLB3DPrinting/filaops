FROM python:3.11-slim

# Build-time metadata (optional)
ARG FILAOPS_BUILD_DATE
ENV FILAOPS_BUILD_DATE=${FILAOPS_BUILD_DATE:-unknown}

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# PostgreSQL client tools for the in-app database backups (Backups page).
# pg_dump's major version must match the server's (postgres:16 in
# docker-compose.yml): a newer pg_dump writes settings an older server rejects
# on restore. Debian's own postgresql-client follows the Debian release, so the
# client comes from the PostgreSQL project's apt repository (PGDG), enabled by
# Debian's postgresql-common script with the signing key that package ships.
ARG PG_CLIENT_MAJOR=16
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-common \
    && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
    && apt-get install -y --no-install-recommends postgresql-client-${PG_CLIENT_MAJOR} \
    && rm -rf /var/lib/apt/lists/*
# Call the versioned binary directly rather than Debian's pg_wrapper.
ENV BACKUP_PG_DUMP_PATH=/usr/lib/postgresql/${PG_CLIENT_MAJOR}/bin/pg_dump \
    BACKUP_DIR=/app/backups

# Copy requirements first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories and non-root user
# /var/lib/filaops/config holds install_uuid and /app/backups the database
# backups; a new named volume mounted on either copies the directory's owner
# and mode. /app/backups is closed to other users after the a+rX below, which
# would otherwise open it again: backups hold customer data. The user
# site-packages directory exists up front so a package pip installs while the
# app runs is importable without a restart.
# sed strips Windows CRLF line endings that break shebangs on Linux
RUN mkdir -p /app/uploads /app/logs /app/static/uploads/products /var/lib/filaops/config /app/backups \
    && addgroup --system appgroup \
    && adduser --system --home /home/appuser --ingroup appgroup appuser \
    && mkdir -p "$(HOME=/home/appuser python -c 'import site; print(site.getusersitepackages())')" \
    && chown -R appuser:appgroup /app/uploads /app/logs /app/static /var/lib/filaops/config /app/backups /home/appuser \
    && chmod 700 /var/lib/filaops/config \
    && chmod -R a+rX /app \
    && chmod 700 /app/backups \
    && sed -i 's/\r$//' /app/scripts/docker-migrate.sh /app/scripts/docker-entrypoint.sh \
    && chmod +x /app/scripts/docker-migrate.sh /app/scripts/docker-entrypoint.sh

EXPOSE 8000

# The entrypoint starts as root to install plugins and fix ownership of the
# directories the app writes, then runs migrations and the app as appuser.
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
