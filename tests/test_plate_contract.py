import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


fake_ocr_module = types.ModuleType("app.services.ocr")


def _fake_run_inference(_image_path: str) -> dict:
    return {
        "detected_plate": "B1234CD",
        "confidence": 0.97,
        "annotated_bytes": b"fake-bytes",
        "stem": "entry",
    }


fake_ocr_module.run_inference = _fake_run_inference
sys.modules["app.services.ocr"] = fake_ocr_module

from app.routes import plate  # noqa: E402


class TestPlateContract(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.state.http_client = object()
        app.include_router(plate.router)
        self.client = TestClient(app)

    def test_detect_plate_uses_go_contract_fields(self) -> None:
        async def _fake_upload(_data: bytes, _filename: str, _client: object) -> str:
            return "https://cdn.example/out.jpg"

        with patch.object(plate, "upload_to_s3_async", _fake_upload):
            response = self.client.post("/detect-plate", json={"image_path": "/tmp/image.jpg"})

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "plate_text": "B1234CD",
                "confidence": 0.97,
                "image_url": "https://cdn.example/out.jpg",
            },
            response.json(),
        )

    def test_detect_plate_returns_empty_image_url_when_upload_fails(self) -> None:
        async def _failing_upload(_data: bytes, _filename: str, _client: object) -> str:
            raise RuntimeError("upload failed")

        with patch.object(plate, "upload_to_s3_async", _failing_upload):
            response = self.client.post("/detect-plate", json={"image_path": "/tmp/image.jpg"})

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("B1234CD", payload["plate_text"])
        self.assertEqual(0.97, payload["confidence"])
        self.assertEqual("", payload["image_url"])

    def test_detect_plate_returns_503_when_inference_queue_busy(self) -> None:
        with patch.object(plate, "_acquire_inference_slot", AsyncMock(return_value=(False, 500.0))):
            response = self.client.post("/detect-plate", json={"image_path": "/tmp/image.jpg"})

        self.assertEqual(503, response.status_code)
        self.assertEqual("OCR service busy, please retry", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
