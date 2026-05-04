FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r /app/server/requirements.txt

# Copy source code
COPY shared/ /app/shared/
COPY server/ /app/server/
COPY frontend/ /app/frontend/

# Create data directories
RUN mkdir -p /app/data/snapshots

EXPOSE 8000

CMD ["python", "-m", "server.server_main"]

