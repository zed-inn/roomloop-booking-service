import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from roomloop.shared.services.logger import app_logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """http middleware logging method, path, response status, duration, and correlation request id"""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start_time: float = time.perf_counter()
        method: str = request.method
        path: str = request.url.path
        request_id: str = (
            request.headers.get("x-request-id")
            or request.headers.get("X-Request-ID")
            or uuid.uuid4().hex[:12]
        )

        response: Response = await call_next(request)

        duration_ms: float = (time.perf_counter() - start_time) * 1000.0
        status_code: int = response.status_code
        response.headers["X-Request-ID"] = request_id

        app_logger.info(
            "[HTTP] %s %s %d - %.2fms (request_id=%s)",
            method,
            path,
            status_code,
            duration_ms,
            request_id,
        )

        return response
