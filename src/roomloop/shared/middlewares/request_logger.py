import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from roomloop.shared.services.logger import app_logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """http middleware logging method, path, response status, and duration in ms"""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start_time: float = time.perf_counter()
        method: str = request.method
        path: str = request.url.path

        response: Response = await call_next(request)

        duration_ms: float = (time.perf_counter() - start_time) * 1000.0
        status_code: int = response.status_code

        # log formatted request details via app_logger with millisecond latency
        app_logger.info(
            "[HTTP] %s %s %d - %.2fms",
            method,
            path,
            status_code,
            duration_ms,
        )

        return response
