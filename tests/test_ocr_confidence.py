import importlib
import sys
import types
import unittest
from unittest.mock import patch

import numpy as np


class _FakeALPR:
    def __init__(self, *args, **kwargs):
        pass

    def predict(self, _frame):
        return []

    def draw_predictions(self, frame):
        return frame


class _FakeOCRPayload:
    def __init__(self, text: str, confidence):
        self.text = text
        self.confidence = confidence


class _FakeResult:
    def __init__(self, text: str, confidence):
        self.ocr = _FakeOCRPayload(text, confidence)


class _FakeDrawPredictionsResult:
    def __init__(self, image, results):
        self.image = image
        self.results = results


class TestOCRConfidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._old_fast_alpr = sys.modules.get("fast_alpr")

        fake_fast_alpr = types.ModuleType("fast_alpr")
        fake_fast_alpr.ALPR = _FakeALPR
        sys.modules["fast_alpr"] = fake_fast_alpr

        sys.modules.pop("app.services.ocr", None)
        cls.ocr = importlib.import_module("app.services.ocr")

    @classmethod
    def tearDownClass(cls) -> None:
        sys.modules.pop("app.services.ocr", None)
        if cls._old_fast_alpr is None:
            sys.modules.pop("fast_alpr", None)
        else:
            sys.modules["fast_alpr"] = cls._old_fast_alpr

    def test_confidence_scalar_from_list(self) -> None:
        value = self.ocr._confidence_scalar([0.7, 0.9, 1.0])
        self.assertAlmostEqual(0.8666666667, value, places=6)

    def test_run_inference_supports_list_confidence(self) -> None:
        fake_frame = np.zeros((24, 24, 3), dtype=np.uint8)
        fake_results = [_FakeResult("B1234CD", [0.8, 1.0])]

        with patch.object(self.ocr.os.path, "exists", return_value=True), patch.object(
            self.ocr.cv2, "imread", return_value=fake_frame
        ), patch.object(
            self.ocr._alpr,
            "draw_predictions",
            return_value=_FakeDrawPredictionsResult(fake_frame.copy(), fake_results),
        ):
            payload = self.ocr.run_inference("C:/tmp/sample.jpg")

        self.assertEqual("B1234CD", payload["detected_plate"])
        self.assertEqual(0.9, payload["confidence"])
        self.assertTrue(payload["annotated_bytes"])

    def test_run_inference_keeps_unrounded_float_confidence(self) -> None:
        fake_frame = np.zeros((24, 24, 3), dtype=np.uint8)
        fake_results = [_FakeResult("B1234CD", 0.9123456789)]

        with patch.object(self.ocr.os.path, "exists", return_value=True), patch.object(
            self.ocr.cv2, "imread", return_value=fake_frame
        ), patch.object(
            self.ocr._alpr,
            "draw_predictions",
            return_value=_FakeDrawPredictionsResult(fake_frame.copy(), fake_results),
        ):
            payload = self.ocr.run_inference("C:/tmp/sample.jpg")

        self.assertAlmostEqual(0.9123456789, payload["confidence"], places=10)
        self.assertNotEqual(round(payload["confidence"], 4), payload["confidence"])


if __name__ == "__main__":
    unittest.main()
