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

## Required manual step after the first deploy

`render.yaml` can't know your services' final `*.onrender.com` names in advance —
those names are globally unique across all of Render, so if `finsight-api` or
`finsight-frontend` is already taken, Render assigns a different one (e.g.
`finsight-api-ab12`). Two places in `render.yaml` hardcode the placeholder names and
**must be updated to match what Render actually assigned**, via Render's dashboard
(Environment tab / Redirects & Rewrites tab — editing there is equivalent to
editing the file and redeploying) or by editing `render.yaml` and pushing again:

- `finsight-api`'s `CORS_ALLOWED_ORIGINS` env var → the frontend's real URL.
- `finsight-frontend`'s three `routes` → each `destination`'s host → the backend's
  real URL.

Until this is corrected, the frontend's rewrite proxy will 404 (wrong backend host)
even though both services deployed successfully — if API calls fail right after a
first deploy, check this first.

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
