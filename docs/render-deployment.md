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

## Seeding the demo account

`backend/app/db/seed_demo.py` creates the existing demo user/account (locally:
`phase22-test@example.com`, account "Test Checking") and imports the verified
90-row sample dataset into it, through the real migrations → ingestion →
merchant-cleaning → rule/ML-categorization pipeline (`app/services/pipeline.py`'s
`run_pipeline` — nothing reimplemented). It's idempotent and strictly additive: safe
to run once, safe to run again (0 rows the second time), and — proven while building
this — safe to run against a database that already has this exact data, including
this project's own local dev database, without duplicating or altering anything
there. See the module's own docstring and `backend/tests/test_seed_demo.py` for the
detail; **the command below only ever needs to be run against Render's database**,
not locally.

```
python -m app.db.seed_demo
```

**`finsight-api` is on the free compute plan**, which does not support Render's
Shell tab or the Jobs API/CLI (both require a paid plan) — so the way to run this is
to temporarily override the container's command, not open a shell:

1. Render dashboard → `finsight-api` → **Settings** → **Advanced** → **Docker
   Command** → set it to `python -m app.db.seed_demo` → Save (triggers a redeploy).
2. Open the **Logs** tab and watch for this container's output — it prints what it
   did (user/account id, rows inserted vs. already-present, categorization counts)
   and then the container exits, since it isn't launching the server this time.
   `docker-entrypoint.sh` still runs `alembic upgrade head` first either way.
3. **Clear the Docker Command field back to empty** and Save again — this redeploys
   with the default command (`docker-entrypoint.sh`'s own `exec uvicorn ...`) so the
   service goes back to actually serving traffic. Until you do this, the service
   has no running web process.

If `finsight-api` is ever upgraded to a paid plan, Render's one-off Jobs (`render
jobs create <serviceID> --start-command "python -m app.db.seed_demo"`, or the
equivalent `POST /v1/services/<serviceID>/jobs` API call) is a cleaner alternative —
it doesn't touch the live service's running command at all, so there's no step 3.

By default the demo user has no password (same as any user created before Phase
7.1: its data is there, it just can't log in until one is set) — nothing is ever
hardcoded. To make the demo account loggable-into from the frontend, set
**`DEMO_USER_PASSWORD`** as a real environment variable on `finsight-api` (dashboard
→ Environment tab, not `render.yaml`, so it's never committed) *before* running the
seed command — it's read once, only when the user doesn't already exist.

## Everything from docs/deployment.md still applies

Same single-process constraint (Render's free plan only ever runs one instance
anyway, so this is automatically satisfied there), same migrate-on-boot behavior,
same ML-model-is-not-baked-in caveat — the `app/ml/models/` directory has no
persistent volume on Render the way `docker-compose.yml`'s local volume gives it,
so a model trained via `POST /api/v1/ml/train` is lost on the next deploy or
cold-start spin-down and must be retrained.
