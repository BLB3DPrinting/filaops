FROM python:3.11-slim

# Version info (passed from docker-compose build args or CI)
ARG FILAOPS_VERSION=3.0.1
ARG FILAOPS_BUILD_DATE
ENV FILAOPS_VERSION=${FILAOPS_VERSION}
ENV FILAOPS_BUILD_DATE=${FILAOPS_BUILD_DATE:-unknown}

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create uploads directory
RUN mkdir -p /app/uploads

EXPOSE 8000

# Run migrations then start server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
