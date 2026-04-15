import json
import os
import unittest
from unittest.mock import Mock

from app.services.timing import (
    build_detect_plate_timing_payload,
    log_detect_plate_timing,
)


class TestTimingService(unittest.TestCase):
    def test_build_detect_plate_timing_payload(self) -> None:
        payload = build_detect_plate_timing_payload(
            image_path="/tmp/a.jpg",
            queue_wait_ms=12.345,
            infer_ms=123.456,
            upload_ms=45.678,
            total_ms=200.111,
            timings_ms={"load_ms": 10.5, "predict_ms": 80.2, "encode_ms": 5.5},
            upload_success=True,
        )

        self.assertEqual("detect_plate_timing", payload["event"])
        self.assertEqual("/tmp/a.jpg", payload["image_path"])
        self.assertEqual(12.35, payload["queue_wait_ms"])
        self.assertEqual(123.46, payload["infer_ms"])
        self.assertEqual(45.68, payload["upload_ms"])
        self.assertEqual(200.11, payload["total_ms"])
        self.assertEqual(10.5, payload["load_ms"])
        self.assertEqual(80.2, payload["predict_ms"])
        self.assertEqual(5.5, payload["encode_ms"])
        self.assertTrue(payload["upload_success"])

    def test_log_detect_plate_timing_json_mode(self) -> None:
        logger = Mock()
        payload = {
            "event": "detect_plate_timing",
            "image_path": "/tmp/a.jpg",
            "queue_wait_ms": 0.2,
            "infer_ms": 1.2,
            "upload_ms": 0.0,
            "total_ms": 1.2,
            "load_ms": 0.1,
            "predict_ms": 1.0,
            "encode_ms": 0.1,
            "upload_success": False,
        }

        with _patched_env({"LPR_TIMING_JSON_LOG": "true"}):
            log_detect_plate_timing(logger, payload)

        logger.info.assert_called_once()
        args, _kwargs = logger.info.call_args
        self.assertEqual("%s", args[0])
        emitted = json.loads(args[1])
        self.assertEqual("detect_plate_timing", emitted["event"])

    def test_log_detect_plate_timing_plain_mode(self) -> None:
        logger = Mock()
        payload = {
            "event": "detect_plate_timing",
            "image_path": "/tmp/a.jpg",
            "queue_wait_ms": 0.2,
            "infer_ms": 1.2,
            "upload_ms": 0.0,
            "total_ms": 1.2,
            "load_ms": 0.1,
            "predict_ms": 1.0,
            "encode_ms": 0.1,
            "upload_success": True,
        }

        with _patched_env({"LPR_TIMING_JSON_LOG": "false"}):
            log_detect_plate_timing(logger, payload)

        logger.info.assert_called_once()
        args, _kwargs = logger.info.call_args
        self.assertIn("detect_plate completed", args[0])
        self.assertIn("queue_wait_ms", args[0])


class _patched_env:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.original = {}

    def __enter__(self):
        keys = {"LPR_TIMING_JSON_LOG"}
        for key in keys:
            self.original[key] = os.environ.get(key)
            if key in self.values:
                os.environ[key] = self.values[key]
            elif key in os.environ:
                del os.environ[key]

    def __exit__(self, exc_type, exc, tb):
        for key, value in self.original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
