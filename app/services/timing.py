import json
import os
from typing import Any


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "")
    if raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def build_detect_plate_timing_payload(
    image_path: str,
    queue_wait_ms: float,
    infer_ms: float,
    upload_ms: float,
    total_ms: float,
    timings_ms: dict[str, Any] | None,
    upload_success: bool,
) -> dict[str, Any]:
    timings = timings_ms or {}
    return {
        "event": "detect_plate_timing",
        "image_path": image_path,
        "queue_wait_ms": round(queue_wait_ms, 2),
        "infer_ms": round(infer_ms, 2),
        "upload_ms": round(upload_ms, 2),
        "total_ms": round(total_ms, 2),
        "load_ms": timings.get("load_ms"),
        "predict_ms": timings.get("predict_ms"),
        "encode_ms": timings.get("encode_ms"),
        "upload_success": upload_success,
    }


def log_detect_plate_timing(logger: Any, payload: dict[str, Any]) -> None:
    if _bool_env("LPR_TIMING_JSON_LOG", True):
        logger.info("%s", json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return

    logger.info(
        (
            "detect_plate completed queue_wait_ms=%.2f infer_ms=%.2f upload_ms=%.2f total_ms=%.2f "
            "load_ms=%s predict_ms=%s encode_ms=%s upload_success=%s"
        ),
        payload["queue_wait_ms"],
        payload["infer_ms"],
        payload["upload_ms"],
        payload["total_ms"],
        payload.get("load_ms"),
        payload.get("predict_ms"),
        payload.get("encode_ms"),
        payload.get("upload_success"),
    )
