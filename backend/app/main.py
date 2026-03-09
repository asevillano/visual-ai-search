"""FastAPI application — entry point."""

import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.config import get_settings
from app.routers import upload, search, documents
from app.services import blob_storage as blob_svc
from app.services import search_index as idx_svc
from app.services import search as search_svc
from app.services import vision as vision_svc
from app.services import openai_embeddings as openai_svc
from app.services import gpt_analysis as gpt_svc

# ---------------------------------------------------------------------------
# Logging configuration  (applied once at import time)
# ---------------------------------------------------------------------------
_LOG_FMT = "%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s"
_LOG_DATEFMT = "%H:%M:%S"

# Ensure logs directory exists
_LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")

# Root logger: console + rotating file
from logging.handlers import RotatingFileHandler

_console = logging.StreamHandler()
_console.setFormatter(logging.Formatter(_LOG_FMT, datefmt=_LOG_DATEFMT))

_file = RotatingFileHandler(_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
_file.setFormatter(logging.Formatter(_LOG_FMT, datefmt="%Y-%m-%d %H:%M:%S"))

logging.basicConfig(level=logging.INFO, handlers=[_console, _file])

# Quiet noisy third-party loggers
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("azure.identity").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger("app.main")
logger.info("Log file → %s", os.path.abspath(_LOG_FILE))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("===== Application starting up =====")
    t0 = time.perf_counter()
    try:
        # Sync services
        blob_svc.init()
        idx_svc.init()          # SearchIndexClient + ensure index
        search_svc.init()       # async SearchClient (queries)
        upload.init()           # sync SearchClient  (upserts)
        documents.init()        # sync SearchClient  (list/delete)

        # Async services — credential + token warm-up
        await openai_svc.init()     # AsyncAzureOpenAI + token warm-up (embeddings)
        await gpt_svc.init()        # AsyncAzureOpenAI + token warm-up (GPT-4.1 vision)
        await vision_svc.init()     # httpx + token + connection warm-up

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("===== All services ready (%.0f ms) =====", elapsed)
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        logger.error("Startup FAILED after %.0f ms: %s", elapsed, e, exc_info=True)
        raise
    yield
    logger.info("===== Application shutting down =====")
    await vision_svc.close()
    await search_svc.close()
    await openai_svc.close()
    await gpt_svc.close()
    blob_svc.close()
    logger.info("===== Shutdown complete =====")


app = FastAPI(
    title="Visual AI Search",
    description="Image search with Azure AI Vision + Azure OpenAI dual vectorization",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response logging middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    logger.info("→ %s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "← %s %s — %d (%.0f ms)",
            request.method, request.url.path, response.status_code, elapsed_ms,
        )
        return response
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error(
            "← %s %s — EXCEPTION (%.0f ms): %s",
            request.method, request.url.path, elapsed_ms, exc, exc_info=True,
        )
        raise


# Routers
app.include_router(upload.router)
app.include_router(search.router)
app.include_router(documents.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "visual-ai-search"}


@app.get("/api/config")
async def frontend_config():
    """Public configuration for the frontend."""
    s = get_settings()
    return {"search_strategy": s.search_strategy}


# Serve frontend static files in production
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
