FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --disabled-password --gecos "" --uid 1000 appuser

WORKDIR /app

FROM base AS deps

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

FROM deps AS final

COPY --chown=appuser:appuser app/ ./app/

RUN mkdir -p /home/appuser/.cache \
    && chown -R appuser:appuser /home/appuser/.cache

USER appuser

EXPOSE 8000

ENV UVICORN_WORKERS=2
ENV UVICORN_TIMEOUT_KEEP_ALIVE=5

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS} --timeout-keep-alive ${UVICORN_TIMEOUT_KEEP_ALIVE}"]
