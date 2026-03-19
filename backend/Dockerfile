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
# sed strips Windows CRLF line endings that break shebangs on Linux
RUN mkdir -p /app/uploads /app/logs /app/static/uploads/products \
    && addgroup --system appgroup \
    && adduser --system --home /home/appuser --ingroup appgroup appuser \
    && chown -R appuser:appgroup /app/uploads /app/logs /app/static \
    && chmod -R a+rX /app \
    && sed -i 's/\r$//' /app/scripts/docker-migrate.sh /app/scripts/docker-entrypoint.sh \
    && chmod +x /app/scripts/docker-migrate.sh /app/scripts/docker-entrypoint.sh

EXPOSE 8000

# Entrypoint runs as root to install plugins, then drops to appuser for the app
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
