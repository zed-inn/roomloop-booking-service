from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from roomloop.shared.middlewares.request_logger import RequestLoggingMiddleware


class FastApiApp:
    """encapsulates fastapi instance, swagger documentation, and middlewares"""

    def __init__(self) -> None:
        self._app: FastAPI = FastAPI(
            title="RoomLoop Booking Service API",
            description="RoomLoop meeting room booking core service",
            version="1.0.0",
            docs_url="/docs",
            redoc_url="/redoc",
        )
        self._configure_middlewares()

    def _configure_middlewares(self) -> None:
        """configures cors and request logging middlewares"""
        self._app.add_middleware(RequestLoggingMiddleware)
        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @property
    def app(self) -> FastAPI:
        """returns the underlying FastAPI instance"""
        return self._app
