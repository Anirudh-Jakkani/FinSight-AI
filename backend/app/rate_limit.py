"""Rate limiting (Phase 8.5): sensible per-IP/per-user limits on authentication and
compute/quota-expensive endpoints. A production-readiness audit found none of this
existed — /auth/login and /auth/signup were completely unthrottled (brute-force
password guessing, mass account creation), and the AI/ML/upload endpoints had no
protection against a single account hammering them (this project has hit
OpenRouter's free-tier quota repeatedly from normal testing alone).

Uses slowapi (an in-memory, single-process limiter by default). That's the right
fit for how this app actually runs (one uvicorn process, no --workers); it is a
real limitation worth stating plainly: a multi-worker/multi-process deployment
would need slowapi's Redis storage backend instead, since each worker would
otherwise keep its own independent counter.

Two rate-limit keys are used, chosen per endpoint:
- Client IP (slowapi's default `get_remote_address`) for the auth endpoints,
  where there is no authenticated identity yet — this is exactly the surface
  the audit flagged.
- The authenticated user's id, decoded from the Authorization header on a
  best-effort basis, for endpoints that already require login. Keying by user
  rather than IP means multiple users behind one NAT/office IP don't throttle
  each other, and one user can't dodge their own limit by rotating IPs. Falls
  back to IP if no valid token is present (the route's own auth dependency is
  what actually enforces login is required; this is only a limiting key).
"""
from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.services.auth import AuthError, decode_access_token


def rate_limit_key(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
        try:
            payload = decode_access_token(token)
            return f"user:{payload['sub']}"
        except AuthError:
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=rate_limit_key)
