import os
import logging
from dataclasses import dataclass

import httpx


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HTTPClientConfig:
    max_connections: int
    max_keepalive_connections: int
    keepalive_expiry_sec: float
    timeout_sec: float


def _int_env(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = os.getenv(name, "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(max_value, value))


def _float_env(name: str, default: float, min_value: float, max_value: float) -> float:
    raw = os.getenv(name, "")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(max_value, value))


def build_http_client_config() -> HTTPClientConfig:
    return HTTPClientConfig(
        max_connections=_int_env("LPR_S3_MAX_CONNECTIONS", 20, 1, 200),
        max_keepalive_connections=_int_env("LPR_S3_MAX_KEEPALIVE_CONNECTIONS", 10, 1, 100),
        keepalive_expiry_sec=_float_env("LPR_S3_KEEPALIVE_EXPIRY_SEC", 10.0, 1.0, 120.0),
        timeout_sec=_float_env("LPR_S3_TIMEOUT_SEC", 15.0, 1.0, 120.0),
    )


def create_http_client(config: HTTPClientConfig | None = None) -> httpx.AsyncClient:
    cfg = config or build_http_client_config()
    limits = httpx.Limits(
        max_connections=cfg.max_connections,
        max_keepalive_connections=cfg.max_keepalive_connections,
        keepalive_expiry=cfg.keepalive_expiry_sec,
    )
    try:
        return httpx.AsyncClient(limits=limits, timeout=cfg.timeout_sec, http2=True)
    except ImportError as exc:
        if "h2" not in str(exc).lower():
            raise
        logger.warning("h2 package is not installed; falling back to HTTP/1.1 for S3 client")
        return httpx.AsyncClient(limits=limits, timeout=cfg.timeout_sec, http2=False)
