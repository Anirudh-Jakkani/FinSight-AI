"""FastAPI entrypoint. Routers are registered here as phases add them."""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.api.ai_assistant import router as ai_assistant_router
from app.api.analytics import router as analytics_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.forecast import router as forecast_router
from app.api.insights import router as insights_router
from app.api.ml import router as ml_router
from app.api.pipeline import router as pipeline_router
from app.api.snapshots import router as snapshots_router
from app.api.transactions import router as transactions_router
from app.config import settings
from app.db.database import engine
from app.logging_config import setup_logging
from app.rate_limit import limiter

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="FinSight AI", version="0.1.0",
              description="Educational personal-finance analytics. Not financial advice.")

# Phase 8.5: production-readiness audit found no rate limiting anywhere — auth
# endpoints were open to brute-force/mass-signup, and AI/ML/upload endpoints had
# no protection against a single account exhausting quota or CPU. See
# app/rate_limit.py for the limiter itself and the per-endpoint decorators.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Phase 8.2: production-readiness audit found no CORS policy configured anywhere.
# Origins are explicit and env-configurable (never "*") — see app/config.py's
# cors_allowed_origins docstring. The local dev proxy (frontend/serve.py) still
# works exactly as before regardless of this; it just also makes the backend
# correct on its own for a caller that's genuinely on a different origin.
_cors_origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transactions_router)
app.include_router(analytics_router)
app.include_router(insights_router)
app.include_router(snapshots_router)
app.include_router(forecast_router)
app.include_router(ai_assistant_router)
app.include_router(chat_router)
app.include_router(ml_router)
app.include_router(pipeline_router)
app.include_router(auth_router)

logger.info("FinSight AI configured: cors_origins=%s log_level=%s", _cors_origins, settings.log_level)


# Phase 8.2: previously an unhandled exception in any endpoint fell through to
# Starlette's default handling with nothing logged anywhere — a 500 in
# production would have been completely invisible. This logs the full
# traceback server-side while still never leaking internals to the client.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # exc_info=exc (not logger.exception()) — this handler isn't itself inside an
    # active except block, so sys.exc_info() isn't reliably populated here; passing
    # the exception object explicitly is the correct way to log its traceback.
    logger.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db():
    """Reports DB connectivity without leaking connection details or stack traces
    to the caller — but (Phase 8.2) now actually logs the failure server-side
    instead of silently swallowing it, so an outage is no longer invisible."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"database": "up"}
    except Exception:
        logger.exception("Database health check failed")
        return {"database": "down"}
