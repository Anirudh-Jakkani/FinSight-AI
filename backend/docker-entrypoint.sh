#!/bin/sh
# Phase 8.8: container startup. Applies any pending Alembic migrations (Phase 8.7,
# app/db/migrations/) before serving traffic, so a deploy that includes a schema
# change never runs against a stale schema. Safe on every boot — `alembic upgrade
# head` is a no-op once the database is already at head.
set -e

alembic upgrade head

# A single uvicorn process, deliberately no --workers: app/rate_limit.py's slowapi
# limiter is in-memory and per-process, so multiple workers would each keep their
# own independent counters and silently weaken the auth rate limits (see that
# file's docstring). $PORT is honored for platforms that inject it (Render,
# Railway, Heroku-style); it defaults to 8000 to match docker-compose.yml.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
