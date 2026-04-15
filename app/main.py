from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Response
from app.routes import plate
from app.services.http_client import build_http_client_config, create_http_client
from app.services.metrics import default_metrics

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = build_http_client_config()
    logger.info(
        "http client config max_connections=%s keepalive=%s keepalive_expiry_sec=%s timeout_sec=%s",
        cfg.max_connections,
        cfg.max_keepalive_connections,
        cfg.keepalive_expiry_sec,
        cfg.timeout_sec,
    )
    app.state.http_client = create_http_client(cfg)
    yield
    await app.state.http_client.aclose()


app = FastAPI(
    title="Parking OCR API",
    description="License plate detection service using ALPR",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(plate.router)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    payload, content_type = default_metrics.render_latest()
    return Response(content=payload, media_type=content_type)
