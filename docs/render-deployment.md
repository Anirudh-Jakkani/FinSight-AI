# Deploying to Render (Phase 8.9)

`render.yaml` (repo root) is a Render Blueprint that provisions all three pieces in
one go: the FastAPI backend (from `backend/Dockerfile`), a static site for
`frontend/`, and a managed PostgreSQL database. This is Render-specific; for the
generic Docker/production picture (required env vars, the single-process rate
limiter, etc.) see `docs/deployment.md` first — everything there still applies.

## Deploy

1. Push this repo to GitHub (already done — see `docs/`).
2. Render dashboard → **New > Blueprint** → pick this repo. Render reads
   `render.yaml` and shows all three resources it's about to create.
3. You'll be prompted for every `sync: false` env var: set **`OPENROUTER_API_KEY`**
   to a real key from openrouter.ai. `JWT_SECRET_KEY` is *not* prompted — it's
   generated automatically (`generateValue: true`) and never has to be typed in.
4. Click Apply. Render builds the Docker image, provisions Postgres, and publishes
   the static site.

## Live URLs

Render assigns `*.onrender.com` names at creation time (they're globally unique
across all of Render, so the literal names in this file aren't guaranteed free —
`finsight-api` and `finsight-frontend` were both already taken when this was first
deployed). The actual assigned hostnames are:

- API: `https://finsight-api-pfqj.onrender.com`
- Frontend: `https://finsight-frontend-6gts.onrender.com`

`render.yaml` is already updated to match: `finsight-api`'s `CORS_ALLOWED_ORIGINS`
points at the frontend URL, and `finsight-frontend`'s three `routes` destinations
point at the API URL. **If either service is ever deleted and recreated** (not a
normal redeploy — pushing to the connected branch redeploys in place and keeps the
same hostname), Render may assign a different hostname, and both spots above need
updating again to match — via the dashboard (Environment tab / Redirects & Rewrites
tab) or by editing `render.yaml` and pushing. Symptom if this ever drifts: the
frontend's rewrite proxy 404s (wrong backend host) even though both services show
as deployed successfully.

## Why the frontend needs no code changes

`frontend/js/api.js` calls relative paths (`/api/v1/...`) and has always relied on
being served from the same origin as the API — locally via `frontend/serve.py`'s
proxy, in this deployment via the `routes` rewrites in `render.yaml` (same prefixes
that script proxies: `/api/*` and `/health*`). Render performs the rewrite
server-side, so the browser only ever sees the frontend's own origin — the API call
is same-origin as far as the browser and CORS are concerned, same as local dev.
`CORS_ALLOWED_ORIGINS` is still set correctly as defense-in-depth (e.g. for direct
`/docs` access against the API's own URL), just not load-bearing for the proxied
frontend calls.

## The DATABASE_URL Render provides

Render's managed Postgres hands out connection strings as `postgres://...`.
SQLAlchemy has not recognized that bare `postgres` scheme since 1.4 (`NoSuchModuleError`)
— `app/config.py`'s `Settings.database_url` validator (Phase 8.9) normalizes it (and
bare `postgresql://`) to `postgresql+psycopg2://` before anything else sees it, so
`fromDatabase`'s generated value just works with no manual edits. Covered by
`backend/tests/test_config.py`.

## Everything from docs/deployment.md still applies

Same single-process constraint (Render's free plan only ever runs one instance
anyway, so this is automatically satisfied there), same migrate-on-boot behavior,
same ML-model-is-not-baked-in caveat — the `app/ml/models/` directory has no
persistent volume on Render the way `docker-compose.yml`'s local volume gives it,
so a model trained via `POST /api/v1/ml/train` is lost on the next deploy or
cold-start spin-down and must be retrained.
