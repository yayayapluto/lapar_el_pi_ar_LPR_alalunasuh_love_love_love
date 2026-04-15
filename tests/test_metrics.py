import unittest

from prometheus_client import CollectorRegistry

from app.services.metrics import LPRMetrics


class TestMetricsService(unittest.TestCase):
    def test_observe_request_and_queue_wait(self) -> None:
        registry = CollectorRegistry()
        metrics = LPRMetrics(registry=registry)

        metrics.observe_queue_wait(25.0)
        metrics.observe_request("ok", infer_ms=120.0, upload_ms=30.0, total_ms=180.0)

        payload, content_type = metrics.render_latest()
        output = payload.decode("utf-8")

        self.assertIn("text/plain", content_type)
        self.assertIn('lpr_detect_plate_requests_total{outcome="ok"} 1.0', output)
        self.assertIn("lpr_detect_plate_queue_wait_seconds_bucket", output)
        self.assertIn("lpr_detect_plate_duration_seconds_bucket", output)

    def test_overload_and_upload_failure_counters(self) -> None:
        registry = CollectorRegistry()
        metrics = LPRMetrics(registry=registry)

        metrics.mark_overload()
        metrics.mark_upload_failure()

        payload, _content_type = metrics.render_latest()
        output = payload.decode("utf-8")

        self.assertIn("lpr_inference_overload_total 1.0", output)
        self.assertIn("lpr_upload_failure_total 1.0", output)

    def test_inference_inflight_gauge(self) -> None:
        registry = CollectorRegistry()
        metrics = LPRMetrics(registry=registry)

        metrics.inference_start()
        metrics.inference_done()

        payload, _content_type = metrics.render_latest()
        output = payload.decode("utf-8")

        self.assertIn("lpr_inference_inflight 0.0", output)


if __name__ == "__main__":
    unittest.main()