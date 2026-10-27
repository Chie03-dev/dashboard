import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from app.cache import is_available as redis_available
from app.config import REDIS_URL
from app.db import get_conn, init_db
from app.http_clients import close_all_clients
from app.logging_conf import set_correlation_id, get_logger, setup_logging
from app.routes import chat, dev, digest, games, settings

setup_logging(json_format=False)
logger = get_logger(__name__)

SYNC_DURATION = Histogram("dashboard_sync_duration_seconds", "Sync job duration", ["job"])
LLM_TOKENS_USED = Counter("dashboard_llm_tokens_used_total", "LLM tokens used", ["model"])
CACHE_HITS = Counter("dashboard_cache_hits_total", "Cache hits", ["cache"])
CACHE_MISSES = Counter("dashboard_cache_misses_total", "Cache misses", ["cache"])
DB_QUERIES = Counter("dashboard_db_queries_total", "Database queries", ["operation"])
HTTP_REQUESTS = Counter("dashboard_http_requests_total", "HTTP requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("dashboard_http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Application started")
    yield
    close_all_clients()
    logger.info("Application shutdown")


app = FastAPI(title="Personal Dashboard", lifespan=lifespan)


@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())[:8]
    set_correlation_id(cid)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    return response


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    HTTP_REQUESTS.labels(method=request.method, endpoint=request.url.path, status=response.status_code).inc()
    REQUEST_LATENCY.labels(method=request.method, endpoint=request.url.path).observe(duration)
    return response


@app.get("/healthz")
def healthz():
    """Health check endpoint with dependency verification."""
    checks = {}
    overall = "healthy"

    # Database check
    try:
        conn = get_conn()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        overall = "unhealthy"

    # Redis check
    if REDIS_URL:
        if redis_available():
            checks["redis"] = "ok"
        else:
            checks["redis"] = "unavailable"
            overall = "degraded"
    else:
        checks["redis"] = "not configured"

    return {"status": overall, "checks": checks, "timestamp": time.time()}


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(games.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(dev.router, prefix="/api")
app.include_router(digest.router, prefix="/api")
app.include_router(settings.router, prefix="/api")

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/", StaticFiles(directory="static", html=True), name="root")