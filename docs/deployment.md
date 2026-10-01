# Deployment (Phase 8.8)

Packaging and server configuration for running the backend in production. The
application itself is unchanged by this phase — this only covers how to run it.

Deploying specifically to Render? See `docs/render-deployment.md` (Phase 8.9) for a
one-file Blueprint that provisions the API, frontend, and database together —
everything below still applies there too.

## Image

`backend/Dockerfile` builds a single self-contained image: Python deps, the app
code, and `backend/alembic.ini` + `app/db/migrations/`. `backend/docker-entrypoint.sh`
runs `alembic upgrade head` on every boot (a no-op once already current, see Phase
8.7) and then starts the server — so a deploy that includes a schema change is
always applied before traffic is served, and a deploy that doesn't is a cheap no-op.

```bash
docker compose up -d --build   # db + api, for local/staging parity testing
```

`docker-compose.yml`'s `api` service overrides `DATABASE_URL` to point at the `db`
service by name instead of `localhost` (which `backend/.env` uses, correct for a
backend running natively on the host, but meaningless inside the compose network).
Everything else (API keys, JWT secret, CORS origins) comes from `backend/.env` via
`env_file` — that file is still never committed (see Phase 8.7/.gitignore).

## Required environment variables in production

All read from `backend/app/config.py`; set these as real environment variables
(container platform secrets, not a committed file) rather than relying on defaults:

| Variable | Why it matters in production |
|---|---|
| `DATABASE_URL` | Must point at the real production database. |
| `JWT_SECRET_KEY` | Must be set to a real secret. Empty is refused by design (`app/services/auth.py`) rather than falling back to a guessable default — auth simply won't issue or verify tokens until this is set. |
| `CORS_ALLOWED_ORIGINS` | Must list the real deployed frontend origin(s). Never `"*"` — this app sends `Authorization` headers, and a wildcard origin with credentials is unsafe regardless. |
| `OPENROUTER_API_KEY` | Required for the AI assistant (Phase 4.1); its absence degrades only that feature, not the rest of the app. |
| `LOG_LEVEL` | `INFO` is a sensible production default; logs go to stdout for the platform/runtime to capture (Phase 8.2). |

## Server: one process, by design

The container's `CMD` is a single `uvicorn` process — no `--workers`, no Gunicorn.
This is deliberate, not a placeholder: `app/rate_limit.py`'s limiter (slowapi) keeps
its counters in-memory, scoped to one process. Running multiple workers or
replicas, each with its own independent counters, would silently weaken the
auth/AI/upload rate limits the Phase 8.5 audit added, without changing any visible
behavior until under attack. Scale this deployment vertically (more CPU/memory to
the one process) until the limiter is moved to a shared backend (slowapi supports
Redis for this); that migration is out of scope for this phase.

## Health checks

- `GET /health` — process liveness only. Used by the image's own `HEALTHCHECK` and
  is the right one for an orchestrator's liveness/restart probe.
- `GET /health/db` — also checks database connectivity. Use this for a *readiness*
  probe (don't route traffic here yet) rather than a liveness probe (don't restart
  the app over a transient database blip it can recover from on its own).

## The ML classifier model is not baked into the image

`app/ml/models/*.joblib` is excluded from both the git repo and the Docker build
context (same reasoning in `.gitignore` and `backend/.dockerignore`: it's a
training artifact, not source). `app/ml/predict.py` already handles its absence
cleanly (`ModelNotTrainedError`, directing to `POST /api/v1/ml/train`) — this is
existing behavior, not new. Operational implication: on an ephemeral/read-only
container filesystem, a trained model is lost on restart or redeploy and must be
retrained. `docker-compose.yml` mounts `backend/app/ml/models/` as a volume so this
isn't an issue for local/staging compose use; a real deployment should do the
same (or retrain as a post-deploy step) if this feature is used.

## Frontend

`frontend/` is static files with no build step — any static host works, as long as
its origin is added to `CORS_ALLOWED_ORIGINS`. `frontend/serve.py` is a local dev
convenience (its same-origin proxy trick) and isn't meant for production use.
