import hmac
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from abos import models  # noqa: F401  (registers all ORM models)
from abos.agents.router import router as agents_router
from abos.audit.router import router as audit_router
from abos.business.router import router as business_router
from abos.company.router import router as company_router
from abos.core import metrics
from abos.core.config import get_settings
from abos.core.db import engine, get_db
from abos.core.errors import (
    AppError,
    error_body,
    install_error_handlers,
    install_error_reporter,
    internal_error_response,
    report_exception,
)
from abos.core.logging import configure_logging, request_id_var
from abos.governance.router import approvals_router, rules_router
from abos.identity.router import auth_router, org_router, orgs_router
from abos.knowledge.router import documents_router, interview_router, knowledge_router
from abos.llm import gateway
from abos.notifications.router import notifications_router, usage_router
from abos.orchestration.router import actions_router, tools_router, workflows_router
from abos.privacy.router import router as privacy_router
from abos.reporting.router import dashboard_router, reports_router
from abos.simulation.router import agent_router as simulation_agent_router
from abos.simulation.router import simulations_router

settings = get_settings()
configure_logging(settings.log_level)
ERROR_REPORTER = install_error_reporter(settings)
log = logging.getLogger("abos.http")

_ROLE_SQL = text("SELECT current_user AS role, r.rolsuper AS superuser, r.rolbypassrls AS bypass_rls "
                 "FROM pg_roles r WHERE r.rolname = current_user")


def db_role_status() -> dict:
    """Which role the app's queries run as, and whether row-level security can apply to it (ADR-003)."""
    with engine.connect() as conn:
        row = conn.execute(_ROLE_SQL).mappings().one()
    return {"role": row["role"], "rls_enforced": not (row["superuser"] or row["bypass_rls"])}


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.env == "production":
        status = db_role_status()
        if not status["rls_enforced"]:
            raise RuntimeError(f"Database role {status['role']!r} bypasses row-level security; refusing to start")
    yield


app = FastAPI(
    title="AI Business OS API",
    version="0.1.0",
    docs_url=None if settings.env == "production" else "/api/docs",
    openapi_url=None if settings.env == "production" else "/api/openapi.json",
    lifespan=lifespan,
)
install_error_handlers(app)

# The API only returns JSON or downloads: nothing may render or frame it. /api/docs (dev only) loads Swagger UI
# from a CDN, so it gets no CSP.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
MAX_JSON_BODY = 1024 * 1024
MAX_MULTIPART_BODY = settings.upload_max_bytes + 64 * 1024  # file + form fields; the route re-checks the file


def _too_large(request: Request) -> bool:
    # Declared sizes only; chunked bodies are capped by the production reverse proxy.
    limit = MAX_MULTIPART_BODY if request.headers.get("content-type", "").startswith("multipart/form-data") \
        else MAX_JSON_BODY
    length = request.headers.get("content-length")
    return length is not None and (not length.isdigit() or int(length) > limit)


def _route(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", None) or "unmatched"


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = (request.headers.get("x-request-id") or uuid.uuid4().hex)[:64]
    token = request_id_var.set(rid)
    start = time.perf_counter()
    try:
        # CSRF: browsers can't add custom headers to cross-site form posts; SameSite=Lax covers the rest (ADR-009).
        if request.method in UNSAFE and request.url.path.startswith("/api/") \
                and request.headers.get("x-requested-with") != "abos":
            response = JSONResponse(error_body("csrf_failed", "Missing X-Requested-With header"), status_code=403)
        elif _too_large(request):
            response = JSONResponse(error_body("payload_too_large", "Request body is too large"), status_code=413)
        else:
            try:
                response = await call_next(request)
            except Exception as exc:  # noqa: BLE001 — error boundary: report, never leak internals
                report_exception(exc, {"method": request.method, "route": _route(request)})
                response = internal_error_response(rid)
        response.headers["X-Request-Id"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        if not request.url.path.startswith("/api/docs"):
            response.headers["Content-Security-Policy"] = API_CSP
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers.setdefault("Cache-Control", "no-store")
        elapsed = time.perf_counter() - start
        route = _route(request)
        metrics.observe_request(request.method, route, response.status_code, elapsed)
        # Path only (no query string): queries can carry search terms typed by users.
        log.info("request", extra={"fields": {
            "method": request.method, "path": request.url.path, "route": route,
            "status": response.status_code, "ms": round(elapsed * 1000, 1)}})
        return response
    finally:
        request_id_var.reset(token)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}


@app.get("/api/health/ready", tags=["health"])
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok", "db_role": db_role_status(),
            "mail": {"adapter": settings.mailer, "delivers": settings.mailer == "smtp"},
            "jobs": {"eager": settings.jobs_eager}, "storage": settings.storage_backend,
            "sms": {"provider": settings.sms_provider, "delivers": False},
            "observability": {"error_reporter": ERROR_REPORTER, "metrics": settings.metrics_token is not None},
            **gateway.status()}


@app.get("/api/metrics", include_in_schema=False)
def metrics_endpoint(authorization: str | None = Header(default=None)):
    token = settings.metrics_token.get_secret_value() if settings.metrics_token else ""
    if not token:
        raise AppError(404, "not_found", "Not found")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        raise AppError(401, "unauthenticated", "Metrics token required")
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")


for r in (auth_router, orgs_router, org_router, company_router, audit_router, documents_router, knowledge_router,
          interview_router, agents_router, simulation_agent_router, simulations_router, rules_router,
          actions_router, approvals_router, business_router, workflows_router, tools_router, reports_router,
          dashboard_router, notifications_router, usage_router, privacy_router):
    app.include_router(r)
