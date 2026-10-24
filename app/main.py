from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import logging
from pathlib import Path
import re
import shutil
from typing import Dict, List, Optional
import uuid

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.config import settings
from app.db.database import get_db, init_db
from app.schemas import ErrorDetail, ErrorResponse
from app.security import SecurityValidationError
from app.services.video_composer import video_composer
from app.services.worker import background_worker
from app.storage import InvalidStateTransitionError, job_store

logger = logging.getLogger("video_engine")

# Context variable for request correlation tracing
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")


class SecretMaskingFilter(logging.Filter):
    """Masks authorization tokens, API keys, and sensitive parameters in log records."""
    SECRET_PATTERNS = [
        (re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE), r"\1[MASKED]"),
        (re.compile(r"([?&](?:api_key|token|key|secret)=)[^&\s]+", re.IGNORECASE), r"\1[MASKED]"),
        (re.compile(r"(PEXELS_API_KEY\s*[:=]\s*)[^\s,]+", re.IGNORECASE), r"\1[MASKED]"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pat, repl in self.SECRET_PATTERNS:
                record.msg = pat.sub(repl, record.msg)
        return True


class CorrelationIdFilter(logging.Filter):
    """Injects current correlation ID into log records."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_ctx.get() or "none"
        return True


# Setup logging with record factory so every record always has correlation_id
_old_record_factory = logging.getLogRecordFactory()

def _correlation_record_factory(*args, **kwargs):
    record = _old_record_factory(*args, **kwargs)
    try:
        record.correlation_id = correlation_id_ctx.get() or "none"
    except Exception:
        record.correlation_id = "none"
    return record

logging.setLogRecordFactory(_correlation_record_factory)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [CID:%(correlation_id)s] %(name)s: %(message)s"
)
root_logger = logging.getLogger()
root_logger.addFilter(CorrelationIdFilter())
root_logger.addFilter(SecretMaskingFilter())
for h in root_logger.handlers:
    h.addFilter(CorrelationIdFilter())
    h.addFilter(SecretMaskingFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure SQLite database and worker are initialized
    init_db()
    await background_worker.start()
    yield
    # Shutdown: gracefully shut down background tasks
    await background_worker.stop()


app = FastAPI(
    title="Script and Voiceover to B-roll Video Engine",
    version="1.0.0",
    lifespan=lifespan,
    description=(
        "Production-grade engine that ingests video scripts, scene plans, and audio narration "
        "to synthesize fully synchronized 1080p B-roll videos, subtitle tracks, timelines, and manifests."
    ),
    openapi_tags=[
        {
            "name": "Video Engine v1",
            "description": "API contracts for render job submission, real-time status/progress tracking, cancellation, and artifact distribution."
        }
    ]
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """
    Extracts or generates an X-Correlation-ID header, propagates it into ContextVar
    for structured logging, and attaches it to the HTTP response headers.
    """
    raw_cid = request.headers.get("X-Correlation-ID", "").strip()
    # Sanitize incoming correlation ID: alphanumeric, dashes, underscores, max 64 chars
    if raw_cid and re.match(r"^[A-Za-z0-9_\-]{1,64}$", raw_cid):
        cid = raw_cid
    else:
        cid = str(uuid.uuid4())

    token = correlation_id_ctx.set(cid)
    try:
        response: Response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        logger.error(f"Unhandled server error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers={"X-Correlation-ID": cid},
            content=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                message="An unexpected internal server error occurred. Please contact support with the correlation ID.",
                details=[ErrorDetail(code="CORRELATION_ID", message=cid)]
            ).model_dump()
        )
    finally:
        correlation_id_ctx.reset(token)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = []
    for err in exc.errors():
        field_loc = " -> ".join(str(loc) for loc in err.get("loc", []))
        details.append(ErrorDetail(
            code=err.get("type", "VALIDATION_ERROR"),
            message=err.get("msg", "Invalid field"),
            field=field_loc
        ))
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error_code="VALIDATION_ERROR",
            message="Request body or query parameter failed schema validation.",
            details=details
        ).model_dump()
    )


@app.exception_handler(SecurityValidationError)
async def security_exception_handler(request: Request, exc: SecurityValidationError):
    status_code = status.HTTP_403_FORBIDDEN if exc.code == "FORBIDDEN_FILE_ACCESS" else status.HTTP_400_BAD_REQUEST
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error_code=exc.code,
            message=exc.message,
            details=[ErrorDetail(code=exc.code, message=exc.message)]
        ).model_dump()
    )


@app.exception_handler(InvalidStateTransitionError)
async def state_transition_exception_handler(request: Request, exc: InvalidStateTransitionError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=ErrorResponse(
            error_code="INVALID_STATE_TRANSITION",
            message=str(exc),
            details=[ErrorDetail(code="INVALID_STATE_TRANSITION", message=str(exc))]
        ).model_dump()
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catches unhandled runtime exceptions, prevents leaking internal filesystem paths or tracebacks,
    logs the diagnostic trace with correlation ID, and returns a sanitized HTTP 500 JSON error.
    """
    if isinstance(exc, HTTPException):
        detail_obj = exc.detail if isinstance(exc.detail, dict) else {
            "error_code": "HTTP_ERROR",
            "message": str(exc.detail)
        }
        return JSONResponse(status_code=exc.status_code, content=detail_obj)

    cid = correlation_id_ctx.get()
    logger.error(f"Unhandled server error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error_code="INTERNAL_SERVER_ERROR",
            message="An unexpected internal server error occurred. Please contact support with the correlation ID.",
            details=[ErrorDetail(code="CORRELATION_ID", message=cid)]
        ).model_dump()
    )



