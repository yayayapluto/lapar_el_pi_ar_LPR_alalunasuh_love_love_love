# Project Guidelines

## Build And Test
- Install dependencies with `pip install -r requirements.txt`.
- Run development server with `python run.py` (loads `.env`).
- Run production-like server with `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- Run tests with `python -m unittest discover tests`.
- From repo root, run monitoring profile with `docker compose --profile monitoring up --build`.
- When behavior changes in routes or services, add or update tests in `tests/` in the same change.

## Architecture
- This repository is a single-responsibility FastAPI service for license plate OCR and annotated-image upload.
- Keep CPU-bound inference in a threadpool (`run_in_threadpool`) and keep network I/O async.
- Keep inference and upload decoupled: inference first, then async S3 upload.
- `app/main.py` owns lifespan state. The shared async HTTP client is created on startup and closed on shutdown.
- `GET /metrics` must stay scrape-friendly and backed by `prometheus-client` collectors.

## Conventions
- Keep `ALPR` and the sync `httpx.Client` as module-level singletons in `app/services/ocr.py`.
- Do not create a new `httpx.AsyncClient` per request. Use the lifespan-managed client via dependency injection.
- Keep manual AWS Signature V4 upload logic in `app/services/s3.py`; do not switch to boto3 unless storage-provider behavior changes.
- Preserve dual input handling for `image_path` (local filesystem path or HTTP(S) URL).
- Preserve observability behavior in `app/routes/plate.py`: metrics should be recorded for both success and failure paths.
- Preserve request outcome labels in metrics: `ok`, `ok_upload_failed`, `overloaded`, `not_found`, `no_plate`, `error`.

## Pitfalls
- First inference may be slow because ALPR models are downloaded on demand.
- S3 upload requires all six env vars (`S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `S3_PUBLIC_BASE_URL`).
- Queue timeout and concurrency env vars (`LPR_INFERENCE_QUEUE_TIMEOUT_SEC`, `LPR_MAX_INFERENCE_CONCURRENCY`) can cause `503` responses under load if tuned too aggressively.
- HTTP client tuning envs are clamped: connections/keepalive/timeout outside allowed bounds are normalized in `app/services/http_client.py`.

## References
- See `README.md` for API contract, endpoint behavior, and local/docker run steps.
- See `CLAUDE.md` for request flow and design rationales.
- Monitoring files live in repo-root `monitoring/` and are used by compose `monitoring` profile.