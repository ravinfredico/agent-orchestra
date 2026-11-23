"""Auth for the API. Off on localhost without APP_TOKEN; required everywhere else.

When APP_TOKEN is set: POST /api/login with the token sets an HttpOnly cookie. Every /api route
accepts that cookie or `Authorization: Bearer <token>`. A cookie is needed because the browser's
EventSource (SSE) can't send headers.
"""

import hmac
import os

from fastapi import HTTPException, Request

COOKIE = "chacha_token"
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def app_token() -> str | None:
    return os.environ.get("APP_TOKEN") or None


def check_host(host: str) -> None:
    """Refuse to listen beyond this machine without a token."""
    if host not in LOOPBACK and not app_token():
        raise SystemExit(f"Refusing to listen on {host} without APP_TOKEN. Set APP_TOKEN, or use 127.0.0.1.")


def token_ok(given: str | None) -> bool:
    expected = app_token()
    return bool(given) and expected is not None and hmac.compare_digest(given, expected)


async def require_auth(request: Request) -> None:
    if not app_token():
        return
    given = request.cookies.get(COOKIE)
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        given = given if token_ok(given) else header[7:].strip()
    if not token_ok(given):
        raise HTTPException(status_code=401, detail="Sign in required")
