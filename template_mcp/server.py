"""MCP-Template Server — produktives Skelett.

Enthaelt:
  - FastMCP mit Streamable-HTTP-Transport
  - Dual-Auth-Middleware (Bearer-Token + OAuth-2.1-JWT parallel)
  - Rate-Limit, Audit-Log, Snapshots, OAuth-Routen
  - Boot-Security-Validation (warnt aber crasht nicht)
  - 5 Beispiel-Tools (search, read, list, create, edit)
  - Health-Endpoint

Stelle die Beispiel-Tools nach mit deinen Domain-Tools. Annotations
({readOnlyHint|destructiveHint|idempotentHint}) sind Spec-Pflicht ab
MCP 2025-06-18 — vergiss sie nicht.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from . import __version__, audit, oauth, oauth_routes, ratelimit, snapshot, storage, validators

# ---------- Logging ----------------------------------------------------------

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("template-mcp.server")


# ---------- Config -----------------------------------------------------------

MCP_TOKEN = os.environ.get("MCP_TOKEN", "").strip()
SERVER_NAME = os.environ.get("MCP_SERVER_NAME", "template-mcp")
ALLOWED_ORIGINS = {
    o.strip() for o in os.environ.get("MCP_ALLOWED_ORIGINS", "").split(",") if o.strip()
}
PUBLIC_PATHS = ("/health", "/.well-known/", "/oauth/")


# ---------- Boot Security Validation ----------------------------------------


def _boot_security_check() -> None:
    """Warnt bei schwacher Konfig — crasht nicht (Startup-Resilienz)."""
    warnings: list[str] = []

    if MCP_TOKEN and len(MCP_TOKEN) < 32:
        warnings.append(f"MCP_TOKEN ist nur {len(MCP_TOKEN)} Zeichen — empfohlen >= 32")

    if not MCP_TOKEN and not oauth.is_configured():
        warnings.append("WEDER MCP_TOKEN NOCH OAuth konfiguriert — Server ist OFFEN")

    if oauth.is_configured():
        ok, msg = oauth.is_jwt_secret_strong()
        if not ok:
            warnings.append(f"JWT-Secret schwach: {msg}")
        ok, msg = oauth.is_password_hash_strong()
        if not ok:
            warnings.append(f"Password-Hash schwach: {msg}")

    audit_dir = os.path.dirname(os.environ.get("MCP_AUDIT_LOG", "/var/log/mcp/audit.log"))
    try:
        os.makedirs(audit_dir, exist_ok=True)
        test = os.path.join(audit_dir, ".write-test")
        with open(test, "w") as f:
            f.write("ok")
        os.unlink(test)
    except OSError as e:
        warnings.append(f"Audit-Log-Verzeichnis nicht schreibbar ({audit_dir}): {e}")

    if warnings:
        for w in warnings:
            log.warning("BOOT-CHECK: %s", w)
    else:
        log.info("BOOT-CHECK: alle Security-Checks ok")


# ---------- Auth Middleware --------------------------------------------------


class DualAuthMiddleware(BaseHTTPMiddleware):
    """Versucht JWT (OAuth) zuerst, faellt zurueck auf statisches Bearer-Token."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Public-Paths: kein Auth
        if any(path == p or path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)

        # Origin-Whitelist (DNS-Rebinding-Schutz)
        if ALLOWED_ORIGINS:
            origin = request.headers.get("origin")
            if origin and origin not in ALLOWED_ORIGINS:
                return JSONResponse({"error": "origin_not_allowed"}, status_code=403)

        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return self._unauthorized("missing_bearer")
        token = auth[7:].strip()

        # 1) Versuch: JWT (OAuth)
        if oauth.is_configured():
            claims = oauth.verify_access_token(token)
            if claims:
                request.state.auth = {"kind": "oauth", "sub": claims.get("sub")}
                return await call_next(request)

        # 2) Fallback: statisches Bearer-Token
        if MCP_TOKEN and token == MCP_TOKEN:
            request.state.auth = {"kind": "bearer", "sub": "static"}
            return await call_next(request)

        ip = request.client.host if request.client else None
        audit.log_auth(success=False, client_ip=ip, reason="invalid_bearer")
        return self._unauthorized("invalid_bearer")

    def _unauthorized(self, reason: str) -> Response:
        headers = {
            "WWW-Authenticate": (
                'Bearer realm="mcp", '
                f'resource_metadata="{oauth.OAUTH_ISSUER}/.well-known/oauth-protected-resource"'
            )
        }
        return JSONResponse({"error": "unauthorized", "reason": reason},
                            status_code=401, headers=headers)


# ---------- FastMCP-Setup ----------------------------------------------------

mcp = FastMCP(SERVER_NAME)


def _ok(**fields: Any) -> dict[str, Any]:
    return {"ok": True, **fields}


def _err(message: str, **fields: Any) -> dict[str, Any]:
    """ToolError-konform: enthaelt 'error' + isError=True."""
    return {"ok": False, "isError": True, "error": message, **fields}


# ---------- Beispiel-Tools (5) -----------------------------------------------


@mcp.tool(
    name="search",
    description="Volltext-Regex-Suche durch alle Files. Case-insensitive.",
    annotations={"title": "Search", "readOnlyHint": True, "openWorldHint": False},
)
@audit.time_call
def search(query: str, scope: str = "", max_results: int = 50) -> dict[str, Any]:
    err = validators.validate_query(query)
    if err:
        return _err(err)
    try:
        hits = storage.grep(query, scope=scope, max_results=max_results)
    except storage.StorageError as e:
        return _err(str(e))
    return _ok(hits=hits, count=len(hits))


