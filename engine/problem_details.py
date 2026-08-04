"""RFC 7807 `application/problem+json` error responses.

Every error the API emits — raised HTTPException, request-validation failure,
or an unhandled exception — comes back in one shape:

    {"type": "...", "title": "...", "status": 404, "detail": "...",
     "instance": "/v1/jobs/abc", "traceId": "..."}

`traceId` matches the `X-Request-ID` response header and the `request_id` field
in the server's JSON logs, so a user-reported failure can be traced to the exact
log lines that produced it.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from logging_config import current_request_id, get_logger

log = get_logger("errors")

PROBLEM_CONTENT_TYPE = "application/problem+json"

_TYPE_BASE = "https://pagecap.local/problems"

_TITLES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    503: "Service Unavailable",
}

_SLUGS: dict[int, str] = {
    400: "bad-request",
    401: "unauthorized",
    403: "forbidden",
    404: "not-found",
    409: "conflict",
    422: "validation-error",
    429: "rate-limit-exceeded",
    500: "internal-error",
    503: "unavailable",
}


def trace_id_for(request: Optional[Request]) -> Optional[str]:
    """The correlation id for this request.

    Reads `scope["state"]` first and the contextvar only as a fallback:
    contextvars do not reliably cross a BaseHTTPMiddleware boundary (the
    downstream app runs in its own task), whereas the ASGI scope is the same
    object for every layer, so the scope is the dependable channel.
    """
    if request is not None:
        state_id = getattr(request.state, "request_id", None)
        if state_id:
            return state_id
    return current_request_id()


def problem(
    status_code: int,
    detail: str,
    *,
    instance: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
    request: Optional[Request] = None,
    **extra: Any,
) -> JSONResponse:
    """Builds an RFC 7807 response. Extra keys become problem extensions."""
    body: dict[str, Any] = {
        "type": f"{_TYPE_BASE}/{_SLUGS.get(status_code, 'error')}",
        "title": _TITLES.get(status_code, "Error"),
        "status": status_code,
        "detail": detail,
    }
    if instance:
        body["instance"] = instance
    trace_id = trace_id_for(request)
    if trace_id:
        body["traceId"] = trace_id
    body.update(extra)

    response = JSONResponse(status_code=status_code, content=body, headers=headers)
    response.media_type = PROBLEM_CONTENT_TYPE
    response.headers["content-type"] = PROBLEM_CONTENT_TYPE
    return response


def install(app: FastAPI) -> None:
    """Registers the handlers. Call once, at app construction."""

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException):
        return problem(
            exc.status_code,
            str(exc.detail),
            instance=request.url.path,
            headers=dict(getattr(exc, "headers", None) or {}),
            request=request,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        errors = [
            {
                "field": ".".join(str(p) for p in err.get("loc", ())),
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            for err in exc.errors()
        ]
        return problem(
            422,
            "The request body failed validation.",
            instance=request.url.path,
            request=request,
            errors=errors,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception(
            "Unhandled exception",
            extra={"extra_fields": {"path": request.url.path, "error": str(exc)}},
        )
        return problem(
            500,
            "An unexpected error occurred. Check the server logs for traceId.",
            instance=request.url.path,
            request=request,
        )
