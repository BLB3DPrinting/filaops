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

# Copy requirements first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories and non-root user
# /var/lib/filaops/config holds install_uuid; a new named volume mounted there
# copies this directory's owner and mode. The user site-packages directory
# exists up front so a package pip installs while the app runs is importable
# without a restart.
# sed strips Windows CRLF line endings that break shebangs on Linux
RUN mkdir -p /app/uploads /app/logs /app/static/uploads/products /var/lib/filaops/config \
    && addgroup --system appgroup \
    && adduser --system --home /home/appuser --ingroup appgroup appuser \
    && mkdir -p "$(HOME=/home/appuser python -c 'import site; print(site.getusersitepackages())')" \
    && chown -R appuser:appgroup /app/uploads /app/logs /app/static /var/lib/filaops/config /home/appuser \
    && chmod 700 /var/lib/filaops/config \
    && chmod -R a+rX /app \
    && sed -i 's/\r$//' /app/scripts/docker-migrate.sh /app/scripts/docker-entrypoint.sh \
    && chmod +x /app/scripts/docker-migrate.sh /app/scripts/docker-entrypoint.sh

EXPOSE 8000

# The entrypoint starts as root to install plugins and fix ownership of the
# directories the app writes, then runs migrations and the app as appuser.
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
