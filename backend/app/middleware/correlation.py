"""Correlation/trace ID middleware: propagate or mint a request-scoped ID."""

from __future__ import annotations

import contextvars
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "hotpush_correlation_id", default=None
)

HEADER_NAME = "X-Correlation-ID"


def current_correlation_id() -> str | None:
    return correlation_id_var.get()


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(HEADER_NAME)
        correlation_id = incoming or str(uuid4())
        token = correlation_id_var.set(correlation_id)
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)
        response.headers[HEADER_NAME] = correlation_id
        return response