@mcp.tool(
    name="read_file",
    description="Liest UTF-8 Text-File ab DATA_PATH.",
    annotations={"title": "Read File", "readOnlyHint": True, "openWorldHint": False},
)
@audit.time_call
def read_file(path: str) -> dict[str, Any]:
    err = validators.validate_rel_path(path, must_exist=True)
    if err:
        return _err(err)
    try:
        text = storage.read_text(path)
    except storage.StorageError as e:
        return _err(str(e))
    return _ok(path=path, content=text)


@mcp.tool(
    name="list_files",
    description="Listet Inhalt eines Folders ab DATA_PATH (sortiert).",
    annotations={"title": "List Files", "readOnlyHint": True, "openWorldHint": False},
)
@audit.time_call
def list_files(scope: str = "") -> dict[str, Any]:
    try:
        entries = storage.list_dir(scope)
    except storage.StorageError as e:
        return _err(str(e))
    return _ok(scope=scope or "/", entries=entries)


@mcp.tool(
    name="create_note",
    description="Erstellt ein Text-File. Slug aus title, Path: notes/{date}_{slug}.md",
    annotations={"title": "Create Note", "readOnlyHint": False, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": False},
)
@audit.time_call
def create_note(title: str, body: str = "") -> dict[str, Any]:
    err = validators.validate_title(title) or validators.validate_body(body)
    if err:
        return _err(err)

    slug = storage.slugify(title)
    err = validators.validate_slug_input(slug)
    if err:
        return _err(err)

    rel = f"notes/{storage.today_iso()}_{slug}.md"
    p = storage.safe_path(rel)
    if p.exists():
        return _err(f"File existiert bereits: {rel}")

    content = f"# {title}\n\n{body}\n" if body else f"# {title}\n"
    storage.write_text(rel, content)
    return _ok(path=rel, title=title, slug=slug)


@mcp.tool(
    name="edit_file_replace",
    description="Find-and-Replace in einem File. Snapshot vor Aenderung.",
    annotations={"title": "Edit File (Replace)", "readOnlyHint": False, "destructiveHint": True,
                 "idempotentHint": False, "openWorldHint": False},
)
@audit.time_call
def edit_file_replace(path: str, find: str, replace: str, count: int = 0) -> dict[str, Any]:
    err = validators.validate_rel_path(path, must_exist=True)
    if err:
        return _err(err)
    if not find:
        return _err("find darf nicht leer sein")
    if len(find) > 10_000:
        return _err("find ist zu lang (>10000 Zeichen)")

    try:
        before = storage.read_text(path)
    except storage.StorageError as e:
        return _err(str(e))

    if find not in before:
        return _err(f"Pattern nicht gefunden in {path}")

    if count > 0:
        after = before.replace(find, replace, count)
        replacements = before.count(find)
        replacements = min(replacements, count)
    else:
        after = before.replace(find, replace)
        replacements = before.count(find)

    # Snapshot vor Schreiben
    snap = snapshot.snapshot_path(path, before.encode("utf-8"), op="edit_replace")

    storage.write_text(path, after)
    return _ok(path=path, replacements=replacements, snapshot=snap)


# ---------- Routes -----------------------------------------------------------


async def health(_request: Request) -> JSONResponse:
    """Health-Endpoint — kein Auth, fuer Caddy/Healthcheck/Monitoring."""
    return JSONResponse({
        "status": "ok",
        "version": __version__,
        "server": SERVER_NAME,
        "auth": {
            "bearer": bool(MCP_TOKEN),
            "oauth": oauth.is_configured(),
        },
        "uptime_s": int(time.monotonic() - _START_TS),
    })


# ---------- App-Bau ----------------------------------------------------------

_START_TS = time.monotonic()


def build_app() -> Starlette:
    """Komponiert die ASGI-App.

    Wichtig:
      1. Lifespan reicht den FastMCP-`session_manager` durch — ohne das
         hangen MCP-`initialize`-Calls. Aequivalent zu main MCP server.py.
      2. Mount sowohl `/mcp` ALS AUCH `/mcp/` — manche MCP-Hosts
         (z.B. claude.ai) folgen dem 307-Slash-Redirect nicht und brechen
         die Verbindung dann mit einem POST-Body ab. Plus
         `redirect_slashes = False`.
      3. Middleware-Reihenfolge: RateLimit (outer) → DualAuth → MCP-Mount.
    """
    _boot_security_check()
    audit.log_event("server_start", server=SERVER_NAME, version=__version__)

    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: Starlette):
        async with mcp_app.router.lifespan_context(app):
            yield
        audit.log_event("server_stop", server=SERVER_NAME)

    routes: list[Any] = [Route("/health", health, methods=["GET"])]
    routes.extend(oauth_routes.routes())
    # Beide Pfade: ohne 307-Redirect (claude.ai BETA folgt dem nicht)
    routes.append(Mount("/mcp", app=mcp_app))
    routes.append(Mount("/mcp/", app=mcp_app))

    middleware = [
        Middleware(ratelimit.RateLimitMiddleware),
        Middleware(DualAuthMiddleware),
    ]

    app = Starlette(routes=routes, middleware=middleware, lifespan=lifespan)
    app.router.redirect_slashes = False
    return app


app = build_app()


if __name__ == "__main__":
    # Development-Run: `python -m template_mcp.server`
    import uvicorn

    uvicorn.run(
        "template_mcp.server:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "5002")),
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )
