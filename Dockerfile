FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Port is provided at runtime via API_PORT env var (see .env.example)
ARG API_PORT=8080
EXPOSE ${API_PORT}

# Start the FastAPI server — port read from env at runtime
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${API_PORT}"]
