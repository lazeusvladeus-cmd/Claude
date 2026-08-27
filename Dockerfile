FROM python:3.12-slim

# matplotlib needs a couple of system libs for font/image rendering even headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    libfreetype6 \
    libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY scripts/ ./scripts/

# Secrets (service account JSON, OAuth token) are mounted at runtime, never baked into the image.
RUN mkdir -p /app/secrets

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "app.main"]
