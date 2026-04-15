import os
import time
import cv2
import httpx
import numpy as np
from pathlib import Path
from fast_alpr import ALPR

_alpr = ALPR(
    detector_model="yolo-v9-t-384-license-plate-end2end",
    ocr_model="cct-xs-v1-global-model",
)

_http = httpx.Client(follow_redirects=True, timeout=10.0)


def run_inference(image_path: str) -> dict:
    """
    Load image, run ALPR, draw annotations, encode to JPEG.
    CPU-bound — call via run_in_threadpool.

    Returns dict with detected_plate, confidence, annotated_bytes, and stem
    for async S3 upload by the caller.

    Raises:
        FileNotFoundError: if the image cannot be found or downloaded.
        ValueError: if no plate is detected.
    """
    is_url = image_path.startswith("http://") or image_path.startswith("https://")

    load_start = time.perf_counter()

    if is_url:
        frame_bgr = _load_from_url(image_path)
    else:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found at path: {image_path}")
        frame_bgr = cv2.imread(image_path)
        if frame_bgr is None:
            raise FileNotFoundError(f"Failed to read image at path: {image_path}")

    frame_bgr = _maybe_resize(frame_bgr)
    frame_bgr = _coerce_uint8_array(frame_bgr, "input image")
    load_ms = (time.perf_counter() - load_start) * 1000

    predict_start = time.perf_counter()
    drawn = _draw_predictions_result(frame_bgr)
    results = drawn["results"]
    predict_ms = (time.perf_counter() - predict_start) * 1000

    if not results:
        raise ValueError("No plate detected in the provided image.")

    best = max(
        (r for r in results if r.ocr),
        key=lambda r: _confidence_scalar(r.ocr.confidence),
        default=None,
    )
    if best is None:
        raise ValueError("No plate detected in the provided image.")

    confidence = _confidence_scalar(best.ocr.confidence)

    stem = Path(image_path).stem.split("?")[0]

    encode_start = time.perf_counter()
    annotated_bytes = _encode_annotated(drawn["image"])
    encode_ms = (time.perf_counter() - encode_start) * 1000

    return {
        "detected_plate": best.ocr.text,
        "confidence": confidence,
        "annotated_bytes": annotated_bytes,
        "stem": stem,
        "timings_ms": {
            "load_ms": round(load_ms, 2),
            "predict_ms": round(predict_ms, 2),
            "encode_ms": round(encode_ms, 2),
        },
    }


def _draw_predictions_result(frame_bgr: np.ndarray) -> dict:
    drawn = _alpr.draw_predictions(frame_bgr)
    if drawn is None:
        return {"image": None, "results": []}

    image = getattr(drawn, "image", None)
    results = getattr(drawn, "results", None)

    if image is not None and results is not None:
        return {"image": image, "results": results}

    # Backward compatibility for older fast-alpr behavior where draw_predictions
    # may return only an annotated ndarray.
    return {
        "image": drawn,
        "results": _alpr.predict(frame_bgr),
    }


def _encode_annotated(annotated_image) -> bytes:
    """Encode annotated image to JPEG bytes. Returns empty bytes on failure."""
    if annotated_image is None:
        return b""
    try:
        annotated_bgr = _to_bgr_for_jpeg(annotated_image)
    except ValueError:
        return b""
    ok, buf = cv2.imencode(
        ".jpg",
        annotated_bgr,
        [cv2.IMWRITE_JPEG_QUALITY, _jpeg_quality()],
    )
    return buf.tobytes() if ok else b""


def _jpeg_quality() -> int:
    raw = os.getenv("LPR_JPEG_QUALITY", "85")
    try:
        quality = int(raw)
    except ValueError:
        quality = 85
    return max(50, min(100, quality))


def _maybe_resize(frame_bgr):
    raw = os.getenv("LPR_MAX_IMAGE_DIM", "0")
    try:
        max_dim = int(raw)
    except ValueError:
        max_dim = 0

    if max_dim <= 0:
        return frame_bgr

    height, width = frame_bgr.shape[:2]
    largest = max(height, width)
    if largest <= max_dim:
        return frame_bgr

    scale = max_dim / float(largest)
    target_w = max(1, int(width * scale))
    target_h = max(1, int(height * scale))
    return cv2.resize(frame_bgr, (target_w, target_h), interpolation=cv2.INTER_AREA)


def _to_bgr_for_jpeg(image) -> np.ndarray:
    arr = _coerce_uint8_array(image, "annotated image")
    if arr.ndim == 2:
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    if arr.ndim != 3:
        raise ValueError("Unsupported annotated image shape")

    channels = arr.shape[2]
    if channels == 3:
        return arr
    if channels == 4:
        return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
    raise ValueError("Unsupported annotated image channels")


def _coerce_uint8_array(image, context: str) -> np.ndarray:
    if isinstance(image, np.ndarray):
        arr = image
    else:
        try:
            arr = np.asarray(image)
        except Exception as exc:
            raise ValueError(f"Invalid {context} format") from exc

    if arr.size == 0:
        raise ValueError(f"Empty {context}")

    if arr.dtype.kind not in {"u", "i", "f", "b"}:
        raise ValueError(f"Invalid {context} dtype")

    if arr.dtype == np.uint8:
        return arr

    clipped = np.clip(arr, 0, 255)
    return clipped.astype(np.uint8)


def _confidence_scalar(value) -> float:
    if isinstance(value, (int, float, np.integer, np.floating)):
        conf = float(value)
    elif isinstance(value, (list, tuple, np.ndarray)):
        try:
            arr = np.asarray(value, dtype=float).reshape(-1)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid OCR confidence format") from exc
        if arr.size == 0:
            raise ValueError("Invalid OCR confidence format")
        conf = float(np.mean(arr))
    else:
        try:
            conf = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid OCR confidence format") from exc

    if np.isnan(conf) or np.isinf(conf):
        raise ValueError("Invalid OCR confidence value")
    return conf


def _load_from_url(url: str):
    """Download image from URL into memory and decode with cv2."""
    try:
        resp = _http.get(url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        arr = np.frombuffer(resp.content, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            raise FileNotFoundError(f"Failed to decode image from URL: {url}")
        return frame
    except httpx.HTTPStatusError as e:
        raise FileNotFoundError(f"HTTP {e.response.status_code} fetching image: {url}")
    except httpx.RequestError as e:
        raise FileNotFoundError(f"Cannot reach URL: {url} — {e}")