@app.get("/health", summary="Service health check")
def health():
    return health_ready()


@app.get("/health/live", summary="Liveness probe")
def health_live():
    """Fast liveness check verifying the application process is running."""
    return {
        "status": "alive",
        "service": "video-broll-engine",
        "timestamp_utc": datetime.now(timezone.utc).isoformat()
    }


@app.get("/health/ready", summary="Readiness probe")
def health_ready():
    """
    Deep readiness check evaluating:
    1. Database connectivity
    2. Output storage directory write access
    3. Free disk space against configurable threshold (MIN_DISK_FREE_BYTES)
    4. Media pipeline binaries (FFmpeg & FFprobe)
    5. Background worker state
    """
    checks = {}
    is_ready = True

    # 1. Database connectivity
    try:
        with get_db() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok", "message": "Database query succeeded."}
    except Exception as exc:
        checks["database"] = {"status": "failed", "message": str(exc)}
        is_ready = False

    # 2. Output directory write check & disk space
    try:
        test_file = settings.OUTPUT_DIR / ".healthcheck_write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        usage = shutil.disk_usage(str(settings.OUTPUT_DIR))
        has_space = usage.free >= settings.MIN_DISK_FREE_BYTES
        checks["storage"] = {
            "status": "ok" if has_space else "failed",
            "free_bytes": usage.free,
            "threshold_bytes": settings.MIN_DISK_FREE_BYTES,
            "writable": True
        }
        if not has_space:
            is_ready = False
    except Exception as exc:
        checks["storage"] = {"status": "failed", "message": str(exc), "writable": False}
        is_ready = False

    # 3. Media binaries
    ffmpeg_ok = video_composer.is_ffmpeg_available()
    ffprobe_ok = video_composer.is_ffprobe_available()
    checks["media_binaries"] = {
        "ffmpeg_available": ffmpeg_ok,
        "ffprobe_available": ffprobe_ok
    }
    checks["ffmpeg_installed"] = ffmpeg_ok
    checks["output_storage"] = {
        "writable": checks.get("storage", {}).get("writable", False)
    }

    # 4. Background worker
    worker_active = background_worker._running
    checks["worker"] = {
        "status": "ok" if worker_active else "failed",
        "active": worker_active
    }
    if not worker_active:
        is_ready = False

    response_payload = {
        "status": "ready" if is_ready else "not_ready",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checks
    }

    if not is_ready:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=response_payload)
    return response_payload


# Include API v1 Router
app.include_router(api_router)

# Mount output directory for direct artifact access and video streaming
from fastapi.staticfiles import StaticFiles
settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(settings.OUTPUT_DIR)), name="output")
