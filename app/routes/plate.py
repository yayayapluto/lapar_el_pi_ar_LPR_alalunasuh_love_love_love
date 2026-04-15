import logging
import time
import os
import asyncio
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from app.services.metrics import default_metrics
from app.services.ocr import run_inference
from app.services.s3 import upload_to_s3_async
from app.services.timing import build_detect_plate_timing_payload, log_detect_plate_timing

router = APIRouter(prefix="/detect-plate", tags=["Plate Detection"])
logger = logging.getLogger(__name__)


def _int_env(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = os.getenv(name, "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(max_value, value))


def _float_env(name: str, default: float, min_value: float, max_value: float) -> float:
    raw = os.getenv(name, "")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(max_value, value))


_MAX_INFERENCE_CONCURRENCY = _int_env("LPR_MAX_INFERENCE_CONCURRENCY", 2, 1, 64)
_INFERENCE_QUEUE_TIMEOUT_SEC = _float_env("LPR_INFERENCE_QUEUE_TIMEOUT_SEC", 0.5, 0.0, 30.0)
_INFERENCE_SEMAPHORE = asyncio.Semaphore(_MAX_INFERENCE_CONCURRENCY)


async def _acquire_inference_slot() -> tuple[bool, float]:
    wait_start = time.perf_counter()
    try:
        await asyncio.wait_for(_INFERENCE_SEMAPHORE.acquire(), timeout=_INFERENCE_QUEUE_TIMEOUT_SEC)
        wait_ms = (time.perf_counter() - wait_start) * 1000
        return True, wait_ms
    except asyncio.TimeoutError:
        wait_ms = (time.perf_counter() - wait_start) * 1000
        return False, wait_ms


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


class DetectPlateRequest(BaseModel):
    image_path: str


class DetectPlateResponse(BaseModel):
    plate_text: str
    confidence: float
    image_url: str = ""


@router.post(
    "",
    response_model=DetectPlateResponse,
    summary="Detect license plate from image",
    description="Accepts an image path or HTTP(S) URL. Returns the detected plate number, confidence score, and path to the annotated output image.",
)
async def detect_plate_endpoint(
    body: DetectPlateRequest,
    client: httpx.AsyncClient = Depends(get_http_client),
):
    total_start = time.perf_counter()
    acquired, queue_wait_ms = await _acquire_inference_slot()
    default_metrics.observe_queue_wait(queue_wait_ms)

    if not acquired:
        total_ms = (time.perf_counter() - total_start) * 1000
        default_metrics.observe_request("overloaded", 0.0, 0.0, total_ms)
        default_metrics.mark_overload()
        logger.warning("detect_plate overloaded: inference queue timeout")
        raise HTTPException(status_code=503, detail="OCR service busy, please retry")

    infer_start = time.perf_counter()
    default_metrics.inference_start()
    try:
        result = await run_in_threadpool(run_inference, body.image_path)
    except FileNotFoundError:
        infer_ms = (time.perf_counter() - infer_start) * 1000
        total_ms = (time.perf_counter() - total_start) * 1000
        default_metrics.observe_request("not_found", infer_ms, 0.0, total_ms)
        raise HTTPException(status_code=404, detail="Cannot find image")
    except ValueError:
        infer_ms = (time.perf_counter() - infer_start) * 1000
        total_ms = (time.perf_counter() - total_start) * 1000
        default_metrics.observe_request("no_plate", infer_ms, 0.0, total_ms)
        raise HTTPException(status_code=422, detail="No plate detected in the provided image")
    except Exception as e:
        infer_ms = (time.perf_counter() - infer_start) * 1000
        total_ms = (time.perf_counter() - total_start) * 1000
        default_metrics.observe_request("error", infer_ms, 0.0, total_ms)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        _INFERENCE_SEMAPHORE.release()
        default_metrics.inference_done()

    infer_ms = (time.perf_counter() - infer_start) * 1000

    image_url = ""
    upload_success = False
    upload_ms = 0.0
    if result.get("annotated_bytes"):
        upload_start = time.perf_counter()
        try:
            image_url = await upload_to_s3_async(
                result["annotated_bytes"],
                f"{result['stem']}_output.jpg",
                client,
            )
            upload_success = image_url != ""
        except Exception as e:
            logger.warning("Failed to upload annotated image to S3: %s", e)
            default_metrics.mark_upload_failure()
        finally:
            upload_ms = (time.perf_counter() - upload_start) * 1000

    total_ms = (time.perf_counter() - total_start) * 1000
    outcome = "ok" if upload_success else "ok_upload_failed"
    default_metrics.observe_request(outcome, infer_ms, upload_ms, total_ms)

    payload = build_detect_plate_timing_payload(
        image_path=body.image_path,
        queue_wait_ms=queue_wait_ms,
        infer_ms=infer_ms,
        upload_ms=upload_ms,
        total_ms=total_ms,
        timings_ms=result.get("timings_ms", {}),
        upload_success=upload_success,
    )
    log_detect_plate_timing(logger, payload)

    return DetectPlateResponse(
        plate_text=result["detected_plate"],
        confidence=result["confidence"],
        image_url=image_url,
    )
