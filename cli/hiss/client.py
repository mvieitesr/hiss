"""HTTP client layer — base URL resolution and error envelope mapping.

Centralizes the thin-client concerns so command groups stay trivial.
Zero domain logic: no validation, just HTTP + error mapping.
"""

from __future__ import annotations

import os
from urllib.parse import quote

import httpx
import typer

DEFAULT_URL = "http://localhost:8000"
API_PREFIX = "/api/v1"


def path_segment(value: str | int) -> str:
    """Encode a single dynamic URL path segment."""
    return quote(str(value), safe="")


def get_base_url(ctx_url: str | None) -> str:
    """Resolve base URL with precedence: --url flag > HISS_URL env > default.

    Strips trailing slash for consistent prefix building.
    """
    if ctx_url:
        # Typer passes the flag value (or envvar value via callback);
        # non-empty string wins.
        return ctx_url.rstrip("/")
    env_url = os.getenv("HISS_URL")
    if env_url:
        return env_url.rstrip("/")
    return DEFAULT_URL


def get_base_url_for_ctx(ctx: typer.Context | None) -> str:
    """Convenience: extract url from Typer context object."""
    ctx_url = None
    if ctx is not None and hasattr(ctx, "obj") and isinstance(ctx.obj, dict):
        ctx_url = ctx.obj.get("url")
    return get_base_url(ctx_url)


def get_client(ctx: typer.Context | None = None, base_url: str | None = None) -> httpx.Client:
    """Create httpx client configured for the hiss API.

    Either pass an explicit base_url or a Typer ctx from which the URL
    is resolved via get_base_url_for_ctx. When both given, base_url wins.
    Timeout 10s, no auth (ADR-0002).
    """
    if base_url is None:
        base_url = get_base_url_for_ctx(ctx)
    # httpx.Client base_url handles trailing slash; we pass stripped.
    return httpx.Client(base_url=base_url, timeout=10.0)


def handle_response(resp: httpx.Response) -> any:
    """Map API error envelope to stderr + Exit(1), or return JSON on success.

    Error envelope from app/app/api/errors.py is always
    {"error": "<code>", "message": "<text>"} with status 400/404/409.
    On success (2xx) return resp.json() (or None if body empty).
    On error print the API message verbatim to stderr.
    """
    if resp.is_success:
        # 204 etc. has no body
        if resp.status_code == 204:
            return None
        try:
            return resp.json()
        except Exception:
            return None

    # Error path — try to extract message verbatim
    msg: str
    try:
        data = resp.json()
        # Prefer `message` field verbatim, fallback to `error`
        if isinstance(data, dict):
            msg = data.get("message") or data.get("error") or str(data)
        else:
            msg = str(data)
    except Exception:
        # Non-JSON error body
        text = resp.text.strip()
        msg = text if text else f"HTTP {resp.status_code}"

    typer.echo(f"Error: {msg}", err=True)
    raise typer.Exit(code=1)


def handle_request_error(exc: Exception, base_url: str) -> None:
    """Map httpx transport errors (ConnectError, Timeout, etc.) to stderr + Exit(1)."""
    typer.echo(f"Error: could not connect to {base_url}: {exc}", err=True)
    raise typer.Exit(code=1)


def api_url(base_url: str, path: str) -> str:
    """Build full API URL (alternative helper when not using Client base_url)."""
    base = get_base_url(base_url).rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    if not path.startswith(API_PREFIX):
        path = API_PREFIX + path
    return base + path
