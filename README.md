# LPR Service — Python OCR Microservice

FastAPI microservice for license plate recognition. Part of the parkieee stack — accepts a local file path or HTTP(S) URL, runs ALPR, and uploads the annotated image to S3-compatible storage.

---

## Stack

| Component | Technology |
|---|---|
| Framework | FastAPI + Uvicorn |
| Plate detection | [fast-alpr](https://github.com/ankandrew/fast-alpr) (YOLO + CCT ONNX) |
| Image processing | OpenCV |
| HTTP client | httpx |
| Runtime | Python 3.11 |
| Containerization | Docker |

---

## How It Works

```
Go API / Client
  │
  ├─ POST /detect-plate {"image_path": "<local path or URL>"}
  │
  ▼
LPR Service
  ├─ Load image (local path or HTTP(S) URL)
  ├─ Run ALPR: plate detection + OCR
  ├─ Encode annotated image → upload to S3
  └─ Return: plate_text, confidence, image_url (public S3 URL)
```

---

## Endpoints

### `GET /health`

```json
{ "status": "ok" }
```

### `GET /metrics`

Prometheus scrape endpoint (text exposition format).

`lpr_detect_plate_requests_total` uses the following `outcome` labels:
- `ok`
- `ok_upload_failed`
- `overloaded`
- `not_found`
- `no_plate`
- `error`

Example metric groups:
- `lpr_detect_plate_requests_total{outcome="..."}`
- `lpr_detect_plate_duration_seconds`
- `lpr_detect_plate_infer_duration_seconds`
- `lpr_detect_plate_upload_duration_seconds`
- `lpr_detect_plate_queue_wait_seconds`
- `lpr_inference_inflight`
- `lpr_inference_overload_total`
- `lpr_upload_failure_total`

---

### `POST /detect-plate`

**Request:**
```json
{
  "image_path": "/mnt/storage/photos/entry_d6c2441a.jpeg"
}
```

`image_path` accepts either a local file path **or** a URL (`http://` / `https://`).

**Response 200:**
```json
{
  "plate_text": "B1701SGI",
  "confidence": 0.9831,
  "image_url": "https://<s3-public-base>/entry_d6c2441a_output.jpg"
}
```

`image_url` is the public S3 URL of the annotated image. Returns `""` if the upload fails — the plate result is still returned.

**Error responses:**

| Status | Condition |
|---|---|
| `404` | File or URL not found |
| `422` | Valid image but no plate detected |
| `503` | Service busy (inference queue timeout) |
| `500` | Internal error |

---

## Configuration

Create a `.env` file in the project root (auto-loaded by `run.py`):

```env
S3_ENDPOINT=https://...
S3_BUCKET=bucket-name
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
S3_REGION=us-east-1
S3_PUBLIC_BASE_URL=https://...
```

All six variables are required. The service raises an error at upload time if any are missing.

> S3 uploads use hand-rolled AWS Signature V4 (no boto3) for compatibility with Ceph-based providers such as NevaObjects.

Optional performance tuning env vars:

```env
# S3 AsyncClient pool/timeout
# Bounds: max_connections(1..200), keepalive_connections(1..100), keepalive_expiry_sec(1..120), timeout_sec(1..120)
LPR_S3_MAX_CONNECTIONS=20
LPR_S3_MAX_KEEPALIVE_CONNECTIONS=10
LPR_S3_KEEPALIVE_EXPIRY_SEC=10
LPR_S3_TIMEOUT_SEC=15

# Inference throughput guard
# Bounds: concurrency(1..64), queue_timeout_sec(0..30)
LPR_MAX_INFERENCE_CONCURRENCY=2
LPR_INFERENCE_QUEUE_TIMEOUT_SEC=0.5

# Optional image processing tuning
LPR_JPEG_QUALITY=85
LPR_MAX_IMAGE_DIM=0

# Structured timing log toggle (JSON string payload)
LPR_TIMING_JSON_LOG=true

# Container runtime
UVICORN_WORKERS=2
UVICORN_TIMEOUT_KEEP_ALIVE=5
```

---

## Running Locally

```bash
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt

python run.py
# → http://localhost:8000
# → Interactive docs: http://localhost:8000/docs
```

### Makefile Commands (from this directory)

If you prefer shorter commands, use the included `Makefile`:

```bash
make help
make install
make dev
make prod
make test
make test-file TEST=tests.test_metrics
make docker-build
make docker-run
```

Monitoring shortcuts are also available from this directory:

```bash
make monitoring-up
make monitoring-down
```

Those targets automatically execute `docker compose --profile monitoring ...` from the parent project root.

---

## Running with Docker

```bash
docker build -t lpr-service .
docker run -p 8000:8000 --env-file .env lpr-service
```

### Optional Monitoring (Prometheus, Non-Redis)

From repo root:

```bash
docker compose --profile monitoring up --build
```

Endpoints:
- LPR API: `http://localhost:8001`
- LPR metrics: `http://localhost:8001/metrics`
- Prometheus UI: `http://localhost:9090`
- Grafana UI: `http://localhost:3000` (default login `admin` / `admin`)

Provisioned Grafana dashboard:
- `LPR Service Overview` (auto-loaded as default home dashboard)

Prometheus alert rules are preloaded for:
- High p95 latency (>1.5s for 10m)
- High overload ratio (>1% for 5m)
- High upload failure ratio (>5% for 10m)

Monitoring assets are versioned at repo root:
- `monitoring/prometheus.yml`
- `monitoring/prometheus-alerts.yml`
- `monitoring/grafana/provisioning/`
- `monitoring/grafana/dashboards/lpr-overview.json`

You can inspect active alerts at Prometheus `http://localhost:9090/alerts`.

Useful starter PromQL:
- `sum(rate(lpr_detect_plate_requests_total[5m])) by (outcome)`
- `histogram_quantile(0.95, sum(rate(lpr_detect_plate_duration_seconds_bucket[5m])) by (le))`
- `histogram_quantile(0.99, sum(rate(lpr_detect_plate_duration_seconds_bucket[5m])) by (le))`
- `rate(lpr_inference_overload_total[5m])`
- `rate(lpr_upload_failure_total[5m])`

---

## ALPR Models

| Parameter | Value |
|---|---|
| Detector | `yolo-v9-t-384-license-plate-end2end` |
| OCR | `cct-xs-v1-global-model` |

Models are downloaded automatically by `fast-alpr` on first run.

`fast-alpr` expects **RGB** input; OpenCV uses **BGR** — the service handles conversion automatically.
