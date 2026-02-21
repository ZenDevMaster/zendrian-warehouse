# ============================================================
# Zendrian Warehouse — Production Dockerfile
# License: AGPLv3
# ============================================================
FROM python:3.12-slim AS production

# Metadata
LABEL org.opencontainers.image.title="Zendrian Warehouse"
LABEL org.opencontainers.image.description="Web-based warehouse inventory management and stocktaking"
LABEL org.opencontainers.image.source="https://github.com/ZenDevMaster/zendrian-warehouse"
LABEL org.opencontainers.image.licenses="AGPL-3.0-or-later"

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies (none needed beyond slim base, but keep
# the pattern here for future extensibility) and clean up in one layer
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 warehouse \
    && useradd --uid 1000 --gid warehouse --shell /bin/bash --create-home warehouse

# Set working directory
WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Cache-busting: this ARG changes on every commit, forcing Docker to
# invalidate the COPY layer (and everything after it) even when the
# GHA layer cache would otherwise serve a stale result.
ARG COMMIT_SHA
ENV COMMIT_SHA=${COMMIT_SHA}

# Copy application code
COPY . .

# Create instance directory for SQLite database
RUN mkdir -p /app/instance \
    && chown -R warehouse:warehouse /app

# Switch to non-root user
USER warehouse

# Expose the application port
EXPOSE 8000

# Health check — verify gunicorn is responding
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/login || exit 1

# Default environment variables
ENV SECRET_KEY="change-me-in-production" \
    DATABASE_URL="sqlite:////app/instance/zendrian_warehouse.db" \
    MIN_SCAN_INTERVAL="0.7" \
    DEFAULT_ADMIN_USER="admin" \
    DEFAULT_ADMIN_PASS="warehouse"

# Run with gunicorn — single worker + threads for SQLite safety
CMD ["gunicorn", \
     "--worker-class", "gthread", \
     "--workers", "1", \
     "--threads", "4", \
     "--bind", "0.0.0.0:8000", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:create_app()"]
