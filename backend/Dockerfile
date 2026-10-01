# Phase 8.8: production image for the FastAPI backend. Packaging only — the
# application code is unchanged by this phase; see docs/deployment.md for the
# full deployment guide and the environment variables production must set.
#
# Pinned to the same Python version this project is developed and tested against
# (see requirements.txt's pinning rationale) to avoid any version skew between the
# image and what's actually been run.
FROM python:3.14.7-slim

WORKDIR /app

# ca-certificates: the AI assistant (app/services/ai_assistant.py) calls OpenRouter
# over HTTPS; slim base images don't guarantee an up-to-date CA bundle otherwise.
RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer cached separately from app code: editing app/ never forces a
# reinstall of pandas/numpy/scikit-learn/etc.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY app ./app
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

# Runs as an unprivileged user — this app never needs root inside the container.
RUN useradd --create-home --no-log-init appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Matches the app's own /health endpoint (app/main.py) — reports process liveness
# only, not DB connectivity (that's /health/db, deliberately not used here: an
# orchestrator restarting this container on a transient DB outage would not help).
#
# Reads $PORT rather than the EXPOSEd 8000: Render (Phase 8.9) assigns its own PORT
# (default 10000) that docker-entrypoint.sh binds uvicorn to, which would otherwise
# leave this probing the wrong port and reporting unhealthy forever on that platform.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:' + os.environ.get('PORT','8000') + '/health', timeout=3)" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
