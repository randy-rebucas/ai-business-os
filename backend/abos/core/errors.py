import logging
import math
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from abos.core.logging import current_log_context, request_id_var

log = logging.getLogger("abos.errors")


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None,
                 headers: dict[str, str] | None = None):
        self.status, self.code, self.message, self.details, self.headers = status, code, message, details, headers


def not_found(what: str = "Resource") -> AppError:
    return AppError(404, "not_found", f"{what} not found")


def forbidden(message: str = "You do not have permission to perform this action") -> AppError:
    return AppError(403, "forbidden", message)


def conflict(message: str) -> AppError:
    return AppError(409, "conflict", message)


def too_many(code: str, message: str, retry_after_seconds: float, scope: str, **details: Any) -> AppError:
    """Every 429 has the same shape: error envelope + details.retry_after_seconds + a Retry-After header."""
    seconds = max(1, math.ceil(retry_after_seconds))
    return AppError(429, code, message, {"retry_after_seconds": seconds, "scope": scope, **details},
                    headers={"Retry-After": str(seconds)})


def error_body(code: str, message: str, details: Any = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


Reporter = Callable[[BaseException, dict[str, Any]], None]
_reporters: list[Reporter] = []


def add_reporter(reporter: Reporter) -> None:
    """Register an extra error sink (e.g. Sentry, see `install_error_reporter`)."""
    if reporter not in _reporters:
        _reporters.append(reporter)


def remove_reporter(reporter: Reporter) -> None:
    if reporter in _reporters:
        _reporters.remove(reporter)


def report_exception(exc: BaseException, context: dict[str, Any], *, where: str = "api") -> None:
    """Single sink for unhandled errors (API and background jobs). Context must not contain bodies, tokens or
    personal data. A failing reporter never masks the original error."""
    from abos.core import metrics  # noqa: PLC0415

    metrics.count_error(where)
    fields = {"error_type": type(exc).__name__, "where": where, **current_log_context(), **context}
    log.error("unhandled_exception", exc_info=exc, extra={"fields": fields})
    for reporter in list(_reporters):
        try:
            reporter(exc, fields)
        except Exception:  # noqa: BLE001
            log.warning("error_reporter_failed", extra={"fields": {"reporter": getattr(reporter, "__name__", "?")}})


def install_error_reporter(settings) -> str:
    """Wire the configured external reporter. Returns its name for /api/health/ready. `sentry` needs the optional
    `sentry-sdk` package and has not been verified against a live Sentry project (docs/STATUS.md)."""
    if settings.error_reporter != "sentry" or not settings.sentry_dsn:
        return "log"
    try:
        import sentry_sdk  # noqa: PLC0415 — optional dependency
    except ImportError as exc:
        raise RuntimeError("ABOS_ERROR_REPORTER=sentry needs `pip install sentry-sdk`") from exc
    # No request bodies, cookies or user data: the reporter only gets the exception and the safe context fields.
    sentry_sdk.init(dsn=settings.sentry_dsn.get_secret_value(), environment=settings.env, send_default_pii=False,
                    default_integrations=False, traces_sample_rate=0.0)

    def _sentry(exc: BaseException, fields: dict[str, Any]) -> None:
        with sentry_sdk.new_scope() as scope:
            for key, value in fields.items():
                scope.set_tag(key, str(value)[:200])
            sentry_sdk.capture_exception(exc)

    add_reporter(_sentry)
    return "sentry"


def internal_error_response(rid: str | None) -> JSONResponse:
    return JSONResponse(error_body("internal_error", "Something went wrong on our side. Quote the request id if you "
                                   "contact support.", {"request_id": rid}), status_code=500,
                        headers={"X-Request-Id": rid or ""})


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status,
                            headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [
            {"loc": [str(p) for p in e["loc"]], "msg": e["msg"], "type": e["type"]} for e in exc.errors()
        ]
        return JSONResponse(error_body("validation_error", "Invalid request", details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return JSONResponse(error_body("http_error", str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Never leak internals to the client; the request id ties the response to the logged error.
        report_exception(exc, {"method": request.method, "path": request.url.path})
        return internal_error_response(request_id_var.get())
