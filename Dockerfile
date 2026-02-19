FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY agora/ agora/

# Create data directory for SQLite
RUN mkdir -p /app/data

# Non-root user for security
RUN useradd -m -u 1000 agora && chown -R agora:agora /app
USER agora

EXPOSE 8000

CMD ["uvicorn", "agora.api_server:app", "--host", "0.0.0.0", "--port", "8000"]
