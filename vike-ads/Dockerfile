FROM python:3.12-slim

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config/ ./config/
COPY references/ ./references/
COPY vike_ads/ ./vike_ads/

# Research, concepts, images and consent records live here; mount a persistent disk on it.
ENV VIKE_DATA_DIR=/var/data \
    WEB_HOST=0.0.0.0 \
    PORT=8765 \
    PYTHONUNBUFFERED=1
RUN mkdir -p /var/data
EXPOSE 8765

# Refuses to start without APP_PASSWORD, because the dashboard spends API credits.
CMD ["python", "-m", "vike_ads", "serve"]
