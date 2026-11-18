# Sparrow backend + web simulator. Small, single process.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SPARROW_DB=/data/sparrow.sqlite \
    SPARROW_COLLECT=1

WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/app backend/app
COPY frontend frontend
COPY config/commute.example.toml config/commute.example.toml

RUN useradd --system --uid 10001 sparrow && mkdir -p /data && chown sparrow /data
USER sparrow

WORKDIR /srv/backend
EXPOSE 8080
# The host terminates HTTPS; trust its forwarded headers so cookies get the Secure flag.
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
