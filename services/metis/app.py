"""FastAPI uygulama fabrikası: güvenlik başlıkları, Host/Origin denetimi, hata zarfı, SPA."""

from __future__ import annotations

import ipaddress
import logging
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from metis import __version__
from metis.core.audit import correlation_id
from metis.core.config import get_settings
from metis.core.errors import AppError
from metis.core.logging import configure_logging

log = logging.getLogger("metis.api")

API_PREFIX = "/api/v1"


def _client_ip(request: Request) -> str:
    settings = get_settings()
    peer = request.client.host if request.client else ""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded and peer in settings.trusted_proxies:
        return forwarded.split(",")[0].strip()
    return peer


def _route_path(scope: Scope) -> str:
    """Alt yolsuz istek yolu (METIS /metis altında yayınlanınca /metis/api/v1/... → /api/v1/...)."""
    path, root = scope["path"], scope.get("root_path", "")
    if root and (path == root or path.startswith(root + "/")):
        return path[len(root) :] or "/"
    return path


class BasePathMiddleware:
    """METIS_PUBLIC_URL bir yol içeriyorsa (ör. http://sunucu/metis) o ön ekle gelen istekleri uygulamaya kökteymiş gibi
    yönlendirir (ASGI root_path). Kökten gelen istekler de aynen çalışır: süreç yalnız 127.0.0.1'de dinler ve başlatıcı ile
    kurulum betiklerinin sağlık denetimleri köke gider."""

    def __init__(self, app: ASGIApp, prefix: str) -> None:
        self.app, self.prefix = app, prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            path = scope["path"]
            if path == self.prefix or path.startswith(self.prefix + "/"):
                scope = {**scope, "root_path": scope.get("root_path", "") + self.prefix}
        await self.app(scope, receive, send)


def _csp() -> str:
    return (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; "
        "object-src 'none'"
    )


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        settings = get_settings()
        cid = request.headers.get("x-request-id", "")
        if not cid or len(cid) > 64 or not cid.replace("-", "").isalnum():
            cid = uuid.uuid4().hex
        correlation_id.set(cid)
        request.state.correlation_id = cid
        request.state.client_ip = _client_ip(request)

        host = (request.headers.get("host") or "").split(":")[0].strip("[]").lower()
        if host and host not in settings.allowed_hosts:
            return JSONResponse(AppError("FORBIDDEN", "host not allowed").envelope(cid), status_code=400)
        route = _route_path(request.scope)
        if request.method not in ("GET", "HEAD", "OPTIONS") and route.startswith(API_PREFIX):
            origin = request.headers.get("origin")
            allowed = {settings.public_origin}
            if settings.is_dev:
                allowed |= {
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                    "http://localhost:8000",
                    "http://127.0.0.1:8000",
                }
            if origin is not None and origin not in allowed:
                return JSONResponse(AppError("ORIGIN_REJECTED", "origin not allowed").envelope(cid), status_code=403)

        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = cid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = _csp()
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if settings.secure_cookies:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if route.startswith(API_PREFIX):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def _register_errors(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        cid = getattr(request.state, "correlation_id", "")
        if exc.status >= 500:
            log.error("app_error", extra={"code": exc.code, "correlation_id": cid})
        return JSONResponse(exc.envelope(cid), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        cid = getattr(request.state, "correlation_id", "")
        fields = [
            {
                "field": ".".join(str(p) for p in e.get("loc", []) if p not in ("body", "query", "path")),
                "type": e.get("type"),
            }
            for e in exc.errors()
        ]
        return JSONResponse(AppError("VALIDATION_ERROR", "request validation failed", fields=fields).envelope(cid), 422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        cid = getattr(request.state, "correlation_id", "")
        code = "NOT_FOUND" if exc.status_code == 404 else "VALIDATION_ERROR" if exc.status_code < 500 else "INTERNAL"
        return JSONResponse(AppError(code, str(exc.detail), status=exc.status_code).envelope(cid), exc.status_code)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        cid = getattr(request.state, "correlation_id", "")
        log.exception("unhandled", extra={"correlation_id": cid})
        return JSONResponse(AppError("INTERNAL", "internal error").envelope(cid), status_code=500)


_HEAD = re.compile(r"<head(\s[^>]*)?>", re.IGNORECASE)


def _register_spa(app: FastAPI) -> None:
    settings = get_settings()
    static: Path = settings.static_dir

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str, request: Request) -> Response:
        if path.startswith("api/"):
            raise AppError("NOT_FOUND", "route not found")
        if path.startswith("_vitrin") and not settings.is_dev:
            raise AppError("NOT_FOUND", "route not found")
        candidate = (static / path).resolve()
        if path and candidate.is_file() and static.resolve() in candidate.parents:
            headers = {"Cache-Control": "public, max-age=31536000, immutable"} if "/assets/" in f"/{path}" else {}
            return FileResponse(candidate, headers=headers)
        index = static / "index.html"
        if not index.is_file():
            return JSONResponse({"detail": "frontend not built"}, status_code=404)
        # Arayüz göreli yollarla derlenir; hangi alt yolda (/ ya da /metis/) yayınlandığını <base> söyler.
        base = f'<base href="{request.scope.get("root_path", "")}/">'
        html = _HEAD.sub(lambda m: m.group(0) + base, index.read_text(encoding="utf-8"), count=1)
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_dir, settings.env)
    app = FastAPI(
        title="METIS API",
        version=__version__,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs" if settings.is_dev else None,
        redoc_url=None,
    )
    app.add_middleware(SecurityMiddleware)
    if settings.base_path:  # en dışta: güvenlik denetimi ön eki çözülmüş yolu görür
        app.add_middleware(BasePathMiddleware, prefix=settings.base_path)
    _register_errors(app)

    from metis.modules.registry import include_routers

    include_routers(app, API_PREFIX)
    _register_spa(app)
    if settings.env != "test":
        from metis.modules.search import rerank

        rerank.preload()  # yeniden sıralayıcı kuruluysa arka planda yüklenir; ilk Mentor sorusu beklemez
    return app


def is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False
