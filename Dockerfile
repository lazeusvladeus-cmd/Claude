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

# Secrets (OAuth client + token files) are mounted at runtime, never baked into the image.
RUN mkdir -p /app/secrets

ENV PYTHONUNBUFFERED=1

# The dashboard's web server (see app/webapp/); PORT is overridable and picked up
# automatically by most PaaS hosts (e.g. Railway sets this for you).
ENV PORT=8080
EXPOSE 8080

CMD ["python", "-m", "app.main"]
