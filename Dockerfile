FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create writable data directory
RUN mkdir -p /app/data

# Make entrypoint executable
RUN chmod +x entrypoint.sh

ENV FLASK_APP=run.py
ENV FLASK_DEBUG=0

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5001/ || exit 1

CMD ["./entrypoint.sh"]
