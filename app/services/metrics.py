from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, REGISTRY, generate_latest


class LPRMetrics:
    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or REGISTRY

        self.detect_plate_requests_total = Counter(
            "lpr_detect_plate_requests_total",
            "Total detect-plate requests by outcome",
            ["outcome"],
            registry=self.registry,
        )
        self.detect_plate_duration_seconds = Histogram(
            "lpr_detect_plate_duration_seconds",
            "End-to-end detect-plate request duration",
            buckets=(0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0),
            registry=self.registry,
        )
        self.detect_plate_infer_duration_seconds = Histogram(
            "lpr_detect_plate_infer_duration_seconds",
            "Inference-only duration for detect-plate",
            buckets=(0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 2.0, 3.0, 5.0),
            registry=self.registry,
        )
        self.detect_plate_upload_duration_seconds = Histogram(
            "lpr_detect_plate_upload_duration_seconds",
            "S3 upload duration for annotated image",
            buckets=(0.01, 0.03, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 2.0),
            registry=self.registry,
        )
        self.detect_plate_queue_wait_seconds = Histogram(
            "lpr_detect_plate_queue_wait_seconds",
            "Semaphore queue wait before inference slot is acquired",
            buckets=(0.0, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 1.0, 2.0),
            registry=self.registry,
        )
        self.inference_inflight = Gauge(
            "lpr_inference_inflight",
            "Current number of in-flight inference jobs",
            registry=self.registry,
        )
        self.inference_overload_total = Counter(
            "lpr_inference_overload_total",
            "Total inference queue timeout events",
            registry=self.registry,
        )
        self.upload_failure_total = Counter(
            "lpr_upload_failure_total",
            "Total annotated image upload failures",
            registry=self.registry,
        )

    @staticmethod
    def _to_seconds(milliseconds: float) -> float:
        return max(0.0, milliseconds / 1000.0)

    def observe_queue_wait(self, queue_wait_ms: float) -> None:
        self.detect_plate_queue_wait_seconds.observe(self._to_seconds(queue_wait_ms))

    def observe_request(self, outcome: str, infer_ms: float, upload_ms: float, total_ms: float) -> None:
        self.detect_plate_requests_total.labels(outcome=outcome).inc()
        self.detect_plate_infer_duration_seconds.observe(self._to_seconds(infer_ms))
        self.detect_plate_upload_duration_seconds.observe(self._to_seconds(upload_ms))
        self.detect_plate_duration_seconds.observe(self._to_seconds(total_ms))

    def mark_overload(self) -> None:
        self.inference_overload_total.inc()

    def mark_upload_failure(self) -> None:
        self.upload_failure_total.inc()

    def inference_start(self) -> None:
        self.inference_inflight.inc()

    def inference_done(self) -> None:
        self.inference_inflight.dec()

    def render_latest(self) -> tuple[bytes, str]:
        return generate_latest(self.registry), CONTENT_TYPE_LATEST


default_metrics = LPRMetrics()