FROM python:3.11-slim AS assets
COPY scripts/sanitize_asset_names.py /tmp/sanitize_asset_names.py
COPY cuestionarios /src/cuestionarios
COPY basamento-legal /src/basamento-legal
RUN python3 /tmp/sanitize_asset_names.py /src/cuestionarios /out/cuestionarios \
    && python3 /tmp/sanitize_asset_names.py /src/basamento-legal /out/basamento-legal

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY --from=assets /out/cuestionarios ./cuestionarios
COPY --from=assets /out/basamento-legal ./basamento-legal

RUN useradd --create-home --uid 1001 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

ENV PORT=8080
EXPOSE 8080

CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
