# Monitor 12 — Mapa de Transparencia (servicio autónomo)
# Imagen para desplegar en Railway (o cualquier PaaS compatible con Docker).

FROM python:3.11-slim

WORKDIR /app

# lxml/psycopg2 necesitan headers de build; se limpian en la misma capa.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway inyecta $PORT en runtime; se lee dentro del CMD via shell form.
ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
