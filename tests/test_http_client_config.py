import os
import unittest

from app.services.http_client import build_http_client_config


class TestHTTPClientConfig(unittest.TestCase):
    def test_default_values(self) -> None:
        with _patched_env({}):
            cfg = build_http_client_config()
        self.assertEqual(20, cfg.max_connections)
        self.assertEqual(10, cfg.max_keepalive_connections)
        self.assertEqual(10.0, cfg.keepalive_expiry_sec)
        self.assertEqual(15.0, cfg.timeout_sec)

    def test_invalid_values_fallback_to_defaults(self) -> None:
        with _patched_env(
            {
                "LPR_S3_MAX_CONNECTIONS": "bad",
                "LPR_S3_MAX_KEEPALIVE_CONNECTIONS": "bad",
                "LPR_S3_KEEPALIVE_EXPIRY_SEC": "bad",
                "LPR_S3_TIMEOUT_SEC": "bad",
            }
        ):
            cfg = build_http_client_config()
        self.assertEqual(20, cfg.max_connections)
        self.assertEqual(10, cfg.max_keepalive_connections)
        self.assertEqual(10.0, cfg.keepalive_expiry_sec)
        self.assertEqual(15.0, cfg.timeout_sec)

    def test_out_of_range_values_are_clamped(self) -> None:
        with _patched_env(
            {
                "LPR_S3_MAX_CONNECTIONS": "9999",
                "LPR_S3_MAX_KEEPALIVE_CONNECTIONS": "0",
                "LPR_S3_KEEPALIVE_EXPIRY_SEC": "500",
                "LPR_S3_TIMEOUT_SEC": "0.1",
            }
        ):
            cfg = build_http_client_config()
        self.assertEqual(200, cfg.max_connections)
        self.assertEqual(1, cfg.max_keepalive_connections)
        self.assertEqual(120.0, cfg.keepalive_expiry_sec)
        self.assertEqual(1.0, cfg.timeout_sec)


class _patched_env:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.original = {}

    def __enter__(self):
        keys = {
            "LPR_S3_MAX_CONNECTIONS",
            "LPR_S3_MAX_KEEPALIVE_CONNECTIONS",
            "LPR_S3_KEEPALIVE_EXPIRY_SEC",
            "LPR_S3_TIMEOUT_SEC",
        }
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
