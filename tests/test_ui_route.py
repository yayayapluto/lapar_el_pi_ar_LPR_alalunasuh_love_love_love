import sys
import types
import unittest

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

from app.main import app  # noqa: E402


class TestUIRoute(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()

    def test_ui_page_is_available(self) -> None:
        response = self.client.get("/ui")

        self.assertEqual(200, response.status_code)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        self.assertIn("LPR Service Test UI", response.text)
        self.assertIn("/detect-plate", response.text)


if __name__ == "__main__":
    unittest.main()
