import os
import unittest
from unittest.mock import patch

from app.services.http_client import HTTPClientConfig, build_http_client_config, create_http_client


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


class TestCreateHTTPClient(unittest.TestCase):
    def test_create_http_client_uses_http2_when_available(self) -> None:
        cfg = HTTPClientConfig(20, 10, 10.0, 15.0)
        sentinel = object()

        with patch("app.services.http_client.httpx.AsyncClient", return_value=sentinel) as mock_client:
            result = create_http_client(cfg)

        self.assertIs(sentinel, result)
        self.assertEqual(1, mock_client.call_count)
        self.assertTrue(mock_client.call_args.kwargs["http2"])

    def test_create_http_client_falls_back_to_http1_when_h2_missing(self) -> None:
        cfg = HTTPClientConfig(20, 10, 10.0, 15.0)
        sentinel = object()

        with patch(
            "app.services.http_client.httpx.AsyncClient",
            side_effect=[ImportError("Using http2=True, but the 'h2' package is not installed."), sentinel],
        ) as mock_client:
            result = create_http_client(cfg)

        self.assertIs(sentinel, result)
        self.assertEqual(2, mock_client.call_count)
        self.assertTrue(mock_client.call_args_list[0].kwargs["http2"])
        self.assertFalse(mock_client.call_args_list[1].kwargs["http2"])

    def test_create_http_client_reraises_unrelated_import_error(self) -> None:
        cfg = HTTPClientConfig(20, 10, 10.0, 15.0)

        with patch(
            "app.services.http_client.httpx.AsyncClient",
            side_effect=ImportError("unexpected import error"),
        ):
            with self.assertRaises(ImportError):
                create_http_client(cfg)


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
