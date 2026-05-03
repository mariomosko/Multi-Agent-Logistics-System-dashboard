FROM python:3.12-slim

# System deps: curl is used by the healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN groupadd -r app && useradd -r -g app -d /app app

WORKDIR /app

# Install Python deps first — separate layer for better cache reuse
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/        ./app/
COPY scripts/    ./scripts/

RUN chmod +x scripts/docker-entrypoint.sh

# Persistent volume for the SQLite database
RUN mkdir -p /data && chown app:app /data

USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=20s \
    CMD curl -sf http://localhost:8000/health || exit 1

ENTRYPOINT ["scripts/docker-entrypoint.sh"]
