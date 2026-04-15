# CLAUDE.md

This file provides guidance to coding agents working inside `lpr_service/`.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server (loads .env automatically)
python run.py

# Run production-like server
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Run tests
python -m unittest discover -s tests -v

# Build and run container
docker build -t lpr-service .
docker run -p 8000:8000 --env-file .env lpr-service

# Full stack + monitoring profile (from repo root)
docker compose --profile monitoring up --build
```

## Architecture

Single-purpose FastAPI OCR service:
- Input: local path or HTTP(S) image URL
- Process: ALPR inference + optional annotated image upload
- Output contract: `plate_text`, `confidence`, `image_url`

### Request flow
1. `POST /detect-plate` in `app/routes/plate.py`
: acquires semaphore slot, runs CPU-bound inference via `run_in_threadpool`, uploads annotation asynchronously, emits timing + Prometheus metrics.
2. `app/services/ocr.py`
: module-level `ALPR` singleton and sync `httpx.Client` for input URL fetches; returns plate result, JPEG bytes, and timing segments.
3. `app/services/s3.py`
: manual AWS Signature V4 upload (`upload_to_s3_async`) for Ceph-compatible providers; no boto3.
4. `app/main.py`
: lifespan creates a single shared `httpx.AsyncClient` (S3 upload client) and exposes `GET /metrics` for scrape.
5. `app/services/metrics.py` + `app/services/timing.py`
: collect request outcomes, latency histograms, inflight gauge, overload/upload-failure counters, and structured timing logs.

### Endpoints
- `GET /health`
- `GET /metrics`
- `POST /detect-plate`

## Environment variables

Required S3 variables:

```env
S3_ENDPOINT=https://...
S3_BUCKET=...
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
S3_REGION=us-east-1
S3_PUBLIC_BASE_URL=https://...
```

Optional tuning variables:

```env
LPR_S3_MAX_CONNECTIONS=20
LPR_S3_MAX_KEEPALIVE_CONNECTIONS=10
LPR_S3_KEEPALIVE_EXPIRY_SEC=10
LPR_S3_TIMEOUT_SEC=15

LPR_MAX_INFERENCE_CONCURRENCY=2
LPR_INFERENCE_QUEUE_TIMEOUT_SEC=0.5

LPR_JPEG_QUALITY=85
LPR_MAX_IMAGE_DIM=0
LPR_TIMING_JSON_LOG=true

UVICORN_WORKERS=2
UVICORN_TIMEOUT_KEEP_ALIVE=5
```

## Key decisions and constraints

- Keep `ALPR` and sync `httpx.Client` as module-level singletons in `app/services/ocr.py`.
- Keep one lifespan-managed `httpx.AsyncClient`; do not create per request.
- Keep manual SigV4 uploader in `app/services/s3.py` unless storage behavior changes.
- Preserve dual input behavior for `image_path` (filesystem path or HTTP(S) URL).
- Preserve queue guard behavior (`LPR_MAX_INFERENCE_CONCURRENCY`, `LPR_INFERENCE_QUEUE_TIMEOUT_SEC`) and 503 overload response.
- Preserve observability instrumentation in `app/routes/plate.py` for all outcomes.

## Monitoring assets (repo root)

- `monitoring/prometheus.yml`
- `monitoring/prometheus-alerts.yml`
- `monitoring/grafana/provisioning/`
- `monitoring/grafana/dashboards/lpr-overview.json`
